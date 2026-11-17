"""엔진 카탈로그 - engines/<id>/recipe.yaml 을 읽어요(4.1·4.10).

레시피 판 2(2026-11-17)에서 넓힌 것 - 옛 꼴(한 줄 문자열·weights 하나)도 그대로 읽어요.
- packages: {<플랫폼>: 파일} 또는 {<플랫폼>: {cuda: 파일, cpu: 파일}} - 장치에 맞는 목록을 골라요.
- runtime: {win-x64: wsl} 이면 Windows 에서는 WSL2 안(리눅스)에서 linux-x64 목록으로 돌아요.
- weights: {sources, files} 하나 또는 [{dir, sources, files}, ...] 여럿(저장소 여럿을 받는 엔진).
- voices_from: shared 면 공용 기본 목소리(engines/_voices) 를 참조 클립으로 써요(복제만 되는 엔진).
"""
import os
from pathlib import Path

import yaml

from . import paths

REQUIRED = ("id", "name", "recipe_version", "role", "devices", "measured", "license", "python", "packages",
            "weights", "adapter")


class RecipeError(ValueError):
    pass


def weight_groups(r: dict) -> list[dict]:
    w = r["weights"]
    if isinstance(w, dict):
        return [{"dir": "", "sources": w.get("sources", []), "files": w.get("files", [])}]
    return [{"dir": g.get("dir", ""), "sources": g["sources"], "files": g["files"]} for g in w]


def all_weight_files(r: dict) -> list[dict]:
    return [f for g in weight_groups(r) for f in g["files"]]


def runtime_for(r: dict, platform: str) -> str:
    """native(이 운영체제에서 바로) · wsl(Windows 의 WSL2 안) · none(이 운영체제용 방법 없음)"""
    rt = (r.get("runtime") or {}).get(platform)
    # 시험용: SORI_RUNTIME_OVERRIDE="supertonic-3:wsl" 이면 그 엔진을 WSL2 로(스팟에서 WSL2 흐름 확인용)
    for item in os.environ.get("SORI_RUNTIME_OVERRIDE", "").split(","):
        if ":" in item and item.split(":", 1)[0] == r.get("id") and platform.startswith("win"):
            return item.split(":", 1)[1]
    if rt:
        return rt
    return "native" if platform in r.get("packages", {}) else "none"


def package_platform(r: dict, platform: str) -> str:
    return "linux-x64" if runtime_for(r, platform) == "wsl" else platform


def package_file(r: dict, platform: str, device: str | None) -> str | None:
    """장치(cuda·cpu)에 맞는 잠금 파일. 한 줄 문자열이면 장치와 상관없이 그것."""
    p = r["packages"].get(package_platform(r, platform))
    if p is None:
        return None
    if isinstance(p, str):
        return p
    return p.get(device or "cpu") or p.get("cuda") or p.get("cpu")


def load_recipe(d: Path) -> dict:
    r = yaml.safe_load((d / "recipe.yaml").read_text(encoding="utf-8"))
    if (d / "i18n.yaml").exists():  # 화면 언어별 문구(영어 등) - 레시피 생성기가 덮어쓰지 않게 따로 둬요
        r["i18n"] = yaml.safe_load((d / "i18n.yaml").read_text(encoding="utf-8")) or {}
    missing = [k for k in REQUIRED if k not in r]
    if missing:
        raise RecipeError(f"{d.name}: 레시피에 {', '.join(missing)} 가 없어요")
    if r["id"] != d.name:
        raise RecipeError(f"{d.name}: 폴더 이름과 id({r['id']})가 달라요")
    for k in ("id", "name", "url", "summary"):
        if k not in r["license"]:
            raise RecipeError(f"{d.name}: license.{k} 가 없어요")
    for g in weight_groups(r):
        if Path(g["dir"]).is_absolute() or ".." in Path(g["dir"]).parts:
            raise RecipeError(f"{d.name}: 가중치 폴더가 밖을 가리켜요: {g['dir']}")
        for f in g["files"]:
            if not {"path", "size", "sha256"} <= set(f):
                raise RecipeError(f"{d.name}: 가중치 파일에 path·size·sha256 이 모두 있어야 해요")
            p = Path(f["path"])
            if p.is_absolute() or ".." in p.parts:
                raise RecipeError(f"{d.name}: 가중치 경로가 폴더 밖을 가리켜요: {f['path']}")
    for c in r.get("code") or []:
        if not {"url", "sha256", "dir"} <= set(c) or "/" in c["dir"] or "\\" in c["dir"] or c["dir"] in ("", ".", ".."):
            raise RecipeError(f"{d.name}: 소스 항목은 url·sha256·dir(폴더 이름 하나)이 있어야 해요")
    for lp in r.get("local_packages") or []:
        lpp = Path(lp)
        if lpp.is_absolute() or ".." in lpp.parts or not lp.startswith("code/"):
            raise RecipeError(f"{d.name}: local_packages 는 code/ 아래만 돼요: {lp}")
    r["_dir"] = str(d)
    return r


def load_all() -> dict[str, dict]:
    out = {}
    root = paths.engines_src()
    for d in sorted(root.iterdir()) if root.exists() else []:
        if d.name.startswith("_"):
            continue  # _voices 같은 공용 자료
        if (d / "recipe.yaml").exists():
            r = load_recipe(d)
            out[r["id"]] = r
    return out


def shared_voices() -> list[dict]:
    """공용 기본 목소리 - Qwen3-TTS 가 한국어 묘사로 만든 가상 인물(실존 인물 아님). 복제만 되는 엔진이 참조로 써요."""
    f = paths.engines_src() / "_voices" / "voices.yaml"
    if not f.exists():
        return []
    vs = yaml.safe_load(f.read_text(encoding="utf-8"))["voices"]
    for v in vs:
        v["_wav"] = str(f.parent / v["wav"])
    return vs


def voices(r: dict) -> list[dict]:
    if r.get("voices_from") == "shared":
        return [{"id": v["id"], "name": v["name"], "name_en": v.get("name_en"), "gender": v.get("gender"), "desc": v.get("desc")}
                for v in shared_voices()]
    return r.get("voices", [])


def voice_ref(r: dict, voice_id: str | None) -> dict:
    """그 목소리를 만들 때 엔진에 넘길 참조(공용 목소리면 클립과 전사)."""
    if r.get("voices_from") != "shared":
        return {}
    for v in shared_voices():
        if v["id"] == voice_id:
            return {"ref": v["_wav"], "ref_text": v.get("text")}
    return {}


def public(r: dict) -> dict:
    """화면·API 로 내보낼 칸만(내부 경로·파일 해시 목록 제외)."""
    keep = ("id", "name", "recipe_version", "role", "summary", "maker", "homepage", "devices", "measured",
            "license", "maintenance", "default_voice", "tags", "max_chars", "human_eval", "good_for",
            "threads", "features", "voices_from", "runtime_note", "speed", "i18n")
    out = {k: r[k] for k in keep if k in r}
    out["voices"] = voices(r)
    if not out.get("default_voice") and out["voices"]:
        out["default_voice"] = out["voices"][0]["id"]
    out["weights_bytes"] = sum(int(f["size"]) for f in all_weight_files(r))
    out["env_bytes"] = env_bytes(r, "cpu"), env_bytes(r, "cuda")
    # 화면 어디서나 같은 "받을 양" = 모델 파일 + 엔진 환경(장치별 실측, 없으면 추정)(리뷰 2026-11-17)
    out["download_bytes"] = out["weights_bytes"] + out["env_bytes"][0]
    out["weights_sources"] = [{"repo": s["repo"], "revision": s["revision"]} for g in weight_groups(r)
                              for s in g["sources"][:1]]
    out["runtime"] = runtime_for(r, paths.platform_key())
    out["has_code"] = bool(r.get("code"))
    out["license"] = {k: v for k, v in r["license"].items() if k not in ("text_file",)}
    out["license"]["has_text"] = bool(r["license"].get("text_file"))
    return out


ENV_BYTES_GUESS = 600 * 2**20


def env_bytes(r: dict, device: str) -> int:
    e = r.get("env_bytes") or {}
    return int(e.get(device) or e.get("cpu") or ENV_BYTES_GUESS)


def license_text(r: dict) -> dict:
    """라이선스 원문(앱에 함께 들어 있어 오프라인에서도 보여요). restrictions = 용도 제한 부분(OpenRAIL)."""
    lic = r["license"]
    if not lic.get("text_file"):
        return {"text": None, "restrictions": None}
    text = (Path(r["_dir"]) / lic["text_file"]).read_text(encoding="utf-8")
    rest = None
    mark = lic.get("restrictions_from")
    if mark and mark in text:
        rest = text[text.rindex(mark):].strip()
    return {"text": text, "restrictions": rest}
