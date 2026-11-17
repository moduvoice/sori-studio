"""CosyVoice3 0.5B 어댑터 - SGLang-Omni 서버(engines/_shared/sglomni.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from sglomni import SglOmniAdapter  # noqa: E402


class Adapter(SglOmniAdapter):
    model_dir = "cosyvoice3"

    def python_paths(self):
        # SGLang 의 CosyVoice3 는 공식 CosyVoice 소스(cosyvoice 패키지)와 그 서브모듈 Matcha-TTS 가 경로에 있어야 해요
        code = Path(self.weights_dir).parent / "code"
        return [code / "cosyvoice", code / "matcha"]

    def body(self, text, voice=None, seed=0, ref=None, ref_text=None):
        # CosyVoice3 는 전사를 빼고 복제해야 정확해요(bench: 빼면 오류율 1.2~1.3%)
        b = {"input": text, "response_format": "wav", "seed": int(seed or 0)}
        if ref:
            b["references"] = [{"audio_path": ref}]
        return b
