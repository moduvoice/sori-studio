import { useEffect, useState } from "react";
import { api, ApiError, setToken, type Settings } from "./lib/api";
import { setLang, t } from "./lib/i18n";
import { go, useRoute } from "./lib/router";
import { useHub } from "./lib/store";
import { Banner, Button } from "./components/ui";
import { Curves } from "./components/art";
import { Logo, Shell } from "./components/shell";
import Home from "./screens/Home";
import Catalog from "./screens/Catalog";
import ModelDetail from "./screens/ModelDetail";
import Installed from "./screens/Installed";
import QuickTry from "./screens/QuickTry";
import Settings_ from "./screens/Settings";
import Wizard from "./screens/Wizard";

function useTheme(s: Settings | null) {
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const theme = s?.theme === "dark" || (s?.theme !== "light" && mq.matches) ? "dark" : "light";
      document.documentElement.dataset.theme = theme;
      document.documentElement.style.setProperty("zoom", String((s?.font_scale ?? 100) / 100));
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [s?.theme, s?.font_scale]);
}

export default function App() {
  const hub = useHub();
  const route = useRoute();
  useTheme(hub.settings);
  setLang(hub.settings?.language); // 그릴 때마다 맞춰요 - 설정에서 바꾸면 다음 그리기부터 그 언어

  // 첫 실행이면 마법사로(design.md 3.1). 받은 모델이 있으면 첫 화면은 홈(rebuild-2026-11.md 3절)
  const hasModel = hub.engines.some((e) => e.install.status === "installed" || e.install.status === "update");
  useEffect(() => {
    if (!hub.settings) return;
    if (!hub.settings.wizard_done && route.name !== "wizard") go({ name: "wizard" });
    else if (hub.settings.wizard_done && !location.hash && hasModel) go({ name: "home" });
  }, [hub.settings, route.name, hasModel]);

  if (hub.authFailed) return <TokenGate />;
  if (!hub.loaded)
    return (
      <div className="startup glow" aria-live="polite">
        <Curves />
        <div className="brand"><Logo size={36} />{t("app.name")}</div>
        {!hub.up ? <Banner tone="danger" title={t("down.title")} body={t("down.body")} /> : <span className="muted">{t("common.loading")}</span>}
      </div>
    );
  if (route.name === "wizard") return <Wizard />;

  return (
    <Shell route={route} key={hub.settings?.language}>
      {route.name === "home" && <Home />}
      {route.name === "models" && <Catalog />}
      {route.name === "model" && <ModelDetail id={route.id} />}
      {route.name === "installed" && <Installed />}
      {route.name === "try" && <QuickTry engineId={route.engine} />}
      {route.name === "settings" && <Settings_ section={route.section} />}
    </Shell>
  );
}

// serve 모드(브라우저)에서 토큰 넣는 화면(design.md 4.2). 주소 줄에 토큰을 넣지 않아요.
function TokenGate() {
  const { refresh } = useHub();
  const [v, setV] = useState("");
  const [err, setErr] = useState(false);
  return (
    <div className="startup glow">
      <Curves />
      <form
        className="gate"
        onSubmit={async (e) => {
          e.preventDefault();
          setToken(v.trim());
          try {
            await api("/hub/settings");
            setErr(false);
            await refresh();
          } catch (x) {
            setErr(x instanceof ApiError && x.status === 401);
          }
        }}
      >
        <div className="row" style={{ gap: 10 }}><Logo size={26} /><h1 className="t-h2" style={{ fontSize: 18 }}>{t("gate.title")}</h1></div>
        <p className="muted">{t("gate.body")}</p>
        <input className={`field ${err ? "err" : ""}`} style={{ height: 42 }} type="password" autoFocus value={v} onChange={(e) => setV(e.target.value)} aria-label={t("gate.field")} placeholder={t("gate.field")} />
        {err && <span className="field-err">{t("gate.wrong")}</span>}
        <Button variant="primary" size="lg" type="submit" disabled={!v.trim()}>{t("gate.connect")}</Button>
      </form>
    </div>
  );
}
