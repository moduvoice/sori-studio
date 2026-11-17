"""원클릭 설치(4.4) - 단계마다 체크포인트가 있어 실패하면 그 단계부터 다시 해요.

단계: plan(계획) → consent(라이선스 동의) → env(uv 환경) → packages(잠금 파일·해시 검증) → weights(공식 출처·이어받기·sha256) → selftest(한국어 3문장) → installed
설치 상태(v0.4): none(안 받음) · installing(받는 중) · paused(멈춤, 이어받기 대기) · failed(실패) · installed(설치됨) · update(업데이트 있음) · source_changed(출처 바뀜)
"""
import errno
import hashlib
import os
import shlex
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import catalog, hardware, paths, wsl
from . import proc
from .hardware import NO_WINDOW

STEPS = ("env", "code", "packages", "weights", "selftest")  # code = 소스 코드(있는 엔진만, 없으면 바로 끝)
ENV_BYTES_GUESS = 600 * 2**20  # 환경(파이썬 + 패키지) 크기 추정 - 계획 화면의 디스크 점검용
CHUNK = 1 << 20
USER_AGENT = "sori-studio-hub"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InstallError(Exception):
    """kind: disk · network · dependency · permission · source · selftest · unknown (4.4 실패 분류)"""

    def __init__(self, kind: str, message: str, step: str = ""):
        super().__init__(message)
        self.kind, self.message, self.step = kind, message, step


# ---------- 상태 파일 ----------

def state_path(eid: str) -> Path:
    return paths.engine_dir(eid) / "state.json"


def read_state(eid: str) -> dict:
    import json

    f = state_path(eid)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"install": "none", "done": []}


def write_state(eid: str, st: dict) -> None:
    paths.engine_dir(eid).mkdir(parents=True, exist_ok=True)
    paths.write_json(state_path(eid), st)


def install_status(recipe: dict, st: dict) -> str:
    s = st.get("install", "none")
    if s == "installed" and st.get("recipe_version") != recipe["recipe_version"]:
        return "update"
    return s


# ---------- 계획 ----------

def choose(recipe: dict) -> dict:
    """이 PC 에서 어떻게 설치할지: runtime(native·wsl) · device(cuda·cpu) · 잠금 파일."""
    plat = paths.platform_key()
    rt = catalog.runtime_for(recipe, plat)
    v = hardware.verdict(recipe, hardware.detect())
    device = "cuda" if v.get("device") == "cuda" else "cpu"
    return {"runtime": rt, "device": device, "packages": catalog.package_file(recipe, plat, device),
            "package_platform": catalog.package_platform(recipe, plat)}


def plan(recipe: dict) -> dict:
    eid = recipe["id"]
    st = read_state(eid)
    wdir = paths.engine_dir(eid) / "weights"
    have = sum(f.stat().st_size for f in wdir.rglob("*") if f.is_file()) if wdir.exists() else 0
    total = sum(int(f["size"]) for f in catalog.all_weight_files(recipe))
    how = choose(recipe)
    env_guess = catalog.env_bytes(recipe, how["device"])
    need = max(total - have, 0) + (0 if "packages" in st.get("done", []) else env_guess)
    free = shutil.disk_usage(paths.models_dir()).free
    return {
        "engine": eid,
        "steps": [s for s in STEPS if s not in st.get("done", []) and (s != "code" or recipe.get("code"))],
        "download_bytes": max(total - have, 0),
        "weights_bytes": total,
        "env_bytes_estimate": 0 if "packages" in st.get("done", []) else env_guess,
        "need_bytes": need,
        "free_bytes": free,
        "disk_ok": free > need * 1.1,
        "license": recipe["license"],
        "sources": [g["sources"][0]["repo"] for g in catalog.weight_groups(recipe) if g["sources"]],
        "runtime": how["runtime"],
        "device": how["device"],
        "wsl": wsl.status() if how["runtime"] == "wsl" else None,
        "target": str(paths.engine_dir(eid)),
        "est_minutes": round(max(total - have, 0) / (100e6 / 8) / 60 + 2, 1),  # 100Mbps 가정 + 환경 2분(추정)
    }


# ---------- 단계 ----------

def _uv() -> str:
    exe = os.environ.get("SORI_UV") or shutil.which("uv")
    if not exe:
        raise InstallError("dependency", "uv 를 찾지 못했어요(설치본에는 함께 들어가요)", "env")
    return exe


def _uv_env() -> dict:
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(paths.models_dir() / ".uv-cache")  # 같은 휠은 한 번만(4.6)
    env["UV_PYTHON_INSTALL_DIR"] = str(paths.models_dir() / ".python")
    env.pop("VIRTUAL_ENV", None)
    return env


def _run(cmd: list[str], step: str, log) -> None:
    log(f"$ {' '.join(cmd)}")
    try:
        code, raw = proc.run(cmd, env=_uv_env())
    except proc.Cancelled:
        raise InstallError("network", "사용자가 멈췄어요", step)
    out = raw.decode("utf-8", errors="replace")
    for line in out.splitlines()[-40:]:
        log(line)
    if code != 0:
        tail = out.strip().splitlines()[-1:] or [""]
        low = out.lower()
        if "no space" in low or "os error 112" in low:
            raise InstallError("disk", "디스크 공간이 모자라요", step)
        if any(k in low for k in ("failed to fetch", "connect", "timed out", "dns")):
            raise InstallError("network", f"받는 중 연결이 끊겼어요: {tail[0]}", step)
        if "access is denied" in low or "permission" in low:
            raise InstallError("permission", f"권한이 없어 막혔어요(백신·보안 프로그램 확인): {tail[0]}", step)
        raise InstallError("dependency", f"패키지 설치가 실패했어요: {tail[0]}", step)


def _wsl_run(cmd: str, step: str, log, timeout: float = 3600) -> None:
    log(f"[WSL] $ {cmd}")
    try:
        code, out = wsl.sh(f"export UV_CACHE_DIR=/root/.sori/uv-cache; {cmd}", timeout=timeout)
    except proc.Cancelled:
        raise InstallError("network", "사용자가 멈췄어요", step)
    for line in out.splitlines()[-40:]:
        log(line)
    if code != 0:
        low = out.lower()
        if "no space" in low:
            raise InstallError("disk", "WSL 안의 디스크 공간이 모자라요", step)
        if any(k in low for k in ("failed to fetch", "connect", "timed out", "dns")):
            raise InstallError("network", "받는 중 연결이 끊겼어요", step)
        raise InstallError("dependency", f"WSL 안에서 설치가 실패했어요: {out.strip().splitlines()[-1:] or ''}", step)


def step_env(recipe: dict, log, how: dict) -> None:
    if how["runtime"] == "wsl":
        wsl.setup_distro(log)
        if how["device"] == "cuda" and not wsl.has_gpu():
            # 수십 GB 를 받기 전에 멈춰요(리뷰: WSL 안에서 GPU 가 안 보여도 다 받은 뒤에야 실패)
            raise InstallError("driver", "WSL 안에서 GPU 가 보이지 않아요. NVIDIA 그래픽 드라이버를 최신으로 올린 뒤 PC 를 다시 시작해 주세요.", "env")
        deps = (recipe.get("system_deps") or {}).get("linux-x64") or []
        if deps:
            wsl.install_system_deps(deps, log)
        root = shlex.quote(wsl.engine_root(recipe["id"]))
        _wsl_run(f"rm -rf {root}/env && mkdir -p {root} && uv venv -q {root}/env --python {shlex.quote(str(recipe['python']))}", "env", log)
        return
    env = paths.engine_dir(recipe["id"]) / "env"
    if env.exists():
        shutil.rmtree(env)
    _run([_uv(), "venv", str(env), "--python", str(recipe["python"]), "--no-project", "-q"], "env", log)


def step_code(recipe: dict, log, progress, cancel: threading.Event) -> None:
    """소스 코드(pip 패키지가 아닌 엔진): GitHub 커밋 고정 묶음을 받아 sha256 확인 뒤 code/<dir> 에 풀어요."""
    import tarfile
    import zipfile

    for c in recipe.get("code") or []:
        base = paths.engine_dir(recipe["id"]) / "code"
        base.mkdir(parents=True, exist_ok=True)
        arc = base / (c["dir"] + (".zip" if ("/zip/" in c["url"] or c["url"].endswith(".zip")) else ".tar.gz"))
        dst = base / c["dir"]
        if dst.exists() and (dst / ".sori-ok").exists():
            continue
        if not (arc.exists() and _sha256(arc) == c["sha256"]):
            log(f"소스 받기: {c['url']}")
            for attempt in range(len(NET_RETRY) + 1):
                try:
                    _download(c["url"], arc, int(c.get("size") or 0) or 1 << 40, progress, cancel)
                    break
                except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
                    if attempt == len(NET_RETRY):
                        raise InstallError("network", f"받는 중 연결이 끊겼어요: {e}", "code")
                    if cancel.wait(NET_RETRY[attempt]):
                        raise InstallError("network", "사용자가 멈췄어요", "code")
            if _sha256(arc) != c["sha256"]:
                arc.unlink()
                raise InstallError("source", f"소스 묶음 해시가 맞지 않아요({c['dir']})", "code")
        if dst.exists():
            shutil.rmtree(dst)
        tmp = base / (c["dir"] + ".tmp")
        if tmp.exists():
            shutil.rmtree(tmp)
        if zipfile.is_zipfile(arc):  # 주소 꼴이 아니라 내용으로 판단(GitHub codeload 주소는 .zip 으로 안 끝남)
            with zipfile.ZipFile(arc) as z:
                for n in z.namelist():
                    if ".." in Path(n).parts or Path(n).is_absolute():
                        raise InstallError("source", "소스 묶음에 폴더 밖을 가리키는 경로가 있어요", "code")
                z.extractall(tmp)
        else:
            with tarfile.open(arc) as t:
                t.extractall(tmp, filter="data")
        inner = [p for p in tmp.iterdir()]
        os.replace(inner[0] if len(inner) == 1 and inner[0].is_dir() else tmp, dst)  # GitHub 묶음의 맨 위 폴더를 벗겨요
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        (dst / ".sori-ok").write_text(c["sha256"], encoding="utf-8")
        log(f"소스 풀기: {c['dir']}")


def step_packages(recipe: dict, log, how: dict) -> None:
    req = how["packages"]
    if not req:
        raise InstallError("dependency", f"이 운영체제({how['package_platform']})용 패키지 목록이 레시피에 없어요", "packages")
    reqf = Path(recipe["_dir"]) / req
    extra = list(recipe.get("pip_extra_args") or [])
    idx = (recipe.get("pip_index") or {}).get(how["device"])
    if idx:  # CUDA 판 torch 처럼 PyPI 밖 저장소에 있는 패키지(잠금 파일의 해시로 그대로 검증)
        extra += ["--index", idx, "--index-strategy", "unsafe-best-match"]
    # 받은 소스를 패키지로(의존성은 위 잠금 파일에서 이미 깔았으니 --no-deps, 소스는 code 단계에서 해시 확인)
    local = [paths.engine_dir(recipe["id"]) / p for p in (recipe.get("local_packages") or [])]
    # 버전이 부딪혀 의존성 없이 까는 목록(해시 잠금은 그대로) - 예: SGLang-Omni 의 Fish 부품
    nd = (recipe.get("packages_nodeps") or {}).get(how["package_platform"])
    ndf = Path(recipe["_dir"]) / nd if nd else None
    if how["runtime"] == "wsl":
        q = shlex.quote
        py = q(wsl.env_python(recipe["id"]))
        _wsl_run(f"uv pip install -q --python {py} --require-hashes -r {q(wsl.to_wsl_path(reqf))} "
                 + " ".join(q(x) for x in extra), "packages", log)
        if ndf:
            _wsl_run(f"uv pip install -q --python {py} --no-deps --require-hashes -r {q(wsl.to_wsl_path(ndf))}", "packages", log)
        for lp in local:
            _wsl_run(f"uv pip install -q --python {py} --no-deps {q(wsl.to_wsl_path(lp))}", "packages", log)
        return
    _run([_uv(), "pip", "install", "--python", str(paths.env_python(recipe["id"])), "--require-hashes",
          "-r", str(reqf), "-q", *extra], "packages", log)
    if ndf:
        _run([_uv(), "pip", "install", "--python", str(paths.env_python(recipe["id"])), "--no-deps", "--require-hashes",
              "-r", str(ndf), "-q"], "packages", log)
    for lp in local:
        _run([_uv(), "pip", "install", "--python", str(paths.env_python(recipe["id"])), "--no-deps", str(lp), "-q"], "packages", log)


def _sha256(f: Path) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for b in iter(lambda: fh.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def _download(url: str, dst: Path, size: int, progress, cancel: threading.Event) -> None:
    part = dst.with_name(dst.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        progress(-have)
        part.unlink()
        have = 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if have:
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req, timeout=30) as r:
        if have and r.status != 206:  # 이어받기를 안 받아 주면 처음부터
            progress(-have)
            have = 0
        with open(part, "ab" if have else "wb") as fh:
            while True:
                if cancel.is_set():
                    raise InstallError("network", "사용자가 멈췄어요", "weights")
                b = r.read(CHUNK)
                if not b:
                    break
                fh.write(b)
                progress(len(b))
    os.replace(part, dst)


NET_RETRY = (2, 5, 15)  # 잠깐 끊긴 것은 스스로 이어받아요(초). 그래도 안 되면 멈춤 → 사용자가 "이어서 받기"


def step_weights(recipe: dict, log, progress, cancel: threading.Event) -> None:
    for g in catalog.weight_groups(recipe):
        _weights_group(recipe, g, log, progress, cancel)


def _weights_group(recipe: dict, g: dict, log, progress, cancel: threading.Event) -> None:
    wdir = paths.engine_dir(recipe["id"]) / "weights" / g["dir"]
    sources = g["sources"]
    for f in g["files"]:
        dst = wdir / f["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size == int(f["size"]) and _sha256(dst) == f["sha256"]:
            progress(int(f["size"]))
            continue
        part = dst.with_name(dst.name + ".part")
        progress(part.stat().st_size if part.exists() else 0)  # 이미 받은 조각은 한 번만 셈
        last = None
        for src in sources:
            url = f"https://huggingface.co/{src['repo']}/resolve/{src['revision']}/{f['path']}"
            for attempt in range(len(NET_RETRY) + 1):
                try:
                    _download(url, dst, int(f["size"]), progress, cancel)
                    if dst.stat().st_size != int(f["size"]) or _sha256(dst) != f["sha256"]:
                        progress(-dst.stat().st_size)
                        dst.unlink()
                        raise InstallError("source", f"{f['path']} 검증이 맞지 않아요(출처 {src['repo']})", "weights")
                    last = None
                    break
                except urllib.error.HTTPError as e:
                    last = InstallError("source", f"{src['repo']} 에서 {f['path']} 를 받지 못했어요(HTTP {e.code})", "weights")
                    log(last.message)
                    break  # 이 출처는 안 됨 → 다음 출처
                except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
                    last = InstallError("network", f"받는 중 연결이 끊겼어요: {e}", "weights")
                    if attempt < len(NET_RETRY):
                        log(f"{last.message} - {NET_RETRY[attempt]}초 뒤 이어서 받아요({attempt + 1}/{len(NET_RETRY)})")
                        if cancel.wait(NET_RETRY[attempt]):
                            raise InstallError("network", "사용자가 멈췄어요", "weights")
                        continue
                    log(last.message)
                    raise last  # 네트워크 문제는 다른 출처로 가도 같아서 여기서 멈춤
                except OSError as e:
                    if e.errno == errno.ENOSPC:
                        raise InstallError("disk", "디스크 공간이 모자라요", "weights")
                    raise
                except InstallError as e:
                    if e.kind != "source":
                        raise
                    last = e
                    log(e.message)
                    break
            if last is None:
                break
        if last:
            raise last


# ---------- 설치 작업 ----------

class Installer:
    """엔진 하나의 설치를 뒤에서 돌리고 진행을 알려 줘요. 허브에 엔진마다 하나."""

    def __init__(self, recipe: dict, selftest):
        self.recipe = recipe
        self.selftest = selftest  # callable(engine_id) -> dict, 실패면 InstallError
        self.thread: threading.Thread | None = None
        self.cancel = threading.Event()
        self.progress = {"step": None, "bytes_done": 0, "bytes_total": 0, "log": []}

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def log(self, msg: str) -> None:
        self.progress["log"] = (self.progress["log"] + [msg])[-200:]
        logf = paths.engine_dir(self.recipe["id"]) / "install.log"
        with open(logf, "a", encoding="utf-8") as fh:
            fh.write(f"{now()} {msg}\n")

    def start(self, accept_license: str) -> None:
        r = self.recipe
        if accept_license != r["license"]["id"]:
            raise InstallError("license", "라이선스 동의가 필요해요")
        if self.running:
            return
        st = read_state(r["id"])
        st["consent"] = {"license": r["license"]["id"], "url": r["license"]["url"], "at": now(),
                         "recipe_version": r["recipe_version"]}
        if st.get("recipe_version") not in (None, r["recipe_version"]):
            st["done"] = []  # 레시피가 바뀌면 처음부터(v1 에서 옆에 새로 만들고 비교하는 방식으로 바꿈)
        st["install"] = "installing"
        st.pop("error", None)
        write_state(r["id"], st)
        self.cancel.clear()
        self.thread = threading.Thread(target=self._run, name=f"install-{r['id']}", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.cancel.set()

    def _bump(self, n: int) -> None:
        self.progress["bytes_done"] += n

    def _run(self) -> None:
        proc.set_cancel(self.cancel)  # 이 스레드의 하위 프로세스가 [멈춤]을 듣게
        r = self.recipe
        eid = r["id"]
        st = read_state(eid)
        self.progress.update(bytes_done=0, bytes_total=sum(int(f["size"]) for f in catalog.all_weight_files(r)))
        try:
            how = choose(r)
            if how["runtime"] == "none":
                raise InstallError("dependency", "이 운영체제에서 설치하는 방법이 아직 없어요", "plan")
            if how["runtime"] == "wsl" and wsl.status()["state"] in ("none", "needs_setup"):
                raise InstallError("wsl", "이 엔진은 WSL2 가 있어야 해요. 먼저 WSL2 를 켜 주세요.", "plan")
            if st.get("device") and st["device"] != how["device"] and "packages" in st.get("done", []):
                st["done"] = [x for x in st["done"] if x not in ("env", "packages", "selftest")]  # 장치가 바뀌면 환경을 다시
            st.update(runtime=how["runtime"], device=how["device"])
            p = plan(r)
            if not p["disk_ok"]:
                raise InstallError("disk", f"공간이 모자라요: {p['need_bytes'] / 2**30:.1f}GB 가 필요해요", "plan")
            for step in STEPS:
                if step in st.get("done", []):
                    continue
                if self.cancel.is_set():
                    raise InstallError("network", "사용자가 멈췄어요", step)
                self.progress["step"] = step
                self.log(f"[{step}] 시작")
                if step == "env":
                    step_env(r, self.log, how)
                elif step == "code":
                    step_code(r, self.log, lambda n: None, self.cancel)
                elif step == "packages":
                    step_packages(r, self.log, how)
                elif step == "weights":
                    step_weights(r, self.log, self._bump, self.cancel)
                elif step == "selftest":
                    st["selftest"] = self.selftest(eid)
                st.setdefault("done", []).append(step)
                write_state(eid, st)
                self.log(f"[{step}] 끝")
            st.update(install="installed", recipe_version=r["recipe_version"], installed_at=now())
            self.progress["step"] = None
        except InstallError as e:
            paused = self.cancel.is_set() or e.kind == "network"
            st.update(install="paused" if paused else "failed",
                      error={"kind": e.kind, "message": e.message, "step": e.step or self.progress["step"]})
            self.log(f"[{e.step or self.progress['step']}] {e.kind}: {e.message}")
        except Exception as e:  # 알 수 없음 - 로그 묶음으로 이슈 보고(4.4)
            st.update(install="failed", error={"kind": "unknown", "message": f"{type(e).__name__}: {e}",
                                               "step": self.progress["step"]})
            self.log(f"[{self.progress['step']}] unknown: {e!r}")
        write_state(eid, st)


def remove(recipe: dict, part: str) -> int:
    """지우기(4.6): all · env · weights. 되찾은 바이트를 돌려줘요."""
    eid = recipe["id"]
    d = paths.engine_dir(eid)
    targets = {"all": [d], "env": [d / "env"], "weights": [d / "weights"]}[part]
    freed = 0
    if part in ("all", "env") and read_state(eid).get("runtime") == "wsl" and wsl.status()["state"] == "ready":
        root = wsl.engine_root(eid)
        wsl.sh(f"rm -rf {shlex.quote(root)}/env", timeout=600)
        # WSL 배포판 디스크 파일(vhdx)은 저절로 줄지 않아 Windows 쪽 빈 공간으로는 바로 돌아오지 않아요 - 되찾은 양에 넣지 않아요
    for t in targets:
        if t.exists():
            freed += sum(f.stat().st_size for f in t.rglob("*") if f.is_file())
            for _ in range(3):  # Windows 는 방금 끈 프로세스가 파일을 잠깐 쥐고 있을 수 있어요
                try:
                    shutil.rmtree(t)
                    break
                except PermissionError:
                    time.sleep(1)
    if part != "all":
        st = read_state(eid)
        drop = {"env": ("env", "packages", "selftest"), "weights": ("weights", "selftest")}[part]
        st["done"] = [s for s in st.get("done", []) if s not in drop]
        st["install"] = "none" if not st["done"] else "paused"
        write_state(eid, st)
    return freed


def disk_usage(recipe: dict) -> dict:
    d = paths.engine_dir(recipe["id"])

    def size(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0

    env = size(d / "env")
    if read_state(recipe["id"]).get("runtime") == "wsl" and wsl.status()["state"] == "ready":
        code, out = wsl.sh(f"du -sb {shlex.quote(wsl.engine_root(recipe['id']))}/env 2>/dev/null | cut -f1", timeout=120)
        env = int(out.split()[0]) if code == 0 and out.split() and out.split()[0].isdigit() else env
    return {"env": env, "weights": size(d / "weights")}


__all__ = ["Installer", "InstallError", "plan", "read_state", "write_state", "install_status", "remove",
           "disk_usage", "catalog"]
