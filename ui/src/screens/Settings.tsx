// G1 설정 - 바꾸면 바로 적용(저장 단추 없음), 되돌릴 수 없는 일만 확인 창
import { useEffect, useState } from "react";
import { Eye, EyeOff, RefreshCw } from "lucide-react";
import { api, errorText, openExternal, type ApiInfo } from "../lib/api";
import { clock, date } from "../lib/format";
import { t } from "../lib/i18n";
import { go, href } from "../lib/router";
import { useHub, useToast } from "../lib/store";
import { Button, CopyButton, Dialog, IconButton, Segmented, Switch } from "../components/ui";

const SECTIONS = ["general", "models", "network", "api", "about"];
const REPO = "https://github.com/moduvoice/sori-studio";

export default function Settings({ section }: { section: string }) {
  const s = SECTIONS.includes(section) ? section : "general";
  return (
    <div className="page" style={{ maxWidth: 1000 }}>
      <h1 className="t-h1" style={{ marginBottom: 20 }}>{t("settings.title")}</h1>
      <div className="settings-grid">
        <nav className="settings-nav" aria-label={t("settings.title")}>
          {SECTIONS.map((x) => (
            <a key={x} className="nav-item" href={href({ name: "settings", section: x })} aria-current={x === s ? "page" : undefined}>
              <span className="label" style={{ display: "inline" }}>{t(`settings.${x}`)}</span>
            </a>
          ))}
        </nav>
        <section className="card card-pad" aria-label={t(`settings.${s}`)}>
          <h2 className="t-h2" style={{ marginBottom: 8 }}>{t(`settings.${s}`)}</h2>
          {s === "general" && <General />}
          {s === "models" && <Models />}
          {s === "api" && <Api />}
          {s === "network" && <Network />}
          {s === "about" && <About />}
        </section>
      </div>
    </div>
  );
}

function General() {
  const { settings, saveSettings } = useHub();
  if (!settings) return null;
  return (
    <>
      <div className="setting">
        <div className="grow">{t("settings.theme")}</div>
        <Segmented
          label={t("settings.theme")}
          value={settings.theme}
          onChange={(v) => saveSettings({ theme: v })}
          options={[
            { value: "system", label: t("settings.themeSystem") },
            { value: "light", label: t("settings.themeLight") },
            { value: "dark", label: t("settings.themeDark") },
          ]}
        />
      </div>
      <div className="setting">
        <div className="grow">{t("settings.language")}</div>
        <Segmented
          label={t("settings.language")}
          value={settings.language ?? "system"}
          onChange={(v) => saveSettings({ language: v })}
          options={[
            { value: "system", label: t("settings.themeSystem") },
            { value: "ko", label: "한국어" },
            { value: "en", label: "English" },
          ]}
        />
      </div>
      <div className="setting">
        <div className="grow">{t("settings.fontScale")}</div>
        <Segmented
          label={t("settings.fontScale")}
          value={[100, 115, 130].includes(settings.font_scale) ? settings.font_scale : 100}
          onChange={(v) => saveSettings({ font_scale: v })}
          options={[
            { value: 100, label: t("settings.fontNormal") },
            { value: 115, label: t("settings.fontLarge") },
            { value: 130, label: t("settings.fontLarger") },
          ]}
        />
      </div>
      <div className="setting">
        <div className="grow">{t("settings.wizardAgain")}</div>
        <Button onClick={() => go({ name: "wizard" })}>{t("settings.wizardAgainBtn")}</Button>
      </div>
    </>
  );
}

function Models() {
  const { settings, engines, hardware } = useHub();
  const locked = engines.some((e) => e.install.status !== "none");
  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>{t("settings.modelsFolderBody")}</p>
      <div className="readonly" style={{ marginBottom: 8 }}><code>{settings?.models_dir}</code></div>
      {hardware && <p className="t-caption muted num">{t("wizard.pcFree")} {hardware.disk_free_gb} GB</p>}
      {locked ? (
        <p className="note">{t("settings.modelsLocked")}</p>
      ) : (
        <Button onClick={() => go({ name: "wizard" })}>{t("settings.change")}</Button>
      )}
    </>
  );
}

function Api() {
  const { saveSettings } = useHub();
  const toast = useToast();
  const [info, setInfo] = useState<ApiInfo | null>(null);
  const [show, setShow] = useState(false);
  const [rotate, setRotate] = useState(false);
  const load = () => api<ApiInfo>("/hub/api").then(setInfo);
  useEffect(() => {
    load();
    const id = window.setInterval(load, 3000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    if (!show) return;
    const id = window.setTimeout(() => setShow(false), 10000); // 보기는 10초 뒤 다시 가려요(components.md 2)
    return () => window.clearTimeout(id);
  }, [show]);
  if (!info) return null;
  const curl = `curl -X POST ${info.base_url}/audio/speech \\\n  -H "Authorization: Bearer $SORI_TOKEN" -H "Content-Type: application/json" \\\n  -d '{"model": "supertonic-3", "input": "안녕하세요", "voice": "F1"}' -o out.wav`;
  const py = `from openai import OpenAI\nclient = OpenAI(base_url="${info.base_url}", api_key=SORI_TOKEN)\nclient.audio.speech.create(model="supertonic-3", voice="F1", input="안녕하세요",\n                           response_format="wav").write_to_file("out.wav")`;
  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>{t("settings.apiBody")}</p>
      <div className="setting">
        <div className="grow">
          <div>{t("settings.apiSwitch")}</div>
          <div className="muted">{t("settings.apiOnlyHere")}</div>
        </div>
        <Switch
          label={t("settings.apiSwitch")}
          checked={info.enabled}
          onChange={async (v) => {
            await saveSettings({ api_enabled: v });
            load();
          }}
        />
      </div>
      {info.enabled && (
        <>
          <div className="setting">
            <div style={{ minWidth: 80 }}>{t("settings.apiAddress")}</div>
            <div className="readonly grow"><code>{info.base_url}</code><CopyButton text={info.base_url} /></div>
          </div>
          <div className="setting">
            <div style={{ minWidth: 80 }}>{t("settings.apiToken")}</div>
            <div className="readonly grow">
              <code>{show ? info.token : "•".repeat(32)}</code>
              <IconButton label={show ? t("settings.apiHide") : t("settings.apiShow")} onClick={() => setShow(!show)}>
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </IconButton>
              <CopyButton text={info.token ?? ""} />
            </div>
            <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} onClick={() => setRotate(true)}>{t("settings.apiRotate")}</Button>
          </div>
          <h3 className="t-h3" style={{ margin: "16px 0 8px" }}>{t("settings.apiTry")}</h3>
          <div className="code" style={{ marginBottom: 8 }}><span className="copy"><CopyButton text={curl} /></span>{curl}</div>
          <div className="code"><span className="copy"><CopyButton text={py} /></span>{py}</div>
        </>
      )}
      <h3 className="t-h3" style={{ margin: "16px 0 8px" }}>{t("settings.apiCalls")}</h3>
      {info.calls.length === 0 ? (
        <p className="muted t-caption">{t("settings.apiCallsEmpty")}</p>
      ) : (
        <table className="table" style={{ fontSize: 13 }}>
          <tbody>
            {info.calls.slice(0, 20).map((c, i) => (
              <tr key={i} style={{ cursor: "default" }}>
                <td className="t-mono muted" style={{ height: 32 }}>{clock(c.at)}</td>
                <td className="t-mono">{c.method} {c.path}</td>
                <td style={{ color: c.status < 400 ? "var(--success)" : "var(--danger)" }} className="num">{c.status}</td>
                <td className="muted">{c.reason ?? (c.ms != null ? `${c.ms} ms` : "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note" style={{ marginTop: 12 }}>{t("settings.apiNoInstall")}</p>
      {rotate && (
        <Dialog
          title={t("settings.apiRotateTitle")}
          onClose={() => setRotate(false)}
          foot={
            <>
              <Button variant="ghost" onClick={() => setRotate(false)}>{t("common.cancel")}</Button>
              <Button
                variant="primary"
                onClick={async () => {
                  try {
                    setInfo(await api<ApiInfo>("/hub/api/token/rotate", { method: "POST" }));
                  } catch (x) {
                    toast(errorText(x));
                  }
                  setRotate(false);
                }}
              >
                {t("settings.apiRotate")}
              </Button>
            </>
          }
        >
          <p>{t("settings.apiRotateBody")}</p>
        </Dialog>
      )}
    </>
  );
}

function Network() {
  const { engines } = useHub();
  const consents = engines.filter((e) => e.install.consent);
  return (
    <>
      <p style={{ marginTop: 0 }}>{t("settings.netBody")}</p>
      <details className="more">
        <summary>{t("common.details")}</summary>
        <ul className="col" style={{ paddingLeft: 18 }}>
          <li style={{ listStyle: "disc" }}>{t("settings.net1")}</li>
          <li style={{ listStyle: "disc" }}>{t("settings.net2")}</li>
          <li style={{ listStyle: "disc" }}>{t("settings.net3")}</li>
        </ul>
      </details>
      <details className="more">
        <summary>{t("settings.consents")}</summary>
        {consents.length === 0 ? (
          <p className="muted t-caption">{t("settings.consentsEmpty")}</p>
        ) : (
          consents.map((e) => (
            <p key={e.id} style={{ margin: "4px 0" }}>
              {t("settings.consentRow", { name: e.name, license: e.license.name, date: date(e.install.consent!.at) })}
            </p>
          ))
        )}
      </details>
    </>
  );
}

function About() {
  const { settings, hardware } = useHub();
  const toast = useToast();
  const diag = [
    `Sori Studio ${settings?.version}`,
    `${hardware?.os_name} ${hardware?.arch}`,
    `CPU ${hardware?.cpu} · ${hardware?.cores} cores · RAM ${hardware?.ram_gb} GB`,
    `GPU ${hardware?.gpus.map((g) => `${g.name} ${g.vram_gb}GB driver ${g.driver}`).join(", ") || "none"}`,
  ].join("\n");
  return (
    <>
      <dl className="kv">
        <dt>{t("settings.version")}</dt>
        <dd className="t-mono">{settings?.version}</dd>
        <dt>{t("settings.appLicense")}</dt>
        <dd>Apache-2.0</dd>
        <dt>{t("settings.repo")}</dt>
        <dd><button className="btn btn-link" onClick={() => openExternal(REPO)}>github.com/moduvoice/sori-studio</button></dd>
        <dt>{t("wizard.pcOs")}</dt>
        <dd>{hardware?.os_name}</dd>
        <dt>{t("wizard.pcCpu")}</dt>
        <dd>{hardware?.cpu}</dd>
      </dl>
      <p className="muted" style={{ margin: "16px 0" }}>{t("settings.madeBy")}</p>
      <Button
        onClick={async () => {
          await navigator.clipboard.writeText(diag);
          toast(t("common.copied"));
        }}
      >
        {t("settings.diag")}
      </Button>
      <p className="note" style={{ marginTop: 6 }}>{t("settings.diagNote")}</p>
    </>
  );
}
