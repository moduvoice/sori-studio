"""데모 영상 설명 목소리 만들기 - 스팟에서 우리 TTS(Qwen3-TTS 소희 · Supertonic-3)로 줄마다 wav 를 만들어요.

  cd hub && uv run python ../etc/narration.py --home C:\\sori\\narr --out C:\\sori\\narr-out
줄 글·장면 위치는 NARRATION(아래)이 정본이고 etc/narrate_video.py 가 같은 목록을 읽어요.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 5150
# (이름, 영상 장면, 글) - 장면은 narrate_video.py 가 영상 시각으로 바꿔요
NARRATION = [
    ("n1", "start", "소리 스튜디오는 내 PC 에서 돌아가는 무료 한국어 음성 합성 앱이에요."),
    ("n2", "choose", "무엇에 쓸지 고르면, 이 PC 에서 잘 돌아가는 모델을 추천해 줘요."),
    ("n3", "download", "사용 조건을 확인하고 받기를 누르면, 공식 출처에서 모델을 바로 받아요."),
    ("n4", "listen", "받기가 끝나면 한국어 세 문장을 바로 들려줘요."),
    ("n5", "make", "이제 읽을 글을 넣고, 만들기를 누르면 끝이에요."),
    ("n6", "end", "계정도 구독도 없이 모두 무료예요. 깃허브에서 소리 스튜디오를 찾아 주세요."),
]
VOICES = {"qwen3-tts": "sohee", "supertonic-3": "F1"}


def api(method, path, token, body=None, timeout=600):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return json.loads(data) if r.headers.get("content-type", "").startswith("application/json") else (data, {k.lower(): v for k, v in r.headers.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    home, out = Path(a.home), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SORI_HOME=str(home))
    hub = subprocess.Popen([sys.executable, "-m", "sori_hub", "serve", "--port", str(PORT)], env=env, cwd=ROOT / "hub",
                           stdout=open(out / "hub.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            if (home / "hub-token").exists():
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2)
                    break
                except Exception:
                    pass
            time.sleep(1)
        token = (home / "hub-token").read_text().strip()
        lic = {"qwen3-tts": "apache-2.0", "supertonic-3": "openrail-m"}
        for eid in VOICES:
            api("POST", f"/hub/engines/{eid}/install", token, {"accept_license": lic[eid]})
            for _ in range(240):
                st = api("GET", f"/hub/engines/{eid}", token)["install"]["status"]
                if st in ("installed", "failed"):
                    break
                time.sleep(5)
            print(eid, st, flush=True)
        report = []
        for eid, voice in VOICES.items():
            for name, scene, text in NARRATION:
                data, hdr = api("POST", "/v1/audio/speech", token, {"model": eid, "input": text, "voice": voice})
                f = out / f"{eid}-{name}.wav"
                f.write_bytes(data)
                report.append({"engine": eid, "name": name, "scene": scene, "text": text,
                               "retries": hdr.get("x-sori-retries"), "suspect": hdr.get("x-sori-suspect"),
                               "audio_s": hdr.get("x-sori-audio-seconds"), "gen_s": hdr.get("x-sori-gen-seconds")})
                print(eid, name, report[-1]["audio_s"], report[-1]["retries"], report[-1]["suspect"], flush=True)
        (out / "narration.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        hub.terminate()
    print("narration ok", flush=True)


if __name__ == "__main__":
    main()
