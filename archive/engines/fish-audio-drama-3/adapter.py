"""Fish Audio Drama-3 (int4) 어댑터 - SGLang-Omni 서버(engines/_shared/sglomni.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from sglomni import SglOmniAdapter  # noqa: E402


class Adapter(SglOmniAdapter):
    model_dir = "drama3"

    def server_args(self):
        # 코덱(codec.pth)은 int4 저장소에 같이 들어 있어요(s2-pro 판과 sha256 같음) - 따로 받지 않게
        # 32GB 카드(RTX PRO 4500 · RTX 5090): 기본 나눔(엔진 0.65·보코더 0.15)으로는 KV 캐시 자리가 없어요.
        # 합계 0.80 은 그대로(전처리 예약 6GiB 와 합쳐 물리 메모리를 넘지 않게) 두고 엔진 0.68·보코더 0.12 로(스팟 2026-11-17)
        return ["--vocoder.factory.codec_path", str(Path(self.weights_dir) / "drama3"),
                "--tts_engine.gpu_memory_fraction", "0.68", "--vocoder.gpu_memory_fraction", "0.12",
                # Blackwell(sm_120)에서 미리 만드는 CUDA 그래프가 수십 분 걸려(0/43 에서 멈춤) 끄고, 동시 요청을 4로 줄여 메모리 여유를
                "--tts_engine.factory.gdn_prefill_cuda_graphs", "false", "--tts_engine.factory.first_frame_cuda_graphs", "false",
                "--tts_engine.factory.max_running_requests", "4"]

    def body(self, text, voice=None, seed=0, ref=None, ref_text=None):
        # 서버 판은 language·seed 칸을 안 받아요(bench 2026-11-16). 복제는 참조 + 전사 필수.
        b = {"input": text, "response_format": "wav"}
        if ref:
            b["references"] = [{"audio_path": ref, **({"text": ref_text} if ref_text else {})}]
        return b
