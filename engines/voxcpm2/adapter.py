"""VoxCPM2 어댑터 - pip voxcpm. 공용 기본 목소리(참조 클립 + 전사)로 복제해서 읽어요(전사 이어 말하기 = Ultimate).
oh-my-tts 벤치 어댑터(jobs/bench/adapters/voxcpm2.py)와 같은 설정(cfg 2.0, 10단계)."""
import os
import random

import numpy as np


class Adapter:
    def __init__(self, weights_dir, threads=None, device="cpu"):
        self.path = os.path.join(weights_dir, "voxcpm2")
        self.device = device
        self.threads = threads

    def load(self):
        import torch
        from voxcpm import VoxCPM

        self.torch = torch
        if self.device != "cuda" and self.threads:
            torch.set_num_threads(int(self.threads))
        try:
            self.m = VoxCPM.from_pretrained(self.path, load_denoiser=False, device=self.device)
        except TypeError:
            self.m = VoxCPM.from_pretrained(self.path, load_denoiser=False)
        self.sr = self.m.tts_model.sample_rate

    def synth(self, text, voice=None, seed=0, ref=None, ref_text=None):
        self.torch.manual_seed(seed)
        random.seed(seed)
        np.random.seed(seed)
        kw = {"cfg_value": 2.0, "inference_timesteps": 10}
        if ref and ref_text:
            kw.update(prompt_wav_path=ref, prompt_text=ref_text, reference_wav_path=ref)
        elif ref:
            kw.update(reference_wav_path=ref)
        y = self.m.generate(text=text, **kw)
        return np.asarray(y, np.float32).reshape(-1), int(self.sr)
