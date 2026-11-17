// A3 첫 실행 마법사 - 3단계: 고르기 → 받기 → 들어 보기(UX 리뷰 2026-11-17: 6단계를 줄임).
// PC 점검은 화면 없이 뒤에서 하고, 설치할 곳은 받기 화면의 "바꾸기"로만 보여요.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Cpu, HardDrive, Megaphone, Theater } from "lucide-react";
import { api, errorText, type Drive, type Hardware, type Recommend } from "../lib/api";
import { bytes } from "../lib/format";
import { t, tl } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub } from "../lib/store";
import { Badge, Banner, Button } from "../components/ui";
import { LicenseBadge, VerdictStatus, loc } from "../components/engine";
import { InstallPanel, SelftestLines } from "../components/install";
import { Logo } from "../components/shell";

type Use = "narration" | "acting" | "light";
const USES: { key: Use; icon: ReactNode }[] = [
  { key: "narration", icon: <Megaphone size={28} /> },
  { key: "acting", icon: <Theater size={28} /> },
  { key: "light", icon: <Cpu size={28} /> },
];

export default function Wizard() {
  const { saveSettings, engine } = useHub();
  const [step, setStep] = useState(0);
  const [hw, setHw] = useState<Hardware | null>(null);
  const [use, setUse] = useState<Use | null>(null);
  const [rec, setRec] = useState<Recommend | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const chosen = pick ? engine(pick) : undefined;
  const installed = Boolean(chosen && (chosen.install.status === "installed" || chosen.install.status === "update"));

  const chooseUse = useCallback(async (u: Use) => {
    setUse(u);
    setRec(null);
    const r = await api<Recommend>(`/hub/recommend?use=${u}&direct=true`);
    setRec(r);
    setPick(r.recommended);
  }, []);

  useEffect(() => {
    api<Hardware>("/hub/hardware?refresh=true").then((h) => {
      setHw(h);
      chooseUse(h.gpus.length ? "narration" : "light"); // 고를 게 없으면 미리 골라 둬요
    });
  }, [chooseUse]);

  // 받기가 끝나면 저절로 들어 보기로
  const wasInstalling = useRef(false);
  useEffect(() => {
    if (step === 1 && chosen?.install.status === "installing") wasInstalling.current = true;
    if (step === 1 && installed && wasInstalling.current) {
      wasInstalling.current = false;
      setStep(2);
    }
  }, [step, chosen?.install.status, installed]);

  async function finish(to: "try" | "models") {
    await saveSettings({ wizard_done: true });
    if (to === "try") go({ name: "try", engine: pick ?? undefined });
    else go({ name: "models" });
  }

  const steps = tl("wizard.steps");
  const busyInstall = chosen?.install.status === "installing";
  return (
    <div className="wizard">
      <header className="wizard-head">
        <div className="row t-label" style={{ fontSize: 15 }}>
          <Logo /> {t("app.name")}
        </div>
        <ol className="stepper" aria-label={t("wizard.stepsLabel")}>
          {steps.map((name, i) => (
            <li key={name} className={i === step ? "now" : i < step ? "done" : ""} aria-current={i === step ? "step" : undefined}>
              {i < step && !busyInstall ? (
                <button onClick={() => setStep(i)}>
                  <span className="n"><Check size={13} strokeWidth={3} /></span>
                  {name}
                </button>
              ) : (
                <>
                  <span className="n">{i < step ? <Check size={13} strokeWidth={3} /> : i + 1}</span>
                  {name}
                </>
              )}
            </li>
          ))}
        </ol>
      </header>

      <div className="wizard-body">
        <div className="wizard-grid" style={{ gridTemplateColumns: "minmax(0, 720px)" }}>
          <div className="col" style={{ gap: 20 }}>
            {step === 0 && <Pick hw={hw} use={use} rec={rec} pick={pick} setPick={setPick} chooseUse={chooseUse} />}
            {step === 1 && chosen && (
              <>
                <h1 className="t-display">{installed ? t("install.installedTitle") : t("wizard.s2Title", { name: chosen.name })}</h1>
                {chosen.install.status === "none" && <FolderLine />}
                <InstallPanel e={chosen} inWizard />
              </>
            )}
            {step === 2 && chosen && (
              <>
                <h1 className="t-display">{t("wizard.s3Title")}</h1>
                <section className="card card-pad">{installed ? <SelftestLines e={chosen} /> : <p className="muted">{t("wizard.s3Wait")}</p>}</section>
                <div className="row" style={{ marginTop: 4 }}>
                  <Button variant="primary" size="lg" disabled={!installed} onClick={() => finish("try")}>{t("wizard.startMaking")}</Button>
                  <Button size="lg" variant="ghost" onClick={() => finish("models")}>{t("wizard.seeModels")}</Button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <footer className="wizard-foot">
        <span className="grow">
          {step === 0 && <Button variant="ghost" onClick={() => finish("models")}>{t("wizard.skip")}</Button>}
        </span>
        {step === 1 && !busyInstall && <Button size="lg" onClick={() => setStep(0)}>{t("common.prev")}</Button>}
        {step === 0 && (
          <Button variant="primary" size="lg" disabled={!pick} onClick={() => setStep(installed ? 2 : 1)}>{t("common.next")}</Button>
        )}
      </footer>
    </div>
  );
}

function Pick({ hw, use, rec, pick, setPick, chooseUse }: {
  hw: Hardware | null; use: Use | null; rec: Recommend | null; pick: string | null; setPick: (v: string) => void; chooseUse: (u: Use) => void;
}) {
  const { engine } = useHub();
  const recs = rec ? [rec.recommended, ...rec.alternatives].filter(Boolean).map((id) => engine(id!)!).filter(Boolean) : [];
  const g = hw?.gpus[0];
  return (
    <>
      <div>
        <h1 className="t-display">{t("wizard.s1Title")}</h1>
        <p className="muted" style={{ margin: "6px 0 0" }}>
          {hw ? (g ? t("wizard.pcGpu", { gpu: g.name }) : t("wizard.pcNoGpu")) : t("common.loading")}
        </p>
      </div>
      {hw?.apple_silicon && <Banner tone="warning" title={t("wizard.mac")} />}
      <div className="choices" role="radiogroup" aria-label={t("wizard.s1Title")}>
        {USES.map((u) => (
          <button key={u.key} type="button" role="radio" className="choice" aria-checked={use === u.key} onClick={() => chooseUse(u.key)}>
            {u.icon}
            <span>{t(`wizard.uses.${u.key}`)}</span>
            <span className="sub">{t(`wizard.usesSub.${u.key}`)}</span>
          </button>
        ))}
      </div>
      {rec &&
        (recs.length > 0 ? (
          <div className="col" role="radiogroup" aria-label={t("wizard.recommendFor")} style={{ gap: 8 }}>
            <h2 className="t-h2">{t("wizard.recommendFor")}</h2>
            {recs.map((e, i) => (
              <button key={e.id} type="button" className="drive" aria-checked={pick === e.id} role="radio" onClick={() => setPick(e.id)} style={{ alignItems: "flex-start" }}>
                <span className="grow col" style={{ gap: 6 }}>
                  <span className="row">
                    <span className="t-h2">{e.name}</span>
                    {i === 0 && <Badge tone="accent">{t("badge.recommended")}</Badge>}
                  </span>
                  <VerdictStatus v={e.this_pc} withReason={false} />
                  {loc(e).human_eval_line && <span className="t-body">“{loc(e).human_eval_line}”</span>}
                  <span className="row row-wrap" style={{ gap: 6 }}><LicenseBadge e={e} /></span>
                </span>
                <span className="col" style={{ alignItems: "flex-end", gap: 2 }}>
                  <span className="t-caption muted">{t("install.plan.download")}</span>
                  <span className="t-h2 num">{bytes(e.download_bytes)}</span>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <Banner tone="info" title={t("wizard.noneYet")}>
            <Button onClick={() => chooseUse("light")}>{t("wizard.uses.light")}</Button>
          </Banner>
        ))}
    </>
  );
}

// 설치할 곳 - 기본 폴더면 한 줄만, [바꾸기]를 누르면 드라이브를 골라요.
function FolderLine() {
  const { settings, refresh } = useHub();
  const [open, setOpen] = useState(false);
  const [drives, setDrives] = useState<Drive[] | null>(null);
  const [custom, setCustom] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cur = settings?.models_dir ?? "";
  useEffect(() => {
    if (open && !drives) api<{ drives: Drive[] }>("/hub/drives").then((d) => setDrives(d.drives));
  }, [open, drives]);
  async function save(path: string) {
    setBusy(true);
    setErr(null);
    try {
      await api("/hub/models-dir", { method: "PUT", json: { path } });
      await refresh();
      setOpen(false);
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="col" style={{ gap: 8 }}>
      <div className="row t-caption muted" style={{ gap: 8 }}>
        <HardDrive size={14} aria-hidden />
        <span className="grow" style={{ wordBreak: "break-all" }}>{t("wizard.folder", { path: cur })}</span>
        <Button variant="link" size="sm" onClick={() => setOpen(!open)}>{t("settings.change")}</Button>
      </div>
      {open && (
        <div className="col card card-pad" style={{ gap: 8 }}>
          {(drives ?? []).map((d) => (
            <button key={d.root} type="button" className="drive" disabled={busy} onClick={() => save(d.suggested)}>
              <HardDrive size={18} aria-hidden />
              <span className="grow col" style={{ gap: 2 }}>
                <span className="t-label">{`${d.root.replace("\\", "")} ${d.label}`.trim()}</span>
                <span className="t-caption muted" style={{ wordBreak: "break-all" }}>{d.suggested}</span>
              </span>
              <span className="num t-caption">{t("wizard.free", { size: bytes(d.free_bytes) })}</span>
            </button>
          ))}
          <div className="row" style={{ gap: 8 }}>
            <input className="field grow" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder={t("wizard.customFolder")} aria-label={t("wizard.customFolder")} />
            <Button disabled={!custom.trim() || busy} onClick={() => save(custom.trim())}>{t("common.apply")}</Button>
          </div>
          {err && <Banner tone="danger" title={err} />}
        </div>
      )}
    </div>
  );
}
