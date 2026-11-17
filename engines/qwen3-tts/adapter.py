"""Qwen3-TTS 1.7B CustomVoice 어댑터 - pip qwen-tts. 기본 목소리(소희 등)로 읽어요.
oh-my-tts 벤치 어댑터(jobs/bench/adapters/qwen3_tts_0_6b_1_7b.py)와 같은 호출. flash-attn 은 쓰지 않고 sdpa(Windows 에 휠이 없음)."""
import os

import numpy as np


class Adapter:
    def __init__(self, weights_dir, threads=None, device="cpu"):
        self.path = os.path.join(weights_dir, "customvoice")
        self.device = device
        self.threads = threads

    def load(self):
        import torch
        from qwen_tts import Qwen3TTSModel

        self.torch = torch
        if self.device == "cuda":
            kw = {"device_map": "cuda:0", "dtype": torch.bfloat16}
        else:
            if self.threads:
                torch.set_num_threads(int(self.threads))
            kw = {"device_map": "cpu", "dtype": torch.float32}
        self.m = Qwen3TTSModel.from_pretrained(self.path, attn_implementation="sdpa", **kw)

    def synth(self, text, voice=None, seed=0):
        self.torch.manual_seed(seed)
        wavs, sr = self.m.generate_custom_voice(text=text, language="Korean", speaker=voice or "sohee")
        w = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
        return np.asarray(w, np.float32).reshape(-1), int(sr)
