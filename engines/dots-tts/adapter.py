"""dots.tts (MeanFlow) 어댑터 - SGLang-Omni 서버(engines/_shared/sglomni.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from sglomni import SglOmniAdapter  # noqa: E402


class Adapter(SglOmniAdapter):
    model_dir = "dots-tts"
