"""허브 1단계 시험 - 카탈로그·판정·보안 장치·가중치 검증(엔진 설치 없이 돌아요)."""
import hashlib
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from sori_hub import catalog, hardware, installer, paths
from sori_hub.server import create_app

PORT = 5150
TOKEN = "t" * 32


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SORI_HOME", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def client():
    app = create_app(PORT, token=TOKEN)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


# ---------- 카탈로그 ----------

def test_supertonic_recipe_loads():
    r = catalog.load_all()["supertonic-3"]
    assert r["license"]["id"] == "openrail-m"
    assert r["devices"] == {"cpu": "native", "nvidia": "no", "mac": "unverified"}
    files = r["weights"]["files"]
    assert len(files) == 16 and all(len(f["sha256"]) == 64 for f in files)
    pub = catalog.public(r)
    assert "weights" not in pub and "_dir" not in pub and pub["download_bytes"] > 300e6


def test_recipe_rejects_path_escape(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "recipe.yaml").write_text(
        "id: bad\nname: b\nrecipe_version: 1\nrole: tts\ndevices: {}\nmeasured: {}\n"
        "license: {id: x, name: x, url: x, summary: []}\npython: '3.12'\npackages: {}\nadapter: a.py\n"
        "weights: {sources: [], files: [{path: ../evil, size: 1, sha256: x}]}\n", encoding="utf-8")
    with pytest.raises(catalog.RecipeError):
        catalog.load_recipe(d)


# ---------- 이 PC 판정 ----------

def _r(**kw):
    base = {"devices": {"cpu": "no", "nvidia": "ok", "mac": "unverified"}, "measured": {"gpu_mem_gb": 6.6},
            "packages": {"win-x64": "r.txt"}}
    base.update(kw)
    return base


def _hw(vram=None, ram=16, mac=False):
    return {"platform": "mac-arm64" if mac else "win-x64", "apple_silicon": mac, "ram_gb": ram,
            "gpus": [{"vram_gb": vram}] if vram else []}


@pytest.mark.parametrize("vram,want", [(12, "gpu_ok"), (7.0, "tight"), (4, "no"), (None, "no")])
def test_verdict_gpu(vram, want):
    assert hardware.verdict(_r(), _hw(vram))["verdict"] == want


def test_verdict_cpu_native_and_mac_and_unmeasured():
    st = catalog.load_all()["supertonic-3"]
    assert hardware.verdict(st, _hw(None, ram=8))["verdict"] == "cpu_ok"
    assert hardware.verdict(st, _hw(None, ram=1.6))["verdict"] == "tight"
    assert hardware.verdict(st, _hw(None, mac=True))["verdict"] == "unverified"
    assert hardware.verdict(_r(measured={}), _hw(24))["verdict"] == "unverified"
    slow = _r(devices={"cpu": "ok", "nvidia": "ok"})
    assert hardware.verdict(slow, _hw(4))["verdict"] == "cpu_slow"


# ---------- 보안 장치 ----------

def test_health_open_but_rest_needs_token(client):
    assert client.get("/hub/health").json()["app"] == "sori-studio-hub"
    assert client.get("/hub/engines").status_code == 401
    assert client.get("/hub/engines", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/hub/engines", headers=auth()).status_code == 200
    assert client.get("/hub/engines", headers={"X-Sori-Token": TOKEN}).status_code == 200


def test_host_check_blocks_dns_rebinding(client):
    r = client.get("/hub/engines", headers={**auth(), "Host": f"evil.example:{PORT}"})
    assert r.status_code == 403
    assert client.get("/hub/health", headers={"Host": "evil.example"}).status_code == 403


def test_no_cors_headers(client):
    r = client.options("/v1/audio/speech", headers={"Origin": "https://evil.example",
                                                     "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_install_requires_license_consent(client):
    r = client.post("/hub/engines/supertonic-3/install", json={"accept_license": "mit"}, headers=auth())
    assert r.status_code == 400 and r.json()["detail"]["kind"] == "license"


def test_engine_view_and_speech_not_installed(client):
    v = client.get("/hub/engines/supertonic-3", headers=auth()).json()
    assert v["install"]["status"] == "none" and v["run"]["state"] == "stopped"
    assert "this_pc" in v and v["license"]["name"] == "BigScience Open RAIL-M"
    assert client.get("/v1/models", headers=auth()).json()["data"] == []
    r = client.post("/v1/audio/speech", json={"model": "supertonic-3", "input": "안녕"}, headers=auth())
    assert r.status_code == 409
    assert client.get("/hub/engines/nope", headers=auth()).status_code == 404


def test_plan(client):
    p = client.get("/hub/engines/supertonic-3/plan", headers=auth()).json()
    assert p["steps"] == ["env", "packages", "weights", "selftest"]
    assert p["download_bytes"] > 300e6 and p["license"]["id"] == "openrail-m"


# ---------- 가중치 받기: 이어받기·검증·다음 출처 ----------

class _Src(BaseHTTPRequestHandler):
    files: dict = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        repo = self.path.split("/resolve/")[0].strip("/")
        name = self.path.split("/", 5)[-1]
        data = self.files.get((repo, name))
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        rng = self.headers.get("Range")
        start = int(rng.split("=")[1].split("-")[0]) if rng else 0
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(data) - start))
        self.end_headers()
        self.wfile.write(data[start:])


def test_weights_resume_verify_and_fallback(monkeypatch, tmp_path):
    good = b"weights!" * 1000
    _Src.files = {("bad/repo", "w/a.bin"): b"x" * len(good), ("good/repo", "w/a.bin"): good}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Src)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    real = installer.urllib.request.Request
    monkeypatch.setattr(installer.urllib.request, "Request",
                        lambda url, headers=None: real(url.replace("https://huggingface.co", base), headers=headers or {}))
    recipe = {"id": "fake", "weights": {
        "sources": [{"repo": "bad/repo", "revision": "r"}, {"repo": "good/repo", "revision": "r"}],
        "files": [{"path": "w/a.bin", "size": len(good), "sha256": hashlib.sha256(good).hexdigest()}]}}
    # 반쯤 받은 조각이 있으면 이어받아요
    part = paths.engine_dir("fake") / "weights" / "w" / "a.bin.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(good[:100])
    logs = []
    installer.step_weights(recipe, logs.append, lambda n: None, threading.Event())
    assert (paths.engine_dir("fake") / "weights" / "w" / "a.bin").read_bytes() == good
    assert any("bad/repo" in m for m in logs)  # 첫 출처는 검증에서 떨어지고 다음 출처로
    srv.shutdown()


def test_remove_parts(tmp_path):
    r = {"id": "fake2"}
    d = paths.engine_dir("fake2")
    (d / "env").mkdir(parents=True)
    (d / "env" / "x").write_bytes(b"1" * 10)
    (d / "weights").mkdir()
    (d / "weights" / "y").write_bytes(b"2" * 20)
    installer.write_state("fake2", {"install": "installed", "done": ["env", "packages", "weights", "selftest"]})
    assert installer.remove(r, "env") == 10
    st = installer.read_state("fake2")
    assert st["done"] == ["weights"] and st["install"] == "paused"
    assert (d / "weights" / "y").exists()


# ---------- 일꾼: 불러오기 실패는 두 번 만에 "죽음", 정상 일꾼은 소리를 돌려줌 ----------

def _fake_engine(tmp_path, monkeypatch, body):
    import sys

    from sori_hub import engines

    d = tmp_path / "eng"
    d.mkdir()
    (d / "adapter.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(paths, "env_python", lambda eid: __import__("pathlib").Path(sys.executable))
    monkeypatch.setattr(engines, "BACKOFF", (0, 0, 0))
    r = {"id": "fake", "_dir": str(d), "adapter": "adapter.py", "measured": {"load_s": 1, "rtf_cpu": 1}}
    paths.engine_dir("fake").mkdir(parents=True, exist_ok=True)
    return engines.Worker(r)


def test_worker_load_failure_goes_dead(tmp_path, monkeypatch):
    from sori_hub.engines import EngineError

    w = _fake_engine(tmp_path, monkeypatch, "class Adapter:\n    def __init__(s, w, t): pass\n"
                                             "    def load(s): raise RuntimeError('weights missing')\n")
    with pytest.raises(EngineError) as e:
        w.synth("안녕", None)
    assert w.state == "dead" and w.error["kind"] == "load_failed"
    assert "weights missing" in w.error["message"]


def test_worker_synth_ok(tmp_path, monkeypatch):
    import wave

    w = _fake_engine(tmp_path, monkeypatch, "import numpy as np\nclass Adapter:\n    def __init__(s, w, t): pass\n"
                                             "    def load(s): pass\n"
                                             "    def synth(s, text, voice=None, seed=0): return np.zeros(8000, 'float32'), 16000\n")
    try:
        wav, meta = w.synth("안녕", None)
        with wave.open(io.BytesIO(wav)) as f:
            assert f.getframerate() == 16000 and f.getnframes() == 8000
        assert meta["audio_s"] == 0.5 and w.state == "ready"
    finally:
        w.stop()


# ---------- 2단계: 설정·API 토큰·추천·화면 파일 ----------

def test_api_token_only_when_enabled_and_only_v1(client):
    from sori_hub.server import load_token

    api = load_token("api-token")
    h = {"Authorization": f"Bearer {api}"}
    assert client.get("/v1/models", headers=h).status_code == 401  # 꺼져 있음
    calls = client.get("/hub/api", headers=auth()).json()["calls"]
    assert calls and calls[0]["status"] == 401
    client.patch("/hub/settings", json={"api_enabled": True}, headers=auth())
    assert client.get("/v1/models", headers=h).status_code == 200
    assert client.get("/hub/engines", headers=h).status_code == 401  # 설치·지우기 쪽은 API 토큰으로 안 됨
    info = client.get("/hub/api", headers=auth()).json()
    assert info["enabled"] and info["calls"][0]["status"] == 200
    new = client.post("/hub/api/token/rotate", headers=auth()).json()["token"]
    assert new != api and client.get("/v1/models", headers=h).status_code == 401


def test_settings_validation(client):
    assert client.patch("/hub/settings", json={"theme": "dark", "font_scale": 110}, headers=auth()).json()["theme"] == "dark"
    assert client.patch("/hub/settings", json={"theme": "pink"}, headers=auth()).status_code == 400
    assert client.patch("/hub/settings", json={"models_dir": "C:/x"}, headers=auth()).status_code == 400


def test_models_dir(client, tmp_path):
    r = client.put("/hub/models-dir", json={"path": str(tmp_path / "m")}, headers=auth())
    assert r.status_code == 200 and r.json()["models_dir"].endswith("m")
    assert client.put("/hub/models-dir", json={"path": "relative/x"}, headers=auth()).status_code == 400
    installer.write_state("supertonic-3", {"install": "installed", "done": []})
    assert client.put("/hub/models-dir", json={"path": str(tmp_path / "n")}, headers=auth()).status_code == 409


def test_recommend_light_and_coming_later(client):
    r = client.get("/hub/recommend?use=narration", headers=auth()).json()
    # GPU 없는 시험 PC: Qwen3-TTS 는 "CPU 로 느리게" 라서 CPU 엔진이 먼저(카탈로그에 없는 CosyVoice3 는 다음 판)
    # 이제 MVP 엔진 넷이 모두 카탈로그에 있어요(CosyVoice3 는 GPU 전용이라 GPU 없는 시험 PC 에서는 not_here)
    assert r["recommended"] == "supertonic-3" and "qwen3-tts" in r["alternatives"] and r["coming_later"] == []
    assert "cosyvoice3" in r["not_here"]
    r = client.get("/hub/recommend?use=clone", headers=auth()).json()
    # GPU 없는 시험 PC: Confucius4·CosyVoice3·dots.tts 는 GPU 전용(not_here), VoxCPM2 는 CPU 로 느리게
    assert r["recommended"] == "voxcpm2" and "confucius4" in r["not_here"] and r["coming_later"] == []
    r = client.get("/hub/recommend?use=light", headers=auth()).json()
    assert r["recommended"] == "supertonic-3" and r["alternatives"] == ["kitten-tts-2-mini"]
    assert client.get("/hub/recommend?use=x", headers=auth()).status_code == 400


def test_license_text_restrictions(client):
    t = client.get("/hub/engines/supertonic-3/license", headers=auth()).json()
    assert t["restrictions"].startswith("Attachment A") and "deepfakes" in t["restrictions"]


def test_ui_files_without_token(client, tmp_path, monkeypatch):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>sori</html>", encoding="utf-8")
    (d / "assets" / "a.js").write_text("x", encoding="utf-8")
    monkeypatch.setenv("SORI_UI", str(d))
    assert "sori" in client.get("/").text
    assert "sori" in client.get("/models/whatever").text  # 화면 길은 index.html
    r = client.get("/assets/a.js")
    assert r.text == "x" and "immutable" in r.headers["cache-control"]
    assert client.get("/assets/../../secret").status_code in (200, 404)  # 폴더 밖은 index.html 로만
    assert "sori" in client.get("/assets/../../secret").text or client.get("/assets/../../secret").status_code == 404
    assert client.get("/hub/nope").status_code == 401  # API 쪽은 여전히 토큰


def test_weights_network_retry(monkeypatch):
    """잠깐 끊긴 것은 스스로 이어받아요(사용자가 누르지 않아도)."""
    import urllib.error

    good = b"abc" * 100
    calls = {"n": 0}

    def flaky(url, dst, size, progress, cancel):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("network unreachable")
        dst.write_bytes(good)
        progress(len(good))

    monkeypatch.setattr(installer, "_download", flaky)
    monkeypatch.setattr(installer, "NET_RETRY", (0, 0, 0))
    recipe = {"id": "fake3", "weights": {"sources": [{"repo": "a/b", "revision": "r"}],
              "files": [{"path": "x.bin", "size": len(good), "sha256": hashlib.sha256(good).hexdigest()}]}}
    seen = []
    installer.step_weights(recipe, seen.append, lambda n: None, threading.Event())
    assert calls["n"] == 3 and any("이어서 받아요" in m for m in seen)


def test_longtext_split_and_join():
    import io
    import wave

    from sori_hub import longtext

    t = "첫 문장이에요. " * 40
    parts = longtext.split(t, 100)
    assert len(parts) > 1 and all(len(p) <= 100 for p in parts)
    assert "".join(parts).replace(" ", "") == t.replace(" ", "")
    one = "가" * 250
    assert all(len(p) <= 100 for p in longtext.split(one, 100))

    def wav(n):
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(1000); w.writeframes(b"\x01\x00" * n)
        return b.getvalue()

    with wave.open(io.BytesIO(longtext.join_wavs([wav(100), wav(50)], gap_s=0.1))) as w:
        assert w.getnframes() == 100 + 100 + 50


def test_verdict_driver_too_old():
    r = {"devices": {"cpu": "ok", "nvidia": "ok"}, "measured": {"gpu_mem_gb": 6}, "packages": {"win-x64": {}},
         "requires": {"nvidia_driver": 580}}
    hw = {"platform": "win-x64", "apple_silicon": False, "ram_gb": 32, "gpus": [{"vram_gb": 24, "driver": "552.12"}]}
    v = hardware.verdict(r, hw)
    assert v["verdict"] == "cpu_slow" and v["reason"] == "driver_old"
    hw["gpus"][0]["driver"] = "596.86"
    assert hardware.verdict(r, hw)["verdict"] == "gpu_ok"


def test_quality_length_check_and_retry():
    from sori_hub import quality

    r = {"measured": {"syll_rate": 5.0}}
    t = "이 문장이 또렷하게 들리면 설치가 끝난 거예요."  # 19음절 → 예상 3.8초
    assert quality.judge(r, t, 8.5) == "too_long"  # VoxCPM2 자가 시험의 실제 환각 소리 길이
    assert quality.judge(r, t, 4.0) is None and quality.judge(r, t, 1.0) == "too_short"
    assert quality.judge({"measured": {}}, t, 99) is None  # 말 빠르기 모르면 검사 안 함

    class W:
        def __init__(self):
            self.lens = [8.5, 8.0, 4.1]

        def synth(self, text, voice, seed, speed=None):
            return b"x", {"audio_s": self.lens.pop(0), "gen_s": 1.0}

    wav, meta = quality.synth_checked(W(), r, t, "bora")
    assert meta["retries"] == 2 and meta["suspect"] is None and meta["audio_s"] == 4.1

    class Bad(W):
        def __init__(self):
            self.lens = [9.0, 8.0, 12.0]

    _, meta = quality.synth_checked(Bad(), r, t, "bora")
    assert meta["suspect"] == "too_long" and meta["audio_s"] == 8.0  # 다 의심이면 예상에 가장 가까운 것


def test_code_step_verifies_and_strips_top_folder(tmp_path, monkeypatch):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Repo-abc123/pkg/__init__.py", "x = 1\n")
    data = buf.getvalue()
    monkeypatch.setattr(installer, "_download", lambda url, dst, size, progress, cancel: dst.write_bytes(data))
    r = {"id": "fakec", "code": [{"url": "https://example/x.zip", "sha256": hashlib.sha256(data).hexdigest(), "dir": "repo"}]}
    installer.step_code(r, lambda m: None, lambda n: None, threading.Event())
    assert (paths.engine_dir("fakec") / "code" / "repo" / "pkg" / "__init__.py").exists()
    bad = {"id": "fakec2", "code": [{"url": "https://example/x.zip", "sha256": "0" * 64, "dir": "repo"}]}
    with pytest.raises(installer.InstallError):
        installer.step_code(bad, lambda m: None, lambda n: None, threading.Event())


def test_proc_run_cancel():
    import sys as _s

    from sori_hub import proc

    ev = threading.Event()
    proc.set_cancel(ev)
    threading.Timer(1.0, ev.set).start()
    t0 = __import__("time").time()
    with pytest.raises(proc.Cancelled):
        proc.run([_s.executable, "-c", "import time; time.sleep(30)"])
    assert __import__("time").time() - t0 < 10
    proc.set_cancel(None)
    code, out = proc.run([_s.executable, "-c", "print('ok')"])
    assert code == 0 and b"ok" in out


def test_recipe_rejects_bad_code_dir(tmp_path):
    d = tmp_path / "bad2"
    d.mkdir()
    (d / "recipe.yaml").write_text(
        "id: bad2\nname: b\nrecipe_version: 1\nrole: tts\ndevices: {}\nmeasured: {}\n"
        "license: {id: x, name: x, url: x, summary: []}\npython: '3.12'\npackages: {}\nadapter: a.py\n"
        "weights: {sources: [], files: []}\ncode: [{url: x, sha256: y, dir: ../up}]\n", encoding="utf-8")
    with pytest.raises(catalog.RecipeError):
        catalog.load_recipe(d)


def test_verdict_small_gpu_untested():
    # 32GB 에서만 확인한 서버형 엔진: 작은 GPU 는 "미검증", 모자라면 "안 됨", 32GB 는 "잘"
    r = _r(measured={"gpu_mem_gb": 6, "gpu_tested_gb": 32})
    assert hardware.verdict(r, _hw(8)) == {"verdict": "unverified", "reason": "gpu_small_untested", "device": "cuda", "need_gb": 32}
    assert hardware.verdict(r, _hw(4))["verdict"] == "no"
    assert hardware.verdict(r, _hw(32))["verdict"] == "gpu_ok"
    assert hardware.verdict(r, _hw(31.5))["verdict"] == "gpu_ok"  # 실제 32GB 카드가 보고하는 값


def test_recommend_direct_only_skips_wsl(monkeypatch):
    from sori_hub import recommend as rc
    recs = {"confucius4": {"devices": {"cpu": "no", "nvidia": "ok"}, "measured": {"gpu_mem_gb": 10},
                           "packages": {"linux-x64": "r.txt"}, "runtime": {"win-x64": "wsl"}},
            "voxcpm2": {"devices": {"cpu": "ok", "nvidia": "ok"}, "measured": {"gpu_mem_gb": 8.4},
                        "packages": {"win-x64": "r.txt"}}}
    hw = _hw(32)
    assert rc.recommend("clone", recs, hw)["recommended"] == "confucius4"
    r = rc.recommend("clone", recs, hw, direct_only=True)
    assert r["recommended"] == "voxcpm2" and "confucius4" not in r["alternatives"]
