"""Confucius4-TTS 어댑터 - 소스 코드(code/confucius4)의 ConfuciusTTS. 전사 없는 복제(참조 클립만), 지시·태그 없음.
oh-my-tts 벤치 어댑터(jobs/bench/adapters/confucius4_tts.py)와 같은 호출. 모델은 허브가 받아 둔 로컬 파일만 읽어요(인터넷 안 씀)."""
import os
import sys
from pathlib import Path

import numpy as np

REPO_DIR = {"netease-youdao/Confucius4-TTS": "confucius4", "funasr/campplus": "campplus"}


class Adapter:
    def __init__(self, weights_dir, threads=None, device="cuda"):
        self.w = Path(weights_dir)
        self.code = self.w.parent / "code" / "confucius4"
        self.device = device

    def load(self):
        os.environ["HF_HUB_OFFLINE"] = "1"
        sys.path.insert(0, str(self.code))
        import torch
        import yaml

        cfg = yaml.safe_load((self.code / "config" / "inference_config.yaml").read_text(encoding="utf-8"))
        p = cfg["paths"]
        p["tokenizer_path"] = str(self.w / "confucius4")
        p["w2v_bert_path"] = str(self.w / "w2v-bert-2.0")
        p["w2v_stat"] = str(self.w / "confucius4" / "wav2vec2bert_stats.pt")
        p["vocoder_path"] = str(self.w / "bigvgan")
        conf = self.w.parent / "inference_config.sori.yaml"
        conf.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        import confuciustts.cli.inference as inf

        inf.hf_hub_download = lambda repo_id, filename, **k: str(self.w / REPO_DIR[repo_id] / filename)
        os.chdir(self.code)  # 저장소의 상대 경로(external 등)
        self.torch = torch
        self.m = inf.ConfuciusTTS(config_path=str(conf), device=self.device)
        self.sr = int(self.m.sample_rate)

    def synth(self, text, voice=None, seed=0, ref=None, ref_text=None):
        self.torch.manual_seed(seed)
        a = self.m.generate(text, "ko", ref, verbose=False)
        return np.asarray(a.detach().cpu().float().numpy(), np.float32).reshape(-1), self.sr
