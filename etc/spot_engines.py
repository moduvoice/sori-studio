"""스팟(Windows·리눅스)에서 엔진을 차례로 진짜로 설치·시험해요 - 사용자 PC 에서는 돌리지 않아요(사용자 2026-11-17).

  cd hub && uv run python ../etc/spot_engines.py --home C:\\sori\\home --out C:\\sori\\out supertonic-3 kitten-tts-2-mini qwen3-tts voxcpm2
허브를 새 홈으로 띄우고 → 엔진마다 계획 → 라이선스 동의로 설치 → 자가 시험 → 한국어 문장(짧은·긴 글) 만들기 →
설치 시간·받은 양·디스크·불러오기·RTF·메모리(GPU 는 nvidia-smi)를 report.json 에, 소리는 out/<엔진>/ 에 남겨요.
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
SHORT = "안녕하세요. 소리 스튜디오에서 만든 한국어 목소리예요. 오늘 날씨는 맑고 기온은 영상 십이 도예요."
LONG = ("옛날 어느 작은 마을에 늘 웃는 할머니가 살았어요. 할머니는 아침마다 마당을 쓸고, 이웃에게 따뜻한 차를 나눠 주었어요. "
        "어느 겨울, 눈이 많이 와서 길이 막히자 마을 사람들은 할머니 집에 모여 함께 겨울을 났어요. "
        "봄이 오자 사람들은 그 겨울을 오래 기억했어요. 서로를 돕는 마음이 마을을 지켜 준다는 것을요. "
        "그 뒤로 마을에는 해마다 첫눈이 오는 날, 모두가 모여 차를 나누는 풍습이 생겼어요.")


def gpu_mem():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=5150)
    ap.add_argument("engines", nargs="+")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SORI_HOME=a.home, PYTHONIOENCODING="utf-8")
    log = open(out / "hub.log", "a", encoding="utf-8")
    hub = subprocess.Popen([sys.executable, "-m", "sori_hub", "serve", "--port", str(a.port)], env=env, cwd=ROOT / "hub",
                           stdout=log, stderr=log)
    report = {"engines": {}, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        base = None
        for _ in range(120):  # 허브가 실제로 뜬 포트는 hub.json 에(쓰이고 있으면 다음 빈 포트로 가요)
            try:
                port = json.loads((Path(a.home) / "hub.json").read_text())["port"]
                base = f"http://127.0.0.1:{port}"
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

        report["hardware"] = call("GET", "/hub/hardware")
        for eid in a.engines:
            rec = {"id": eid}
            report["engines"][eid] = rec
            d = out / eid
            d.mkdir(exist_ok=True)
            try:
                e = call("GET", f"/hub/engines/{eid}")
                rec["verdict"] = e["this_pc"]
                p = call("GET", f"/hub/engines/{eid}/plan")
                rec["plan"] = {k: p[k] for k in ("download_bytes", "env_bytes_estimate", "runtime", "device", "est_minutes")}
                print(f"[{eid}] 판정 {e['this_pc']['verdict']} · 장치 {p['device']} · 받을 양 {(p['download_bytes'] + p['env_bytes_estimate']) / 1e9:.2f} GB", flush=True)
                t0 = time.time()
                call("POST", f"/hub/engines/{eid}/install", {"accept_license": e["license"]["id"]})
                last = None
                while True:
                    time.sleep(3)
                    e = call("GET", f"/hub/engines/{eid}")
                    ins = e["install"]
                    step = (ins.get("progress") or {}).get("step")
                    if step != last:
                        print(f"  {time.time() - t0:5.0f}s {ins['status']} {step}", flush=True)
                        last = step
                    if ins["status"] != "installing":
                        break
                    if time.time() - t0 > 3600:
                        raise RuntimeError("설치가 1시간을 넘었어요")
                rec["install_s"] = round(time.time() - t0)
                rec["install"] = {k: ins.get(k) for k in ("status", "error", "selftest")}
                rec["disk"] = call("GET", f"/hub/engines/{eid}/disk")
                if ins["status"] != "installed":
                    rec["install_log"] = call("GET", f"/hub/engines/{eid}/install/log")["log"][-60:]
                    print(f"  실패: {ins.get('error')}", flush=True)
                    continue
                print(f"  설치 {rec['install_s']}s · 디스크 env {rec['disk']['env'] / 1e9:.2f} GB + 모델 {rec['disk']['weights'] / 1e9:.2f} GB · 자가 시험 RTF {ins['selftest'].get('rtf')}", flush=True)
                for i in range(3):
                    try:
                        w, _ = call("GET", f"/hub/engines/{eid}/selftest/{i}.wav", raw=True)
                        (d / f"selftest-{i}.wav").write_bytes(w)
                    except Exception:
                        pass
                g0 = gpu_mem()
                voices = call("GET", f"/v1/audio/voices?model={eid}")["voices"]
                runs = []
                for name, text in (("short", SHORT), ("long", LONG)):
                    for v in voices[:2]:
                        t1 = time.time()
                        wav, h = call("POST", "/v1/audio/speech", {"model": eid, "input": text, "voice": v["id"]}, raw=True, timeout=1800)
                        f = d / f"{name}-{v['id']}.wav"
                        f.write_bytes(wav)
                        runs.append({"text": name, "voice": v["id"], "wall_s": round(time.time() - t1, 2),
                                     "gen_s": float(h.get("X-Sori-Gen-Seconds") or h.get("x-sori-gen-seconds") or 0),
                                     "audio_s": float(h.get("X-Sori-Audio-Seconds") or h.get("x-sori-audio-seconds") or 0)})
                        print(f"  {name} {v['id']}: 소리 {runs[-1]['audio_s']:.1f}s / 생성 {runs[-1]['gen_s']:.1f}s / 요청 {runs[-1]['wall_s']:.1f}s", flush=True)
                rec["runs"] = runs
                info = call("GET", f"/hub/engines/{eid}")["run"]
                rec["rss_bytes"] = info.get("rss_bytes")
                rec["gpu_mem_mb"] = {"before": g0, "after": gpu_mem()}
                rec["events"] = info.get("events")
                call("POST", f"/hub/engines/{eid}/stop")
            except urllib.error.HTTPError as ex:
                rec["error"] = f"HTTP {ex.code} {ex.read().decode('utf-8', 'replace')[:500]}"
                print("  오류:", rec["error"], flush=True)
            except Exception as ex:  # 다음 엔진은 계속
                rec["error"] = repr(ex)
                print("  오류:", rec["error"], flush=True)
            (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        hub.terminate()
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
