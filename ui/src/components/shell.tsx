// 앱 틀(rebuild-2026-11.md 3-1): 왼쪽 아이콘 막대 · 위 머리줄 · 화면.
// UX 리뷰(2026-11-17): 빠른 이동(Ctrl+K)·단축키 표시는 뺐고, 상태 알림은 받는 중이거나 문제가 있을 때만 머리줄 오른쪽에 보여요.
import { type ReactNode } from "react";
import { AudioLines, Box, ChevronRight, HardDriveDownload, House, Settings as SettingsIcon } from "lucide-react";
import { t } from "../lib/i18n";
import { go, href, type Route } from "../lib/router";
import { useHub } from "../lib/store";
import { Banner } from "./ui";

export function Logo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs>
        <linearGradient id="sori-logo" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" style={{ stopColor: "var(--accent)" }} />
          <stop offset="1" style={{ stopColor: "var(--accent-2)" }} />
        </linearGradient>
      </defs>
      <path d="M8 50 C19 40 25 27 32 12 C39 27 45 40 56 50" fill="none" stroke="url(#sori-logo)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

type NavItem = { route: Route; icon: (size: number) => ReactNode; key: string; names: Route["name"][] };
const NAV: NavItem[] = [
  { route: { name: "home" }, icon: (s) => <House size={s} />, key: "nav.home", names: ["home"] },
  { route: { name: "try" }, icon: (s) => <AudioLines size={s} />, key: "nav.try", names: ["try"] },
  { route: { name: "models" }, icon: (s) => <Box size={s} />, key: "nav.models", names: ["models", "model"] },
  { route: { name: "installed", tab: "engines" }, icon: (s) => <HardDriveDownload size={s} />, key: "nav.installed", names: ["installed"] },
];
const SETTINGS: NavItem = { route: { name: "settings", section: "general" }, icon: (s) => <SettingsIcon size={s} />, key: "nav.settings", names: ["settings"] };

export function Shell({ route, children }: { route: Route; children: ReactNode }) {
  const { engines, up, engine } = useHub();
  const desktop = Boolean(window.sori?.desktop);
  const installing = engines.find((e) => e.install.status === "installing");
  const dead = engines.some((e) => e.run.state === "dead" || e.install.status === "failed");
  const here = [...NAV, SETTINGS].find((n) => n.names.includes(route.name)) ?? NAV[0];
  const sub = route.name === "model" ? engine(route.id)?.name : undefined;

  const item = (n: NavItem) => (
    <a key={n.key} className="rail-item" href={href(n.route)} aria-label={t(n.key)} aria-current={n.names.includes(route.name) ? "page" : undefined}>
      {n.icon(20)}
      {n.key === "nav.models" && installing && <span className="rail-mark spinner" style={{ color: "var(--accent-strong)", width: 9, height: 9 }} aria-label={t("install.status.installing")} />}
      {n.key === "nav.installed" && dead && <span className="rail-mark dot bad" aria-label={t("status.problem")} />}
      <span className="rail-tip" aria-hidden>{t(n.key)}</span>
    </a>
  );

  return (
    <div className={`app ${desktop ? "desktop" : ""}`}>
      <nav className="rail" aria-label={t("nav.label")}>
        <a className="rail-logo" href={href({ name: "home" })} aria-label={t("app.name")}>
          <span><Logo size={18} /></span>
        </a>
        {NAV.map(item)}
        <div className="rail-spacer" />
        {item(SETTINGS)}
      </nav>
      <header className="topbar">
        <div className="crumbs">
          <span className="ic" aria-hidden>{here.icon(16)}</span>
          {sub ? (
            <>
              <a href={href({ name: "models" })} title={t("detail.backToList")}>{t(here.key)}</a>
              <span className="sep" aria-hidden><ChevronRight size={14} /></span>
              <span className="ellipsis">{sub}</span>
            </>
          ) : (
            <span>{t(here.key)}</span>
          )}
        </div>
        <TopStatus />
      </header>
      <main className="main" id="main">
        {!up && (
          <div className="main-banner">
            {desktop ? (
              <Banner tone="warning" title={t("down.desktopTitle")} body={t("down.readonly")} />
            ) : (
              <Banner tone="danger" title={t("down.title")} body={`${t("down.body")} ${t("down.readonly")}`} />
            )}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}

// 받는 중이거나 모델에 문제가 있을 때만 머리줄 오른쪽에 알약 하나(평소에는 비워 둬요)
function TopStatus() {
  const { engines } = useHub();
  const worst =
    engines.find((e) => e.run.state === "dead") ??
    engines.find((e) => e.run.state === "restarting" || e.run.state === "stalled");
  const installing = engines.find((e) => e.install.status === "installing");
  const p = installing?.install.progress;
  if (!worst && !installing) return null;
  return (
    <div className="top-status" aria-label={t("status.label")}>
      {worst && (
        <button className={`top-pill ${worst.run.state === "dead" ? "bad" : "warn"}`} onClick={() => go({ name: "installed", tab: "engines" })}>
          {t(worst.run.state === "dead" ? "status.engineDead" : worst.run.state === "stalled" ? "status.engineStalled" : "status.engineRestarting", { name: worst.name })}
        </button>
      )}
      {installing && (
        <button className="top-pill num" onClick={() => go({ name: "model", id: installing.id })}>
          <span className="spinner" aria-hidden style={{ color: "var(--accent-strong)" }} />
          {t("status.installing", { name: installing.name, pct: p && p.bytes_total ? Math.floor((p.bytes_done / p.bytes_total) * 100) : 0 })}
        </button>
      )}
    </div>
  );
}
