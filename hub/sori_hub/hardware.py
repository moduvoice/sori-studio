"""하드웨어 감지와 "이 PC" 판정(4.5, v0.4 여섯 단계)."""
import ctypes
import os
import platform
import shutil
import subprocess
import sys

from . import paths

MARGIN = 1.15  # 측정 최대 메모리에 붙이는 여유(처음 값 15%, 추정 - 시험으로 조정)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 2**30, 1)
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
            return round(int(out) / 2**30, 1)
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 2**20, 1)
    except Exception:
        return None
    return None


def _nvidia() -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=index,name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout
    except Exception:
        return []
    gpus = []
    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 4:
            try:
                gpus.append({"index": int(p[0]), "name": p[1], "vram_gb": round(float(p[2]) / 1024, 1),
                             "driver": p[3], "compute_cap": p[4] if len(p) > 4 else None, "vendor": "nvidia"})
            except ValueError:
                continue
    return gpus


def drives() -> list[dict]:
    """마법사 2단계 드라이브 목록(Windows 는 글자 드라이브, 그 밖은 홈이 있는 곳 하나)."""
    out = []
    if sys.platform == "win32":
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = f"{chr(65 + i)}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) not in (2, 3):  # 이동식·고정 디스크만
                continue
            try:
                du = shutil.disk_usage(root)
            except OSError:
                continue
            name = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(root, name, 261, None, None, None, None, 0)
            out.append({"root": root, "label": name.value, "total_bytes": du.total, "free_bytes": du.free,
                        "suggested": f"{root}SoriStudio\\models"})
    else:
        du = shutil.disk_usage(os.path.expanduser("~"))
        out.append({"root": "/", "label": "", "total_bytes": du.total, "free_bytes": du.free,
                    "suggested": os.path.expanduser("~/.sori-studio/models")})
    return out


def _os_name() -> str:
    if sys.platform == "win32":
        build = int(platform.version().split(".")[-1]) if platform.version().split(".")[-1].isdigit() else 0
        return f"Windows {'11' if build >= 22000 else platform.release()}"
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]}"
    return f"Linux {platform.release()}"


def _cpu_name() -> str:
    try:
        if sys.platform == "win32":
            import winreg

            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


def detect() -> dict:
    mdir = paths.models_dir()
    du = shutil.disk_usage(mdir)
    return {
        "os": sys.platform,
        "os_name": _os_name(),
        "os_version": platform.version(),
        "platform": paths.platform_key(),
        "arch": platform.machine(),
        "cpu": _cpu_name(),
        "cores": os.cpu_count(),
        "ram_gb": _ram_gb(),
        "gpus": _nvidia(),
        "apple_silicon": sys.platform == "darwin" and platform.machine() == "arm64",
        "models_dir": str(mdir),
        "disk_free_gb": round(du.free / 2**30, 1),
    }


# 판정 키(화면 문구는 화면의 언어 표가 정해요)
GPU_OK, CPU_OK, CPU_SLOW, TIGHT, NO, UNVERIFIED = "gpu_ok", "cpu_ok", "cpu_slow", "tight", "no", "unverified"


def _driver_major(v) -> int:
    try:
        return int(str(v).split(".")[0])
    except (TypeError, ValueError):
        return 0


def verdict(recipe: dict, hw: dict) -> dict:
    """엔진 하나의 "이 PC" 판정 → {"verdict": 키, "reason": 이유 키, "device": 쓸 장치, ...}"""
    dev = recipe.get("devices", {})
    m = recipe.get("measured", {})
    if hw.get("apple_silicon"):
        if dev.get("mac") in ("ok", "native"):
            return {"verdict": GPU_OK, "reason": "", "device": "mac"}
        if dev.get("mac") == "no":
            return {"verdict": NO, "reason": "mac_unsupported", "device": None}
        return {"verdict": UNVERIFIED, "reason": "mac_not_measured", "device": "mac"}
    from . import catalog

    rt = catalog.runtime_for(recipe, hw.get("platform", ""))
    if rt == "none":
        return {"verdict": NO, "reason": "platform_unsupported", "device": None}
    out = _verdict_devices(recipe, hw, dev, m)
    if rt == "wsl":
        out["via"] = "wsl"  # Windows 에서는 WSL2 안에서 돌아요(화면이 WSL2 안내를 붙여요)
    return out


def _verdict_devices(recipe: dict, hw: dict, dev: dict, m: dict) -> dict:
    if dev.get("cpu") == "native":
        need, ram = m.get("ram_gb"), hw.get("ram_gb")
        if need and ram and ram < need:
            return {"verdict": NO, "reason": "ram_short", "device": None, "need_gb": need}
        if need and ram and ram < need * MARGIN:
            return {"verdict": TIGHT, "reason": "ram_tight", "device": "cpu", "need_gb": need}
        return {"verdict": CPU_OK, "reason": "", "device": "cpu"}
    if dev.get("nvidia") in ("ok", "native"):
        need = m.get("gpu_mem_gb")
        best = max((g["vram_gb"] for g in hw.get("gpus", [])), default=0)
        want = (recipe.get("requires") or {}).get("nvidia_driver")
        have = max((_driver_major(g.get("driver")) for g in hw.get("gpus", [])), default=0)
        if best and want and have < want:
            # 드라이버가 낮으면 GPU 판 torch 가 GPU 를 못 써요 - CPU 로 되는 엔진이면 느리게, 아니면 안 돌아요
            if dev.get("cpu") == "ok":
                return {"verdict": CPU_SLOW, "reason": "driver_old", "device": "cpu", "need_driver": want, "rtf_cpu": m.get("rtf_cpu")}
            return {"verdict": NO, "reason": "driver_old", "device": None, "need_driver": want}
        if best and need is None:
            return {"verdict": UNVERIFIED, "reason": "gpu_mem_not_measured", "device": "cuda"}
        tested = m.get("gpu_tested_gb")
        if tested and need and need <= best < tested * 0.95:  # 32GB 카드는 31.5GB 쯤으로 잡혀요(스팟 실측) - 같은 급으로 봐요
            # GPU 메모리 값이 추정이고 더 큰 카드에서만 돌려 봤어요(서버형 엔진은 카드 메모리의 비율을 잡아요) - 된다고 말하지 않아요
            return {"verdict": UNVERIFIED, "reason": "gpu_small_untested", "device": "cuda", "need_gb": tested}
        if need and best >= need * MARGIN:
            return {"verdict": GPU_OK, "reason": "", "device": "cuda"}
        if need and best >= need:
            return {"verdict": TIGHT, "reason": "vram_tight", "device": "cuda", "need_gb": need}
    if dev.get("cpu") == "ok":
        return {"verdict": CPU_SLOW, "reason": "no_fitting_gpu", "device": "cpu", "rtf_cpu": m.get("rtf_cpu")}
    return {"verdict": NO, "reason": "vram_short" if hw.get("gpus") else "needs_gpu", "device": None,
            "need_gb": m.get("gpu_mem_gb")}
