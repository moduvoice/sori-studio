"""엔진 일꾼 - 엔진의 uv 환경 파이썬으로 따로 떠요(4.8 겹 2).

허브가 `<env>/python -I worker_main.py --adapter <adapter.py> --weights <dir> [--threads N]` 로 띄우고,
환경 변수 SORI_WORKER_TOKEN 을 줘요. 표준 라이브러리 + 엔진 환경의 numpy 만 써요(허브 패키지를 import 하지 않음).

- 127.0.0.1 빈 포트에 HTTP 로 떠서 stdout 첫 줄에 `READY <포트>` 를 써요.
- stdin 이 닫히면(허브가 죽으면) 스스로 끝나요 - 고아 프로세스가 메모리를 붙잡지 않게.
- GET /health → {"ok", "busy", "loaded_s"} / POST /synth {"text","voice","seed"} → audio/wav(16비트)
"""
import argparse
import hmac
import importlib.util
import io
import json
import os
import sys
import threading
import time
import traceback
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def load_adapter(path, weights, threads, device):
    spec = importlib.util.spec_from_file_location("sori_engine_adapter", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return mod.Adapter(weights, threads, device=device)
    except TypeError:  # 판 1 어댑터(장치 인자 없음)
        return mod.Adapter(weights, threads)


def to_wav(samples, sr):
    import numpy as np

    x = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
    pcm = (x * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()
    token = os.environ.get("SORI_WORKER_TOKEN", "")

    t0 = time.time()
    adapter = load_adapter(a.adapter, a.weights, a.threads or None, a.device)
    import inspect

    params = inspect.signature(adapter.synth).parameters if hasattr(adapter, "synth") else {}
    takes_ref = "ref" in params
    takes_speed = "speed" in params
    adapter.load()
    loaded_s = round(time.time() - t0, 2)
    lock = threading.Lock()
    state = {"busy": False}

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            sys.stderr.write("[worker] " + fmt % args + "\n")

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            if not hmac.compare_digest(self.headers.get("X-Sori-Worker-Token") or "", token):
                self._send(403, {"error": "forbidden"})
                return False
            return True

        def do_GET(self):
            if not self._authed():
                return
            if self.path == "/health":
                self._send(200, {"ok": True, "busy": state["busy"], "loaded_s": loaded_s, "pid": os.getpid()})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return
            if self.path != "/synth":
                return self._send(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                text = str(req.get("text") or "").strip()
                if not text:
                    return self._send(400, {"error": "empty text"})
                with lock:  # 엔진은 한 번에 한 줄(묶음은 다음 단계)
                    state["busy"] = True
                    try:
                        t = time.time()
                        kw = {"voice": req.get("voice"), "seed": int(req.get("seed") or 0)}
                        if takes_ref and req.get("ref"):
                            kw.update(ref=req["ref"], ref_text=req.get("ref_text"))
                        if takes_speed and req.get("speed"):
                            kw["speed"] = float(req["speed"])
                        wav, sr = adapter.synth(text, **kw)
                        took = time.time() - t
                    finally:
                        state["busy"] = False
                body = to_wav(wav, sr)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Sori-Gen-Seconds", f"{took:.3f}")
                self.send_header("X-Sori-Audio-Seconds", f"{len(wav) / sr:.3f}")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                traceback.print_exc()
                msg = f"{type(e).__name__}: {e}"
                kind = "oom" if "out of memory" in msg.lower() or isinstance(e, MemoryError) else "engine"
                self._send(500, {"error": msg, "kind": kind})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True

    def watch_parent():
        try:
            while sys.stdin.read(1):
                pass
        except Exception:
            pass
        close = getattr(adapter, "close", None)  # 엔진이 띄운 서버 등을 먼저 정리(os._exit 는 atexit 를 거치지 않아요)
        if close:
            try:
                close()
            except Exception:
                pass
        os._exit(0)

    threading.Thread(target=watch_parent, daemon=True).start()
    print(f"READY {srv.server_address[1]}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
