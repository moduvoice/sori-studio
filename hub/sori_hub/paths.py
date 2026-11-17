"""허브가 쓰는 폴더·파일 자리.

- 허브 홈(설정·토큰·잠금·로그): SORI_HOME, 없으면 Windows %LOCALAPPDATA%/SoriStudio, 그 밖 ~/.sori-studio
- 모델 폴더(엔진 환경·가중치): settings.json 의 models_dir, 없으면 <홈>/models (첫 실행 마법사가 고름, 4.6)
- 엔진 레시피: SORI_ENGINES, 없으면 저장소의 engines/
"""
import json
import os
import platform
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def home() -> Path:
    env = os.environ.get("SORI_HOME")
    if env:
        p = Path(env)
    elif sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        p = Path(os.environ["LOCALAPPDATA"]) / "SoriStudio"
    else:
        p = Path.home() / ".sori-studio"
    p = p.resolve()  # 일꾼은 다른 작업 폴더에서 돌아서 상대 경로가 깨져요
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings() -> dict:
    f = home() / "settings.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_settings(d: dict) -> None:
    write_json(home() / "settings.json", d)


def write_json(f: Path, d) -> None:
    """반쯤 쓴 파일이 남지 않게 임시 파일에 쓰고 바꿔 끼워요."""
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


def models_dir() -> Path:
    p = Path(settings().get("models_dir") or home() / "models").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def engines_src() -> Path:
    return Path(os.environ.get("SORI_ENGINES") or REPO / "engines")


def engine_dir(engine_id: str) -> Path:
    """엔진 하나의 설치 자리: env/(uv 환경) · weights/ · state.json"""
    return models_dir() / engine_id


def env_python(engine_id: str) -> Path:
    env = engine_dir(engine_id) / "env"
    return env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def platform_key() -> str:
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64"
    osk = {"win32": "win", "darwin": "mac"}.get(sys.platform, "linux")
    return f"{osk}-{arch}"
