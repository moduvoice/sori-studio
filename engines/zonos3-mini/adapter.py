"""ZONOS3-Mini 어댑터 - SGLang-Omni 서버(engines/_shared/sglomni.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from sglomni import SglOmniAdapter  # noqa: E402


class Adapter(SglOmniAdapter):
    model_dir = "zonos3"

    def body(self, text, voice=None, seed=0, ref=None, ref_text=None):
        # 이 SGLang-Omni 판의 ZONOS3 는 voice 칸을 쓰지 않고 참조 클립만 받아요(서연·민준이 같은 소리였음 - 리뷰 2026-11-17).
        # 복제는 전사 없이 참조만(bench 와 같음).
        b = {"input": text, "response_format": "wav", "seed": int(seed or 0)}
        if ref:
            b["references"] = [{"audio_path": ref}]
        return b
