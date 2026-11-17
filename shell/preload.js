// 화면에 window.sori 를 넘겨요. 토큰은 main 이 허브 주소(127.0.0.1:포트)일 때만 줘요.
const { contextBridge, ipcRenderer } = require("electron");

const info = ipcRenderer.sendSync("sori:info");

contextBridge.exposeInMainWorld("sori", {
  desktop: true,
  platform: info.platform,
  token: info.token,
  openExternal: (url) => ipcRenderer.send("sori:open-external", url),
  installWsl: info.platform === "win32" ? () => ipcRenderer.invoke("sori:install-wsl") : undefined,
});

// 시작 화면·복구 모드(file://)에서만 쓰는 것
if (location.protocol === "file:" && location.pathname.endsWith("/startup.html")) {
  contextBridge.exposeInMainWorld("soriShell", {
    onStage: (fn) => ipcRenderer.on("sori:stage", (_e, d) => fn(d)),
    onReset: (fn) => ipcRenderer.on("sori:reset", (_e, d) => fn(d)),
    recoveryInfo: () => ipcRenderer.invoke("sori:recovery-info"),
    retry: () => ipcRenderer.invoke("sori:retry"),
    openLogs: () => ipcRenderer.invoke("sori:open-logs"),
    fixEnv: () => ipcRenderer.invoke("sori:fix-env"),
    report: () => ipcRenderer.invoke("sori:report"),
    lang: info.lang,
  });
}

// 화면 테마가 바뀌면 창 제목 줄(창 단추 자리) 색도 맞춰요
window.addEventListener("DOMContentLoaded", () => {
  const send = () => ipcRenderer.send("sori:theme", document.documentElement.dataset.theme || "light");
  new MutationObserver(send).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  send();
});
