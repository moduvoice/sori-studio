"""길이 검사와 자동 다시 만들기(기능 설계 5.5 의 ASR 없는 검사를 앞당김, 사용자 평 2026-11-17 "VoxCPM2 환각·외국어").

엔진마다 말 빠르기(초당 한글 음절, 스팟 실측)로 예상 길이를 잡고,
소리가 예상의 1.8배를 넘으면(대본에 없는 말·반복·외국어가 끼었을 가능성) 또는 0.5배보다 짧으면(잘림) 의심으로 봐요.
의심이면 씨앗을 바꿔 두 번까지 다시 만들고, 예상 길이에 가장 가까운 것을 골라요.
한계: 길이로만 봐서 같은 길이로 엉뚱한 말을 하면 못 잡아요(받아쓰기 점검은 v1).
"""
import re

LONG, SHORT = 1.8, 0.5
MIN_SYLLABLES = 8  # 너무 짧은 글은 길이로 판단하기 어려워 검사하지 않아요


def syllables(text: str) -> int:
    return len(re.findall(r"[가-힣]", text))


def expected_seconds(recipe: dict, text: str, speed: float | None = None) -> float | None:
    rate = (recipe.get("measured") or {}).get("syll_rate")
    n = syllables(text)
    if not rate or n < MIN_SYLLABLES:
        return None
    return n / (float(rate) * float(speed or 1.0))


def judge(recipe: dict, text: str, audio_s: float, speed: float | None = None) -> str | None:
    """None = 정상, "too_long" · "too_short" = 의심"""
    exp = expected_seconds(recipe, text, speed)
    if exp is None:
        return None
    if audio_s > exp * LONG:
        return "too_long"
    if audio_s < exp * SHORT:
        return "too_short"
    return None


def synth_checked(worker, recipe: dict, text: str, voice, seed: int = 0, speed=None, tries: int = 3):
    """(wav, meta) - meta 에 retries·suspect(남은 의심 이유) 를 더해요."""
    best = None
    for i in range(tries):
        wav, meta = worker.synth(text, voice, seed + i * 7919, speed=speed)
        why = judge(recipe, text, meta["audio_s"], speed)
        exp = expected_seconds(recipe, text, speed) or meta["audio_s"]
        score = abs(meta["audio_s"] - exp)
        if best is None or score < best[0]:
            best = (score, wav, {**meta, "retries": i, "suspect": why, "seed": seed + i * 7919})
        if why is None:
            return wav, {**meta, "retries": i, "suspect": None, "seed": seed + i * 7919}
    return best[1], best[2]
