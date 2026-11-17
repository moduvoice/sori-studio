"""Kitten TTS 2 mini 어댑터 - pip kittenml, ONNX int8(CPU). 한국어 목소리 Seoyeon·Minjun·Jihoon."""
import os

import numpy as np


class Adapter:
    def __init__(self, weights_dir, threads=None, device="cpu"):
        self.path = os.path.join(weights_dir, "kitten")
        self.threads = threads

    def load(self):
        if self.threads:
            os.environ.setdefault("OMP_NUM_THREADS", str(self.threads))
        from kittenml import KittenTTS

        self.m = KittenTTS(self.path)
        self.sr = int(getattr(self.m, "sample_rate", None) or 24000)

    def synth(self, text, voice=None, seed=0, speed=None):
        try:
            a = self.m.generate(text, voice=voice or "Seoyeon", language="ko", speed=float(speed or 1.0))
        except TypeError:
            a = self.m.generate(text, voice=voice or "Seoyeon")
        if isinstance(a, tuple):
            a, sr = a[0], int(a[1])
        else:
            sr = self.sr
        return np.asarray(a, np.float32).reshape(-1), sr
