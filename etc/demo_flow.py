"""공개용 스크린샷·녹화 - 깨끗한 Windows 스팟에서 처음 쓰는 사람처럼 눌러요(사용자 2026-11-17 "윈도우 스팟으로 스크린샷").

  cd hub && uv run python ../etc/demo_flow.py --home C:\\sori\\demo --out C:\\sori\\demo-out
1) 새 홈으로 허브를 켜고 마법사: 가볍고 빠르게 → Supertonic-3 받기 → 들어 보기 → 소리 만들기(녹화 + 장면별 캡처)
2) Qwen3-TTS 를 API 로 받아 두고 소리 만들기·모델·내 모델·상세를 캡처(한국어·영어·어두운 화면)
녹화(webm)에는 소리가 없어서, 재생을 누른 시각(events.json)과 그 소리(wav)를 남겨 나중에 합쳐요.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEMO_TEXT = "안녕하세요. 소리 스튜디오는 내 PC 에서 돌아가는 무료 한국어 음성 합성 앱이에요. 글을 넣고 만들기를 누르면 바로 들을 수 있어요."
PORT = 5150


def api(method, path, token, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return json.loads(data) if r.headers.get("content-type", "").startswith("application/json") else data


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
        api("PATCH", "/hub/settings", token, {"language": "ko"})
        run(token, out)
    finally:
        hub.terminate()


def run(token, out):
    events = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        init = f"window.sori = {{desktop: false, token: '{token}', platform: 'win32'}};"

        # ---------- 1) 녹화: 마법사 → 소리 만들기 ----------
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(out / "video"),
                            record_video_size={"width": 1440, "height": 900}, accept_downloads=True)
        ctx.add_init_script(init)
        page = ctx.new_page()
        page.on("console", lambda m: m.type == "error" and print("console error:", m.text[:300], flush=True))
        t0 = time.time()
        mark = lambda name, **kw: events.append({"t": round(time.time() - t0, 2), "name": name, **kw})  # noqa: E731
        shot = lambda name: page.screenshot(path=str(out / f"{name}.png"))  # noqa: E731

        page.goto(f"http://127.0.0.1:{PORT}/#/wizard")
        page.wait_for_selector("text=추천 모델", timeout=60000)
        page.wait_for_timeout(2500)
        shot("01-wizard-gpu")
        mark("wizard")
        page.get_by_role("radio", name="가볍고 빠르게").click()
        page.wait_for_selector("text=Supertonic-3")
        page.wait_for_timeout(2000)
        shot("02-wizard-light")
        page.get_by_role("button", name="다음").click()
        page.wait_for_selector("text=사용 조건")
        page.wait_for_timeout(2500)
        shot("03-download")
        page.get_by_text("사용 조건을 확인했어요").click()
        page.wait_for_timeout(800)
        page.get_by_role("button", name="받기 시작").click()
        mark("install_start")
        page.wait_for_timeout(6000)
        shot("04-downloading")
        page.wait_for_selector("text=들어 보세요", timeout=900000)
        mark("install_end")
        page.wait_for_timeout(2500)
        shot("05-listen")
        for i in range(2):
            page.get_by_role("button", name="듣기").nth(i).click()
            mark("play", file=f"selftest-{i}.wav")
            page.wait_for_timeout(4500)
        page.get_by_role("button", name="소리 만들기 시작").click()
        try:
            page.wait_for_selector("textarea", timeout=20000)
        except Exception:
            shot("error")
            print("url", page.url, page.content()[:3000], flush=True)
            raise
        page.wait_for_timeout(1500)
        box = page.locator("textarea")
        box.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.type(DEMO_TEXT, delay=25)
        page.wait_for_timeout(800)
        shot("06-make")
        page.get_by_role("button", name="만들기", exact=True).click()
        page.wait_for_selector("text=만든 소리", timeout=300000)
        page.wait_for_timeout(1500)
        with page.expect_download() as dl:
            page.get_by_text("파일로 저장").click()
        dl.value.save_as(str(out / "made-supertonic.wav"))
        page.locator(".card").filter(has_text="만든 소리").get_by_role("button", name="듣기").first.click()
        mark("play", file="made-supertonic.wav")
        page.wait_for_timeout(1000)
        shot("07-made")
        page.wait_for_timeout(9000)
        mark("end")
        ctx.close()  # 녹화 파일이 여기서 써져요
        vids = sorted((out / "video").glob("*.webm"))
        if vids:
            vids[-1].replace(out / "demo-raw.webm")
        for i in range(3):
            (out / f"selftest-{i}.wav").write_bytes(api("GET", f"/hub/engines/supertonic-3/selftest/{i}.wav", token))
        (out / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")

        # ---------- 2) Qwen3-TTS 받기(화면 밖) ----------
        api("POST", "/hub/engines/qwen3-tts/install", token, {"accept_license": "apache-2.0"})
        for _ in range(240):
            e = api("GET", "/hub/engines/qwen3-tts", token)
            if e["install"]["status"] in ("installed", "failed"):
                break
            time.sleep(5)
        print("qwen3:", e["install"]["status"], flush=True)

        # ---------- 3) 캡처: 한국어·영어·어두운 화면 ----------
        def stills(lang, dark=False):
            api("PATCH", "/hub/settings", token, {"language": lang})
            c = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark" if dark else "light", accept_downloads=True)
            c.add_init_script(init)
            pg = c.new_page()
            sfx = f"-{lang}" + ("-dark" if dark else "")
            pg.goto(f"http://127.0.0.1:{PORT}/#/try/qwen3-tts")
            pg.wait_for_selector("textarea")
            pg.locator("textarea").click()
            pg.keyboard.press("Control+A")
            pg.keyboard.type(DEMO_TEXT)
            pg.get_by_role("button", name="만들기" if lang == "ko" else "Make", exact=True).click()
            pg.wait_for_selector("text=" + ("만든 소리" if lang == "ko" else "Your audio"), timeout=300000)
            pg.wait_for_timeout(1500)
            if lang == "ko" and not dark:
                with pg.expect_download() as dl2:
                    pg.get_by_text("파일로 저장").click()
                dl2.value.save_as(str(out / "made-qwen3.wav"))
            pg.screenshot(path=str(out / f"10-try-qwen3{sfx}.png"))
            for route, name in [("#/models", "11-models"), ("#/models/qwen3-tts", "12-detail-qwen3"),
                                ("#/models/cosyvoice3", "13-detail-wsl"), ("#/installed/engines", "14-my-models"),
                                ("#/settings/general", "15-settings")]:
                pg.goto(f"http://127.0.0.1:{PORT}/{route}")
                pg.wait_for_timeout(2000)
                pg.screenshot(path=str(out / f"{name}{sfx}.png"))
            c.close()

        stills("ko")
        stills("en")
        stills("ko", dark=True)
        api("PATCH", "/hub/settings", token, {"language": "system"})
        b.close()
    print("demo ok", flush=True)


if __name__ == "__main__":
    main()
