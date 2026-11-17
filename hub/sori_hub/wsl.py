"""WSL2 - Windows 에서 리눅스 전용 엔진을 돌리는 길(사용자 2026-11-17 "윈도우에 맞지 않으면 WSL2 를 안내").

- 감지: wsl.exe 가 있는지, WSL2 가 켜져 있는지(가상화), 우리 배포판(SoriStudio)이 있는지.
- WSL 자체 설치(`wsl --install --no-distribution`)는 관리자 권한과 다시 시작이 필요해서 허브가 하지 않아요.
  화면(껍데기)이 관리자 창으로 띄우고, 다시 켜면 이어서 해요.
- 우리 배포판은 Ubuntu 공식 WSL 이미지를 받아 `wsl --import` 로 따로 만들어요(사용자의 다른 리눅스를 건드리지 않음).
- 엔진 환경(venv)은 리눅스 파일 시스템 안(~/.sori/engines/<id>)에, 모델 파일은 Windows 모델 폴더를 /mnt 로 읽어요.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path, PureWindowsPath

from . import paths

DISTRO = os.environ.get("SORI_WSL_DISTRO", "SoriStudio")
# Ubuntu 24.04 공식 WSL 이미지 - 날짜 판으로 고정하고 sha256 을 코드에 박아요(판이 바뀌어도 같은 배포판이 만들어지게).
ROOTFS_URL = "https://cloud-images.ubuntu.com/wsl/releases/24.04/20240423/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz"
ROOTFS_SHA256 = "2a790896740b14d637dbdc583cce1ba081ac53b9e9cdb46dc09a2f73abbd9934"
ROOTFS_SIZE = 356736729
# WSL 안의 uv - 판 고정 GitHub 릴리스 묶음(sha256 확인). 설치 스크립트를 curl|sh 로 돌리지 않아요.
UV_URL = "https://github.com/astral-sh/uv/releases/download/0.13.8/uv-x86_64-unknown-linux-gnu.tar.gz"
UV_SHA256 = "5acfd9177cfecf0bf87578f059728215ccc884388988f55f7a65041b57387d91"
# NVIDIA 공식 WSL-Ubuntu 저장소 키링(sha256 확인)
CUDA_KEYRING_URL = "https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb"
CUDA_KEYRING_SHA256 = "eea6cc5f0eaeb99082d054b8c05ae206a378e31e88048df0310d59f651dceed2"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _wsl_exe() -> str | None:
    if sys.platform != "win32":
        return None
    p = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wsl.exe"
    return str(p) if p.exists() else shutil.which("wsl")


def _run(args: list[str], timeout: float = 60, input_text: str | None = None) -> tuple[int, str]:
    exe = _wsl_exe()
    if not exe:
        return 127, "wsl.exe 없음"
    from . import proc

    env = dict(os.environ, WSL_UTF8="1")  # wsl.exe 자체 출력을 UTF-16 대신 UTF-8 로
    # 멈출 수 있게(설치 중 [멈춤]) - proc.Cancelled 는 부른 쪽에서 받아요
    code, raw = proc.run([exe, *args], env=env, timeout=timeout, input_bytes=input_text.encode() if input_text else None)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-16-le", errors="replace")
    return code, text.replace("\x00", "")


def status() -> dict:
    """화면의 WSL2 안내가 쓰는 상태: none(wsl 없음) · needs_setup(WSL 은 있으나 꺼짐·재시작 필요) · no_distro · ready"""
    if sys.platform != "win32":
        return {"state": "not_windows"}
    if not _wsl_exe():
        return {"state": "none", "detail": "wsl.exe 가 없어요"}
    code, out = _run(["--status"], timeout=30)
    low = out.lower()
    if code != 0 or "not installed" in low or "설치되어 있지 않" in out or "wsl --install" in low:
        virt = "virtualization" in low or "가상" in out
        return {"state": "needs_setup", "virtualization_off": virt, "detail": out.strip()[-400:]}
    code, out = _run(["-l", "-q"], timeout=30)
    distros = [x.strip() for x in out.splitlines() if x.strip()]
    if DISTRO not in distros:
        return {"state": "no_distro", "distros": distros}
    return {"state": "ready", "distros": distros}


def to_wsl_path(p: str | Path) -> str:
    """D:\\a\\b → /mnt/d/a/b"""
    w = PureWindowsPath(str(p))
    drive = w.drive.rstrip(":").lower()
    rest = "/".join(w.parts[1:])
    return f"/mnt/{drive}/{rest}"


def sh(cmd: str, timeout: float = 3600, user: str = "root") -> tuple[int, str]:
    """우리 배포판 안에서 bash 명령."""
    return _run(["-d", DISTRO, "-u", user, "--", "bash", "-lc", cmd], timeout=timeout)


def setup_distro(log, progress=None) -> None:
    """우리 배포판 만들기: Ubuntu 이미지 받기(해시 확인) → wsl --import → 기본 도구(uv)."""
    from .installer import InstallError, _download  # 순환 import 피하기

    st = status()
    if st["state"] in ("none", "needs_setup", "not_windows"):
        raise InstallError("wsl", "WSL2 가 먼저 켜져 있어야 해요", "env")
    if st["state"] == "ready":
        return
    base = paths.models_dir() / ".wsl"
    base.mkdir(parents=True, exist_ok=True)
    tar = base / "ubuntu-rootfs.tar.gz"
    want = ROOTFS_SHA256
    if not (tar.exists() and _sha(tar) == want):
        log(f"Ubuntu 이미지 받기: {ROOTFS_URL}")
        import threading

        _download(ROOTFS_URL, tar, ROOTFS_SIZE, progress or (lambda n: None), threading.Event())
        if _sha(tar) != want:
            tar.unlink()
            raise InstallError("source", "받은 Ubuntu 이미지의 해시가 맞지 않아요", "env")
    log(f"WSL 배포판 {DISTRO} 만들기")
    code, out = _run(["--import", DISTRO, str(base / DISTRO), str(tar), "--version", "2"], timeout=900)
    log(out.strip())
    if code != 0:
        raise InstallError("wsl", f"WSL 배포판을 만들지 못했어요: {out.strip()[-200:]}", "env")
    code, out = sh("apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl ca-certificates "
                   "libsndfile1 ffmpeg git build-essential >/dev/null && "
                   f"curl -fsSL -o /tmp/uv.tgz {UV_URL} && echo '{UV_SHA256}  /tmp/uv.tgz' | sha256sum -c - && "
                   "tar -xzf /tmp/uv.tgz -C /tmp && install -m 755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv && "
                   "rm -rf /tmp/uv.tgz /tmp/uv-x86_64-unknown-linux-gnu", timeout=1800)
    log(out.strip()[-2000:])
    if code != 0:
        raise InstallError("dependency", "WSL 안에 기본 도구를 깔지 못했어요", "env")


# 엔진이 요구하는 시스템 부품(레시피 system_deps). CUDA 툴킷은 NVIDIA 공식 WSL-Ubuntu 저장소에서(드라이버는 Windows 것을 써요 - WSL 안에 드라이버 금지)
SYSTEM_DEPS = {
    "cuda-toolkit-13-0": (
        "test -x /usr/local/cuda-13.0/bin/nvcc || ("
        f"cd /tmp && curl -fsSLO {CUDA_KEYRING_URL}"
        f" && echo '{CUDA_KEYRING_SHA256}  cuda-keyring_1.1-1_all.deb' | sha256sum -c -"
        " && dpkg -i cuda-keyring_1.1-1_all.deb && apt-get update -qq"
        " && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cuda-toolkit-13-0 >/dev/null)"
        " && ln -sfn /usr/local/cuda-13.0 /usr/local/cuda"),
}


def install_system_deps(deps: list[str], log) -> None:
    from .installer import InstallError

    for d in deps:
        if d not in SYSTEM_DEPS:
            raise InstallError("dependency", f"모르는 시스템 부품이에요: {d}", "env")
        log(f"[WSL] 시스템 부품 {d}")
        code, out = sh(SYSTEM_DEPS[d], timeout=3600)
        log(out.strip()[-1500:])
        if code != 0:
            raise InstallError("dependency", f"WSL 안에 {d} 를 깔지 못했어요", "env")


def _sha(f: Path) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def engine_root(eid: str) -> str:
    return f"/root/.sori/engines/{eid}"


def env_python(eid: str) -> str:
    return f"{engine_root(eid)}/env/bin/python"


def has_gpu() -> bool:
    """WSL 안에서 GPU 가 보이는지(Windows 의 NVIDIA 드라이버가 WSL 에 GPU 를 넘겨줘야 해요)."""
    code, out = sh("nvidia-smi -L 2>/dev/null | head -1", timeout=60)
    return code == 0 and bool(re.search(r"GPU \d", out))
