"""Windows 설치 프로그램(.exe) 만들기 - electron-builder NSIS, 사용자별 설치(관리자 권한 없음).

  python etc/build_installer.py            → shell/dist/Sori-Studio-Setup-<판>.exe

설치본 안(resources/app-root): 허브 코드(sori_hub · pyproject · uv.lock · .python-version), 엔진 레시피(engines/),
화면(ui/dist), 판 고정 uv.exe(sha256 확인), LICENSE·NOTICE. 파이썬과 허브 패키지는 넣지 않고, 처음 켤 때 uv 가
잠금 파일대로 사용자 폴더(%LOCALAPPDATA%/SoriStudio/hub-env)에 만들어요(shell/main.js syncHubEnv).
서명은 아직 없어요(README 에 SmartScreen 안내).
"""
import hashlib
import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "shell" / "build" / "app-root"
UV_URL = "https://github.com/astral-sh/uv/releases/download/0.13.8/uv-x86_64-pc-windows-msvc.zip"
UV_SHA256 = "529e78a9cec6cd7e3e014f7ecd8bda0c113969d4ed0f2efeedb85c30943325b8"
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".venv", "tests")


def run(cmd, cwd):
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=sys.platform == "win32")


def main():
    run(["npm", "run", "build"], ROOT / "ui")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "hub").mkdir(parents=True)
    shutil.copytree(ROOT / "hub" / "sori_hub", STAGE / "hub" / "sori_hub", ignore=SKIP)
    for f in ("pyproject.toml", "uv.lock", ".python-version"):
        shutil.copy2(ROOT / "hub" / f, STAGE / "hub" / f)
    shutil.copytree(ROOT / "engines", STAGE / "engines", ignore=SKIP)
    shutil.copytree(ROOT / "ui" / "dist", STAGE / "ui" / "dist")
    for f in ("LICENSE", "NOTICE"):
        shutil.copy2(ROOT / f, STAGE / f)
    data = urllib.request.urlopen(UV_URL, timeout=120).read()
    if hashlib.sha256(data).hexdigest() != UV_SHA256:
        raise SystemExit("uv 묶음의 sha256 이 맞지 않아요")
    (STAGE / "bin").mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        (STAGE / "bin" / "uv.exe").write_bytes(z.read("uv.exe"))
    print(f"묶음 준비: {STAGE}", flush=True)
    run(["npx", "electron-builder", "--win", "nsis", "--x64", "--publish", "never"], ROOT / "shell")
    for f in sorted((ROOT / "shell" / "dist").glob("*.exe")):
        print(f"{f} · {f.stat().st_size / 1e6:.0f} MB · sha256 {hashlib.sha256(f.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
