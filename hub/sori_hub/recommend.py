"""첫 실행 마법사·카탈로그 추천(기능 설계 4.3 "MVP 대응표").

순서는 측정·사람 평가로만 정해요(라이선스와 섞지 않음). 카탈로그에 아직 없는 엔진(다음 판)은 건너뛰고,
건너뛴 것은 "다음 판에 들어와요" 로 솔직하게 알려 줘요.
"""
from . import hardware

# 쓰임새 → 엔진 id 순서(1순위부터). 이름은 카탈로그에 없을 때 안내용.
USES = {
    # 사람 평가(oh-my-tts bank/human-eval.md)·측정 순서. 카탈로그에 없는 엔진은 "다음 판"으로 알려요.
    "narration": [("qwen3-tts", "Qwen3-TTS"), ("voxcpm2", "VoxCPM2"), ("cosyvoice3", "CosyVoice3"),
                  ("supertonic-3", "Supertonic-3"), ("kitten-tts-2-mini", "Kitten TTS 2 mini")],
    "acting": [("qwen3-tts", "Qwen3-TTS"), ("voxcpm2", "VoxCPM2")],
    "clone": [("confucius4", "Confucius4-TTS"), ("voxcpm2", "VoxCPM2"), ("cosyvoice3", "CosyVoice3"), ("dots-tts", "dots.tts")],
    "light": [("supertonic-3", "Supertonic-3"), ("kitten-tts-2-mini", "Kitten TTS 2 mini")],
}
RUNS = (hardware.GPU_OK, hardware.CPU_OK, hardware.TIGHT, hardware.CPU_SLOW, hardware.UNVERIFIED)


def recommend(use: str, recipes: dict, hw: dict, direct_only: bool = False) -> dict:
    """direct_only: 첫 실행 마법사용 - 추가 설치(WSL2)가 필요한 엔진은 빼요(관리자 창·다시 시작 없이 바로 소리까지)."""
    if use not in USES:
        raise KeyError(use)
    order = USES[use]
    if direct_only:
        from . import catalog

        order = [(e, n) for e, n in order if e not in recipes or catalog.runtime_for(recipes[e], hw.get("platform", "")) != "wsl"]
    present, later = [], []
    for eid, name in order:
        if eid in recipes:
            present.append((eid, hardware.verdict(recipes[eid], hw)))
        else:
            later.append(name)
    runnable = [(e, v) for e, v in present if v["verdict"] in RUNS]
    # 같은 순위 안에서는 잘 도는 것을 앞으로(빠듯함·느림·미검증은 뒤로)
    rank = {k: i for i, k in enumerate(RUNS)}
    runnable.sort(key=lambda x: (rank[x[1]["verdict"]] > 1, [e for e, _ in order].index(x[0])))
    rec = runnable[0][0] if runnable else None
    return {
        "use": use,
        "recommended": rec,
        "alternatives": [e for e, _ in runnable[1:]],
        "not_here": [e for e, v in present if v["verdict"] not in RUNS],
        "coming_later": later,  # 이 판에는 아직 없는 엔진(이름)
    }
