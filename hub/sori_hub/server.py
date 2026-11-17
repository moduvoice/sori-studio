"""허브 서버 - 화면(UI)과 공통 로컬 API(4.9)가 같은 주소를 써요.

보안(4.9·10절)
- 127.0.0.1 에만 열고, Host 머리가 허용 목록에 있어야 해요(DNS 재바인딩 막기). CORS 는 열지 않아요.
- 토큰 둘:
  - 화면 토큰(hub-token): 화면·껍데기용. /hub/*(설치·지우기 포함)와 /v1/* 모두.
  - API 토큰(api-token): 다른 앱용. 설정에서 "로컬 API" 를 켰을 때만, /v1/* 만(설치와 지우기는 API 로 열지 않아요).
- 토큰 없이 되는 것: /hub/health 와 화면 파일(/, /assets/*).
"""
import collections
import hmac
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import __version__, catalog, hardware, installer, longtext, paths, quality, recommend, wsl
from .engines import EngineError, Manager

DEFAULT_PORT = 5150
SETTINGS_DEFAULTS = {"theme": "dark", "font_scale": 100, "wizard_done": False, "api_enabled": False, "language": "system"}
SETTINGS_KEYS = {"theme": ("system", "light", "dark"), "font_scale": range(90, 131), "wizard_done": (True, False),
                 "api_enabled": (True, False), "last_screen": None, "language": ("system", "ko", "en")}


def _token_file(name: str) -> Path:
    return paths.home() / name


def load_token(name: str = "hub-token", rotate: bool = False) -> str:
    f = _token_file(name)
    if f.exists() and not rotate:
        t = f.read_text(encoding="utf-8").strip()
        if t:
            return t
    t = secrets.token_urlsafe(32)
    f.write_text(t, encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass
    return t


def ui_dist() -> Path:
    import os

    return Path(os.environ.get("SORI_UI") or paths.REPO / "ui" / "dist")


class Hub:
    def __init__(self, port: int):
        self.port = port
        self.recipes = catalog.load_all()
        self.manager = Manager(self.recipes)
        self.installers = {eid: installer.Installer(r, self.selftest) for eid, r in self.recipes.items()}
        self._hw = None
        self._hw_lock = threading.Lock()
        self._disk: dict[str, tuple[float, int]] = {}
        self.calls: collections.deque = collections.deque(maxlen=50)  # 다른 앱이 부른 기록(설정 > 로컬 API)

    def hw(self, refresh: bool = False) -> dict:
        with self._hw_lock:
            if self._hw is None or refresh:
                self._hw = hardware.detect()
            return self._hw

    def disk_bytes(self, eid: str) -> int:
        """엔진이 차지한 용량(30초 캐시 - 파일을 다 세는 일이라 화면 갱신마다 하지 않아요)."""
        hit = self._disk.get(eid)
        if hit and time.time() - hit[0] < 30 and not self.installers[eid].running:
            return hit[1]
        d = installer.disk_usage(self.recipes[eid])
        n = d["env"] + d["weights"]
        self._disk[eid] = (time.time(), n)
        return n

    def selftest(self, eid: str) -> dict:
        """자가 시험(4.4): 한국어 3문장이 소리로 나와야 설치됨."""
        r = self.recipes[eid]
        w = self.manager.get(eid)
        out = []
        try:
            for i, text in enumerate(r.get("selftest") or ["안녕하세요."]):
                vs = catalog.voices(r)
                wav, meta = quality.synth_checked(w, r, text, r.get("default_voice") or (vs[0]["id"] if vs else None), seed=i)
                if meta["audio_s"] < 0.3 or len(wav) < 2000:
                    raise installer.InstallError("selftest", f"{i + 1}번째 문장의 소리가 비었어요", "selftest")
                out.append({"text": text, **meta})
                (paths.engine_dir(eid) / f"selftest-{i}.wav").write_bytes(wav)
        except EngineError as e:
            raise installer.InstallError("selftest", f"자가 시험에서 엔진이 실패했어요: {e.message}", "selftest")
        finally:
            w.stop()
        audio = sum(x["audio_s"] for x in out)
        gen = sum(x["gen_s"] for x in out)
        return {"lines": out, "rtf": round(gen / audio, 3) if audio else None, "load_s": w.loaded_s,
                "at": installer.now()}

    def engine_view(self, eid: str) -> dict:
        r = self.recipes[eid]
        st = installer.read_state(eid)
        ins = self.installers[eid]
        v = catalog.public(r)
        v["this_pc"] = hardware.verdict(r, self.hw())
        dev = "cuda" if v["this_pc"].get("device") == "cuda" else "cpu"
        v["download_bytes"] = v["weights_bytes"] + catalog.env_bytes(r, dev)
        status = "installing" if ins.running else installer.install_status(r, st)
        v["install"] = {
            "status": status,
            "done": st.get("done", []),
            "error": st.get("error"),
            "consent": st.get("consent"),
            "selftest": st.get("selftest"),
            "installed_at": st.get("installed_at"),
            "progress": {k: ins.progress[k] for k in ("step", "bytes_done", "bytes_total")} if ins.running else None,
        }
        v["disk_bytes"] = self.disk_bytes(eid) if status != "none" else 0
        v["run"] = self.manager.get(eid).info()
        return v


# ---------- 요청 모양 ----------

class InstallReq(BaseModel):
    accept_license: str = Field(..., description="동의한 라이선스 id(레시피의 license.id 와 같아야 해요)")


class SpeechReq(BaseModel):
    """OpenAI /v1/audio/speech 호환. model = 엔진 id."""
    model: str
    input: str = Field(..., max_length=20000)
    voice: str | None = None
    response_format: str = "wav"
    speed: float | None = None
    seed: int = 0


class ModelsDirReq(BaseModel):
    path: str


def _err(code: int, kind: str, message: str):
    raise HTTPException(code, {"kind": kind, "message": message})


def create_app(port: int = DEFAULT_PORT, token: str | None = None, allowed_hosts: set[str] | None = None) -> FastAPI:
    token = token or load_token()
    hub = Hub(port)
    hosts = allowed_hosts or {f"127.0.0.1:{port}", f"localhost:{port}"}

    @asynccontextmanager
    async def lifespan(_app):
        hub.manager.start_watchdog()
        yield
        hub.manager.shutdown()

    app = FastAPI(title="Sori Studio hub", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.hub = hub

    def api_token() -> str | None:
        return load_token("api-token") if paths.settings().get("api_enabled") else None

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").lower()
        if host not in hosts:
            return JSONResponse({"error": {"kind": "host", "message": "허용하지 않은 Host 예요"}}, status_code=403)
        path = request.url.path
        is_api = path.startswith("/v1/")
        if (path.startswith("/hub/") and path != "/hub/health") or is_api:
            auth = request.headers.get("authorization", "")
            got = auth[7:] if auth.lower().startswith("bearer ") else request.headers.get("x-sori-token", "")
            ui_ok = bool(got) and hmac.compare_digest(got, token)
            at = api_token() if is_api else None
            api_ok = bool(got and at) and hmac.compare_digest(got, at)
            if not (ui_ok or api_ok):
                if is_api:
                    hub.calls.append({"at": time.time(), "method": request.method, "path": path, "status": 401,
                                      "reason": "토큰 없음" if not got else "토큰이 맞지 않음(로컬 API 가 꺼져 있을 수도 있어요)"})
                return JSONResponse({"error": {"kind": "auth", "message": "토큰이 필요해요"}}, status_code=401)
            t0 = time.time()
            resp = await call_next(request)
            if api_ok and not ui_ok:
                hub.calls.append({"at": t0, "method": request.method, "path": path, "status": resp.status_code,
                                  "ms": round((time.time() - t0) * 1000)})
        else:
            resp = await call_next(request)
        if not path.startswith("/assets/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def engine_or_404(eid: str) -> dict:
        if eid not in hub.recipes:
            _err(404, "not_found", f"엔진 {eid} 가 카탈로그에 없어요")
        return hub.recipes[eid]

    # --- 허브 ---
    @app.get("/hub/health")
    def health():
        return {"app": "sori-studio-hub", "version": __version__, "ok": True}

    @app.get("/hub/hardware")
    def hw(refresh: bool = False):
        return hub.hw(refresh)

    @app.get("/hub/drives")
    def drives():
        return {"drives": hardware.drives(), "current": str(paths.models_dir())}

    @app.get("/hub/settings")
    def get_settings():
        return {**SETTINGS_DEFAULTS, **paths.settings(), "models_dir": str(paths.models_dir()),
                "version": __version__, "home": str(paths.home())}

    @app.patch("/hub/settings")
    def patch_settings(body: dict):
        s = paths.settings()
        for k, v in body.items():
            if k not in SETTINGS_KEYS:
                _err(400, "bad_request", f"{k} 는 바꿀 수 없는 칸이에요")
            allowed = SETTINGS_KEYS[k]
            if allowed is not None and v not in allowed:
                _err(400, "bad_request", f"{k} 값이 맞지 않아요")
            s[k] = v
        paths.save_settings(s)
        return get_settings()

    @app.put("/hub/models-dir")
    def set_models_dir(req: ModelsDirReq):
        p = Path(req.path).expanduser()
        if not p.is_absolute():
            _err(400, "path", "전체 경로를 넣어 주세요(예: D:\\SoriStudio\\models)")
        if any(installer.read_state(e).get("install", "none") != "none" or hub.installers[e].running
               for e in hub.recipes):
            _err(409, "has_engines", "이미 받은 엔진이 있어서 지금은 폴더를 바꿀 수 없어요. 폴더 옮기기는 다음 판에 와요.")
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".sori-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as e:
            _err(400, "path", f"이 폴더에는 쓸 수 없어요({e.strerror or e})")
        s = paths.settings()
        s["models_dir"] = str(p.resolve())
        paths.save_settings(s)
        hub._hw = None
        hub._disk.clear()
        return get_settings()

    @app.get("/hub/wsl")
    def wsl_status():
        """WSL2 상태(리눅스 전용 엔진 안내용): not_windows · none · needs_setup · no_distro · ready"""
        return wsl.status()

    @app.get("/hub/recommend")
    def rec(use: str, direct: bool = False):
        try:
            return recommend.recommend(use, hub.recipes, hub.hw(), direct_only=direct)
        except KeyError:
            _err(400, "bad_request", "쓰임새는 narration·acting·clone·light 중 하나예요")

    @app.get("/hub/engines")
    def engines():
        return {"engines": [hub.engine_view(eid) for eid in hub.recipes]}

    @app.get("/hub/engines/{eid}")
    def engine(eid: str):
        engine_or_404(eid)
        return hub.engine_view(eid)

    @app.get("/hub/engines/{eid}/license")
    def license_text(eid: str):
        return catalog.license_text(engine_or_404(eid))

    @app.get("/hub/engines/{eid}/plan")
    def plan(eid: str):
        return installer.plan(engine_or_404(eid))

    @app.post("/hub/engines/{eid}/install")
    def install(eid: str, req: InstallReq):
        engine_or_404(eid)
        try:
            hub.installers[eid].start(req.accept_license)
        except installer.InstallError as e:
            _err(400, e.kind, e.message)
        hub._disk.pop(eid, None)
        return hub.engine_view(eid)

    @app.post("/hub/engines/{eid}/install/stop")
    def install_stop(eid: str):
        engine_or_404(eid)
        hub.installers[eid].stop()
        return {"ok": True}

    @app.get("/hub/engines/{eid}/install/log")
    def install_log(eid: str):
        engine_or_404(eid)
        from .engines import mask_paths

        return {"log": [mask_paths(x) for x in hub.installers[eid].progress["log"]]}

    @app.get("/hub/engines/{eid}/selftest/{i}.wav")
    def selftest_wav(eid: str, i: int):
        engine_or_404(eid)
        f = paths.engine_dir(eid) / f"selftest-{i}.wav"
        if i not in (0, 1, 2) or not f.exists():
            _err(404, "not_found", "자가 시험 소리가 없어요")
        return FileResponse(f, media_type="audio/wav")

    @app.post("/hub/engines/{eid}/start")
    def start(eid: str):
        engine_or_404(eid)
        if installer.read_state(eid).get("install") != "installed":
            _err(409, "not_installed", "설치가 끝난 엔진만 켤 수 있어요")
        w = hub.manager.get(eid)
        try:
            w.reset() if w.state == "dead" else w.start()
        except EngineError as e:
            _err(409, e.kind, e.message)
        return w.info()

    @app.post("/hub/engines/{eid}/stop")
    def stop(eid: str):
        engine_or_404(eid)
        hub.manager.get(eid).stop()
        return hub.manager.get(eid).info()

    @app.get("/hub/engines/{eid}/log")
    def engine_log(eid: str):
        engine_or_404(eid)
        return {"log": hub.manager.get(eid).log_tail()}

    @app.get("/hub/engines/{eid}/disk")
    def disk(eid: str):
        return installer.disk_usage(engine_or_404(eid))

    @app.delete("/hub/engines/{eid}")
    def remove(eid: str, part: str = "all"):
        r = engine_or_404(eid)
        if part not in ("all", "env", "weights"):
            _err(400, "bad_request", "part 는 all·env·weights 중 하나예요")
        if hub.installers[eid].running:
            _err(409, "busy", "받는 중에는 지울 수 없어요. 먼저 멈춰 주세요.")
        hub.manager.get(eid).stop()
        freed = installer.remove(r, part)
        hub._disk.pop(eid, None)
        return {"freed_bytes": freed}

    # --- 로컬 API 설정 ---
    @app.get("/hub/api")
    def api_info():
        on = bool(paths.settings().get("api_enabled"))
        return {"enabled": on, "base_url": f"http://127.0.0.1:{port}/v1",
                "token": load_token("api-token") if on else None, "calls": list(hub.calls)[::-1]}

    @app.post("/hub/api/token/rotate")
    def api_rotate():
        load_token("api-token", rotate=True)
        return api_info()

    # --- 공통 로컬 API(OpenAI 호환) ---
    def installed(eid: str) -> bool:
        return installer.read_state(eid).get("install") == "installed"

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [
            {"id": eid, "object": "model", "owned_by": "sori-studio", "role": r["role"]}
            for eid, r in hub.recipes.items() if installed(eid)]}

    @app.get("/v1/audio/voices")
    def voices(model: str):
        r = engine_or_404(model)
        vs = catalog.voices(r)
        return {"model": model, "voices": vs, "default": r.get("default_voice") or (vs[0]["id"] if vs else None)}

    @app.post("/v1/audio/speech")
    def speech(req: SpeechReq):
        r = engine_or_404(req.model)
        if not installed(req.model):
            _err(409, "not_installed", f"{r['name']} 가 설치되지 않았어요")
        if req.response_format != "wav":
            _err(400, "format", "지금은 wav 만 돼요(mp3 는 다음 판)")
        text = req.input.strip()
        if not text:
            _err(400, "empty", "읽을 글이 비었어요")
        chunks = longtext.split(text, int(r.get("max_chars") or 4096))
        ids = {v["id"] for v in catalog.voices(r)}
        if req.voice and ids and req.voice not in ids:
            _err(400, "voice", f"목소리 {req.voice} 가 이 엔진에 없어요")
        try:
            vs = catalog.voices(r)
            default = r.get("default_voice") or (vs[0]["id"] if vs else None)
            w = hub.manager.get(req.model)
            outs = [quality.synth_checked(w, r, c, req.voice or default, req.seed, speed=req.speed) for c in chunks]
            wav = outs[0][0] if len(outs) == 1 else longtext.join_wavs([o[0] for o in outs])
            meta = {"gen_s": sum(o[1]["gen_s"] for o in outs), "audio_s": sum(o[1]["audio_s"] for o in outs) + 0.25 * (len(outs) - 1),
                    "retries": sum(o[1].get("retries", 0) for o in outs),
                    "suspect": next((o[1]["suspect"] for o in outs if o[1].get("suspect")), None)}
        except EngineError as e:
            _err(503 if e.kind in ("dead", "load_timeout", "load_failed", "not_installed") else 500, e.kind, e.message)
        return Response(wav, media_type="audio/wav", headers={
            "X-Sori-Gen-Seconds": f"{meta['gen_s']:.3f}", "X-Sori-Audio-Seconds": f"{meta['audio_s']:.3f}",
            "X-Sori-Retries": str(meta.get("retries", 0)), "X-Sori-Suspect": meta.get("suspect") or ""})

    # --- 화면 파일 ---
    @app.get("/{rest:path}")
    def ui(rest: str):
        root = ui_dist().resolve()
        if rest.startswith(("hub/", "v1/")):
            _err(404, "not_found", "없는 주소예요")
        f = (root / rest).resolve() if rest else root / "index.html"
        if rest and f.is_file() and root in f.parents:
            return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable"}
                                if rest.startswith("assets/") else None)
        index = root / "index.html"
        if not index.exists():
            return JSONResponse({"error": {"kind": "no_ui", "message": "화면 파일이 없어요(ui 에서 npm run build)"}},
                                status_code=404)
        return FileResponse(index)

    return app
