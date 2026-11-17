"""SGLang-Omni 서버형 엔진 공용 어댑터 - 일꾼 안에서 `sgl-omni serve` 를 빈 포트로 띄우고 OpenAI 호환 /v1/audio/speech 로 받아요.
일꾼이 끝나면 서버도 함께 끝나요(같은 프로세스 묶음 - Windows Job / WSL 안에서는 일꾼의 자식).
bench 어댑터(oh-my-tts jobs/bench/adapters/_sglomni.py)와 같은 요청 꼴."""
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SglOmniAdapter:
    model_dir = ""        # weights/<dir>
    extra_args: list = []
    language = "Korean"
    load_timeout = 7200   # 허브의 한도(레시피 load_s × 3)가 먼저 끊어요 - 여기는 안전망만

    def __init__(self, weights_dir, threads=None, device="cuda"):
        self.weights_dir = weights_dir
        self.device = device

    def load(self):
        exe = Path(sys.executable).parent / ("sgl-omni.exe" if os.name == "nt" else "sgl-omni")
        self.port = free_port()
        log = open(Path(self.weights_dir).parent / "sgl-omni.log", "a", encoding="utf-8")
        env = dict(os.environ, HF_HUB_OFFLINE="1")
        env.pop("LD_LIBRARY_PATH", None)
        # 커널 즉석 컴파일(JIT)은 정식 CUDA 툴킷으로(pip 로 나뉜 CUDA 조각은 헤더 판이 섞여 컴파일이 깨졌어요 - 스팟 2026-11-17).
        # WSL2 는 허브가 NVIDIA 공식 WSL 용 cuda-toolkit 을 깔아 둬요(recipe system_deps). ninja 는 엔진 환경의 bin.
        import site
        bindir = str(Path(sys.executable).parent)
        if Path("/usr/local/cuda/bin/nvcc").exists():
            env["CUDA_HOME"] = "/usr/local/cuda"
            bindir = f"{bindir}{os.pathsep}/usr/local/cuda/bin"
        else:
            for sp in site.getsitepackages():
                cu = Path(sp) / "nvidia" / "cu13"
                if (cu / "bin" / "nvcc").exists():
                    env["CUDA_HOME"] = str(cu)
                    bindir = f"{bindir}{os.pathsep}{cu / 'bin'}"
                    break
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
        extra_py = [str(p) for p in self.python_paths()]
        if extra_py:
            env["PYTHONPATH"] = os.pathsep.join(extra_py + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        voices = Path(__file__).resolve().parents[1] / "_voices"  # 공용 목소리(참조 클립)는 이 폴더만 읽게 허용
        self.proc = subprocess.Popen([str(exe), "serve", "--model-path", str(Path(self.weights_dir) / self.model_dir),
                                      "--host", "127.0.0.1", "--port", str(self.port),
                                      "--allowed-local-media-path", str(voices), *self.server_args()],
                                     stdout=log, stderr=subprocess.STDOUT, env=env)  # 일꾼과 같은 프로세스 그룹 - 허브가 그룹째 끝내요
        import atexit

        atexit.register(self.close)
        self.url = f"http://127.0.0.1:{self.port}"
        t0 = time.time()
        while time.time() - t0 < self.load_timeout:
            if self.proc.poll() is not None:
                self.close()  # 단계 프로세스가 남아 GPU 를 쥐지 않게
                raise RuntimeError(f"sgl-omni 서버가 끝났어요(코드 {self.proc.returncode}) - sgl-omni.log")
            try:
                urllib.request.urlopen(self.url + "/health", timeout=3).read()
                return
            except Exception:
                time.sleep(3)
        self.close()
        raise RuntimeError("sgl-omni 서버가 시간 안에 뜨지 않았어요")

    def close(self):
        p = getattr(self, "proc", None)
        if not p:
            return
        # 서버와 그 단계 프로세스(서버의 자식)를 끝내요. 같은 그룹이라 일꾼 자신은 건드리지 않게 자식만 골라요.
        kids = []
        if os.name != "nt":
            try:
                out = subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout
                kids = [int(x) for x in out.split()]
            except Exception:
                kids = []
        for pid in [p.pid, *kids]:
            try:
                os.kill(pid, 15)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            p.wait(10)
        except Exception:
            p.kill()
        for pid in kids:
            try:
                os.kill(pid, 9)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def python_paths(self) -> list:
        return []

    def server_args(self) -> list:
        return list(self.extra_args)

    def body(self, text, voice=None, seed=0, ref=None, ref_text=None):
        b = {"input": text, "response_format": "wav", "language": self.language, "seed": int(seed or 0)}
        if ref:
            b["references"] = [{"audio_path": ref, **({"text": ref_text} if ref_text else {})}]
        elif voice:
            b["voice"] = voice
        return b

    def synth(self, text, voice=None, seed=0, ref=None, ref_text=None):
        import soundfile as sf

        req = urllib.request.Request(self.url + "/v1/audio/speech", data=json.dumps(self.body(text, voice, seed, ref, ref_text)).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            data = r.read()
        y, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        return np.asarray(y.mean(1), np.float32), int(sr)
