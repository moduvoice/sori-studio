// 앱 틀(design.md 3.2): 제목 줄 · 내비게이션 · 상태 줄.
// UX 리뷰(2026-11-17): 빠른 이동(Ctrl+K)·단축키 표시는 뺐고, 상태 줄은 받는 중이거나 문제가 있을 때만 보여요.
import { type ReactNode } from "react";
import { AudioLines, Box, Download, Settings as SettingsIcon } from "lucide-react";
import { t } from "../lib/i18n";
import { go, href, type Route } from "../lib/router";
import { useHub } from "../lib/store";
import { Banner } from "./ui";

export function Logo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <path d="M8 50 C19 40 25 27 32 12 C39 27 45 40 56 50" fill="none" stroke="var(--accent)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const NAV: { route: Route; icon: ReactNode; key: string; names: Route["name"][] }[] = [
  { route: { name: "try" }, icon: <AudioLines size={18} />, key: "nav.try", names: ["try"] },
  { route: { name: "models" }, icon: <Box size={18} />, key: "nav.models", names: ["models", "model"] },
  { route: { name: "installed", tab: "engines" }, icon: <Download size={18} />, key: "nav.installed", names: ["installed"] },
];

export function Shell({ route, children }: { route: Route; children: ReactNode }) {
  const { engines, up } = useHub();
  const desktop = Boolean(window.sori?.desktop);
  const installing = engines.find((e) => e.install.status === "installing");
  const dead = engines.some((e) => e.run.state === "dead" || e.install.status === "failed");

  return (
    <div className={`app ${desktop ? "" : "no-titlebar"}`}>
      {desktop ? (
        <header className="titlebar">
          <Logo size={16} />
          <span className="t-label">{t("app.name")}</span>
        </header>
      ) : (
        <div />
      )}
      <nav className="nav" aria-label={t("nav.label")}>
        <div className="nav-logo">
          <Logo />
          <span className="label">{t("app.name")}</span>
        </div>
        {NAV.map((n) => (
          <a key={n.key} className="nav-item" href={href(n.route)} aria-current={n.names.includes(route.name) ? "page" : undefined}>
            {n.icon}
            <span className="label">{t(n.key)}</span>
            {n.key === "nav.models" && installing && <span className="mark spinner" style={{ color: "var(--accent)" }} aria-label={t("install.status.installing")} />}
            {n.key === "nav.installed" && dead && <span className="mark dot bad" aria-label={t("status.problem")} />}
          </a>
        ))}
        <div className="nav-spacer" />
        <a className="nav-item" href={href({ name: "settings", section: "general" })} aria-current={route.name === "settings" ? "page" : undefined}>
          <SettingsIcon size={18} />
          <span className="label">{t("nav.settings")}</span>
        </a>
      </nav>
      <main className="main" id="main">
        {!up && (
          <div style={{ padding: "16px 32px 0" }}>
            {desktop ? (
              <Banner tone="warning" title={t("down.desktopTitle")} body={t("down.readonly")} />
            ) : (
              <Banner tone="danger" title={t("down.title")} body={`${t("down.body")} ${t("down.readonly")}`} />
            )}
          </div>
        )}
        {children}
      </main>
      <StatusBar />
    </div>
  );
}

// 받는 중이거나 모델에 문제가 있을 때만 한 줄(평소에는 비워 둬요)
function StatusBar() {
  const { engines } = useHub();
  const worst =
    engines.find((e) => e.run.state === "dead") ??
    engines.find((e) => e.run.state === "restarting" || e.run.state === "stalled");
  const installing = engines.find((e) => e.install.status === "installing");
  const p = installing?.install.progress;
  return (
    <footer className="statusbar" aria-label={t("status.label")}>
      {worst && (
        <button className={`sb-item ${worst.run.state === "dead" ? "bad" : "warn"}`} onClick={() => go({ name: "installed", tab: "engines" })}>
          {t(worst.run.state === "dead" ? "status.engineDead" : worst.run.state === "stalled" ? "status.engineStalled" : "status.engineRestarting", { name: worst.name })}
        </button>
      )}
      {installing && (
        <button className="sb-item num" onClick={() => go({ name: "model", id: installing.id })}>
          <span className="spinner" aria-hidden style={{ color: "var(--accent)" }} />
          {t("status.installing", { name: installing.name, pct: p && p.bytes_total ? Math.floor((p.bytes_done / p.bytes_total) * 100) : 0 })}
        </button>
      )}
    </footer>
  );
}
