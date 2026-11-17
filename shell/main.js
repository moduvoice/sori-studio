// Sori Studio 데스크톱 껍데기 - 허브 서버를 켜고 지켜봐요(기능 설계 4.8 겹 1, 화면 설계 A1·A2).
//
// - 시작 화면: 파이썬 확인 → 서버 켜는 중 → 엔진 목록 읽는 중 → 준비. 단계마다 시간 한도, 실패하면 원인과 단추.
// - 이미 켜진 허브가 있으면 그쪽에 붙어요(한 컴퓨터에 허브는 하나).
// - 허브가 죽으면 다시 켜요(10분에 3번까지). 넘으면 복구 모드.
// - 토큰은 허브 화면(127.0.0.1:포트)에만 넘겨요. 다른 주소로는 창 안에서 가지 않고, 링크는 기본 브라우저로 열어요.
const { app, BrowserWindow, ipcMain, shell, nativeTheme } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");

const REPO = path.resolve(__dirname, "..");
const PORT = Number(process.env.SORI_PORT || 5150);
const STAGES = ["python", "server", "engines", "ready"];
const LIMIT_MS = { python: 5000, server: 40000, engines: 20000 };
const RESTART_LIMIT = 3;
const RESTART_WINDOW_MS = 10 * 60 * 1000;

// 화면 언어: 허브 설정의 language(system·ko·en), system 이면 OS 언어. 시작·복구 화면이 써요.
function uiLang() {
  let pref = "system";
  try {
    pref = JSON.parse(fs.readFileSync(path.join(hubHome(), "settings.json"), "utf-8")).language || "system";
  } catch {
    /* 설정 없음 */
  }
  const l = pref === "system" ? app.getLocale().slice(0, 2).toLowerCase() : pref;
  return l === "ko" ? "ko" : "en";
}

function hubHome() {
  if (process.env.SORI_HOME) return path.resolve(process.env.SORI_HOME);
  if (process.platform === "win32" && process.env.LOCALAPPDATA) return path.join(process.env.LOCALAPPDATA, "SoriStudio");
  return path.join(require("node:os").homedir(), ".sori-studio");
}

function hubPython() {
  if (process.env.SORI_HUB_PYTHON) return process.env.SORI_HUB_PYTHON;
  const venv = path.join(REPO, "hub", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return venv; // 개발판: hub 폴더의 uv 환경. 설치본은 함께 넣은 파이썬을 SORI_HUB_PYTHON 으로 가리켜요(7단계)
}

let win = null;
let hub = null; // 우리가 띄운 허브 프로세스
let port = PORT;
let token = "";
let restarts = [];
let quitting = false;
let lastFailure = null; // 복구 모드에 보여 줄 마지막 일
let lastHash = ""; // 허브가 다시 켜져도 보던 화면으로 돌아가요(리뷰 2026-11-17)
let healthTimer = null;
const logLines = [];

function logFile() {
  const d = path.join(hubHome(), "logs");
  fs.mkdirSync(d, { recursive: true });
  return path.join(d, "hub.log");
}
function log(line) {
  const s = `${new Date().toISOString()} ${line}`;
  logLines.push(s);
  if (logLines.length > 400) logLines.shift();
  try {
    fs.appendFileSync(logFile(), s + "\n");
  } catch {}
}

function send(ch, data) {
  if (win && !win.isDestroyed()) win.webContents.send(ch, data);
}
function stage(name, state, extra = {}) {
  send("sori:stage", { name, state, ...extra });
}

function get(pathname, withToken = false, timeout = 3000) {
  return new Promise((resolve, reject) => {
    const req = http.get(
      { host: "127.0.0.1", port, path: pathname, timeout, headers: { Host: `127.0.0.1:${port}`, ...(withToken ? { Authorization: `Bearer ${token}` } : {}) } },
      (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => (res.statusCode === 200 ? resolve(body) : reject(new Error(`HTTP ${res.statusCode}`))));
      },
    );
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
  });
}

async function healthy() {
  try {
    return JSON.parse(await get("/hub/health")).app === "sori-studio-hub";
  } catch {
    return false;
  }
}

function readHubJson() {
  try {
    return JSON.parse(fs.readFileSync(path.join(hubHome(), "hub.json"), "utf-8"));
  } catch {
    return null;
  }
}

function classify(text) {
  const t = text.toLowerCase();
  if (t.includes("access is denied") || t.includes("permissionerror") || t.includes("winerror 5")) return "blocked";
  if (t.includes("modulenotfounderror") || t.includes("importerror") || t.includes("no module named")) return "broken";
  if (t.includes("no space") || t.includes("errno 28") || t.includes("winerror 112")) return "disk";
  if (t.includes("SORI_NO_PORT")) return "port"; // 허브가 찍는 코드(문구는 번역될 수 있어요)
  return "unknown";
}

function waitFor(fn, ms, every = 300) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const tick = async () => {
      if (await fn()) return resolve(true);
      if (Date.now() - t0 > ms) return resolve(false);
      setTimeout(tick, every);
    };
    tick();
  });
}

function onApp() {
  try {
    return win && isHubUrl(win.webContents.getURL());
  } catch {
    return false;
  }
}

async function boot() {
  stopHealth();
  send("sori:reset", { restarting: restarts.length, limit: RESTART_LIMIT });
  // 이미 켜진 허브가 있으면 붙어요
  const existing = readHubJson();
  if (existing && existing.port) {
    port = existing.port;
    if (await healthy()) {
      log(`이미 켜진 허브에 붙어요: ${port} (pid ${existing.pid})`);
      return afterServer(true);
    }
    port = PORT;
  }

  // 1 파이썬 확인
  stage("python", "run");
  const py = hubPython();
  if (!fs.existsSync(py)) {
    return fail("python", "missing", `허브 파이썬을 찾지 못했어요: ${py}`);
  }
  stage("python", "done");

  // 2 서버 켜는 중
  stage("server", "run");
  let errText = "";
  hub = spawn(py, ["-m", "sori_hub", "serve", "--port", String(PORT)], {
    cwd: path.join(REPO, "hub"),
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    windowsHide: true,
  });
  const me = hub;
  hub.stdout.on("data", (d) => {
    const s = d.toString();
    log(s.trim());
    const m = s.match(/127\.0\.0\.1:(\d+)/);
    if (m) port = Number(m[1]);
  });
  hub.stderr.on("data", (d) => {
    errText += d.toString();
    log(d.toString().trim());
  });
  hub.on("exit", (code) => {
    log(`허브가 끝났어요(코드 ${code})`);
    if (me !== hub) return;
    hub = null;
    if (quitting) return;
    if (code === 0 && /SORI_ALREADY_RUNNING/.test(logLines.slice(-5).join("\n"))) return; // 다른 허브에 붙음
    onHubDown(classify(errText), errText.trim().split("\n").slice(-1)[0] || `코드 ${code}`);
  });

  const slow = setTimeout(() => stage("server", "slow"), LIMIT_MS.server / 2);
  const ok = await waitFor(async () => {
    const j = readHubJson();
    if (j && j.port) port = j.port;
    return healthy();
  }, LIMIT_MS.server);
  clearTimeout(slow);
  if (!ok) {
    if (hub) hub.kill();
    return fail("server", classify(errText), errText.trim().split("\n").slice(-1)[0] || "시간 안에 켜지지 않았어요");
  }
  return afterServer(false);
}

async function afterServer(attached) {
  stage("python", "done");
  stage("server", "done", { attached });
  // 3 엔진 목록 읽는 중(토큰이 맞는지도 여기서 확인)
  stage("engines", "run");
  try {
    token = fs.readFileSync(path.join(hubHome(), "hub-token"), "utf-8").trim();
    await get("/hub/engines", true, LIMIT_MS.engines);
  } catch (e) {
    return fail("engines", "unknown", String(e.message || e));
  }
  stage("engines", "done");
  stage("ready", "done");
  lastFailure = null;
  if (!onApp()) {
    // 처음 켤 때·포트가 바뀌었을 때만 화면을 새로 열어요. 이미 앱 화면이면 화면이 스스로 다시 붙어요.
    setTimeout(() => win && win.loadURL(`http://127.0.0.1:${port}/${lastHash}`), 250);
  }
  startHealth();
}

function fail(stageName, kind, detail) {
  log(`[${stageName}] ${kind}: ${detail}`);
  lastFailure = { stage: stageName, kind, detail, at: new Date().toISOString() };
  stage(stageName, "fail", { kind, detail });
}

function onHubDown(kind, detail) {
  stopHealth();
  const now = Date.now();
  restarts = restarts.filter((t) => now - t < RESTART_WINDOW_MS);
  lastFailure = { stage: "running", kind, detail, at: new Date().toISOString() };
  if (restarts.length >= RESTART_LIMIT) {
    log("10분에 3번 넘게 멈춰 복구 모드로 가요");
    return showRecovery();
  }
  restarts.push(now);
  log(`허브를 다시 켜요 (${restarts.length} / ${RESTART_LIMIT})`);
  if (onApp()) {
    // 앱 화면은 그대로 두고(화면 위 띠가 "다시 켜는 중"을 알려요) 뒤에서 다시 켜요
    try {
      lastHash = new URL(win.webContents.getURL()).hash;
    } catch {}
    boot();
  } else {
    showStartup().then(boot);
  }
}

function startHealth() {
  stopHealth();
  let fails = 0;
  healthTimer = setInterval(async () => {
    if (await healthy()) {
      fails = 0;
      return;
    }
    fails += 1;
    if (fails >= 3 && !hub) onHubDown("unknown", "붙어 있던 허브가 답하지 않아요"); // 남의 허브에 붙었을 때
    if (fails >= 3 && hub) {
      hub.kill();
    }
  }, 5000);
}
function stopHealth() {
  if (healthTimer) clearInterval(healthTimer);
  healthTimer = null;
}

function showStartup() {
  return win.loadFile(path.join(__dirname, "startup.html"));
}
function showRecovery() {
  return win.loadFile(path.join(__dirname, "startup.html"), { hash: "recovery" });
}

function isHubUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" && u.hostname === "127.0.0.1" && Number(u.port) === port;
  } catch {
    return false;
  }
}

function createWindow() {
  const dark = nativeTheme.shouldUseDarkColors;
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1120,
    minHeight: 720,
    title: "Sori Studio",
    backgroundColor: dark ? "#101216" : "#F6F5F1",
    titleBarStyle: "hidden",
    titleBarOverlay: { color: dark ? "#101216" : "#F6F5F1", symbolColor: dark ? "#ECEEF2" : "#16181D", height: 36 },
    icon: path.join(__dirname, "icon.png"),
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !isHubUrl(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  const startupUrl = require("node:url").pathToFileURL(path.join(__dirname, "startup.html")).href;
  win.webContents.on("will-navigate", (e, url) => {
    // 창 안에서는 허브 화면과 시작 화면(startup.html)만 - 다른 file: 주소는 막아요(그 페이지에 soriShell 이 열리지 않게)
    if (!isHubUrl(url) && url.split("#")[0] !== startupUrl) {
      e.preventDefault();
      if (/^https?:\/\//.test(url)) shell.openExternal(url);
    }
  });
  win.webContents.on("render-process-gone", () => win.reload());
  showStartup().then(boot);
}

// ---------- 화면과 주고받기 ----------
ipcMain.on("sori:info", (e) => {
  const url = e.senderFrame ? e.senderFrame.url : "";
  // 토큰은 허브 화면에만
  e.returnValue = { desktop: true, platform: process.platform, token: isHubUrl(url) ? token : "", lang: uiLang() };
});
ipcMain.on("sori:open-external", (_e, url) => {
  if (typeof url === "string" && /^https?:\/\//.test(url)) shell.openExternal(url);
});
ipcMain.on("sori:theme", (_e, theme) => {
  if (!win || process.platform === "darwin") return;
  const dark = theme === "dark";
  try {
    win.setTitleBarOverlay({ color: dark ? "#101216" : "#F6F5F1", symbolColor: dark ? "#ECEEF2" : "#16181D" });
    win.setBackgroundColor(dark ? "#101216" : "#F6F5F1");
  } catch {}
});
ipcMain.handle("sori:recovery-info", () => ({ failure: lastFailure, log: logLines.slice(-200), home: hubHome(), restarts: restarts.length }));
ipcMain.handle("sori:retry", () => {
  restarts = [];
  showStartup().then(boot);
});
ipcMain.handle("sori:install-wsl", (e) => {
  // WSL2 켜기: 관리자 권한 창(UAC)으로 wsl --install --no-distribution. 끝나면 PC 를 다시 시작해야 해요.
  if (process.platform !== "win32" || !isHubUrl(e.senderFrame ? e.senderFrame.url : "")) return { ok: false, code: -1, out: "" };
  return new Promise((resolve) => {
    // 관리자 창(UAC)으로 wsl-install.ps1 - wsl --install 이 안 되는 Windows(Server·오래된 10)는 기능 켜기 + 공식 MSI(해시 확인)
    const file = path.join(__dirname, "wsl-install.ps1").replace(/'/g, "''");
    const ps = `$p = Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','"${file}"' -Verb RunAs -Wait -PassThru; exit $p.ExitCode`;
    const p = spawn("powershell.exe", ["-NoProfile", "-Command", ps], { windowsHide: true });
    let out = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (out += d));
    p.on("error", (err) => resolve({ ok: false, code: -1, out: String(err) }));
    p.on("exit", (code) => {
      log(`WSL2 켜기 끝(코드 ${code})`);
      resolve({ ok: code === 0, code, out: out.trim().slice(-500) });
    });
  });
});
ipcMain.handle("sori:open-logs", () => shell.openPath(path.join(hubHome(), "logs")));
ipcMain.handle("sori:report", () => {
  // 문제 알리기: 미리 채운 GitHub 이슈(로그는 사용자가 보고 직접 붙여요 - 자동으로 보내지 않아요)
  // 이슈는 누구나 읽게 영어로(한국어로 더 써도 돼요)
  const body = encodeURIComponent(`What happened?\n\nLast stage: ${lastFailure ? lastFailure.stage + " · " + lastFailure.detail : "-"}\nOS: ${process.platform} ${require("node:os").release()}\n\n(Paste the log from "Show log")`);
  shell.openExternal(`https://github.com/moduvoice/sori-studio/issues/new?title=${encodeURIComponent("App won't start")}&body=${body}`);
});
ipcMain.handle("sori:fix-env", () => {
  // 환경 고치기: 허브 파이썬 환경을 잠금 파일대로 다시 맞춰요(프로젝트·받은 모델은 그대로).
  // 개발판은 uv sync, 설치본은 함께 넣은 잠금 파일로(7단계).
  return new Promise((resolve) => {
    const p = spawn("uv", ["sync", "--frozen"], { cwd: path.join(REPO, "hub"), windowsHide: true, shell: process.platform === "win32" });
    let out = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (out += d));
    p.on("error", (e) => resolve({ ok: false, out: String(e) }));
    p.on("exit", (code) => {
      log(`환경 고치기 끝(코드 ${code})`);
      resolve({ ok: code === 0, out: out.trim().split("\n").slice(-20).join("\n") });
    });
  });
});

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(createWindow);
  app.on("before-quit", () => {
    quitting = true;
    stopHealth();
    if (hub) hub.kill(); // 허브가 끝나면 엔진 일꾼도 함께 끝나요(허브의 Windows Job)
  });
  app.on("window-all-closed", () => app.quit());
}
