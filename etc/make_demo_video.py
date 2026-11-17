"""demo_flow.py 녹화(소리 없음) → 1분 안팎 영상. 받는 동안은 빨리 감고, 재생을 누른 시각에 그 소리를 얹고,
설명 목소리(etc/narration.py 로 만든 wav)를 장면마다 넣어요. 설명이 앱 소리와 겹치면 그 장면을 잠깐 멈춰 둬요.

  python etc/make_demo_video.py tmp/demo-out [--narr tmp/narr-out --engine qwen3-tts] [--out 이름.mp4]
"""
import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from narration import NARRATION  # noqa: E402

FAST_SECONDS = 4.0  # 받는 동안(수십 초)을 이 길이로
LEAD = 4.0          # 받기 시작 뒤 몇 초는 그대로(진행 막대가 움직이는 것)
GAP = 0.35          # 설명과 앱 소리 사이 틈


def dur(f: Path) -> float:
    with wave.open(str(f)) as w:
        return w.getnframes() / w.getframerate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("demo")
    ap.add_argument("--narr")
    ap.add_argument("--engine", default="qwen3-tts")
    ap.add_argument("--out", default="sori-studio-demo.mp4")
    a = ap.parse_args()
    d = Path(a.demo)
    ev = json.loads((d / "events.json").read_text(encoding="utf-8"))
    t = {e["name"]: e["t"] for e in ev if e["name"] != "play"}
    plays = [e for e in ev if e["name"] == "play"]
    fa, fb, end = t["install_start"] + LEAD, t["install_end"], t["end"]
    k = FAST_SECONDS / max(1.0, fb - fa)

    def g(x):  # 녹화 시각 → 빨리 감은 영상 시각(멈춤 전)
        if x <= fa:
            return x
        if x <= fb:
            return fa + (x - fa) * k
        return fa + FAST_SECONDS + (x - fb)

    # 앱 소리(보호 구간) - 빨리 감은 시각
    prot = [(g(p["t"]), g(p["t"]) + dur(d / p["file"]), d / p["file"]) for p in plays]
    # 설명 줄 → 녹화 시각의 장면 위치
    scene_raw = {"start": 1.0, "choose": t["wizard"] - 0.4,  # 고르기 클릭은 wizard 표시 직후라 그 앞에서 멈춰요
                 "download": t["install_start"] - 3.4,
                 "listen": t["install_end"] + 0.3, "make": plays[1]["t"] + 6.5 if len(plays) > 1 else t["install_end"] + 10,
                 "end": end}
    narr = []
    if a.narr:
        for name, scene, _ in NARRATION:
            f = Path(a.narr) / f"{a.engine}-{name}.wav"
            narr.append({"raw": scene_raw[scene], "file": f, "dur": dur(f), "scene": scene})
    narr.sort(key=lambda n: n["raw"])

    # 멈춤 계산: 줄마다 (빨리 감은 시각의) 시작 = 장면 위치 또는 앞 소리가 끝난 뒤, 다음 앱 소리·다음 줄 전에 끝나야 해요
    shift = 0.0
    prev_end = 0.0  # 출력 시각
    for i, n in enumerate(narr):
        anchor_out = g(n["raw"]) + shift
        busy_until = max([prev_end] + [e + shift + GAP for s, e, _ in prot if s + shift <= anchor_out < e + shift + GAP])
        start = max(anchor_out, busy_until)
        nxt = [s + shift for s, _, _ in prot if s + shift > anchor_out]
        if i + 1 < len(narr):
            nxt.append(g(narr[i + 1]["raw"]) + shift)
        limit = min(nxt) if nxt else g(end) + shift
        if n["scene"] == "end":
            limit = max(limit, g(end) + shift)
        need = start + n["dur"] + GAP - limit + (1.2 if n["scene"] == "end" else 0)
        n["freeze"] = max(0.0, need)
        n["start"] = start
        shift += n["freeze"]
        prev_end = start + n["dur"] + GAP

    # 영상: 자를 곳 = 빨리 감기 경계 + 설명 장면(멈춤은 그 장면 첫 프레임을 늘려요)
    cuts = sorted({0.0, fa, fb, end, *[min(n["raw"], end) for n in narr]})
    freeze_at = {}
    for n in narr:
        freeze_at[min(n["raw"], end)] = freeze_at.get(min(n["raw"], end), 0) + n["freeze"]
    vparts, labels = [], []
    tail = freeze_at.get(end, 0)
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        if e - s < 0.02:
            continue
        sp = k if fa <= s < fb else 1.0
        pad = freeze_at.get(s, 0)
        f = f"[0:v]trim={s}:{e},setpts=(PTS-STARTPTS)*{sp}"
        if pad > 0:
            f += f",tpad=start_mode=clone:start_duration={pad:.3f}"
        if i == len(cuts) - 2 and tail > 0:
            f += f",tpad=stop_mode=clone:stop_duration={tail:.3f}"
        vparts.append(f + f"[v{i}]")
        labels.append(f"[v{i}]")
    vf = ";".join(vparts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=1:a=0,fps=30,format=yuv420p[v]"

    def out_time(raw):  # 녹화 시각 → 최종 시각(멈춤 포함)
        return g(raw) + sum(n["freeze"] for n in narr if n["raw"] <= raw and n["raw"] < end)

    total = g(end) + sum(n["freeze"] for n in narr)
    inputs = ["-i", str(d / "demo-raw.webm")]
    af, mix = [], []
    clips = [(out_time(p["t"]), d / p["file"], 1.0) for p in plays] + [(n["start"], n["file"], 1.0) for n in narr]
    for i, (at, f, vol) in enumerate(clips, start=1):
        inputs += ["-i", str(f)]
        ms = int(at * 1000)
        af.append(f"[{i}:a]aresample=48000,volume={vol},adelay=delays={ms}:all=1[a{i}]")
        mix.append(f"[a{i}]")
    af.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0,apad,atrim=0:{total}[a]")
    out = d / a.out
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", vf + ";" + ";".join(af),
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print(f"{out} · {total:.1f}초 (받기 {fb - fa:.0f}초 → {FAST_SECONDS:.0f}초, 설명 {len(narr)}줄, 멈춤 {sum(n['freeze'] for n in narr):.1f}초)")
    for n in narr:
        print(f"  {n['scene']:8} 시작 {n['start']:5.1f}초 · 길이 {n['dur']:.1f}초 · 멈춤 {n['freeze']:.1f}초")


if __name__ == "__main__":
    main()
