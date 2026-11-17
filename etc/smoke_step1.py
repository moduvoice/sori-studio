"""1단계 끝까지 시험: 허브를 띄우고 → Supertonic-3 을 라이선스 동의로 설치 → 한국어 소리 → 엔진을 죽여 자동 재시작 확인.

  cd hub && uv run python ../etc/smoke_step1.py [--home ../tmp/smoke-home] [--keep]
결과 소리: tmp/smoke-step1.wav. 홈 폴더를 지우지 않으면 두 번째부터는 설치를 건너뛰어요(이어받기·체크포인트 확인용).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=str(ROOT / "tmp" / "smoke-home"))
    ap.add_argument("--port", type=int, default=5199)
    a = ap.parse_args()
    env = dict(os.environ, SORI_HOME=a.home, PYTHONIOENCODING="utf-8")
    Path(a.home).mkdir(parents=True, exist_ok=True)
    hub = subprocess.Popen([sys.executable, "-m", "sori_hub", "serve", "--port", str(a.port)], env=env,
                           cwd=ROOT / "hub")
    base = f"http://127.0.0.1:{a.port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/hub/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        token = (Path(a.home) / "hub-token").read_text().strip()

        def call(method, path, body=None, raw=False, timeout=60):
            req = urllib.request.Request(base + path, method=method,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return (r.read(), dict(r.headers)) if raw else json.loads(r.read())

        hw = call("GET", "/hub/hardware")
        print("이 PC:", hw["platform"], hw["cores"], "코어", hw["ram_gb"], "GB", [g["name"] for g in hw["gpus"]])
        e = call("GET", "/hub/engines/supertonic-3")
        print("판정:", e["this_pc"], "| 설치:", e["install"]["status"])
        if e["install"]["status"] != "installed":
            p = call("GET", "/hub/engines/supertonic-3/plan")
            print(f"계획: 받을 양 {p['download_bytes'] / 1e6:.0f}MB, 단계 {p['steps']}, 라이선스 {p['license']['name']}")
            t0 = time.time()
            call("POST", "/hub/engines/supertonic-3/install", {"accept_license": p["license"]["id"]})
            last = None
            while True:
                time.sleep(2)
                e = call("GET", "/hub/engines/supertonic-3")
                ins = e["install"]
                pr = ins["progress"] or {}
                now = (ins["status"], pr.get("step"), int((pr.get("bytes_done") or 0) / 50e6))
                if now != last:
                    print(f"  {time.time() - t0:5.0f}s {ins['status']} {pr.get('step')} "
                          f"{(pr.get('bytes_done') or 0) / 1e6:.0f}/{(pr.get('bytes_total') or 0) / 1e6:.0f}MB")
                    last = now
                if ins["status"] not in ("installing",):
                    break
            print("설치 결과:", ins["status"], ins.get("error"), f"{time.time() - t0:.0f}s")
            if ins["status"] != "installed":
                print("\n".join(call("GET", "/hub/engines/supertonic-3/install/log")["log"][-30:]))
                return 1
            print("자가 시험:", json.dumps(ins["selftest"], ensure_ascii=False)[:300])
        print("모델:", [m["id"] for m in call("GET", "/v1/models")["data"]])
        text = "소리 스튜디오 허브가 처음으로 끝까지 소리를 냈어요. 반가워요!"
        t0 = time.time()
        wav, h = call("POST", "/v1/audio/speech", {"model": "supertonic-3", "input": text, "voice": "M1"}, raw=True,
                      timeout=300)
        out = ROOT / "tmp" / "smoke-step1.wav"
        out.write_bytes(wav)
        print(f"소리: {out} {len(wav) / 1e3:.0f}KB, 소리 {h.get('X-Sori-Audio-Seconds') or h.get('x-sori-audio-seconds')}초, "
              f"생성 {h.get('X-Sori-Gen-Seconds') or h.get('x-sori-gen-seconds')}초, 요청 전체 {time.time() - t0:.1f}초(첫 불러오기 포함)")
        # 자동 재시작: 일꾼을 죽이고 다시 부르면 다시 켜서 답해야 해요
        pid = call("GET", "/hub/engines/supertonic-3")["run"]["pid"]
        subprocess.run(["taskkill", "/F", "/PID", str(pid)] if os.name == "nt" else ["kill", "-9", str(pid)],
                       capture_output=True)
        time.sleep(1)
        t0 = time.time()
        wav2, _ = call("POST", "/v1/audio/speech", {"model": "supertonic-3", "input": "다시 켜졌어요."}, raw=True,
                       timeout=300)
        run = call("GET", "/hub/engines/supertonic-3")["run"]
        print(f"죽인 뒤 다시: {len(wav2) / 1e3:.0f}KB, {time.time() - t0:.1f}초, 상태 {run['state']}, "
              f"다시 켠 횟수 {run['restarts']}, pid {pid} → {run['pid']}")
        return 0
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode("utf-8", "replace"))
        return 1
    finally:
        hub.terminate()
        hub.wait(10)


if __name__ == "__main__":
    sys.exit(main())
