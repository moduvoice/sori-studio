"""엔진 일꾼 관리 - 띄우기·생존 확인·자동 재시작(4.8 겹 2).

실행 상태(v0.4): stopped(꺼짐) · loading(불러오는 중) · ready(켜짐) · idle(쉬는 중) · restarting(다시 켜는 중) · stalled(멈춤) · dead(죽음)
- 생존 확인 5초마다, 세 번 연달아 답이 없으면 멈춤 → 다시 켬
- 다시 켜기 간격 0 → 10 → 60초, 10분에 3번 넘게 죽으면 dead(원인과 함께)
- 불러오기 한도 = max(120초, 측정 불러오기 × 3), 생성 한도 = 예상 소리 길이 × RTF × 3 + 30초
- 일꾼은 한 Job(Windows)으로 묶어 허브가 죽으면 함께 끝나요. 일꾼도 stdin 이 닫히면 스스로 끝나요.
"""
import collections
import json
import os
import secrets
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import catalog, paths, wsl
from .hardware import NO_WINDOW

WORKER = Path(__file__).with_name("worker_main.py")
HEALTH_EVERY = 5
HEALTH_FAILS = 3
BACKOFF = (0, 10, 60)
CRASH_WINDOW = 600
CRASH_LIMIT = 3


class EngineError(Exception):
    """kind: not_installed · dead · load_timeout · synth_timeout · oom · engine · busy"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


# ---------- Windows Job: 허브가 죽으면 일꾼도 함께 끝나게 ----------

class _Job:
    def __init__(self):
        self.h = None
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.CreateJobObjectW(None, None)
        if not h:
            return

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class EXT(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = EXT()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):  # ExtendedLimitInformation
            self.h, self.k32 = h, k32

    def add(self, pid: int) -> None:
        if not self.h:
            return
        ph = self.k32.OpenProcess(0x0001 | 0x0100, False, pid)  # PROCESS_TERMINATE | PROCESS_SET_QUOTA
        if ph:
            self.k32.AssignProcessToJobObject(self.h, ph)
            self.k32.CloseHandle(ph)


JOB = _Job()


# ---------- 일꾼 하나 ----------

class Worker:
    def __init__(self, recipe: dict):
        self.recipe = recipe
        self.id = recipe["id"]
        self.proc: subprocess.Popen | None = None
        self.port = None
        self.token = None
        self.state = "stopped"
        self.error: dict | None = None
        self.crashes: collections.deque = collections.deque()
        self.lock = threading.RLock()
        self.queue = threading.Lock()  # 엔진은 한 번에 한 줄 - 기다리는 요청은 여기서 줄 서요(대기 시간은 생성 한도에 안 들어가요)
        self._logfh = None
        self.ready = threading.Event()
        self.wanted = False  # 사용자가 켜 둔 상태인지(죽으면 다시 켤지)
        self.last_used = 0.0
        self.loaded_s = None
        self.restarts = 0
        self.fails = 0
        self.load_fails = 0
        self.events: collections.deque = collections.deque(maxlen=50)  # 최근 일(화면 H3)

    def event(self, kind: str, msg: str) -> None:
        """kind: user(사용자가 한 일) · auto(스스로 고침) · error"""
        self.events.append({"at": time.time(), "kind": kind, "msg": msg})

    # --- 띄우기 ---
    def _log(self) -> Path:
        d = paths.home() / "logs"
        d.mkdir(exist_ok=True)
        return d / f"{self.id}.log"

    def _state(self) -> dict:
        from .installer import read_state

        return read_state(self.id)

    def _runtime(self) -> str:
        return self._state().get("runtime") or catalog.runtime_for(self.recipe, paths.platform_key())

    def load_timeout(self) -> float:
        # 레시피의 불러오기 시간 × 3(최소 3분). 서버형 엔진의 어댑터는 이보다 오래 기다리지 않아요 - 한도는 허브가 정해요
        return max(180.0, float(self.recipe["measured"].get("load_s") or 0) * 3)

    def start(self) -> None:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            if self.proc is not None and self.wanted and self.state != "dead":
                # 감시가 알아채기 전에 요청이 먼저 왔어요 - 죽은 것으로 세고 바로 다시 켜요
                self.crashes.append(time.time())
                self.restarts += 1
                self.proc = None
                self.event("error", "일꾼이 끝나 있어서 바로 다시 켜요")
            if self.state == "dead":
                raise EngineError("dead", self.error["message"] if self.error else "엔진이 죽었어요")
            if self._runtime() != "wsl" and not paths.env_python(self.id).exists():
                raise EngineError("not_installed", "엔진이 설치되지 않았어요")
            self.wanted = True
            self.event("user", "켜기")
            self._spawn()

    def _spawn(self) -> None:
        self.ready.clear()
        self.state = "loading" if not self.restarts else "restarting"
        self.token = secrets.token_hex(16)
        env = dict(os.environ, SORI_WORKER_TOKEN=self.token, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        for k in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            env.pop(k, None)
        adapter = Path(self.recipe["_dir"]) / self.recipe["adapter"]
        weights = paths.engine_dir(self.id) / "weights"
        device = self._state().get("device", "cpu")
        if self._runtime() == "wsl":
            # WSL2 안 리눅스 파이썬으로. 토큰은 WSLENV 로 넘기고, 포트는 WSL 의 localhost 전달로 Windows 에서 닿아요.
            env["WSLENV"] = "SORI_WORKER_TOKEN/u:PYTHONUNBUFFERED/u:PYTHONIOENCODING/u"
            cmd = [wsl._wsl_exe() or "wsl.exe", "-d", wsl.DISTRO, "-u", "root", "--", wsl.env_python(self.id), "-I",
                   wsl.to_wsl_path(WORKER), "--adapter", wsl.to_wsl_path(adapter), "--weights", wsl.to_wsl_path(weights)]
        else:
            cmd = [str(paths.env_python(self.id)), "-I", str(WORKER), "--adapter", str(adapter), "--weights", str(weights)]
        cmd += ["--device", device]
        if self.recipe.get("threads"):
            cmd += ["--threads", str(self.recipe["threads"])]
        if self._logfh:
            self._logfh.close()  # 다시 켤 때마다 열린 채 쌓이지 않게
        log = self._logfh = open(self._log(), "a", encoding="utf-8")
        log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} 시작 ====\n")
        log.flush()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env,
                                     cwd=str(paths.engine_dir(self.id)), creationflags=NO_WINDOW,
                                     start_new_session=(os.name != "nt"))  # 리눅스: 일꾼과 그 자식(엔진 서버)을 한 그룹으로
        JOB.add(self.proc.pid)
        proc = self.proc
        t0 = time.time()

        def read_ready():
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("READY "):
                    self.port = int(line.split()[1])
                    self.loaded_s = round(time.time() - t0, 1)
                    self.state, self.error, self.fails, self.load_fails = "ready", None, 0, 0
                    self.event("auto", f"켜짐 · 불러오기 {self.loaded_s}초")
                    self.ready.set()
                else:
                    log.write(line + "\n")
                    log.flush()
            if self.ready.is_set():
                return
            # READY 전에 끝남 = 불러오기 실패. 두 번 연달아면 다시 켜도 소용없어 바로 죽음으로.
            proc.wait()
            with self.lock:
                if self.proc is not proc:
                    return
                self.load_fails += 1
                if self.load_fails >= 2:
                    self._kill()
                    self.state = "dead"
                    self.error = {"kind": "load_failed", "message": f"엔진을 불러오지 못했어요: {self._log_tail()}",
                                  "log": str(self._log())}
                    self.event("error", "불러오기 두 번 실패 · 죽음")
                    self.ready.set()  # 기다리던 요청을 깨워 실패를 알림
                else:
                    self._crashed(f"불러오다 끝났어요(코드 {proc.returncode})")

        threading.Thread(target=read_ready, daemon=True, name=f"ready-{self.id}").start()

    def _log_tail(self) -> str:
        try:
            lines = [x for x in self._log().read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
            return lines[-1][:300] if lines else ""
        except OSError:
            return ""

    def wait_ready(self) -> None:
        if not self.ready.wait(self.load_timeout()):
            with self.lock:
                self._kill()
                self.state = "stopped"
                self.error = {"kind": "load_timeout", "message": f"{self.load_timeout():.0f}초 안에 엔진을 불러오지 못했어요",
                              "log": str(self._log())}
                self.event("error", "불러오기 시간 초과")
            raise EngineError("load_timeout", f"{self.load_timeout():.0f}초 안에 엔진을 불러오지 못했어요")
        if self.state == "dead":
            raise EngineError("dead", self.error["message"] if self.error else "엔진이 죽었어요")

    def reset(self) -> None:
        """죽음 상태에서 사용자가 "다시 켜기"를 누를 때."""
        with self.lock:
            self.crashes.clear()
            self.error, self.state, self.restarts = None, "stopped", 0
        self.start()

    def stop(self) -> None:
        with self.lock:
            if self.wanted:
                self.event("user", "내리기")
            self.wanted = False
            self._kill()
            self.state = "stopped"

    def _kill(self) -> None:
        p = self.proc
        if p and p.poll() is None:
            try:
                p.stdin.close()  # 일꾼이 스스로 끝날 기회
                p.wait(3)
            except Exception:
                p.kill()
                try:
                    p.wait(5)
                except Exception:
                    pass
        if p and self._runtime() == "wsl":
            # Windows 에서 wsl.exe 만 끝내면 WSL 안 일꾼·서버가 남을 수 있어요 - 그 엔진 환경의 프로세스를 WSL 안에서 끝내요
            try:
                wsl.sh(f"pkill -TERM -f {shlex.quote(wsl.engine_root(self.id))}/env/; sleep 5; "
                       f"pkill -KILL -f {shlex.quote(wsl.engine_root(self.id))}/env/; true", timeout=60)
            except Exception:
                pass
        if p and os.name != "nt":
            # 일꾼이 띄운 하위 프로세스(엔진 서버·그 단계 프로세스)까지 - 남으면 GPU 메모리를 쥔 채 고아가 돼요(스팟 2026-11-17)
            import signal

            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                time.sleep(2)
        self.proc, self.port = None, None
        self.ready.clear()

    # --- 감시 ---
    def _crashed(self, why: str) -> None:
        now = time.time()
        self.crashes.append(now)
        while self.crashes and now - self.crashes[0] > CRASH_WINDOW:
            self.crashes.popleft()
        self._kill()
        self.event("error", why)
        if len(self.crashes) > CRASH_LIMIT:
            self.state = "dead"
            self.error = {"kind": "dead", "message": f"10분에 {len(self.crashes)}번 죽었어요: {why}",
                          "log": str(self._log())}
            self.ready.set()  # 기다리던 요청을 깨워 실패를 알림
            return
        wait = BACKOFF[min(len(self.crashes) - 1, len(BACKOFF) - 1)]
        self.state = "restarting"
        self.error = {"kind": "restarting", "message": why, "retry_at": time.time() + wait,
                      "attempt": len(self.crashes)}
        self.restarts += 1
        self.event("auto", f"다시 켜기 {len(self.crashes)}번째" + (f" · {wait}초 뒤" if wait else ""))

        def later():
            time.sleep(wait)
            with self.lock:
                if self.wanted and self.state == "restarting" and self.proc is None:
                    self._spawn()

        threading.Thread(target=later, daemon=True).start()

    def check(self) -> None:
        """감시 한 번(허브의 감시 스레드가 5초마다 불러요)."""
        with self.lock:
            # 꺼 둠·죽음·다시 켜기 간격·불러오는 중(불러오다 죽는 것은 read_ready 가 봄)은 건너뜀
            p = self.proc
            if not self.wanted or self.state == "dead" or p is None or not self.ready.is_set():
                return
            if p.poll() is not None:
                self._crashed(f"일꾼이 끝났어요(코드 {p.returncode})")
                return
        try:
            self._get("/health", timeout=3)
            self.fails = 0
        except Exception:
            self.fails += 1
            if self.fails >= HEALTH_FAILS:
                with self.lock:
                    self._crashed("세 번 연달아 답이 없어요(멈춤)")

    # --- 부르기 ---
    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path: str, timeout: float) -> dict:
        req = urllib.request.Request(self._url(path), headers={"X-Sori-Worker-Token": self.token})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def synth_timeout(self, text: str) -> float:
        m = self.recipe["measured"]
        rate = float(m.get("syll_rate") or 5.0)
        est_audio = max(len(text) / rate, 1.0)
        dev = self._state().get("device", "cpu")
        rtf = float((m.get("rtf_gpu") if dev == "cuda" else m.get("rtf_cpu")) or m.get("rtf_gpu") or m.get("rtf_cpu") or 1.0)
        return est_audio * rtf * 3 + 60

    def synth(self, text: str, voice: str | None, seed: int = 0, _retry: bool = True, speed: float | None = None) -> tuple[bytes, dict]:
        with self.queue:  # 한 줄씩 - 기다린 시간은 아래 생성 한도에 들어가지 않아요(리뷰: 동시 요청이 멀쩡한 일꾼을 죽임)
            return self._synth(text, voice, seed, _retry, speed)

    def _synth(self, text: str, voice: str | None, seed: int = 0, _retry: bool = True, speed: float | None = None) -> tuple[bytes, dict]:
        self.start()
        self.wait_ready()
        self.state = "ready"
        self.last_used = time.time()
        ref = catalog.voice_ref(self.recipe, voice)
        if ref and self._runtime() == "wsl":
            ref["ref"] = wsl.to_wsl_path(ref["ref"])
        sp = speed or (self.recipe.get("speed") or {}).get("default")
        body = json.dumps({"text": text, "voice": voice, "seed": seed, **ref, **({"speed": sp} if sp else {})}).encode()
        req = urllib.request.Request(self._url("/synth"), data=body, method="POST",
                                     headers={"X-Sori-Worker-Token": self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.synth_timeout(text)) as r:
                meta = {"gen_s": float(r.headers.get("X-Sori-Gen-Seconds") or 0),
                        "audio_s": float(r.headers.get("X-Sori-Audio-Seconds") or 0)}
                return r.read(), meta
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read())
            except Exception:
                err = {"error": str(e)}
            raise EngineError(err.get("kind", "engine"), err.get("error", "엔진 오류"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            # 일꾼이 죽었거나 시간 초과 - 다시 켜고 같은 씨앗으로 한 번 더(4.8)
            timed_out = "timed out" in str(e).lower()
            with self.lock:
                self._crashed("생성 시간 한도를 넘었어요" if timed_out else f"생성 중 연결이 끊겼어요: {e}")
            if not _retry or self.state == "dead":
                raise EngineError("synth_timeout" if timed_out else "dead", str(e))
            return self._synth(text, voice, seed, _retry=False, speed=speed)

    def info(self) -> dict:
        pid = self.proc.pid if self.proc and self.proc.poll() is None else None
        return {"state": self.state, "error": self.error, "pid": pid, "loaded_s": self.loaded_s,
                "restarts": self.restarts, "crashes_10min": len(self.crashes),
                "rss_bytes": rss_bytes(pid) if pid else None, "threads": self.recipe.get("threads"),
                "events": list(self.events)}

    def log_tail(self, n: int = 300) -> list[str]:
        try:
            lines = self._log().read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError:
            return []
        return [mask_paths(x) for x in lines]


def mask_paths(line: str) -> str:
    """로그를 화면·이슈로 보낼 때 사용자 폴더 경로를 가려요(10.3)."""
    for real, alias in ((str(paths.models_dir()), "<모델 폴더>"), (str(paths.home()), "<허브 홈>"),
                        (os.path.expanduser("~"), "~")):
        line = line.replace(real, alias)
    return line


def _win_children(root: int) -> list[int]:
    """root 와 그 아래 프로세스 전부(Windows 의 venv python.exe 는 진짜 파이썬을 자식으로 띄우는 실행기예요)."""
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32")
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    parent: dict[int, list[int]] = {}
    try:
        e = PE()
        e.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            parent.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    out, todo = [], [root]
    while todo:
        p = todo.pop()
        out.append(p)
        todo += [c for c in parent.get(p, []) if c not in out]
    return out


def rss_bytes(pid: int) -> int | None:
    """일꾼(과 그 자식 프로세스)이 쓰는 메모리(실제 올라간 양)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                   "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                   "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

            k32 = ctypes.WinDLL("kernel32")
            k32.OpenProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            total = 0
            for p in _win_children(pid):
                h = k32.OpenProcess(0x1000 | 0x0010, False, p)  # QUERY_LIMITED_INFORMATION | VM_READ
                if not h:
                    continue
                try:
                    c = PMC()
                    c.cb = ctypes.sizeof(PMC)
                    if psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
                        total += int(c.WorkingSetSize)
                finally:
                    k32.CloseHandle(h)
            return total or None
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        return None
    return None


class Manager:
    """엔진 일꾼 전부 + 감시 스레드 하나."""

    def __init__(self, recipes: dict[str, dict]):
        self.workers = {eid: Worker(r) for eid, r in recipes.items()}
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._watch, daemon=True, name="watchdog")

    def start_watchdog(self) -> None:
        self._t.start()

    def _watch(self) -> None:
        while not self._stop.wait(HEALTH_EVERY):
            for w in list(self.workers.values()):
                try:
                    w.check()
                except Exception:
                    pass

    def shutdown(self) -> None:
        self._stop.set()
        for w in self.workers.values():
            w.stop()

    def get(self, eid: str) -> Worker:
        if eid not in self.workers:
            raise KeyError(eid)
        return self.workers[eid]
