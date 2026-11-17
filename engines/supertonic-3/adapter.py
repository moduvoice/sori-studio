"""Supertonic-3 어댑터 - 엔진 환경 안에서 일꾼(worker)이 불러요.

규약(docs/sori-studio-features.md 4.10): Adapter(weights_dir, threads) → load() → synth(text, voice, seed) -> (float32 1차원, 표본율).
oh-my-tts 벤치 어댑터(jobs/bench/adapters/supertonic_3.py)와 같은 호출을 써요.
"""
import numpy as np


class Adapter:
    def __init__(self, weights_dir, threads=None):
        self.weights_dir = weights_dir
        self.threads = threads
        self.styles = {}

    def load(self):
        from supertonic import TTS

        kw = {"intra_op_num_threads": int(self.threads)} if self.threads else {}
        self.tts = TTS(model="supertonic-3", model_dir=self.weights_dir, auto_download=False, **kw)
        self.sr = int(getattr(self.tts, "sample_rate", None) or 44100)

    def synth(self, text, voice=None, seed=0):
        name = voice or "F1"
        if name not in self.styles:
            self.styles[name] = self.tts.get_voice_style(voice_name=name)
        r = self.tts.synthesize(text, voice_style=self.styles[name], lang="ko")
        wav = r[0] if isinstance(r, tuple) else r
        return np.asarray(wav, np.float32).reshape(-1), self.sr
