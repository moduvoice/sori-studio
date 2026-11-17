// 설치 패널(components.md 6) - 받기 전 확인(양·시간·사용 조건)을 한 장에 두고, 받는 중·멈춤·실패·설치됨으로 바뀌어요.
// UX 리뷰(2026-11-17): 동의 칸은 늘 켜 두고, 단계는 준비·받기·확인 셋만, 취소는 단추 하나(받은 것은 남겨요).
import { useEffect, useRef, useState } from "react";
import { Check, Pause, X } from "lucide-react";
import { api, errorText, openExternal, type Engine, type InstallStep, type Plan } from "../lib/api";
import { bytes, secs } from "../lib/format";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub, useToast } from "../lib/store";
import { Banner, Button, Dialog, Progress } from "./ui";
import { Player } from "./player";
import { isRunnable, loc } from "./engine";
import { WslGate, useWsl } from "./wsl";

// 사람에게 보이는 단계 셋 - 허브의 env·code·packages 는 "준비하기" 하나로 묶어요
type Phase = "prepare" | "weights" | "selftest";
const PHASES: { key: Phase; steps: InstallStep[] }[] = [
  { key: "prepare", steps: ["env", "code", "packages"] },
  { key: "weights", steps: ["weights"] },
  { key: "selftest", steps: ["selftest"] },
];

export function InstallPanel({ e, inWizard }: { e: Engine; inWizard?: boolean }) {
  const s = e.install.status;
  return (
    <section className="card card-pad" aria-labelledby={`inst-${e.id}`}>
      {/* 마법사에서는 화면 제목에 이름이 이미 있어요 */}
      <h2 className={inWizard ? "sr-only" : "t-h2"} id={`inst-${e.id}`} style={{ marginBottom: 12 }}>
        {inWizard ? e.name : t("install.panelTitle")}
      </h2>
      {s === "installed" || s === "update" ? (
        <Installed e={e} inWizard={inWizard} />
      ) : s === "installing" || s === "paused" || (s === "failed" && e.install.done.length > 0) || (s === "failed" && e.install.consent) ? (
        <Running e={e} />
      ) : (
        <PlanConsent e={e} />
      )}
    </section>
  );
}

// ---------- 받기 전 확인 + 사용 조건 ----------
function PlanConsent({ e }: { e: Engine }) {
  const { refresh } = useHub();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Plan>(`/hub/engines/${e.id}/plan`).then(setPlan).catch(() => undefined);
  }, [e.id]);

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/hub/engines/${e.id}/install`, { method: "POST", json: { accept_license: e.license.id } });
      await refresh();
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }

  const runnable = isRunnable(e.this_pc);
  const total = plan ? plan.download_bytes + plan.env_bytes_estimate : e.download_bytes;
  const wslSt = useWsl(e.runtime === "wsl");
  const wslBlocked = e.runtime === "wsl" && wslSt != null && ["none", "needs_setup"].includes(wslSt.state);
  return (
    <div className="col" style={{ gap: 16 }}>
      <div>
        <p className="t-body" style={{ margin: 0 }}>
          {t("install.plan.oneLine", { size: bytes(total), min: plan ? Math.max(1, Math.round(plan.est_minutes)) : "…" })}
        </p>
        <p className="note" style={{ marginTop: 4 }}>{t("install.plan.officialOnly")}</p>
      </div>
      {e.runtime === "wsl" && runnable && <WslGate st={wslSt} />}
      {plan && !plan.disk_ok && (
        <Banner tone="warning" title={t("install.plan.diskShort", { n: bytes(plan.need_bytes - plan.free_bytes) })} />
      )}
      <LicenseConsent e={e} agree={agree} setAgree={setAgree} />
      {!runnable && <Banner tone="warning" title={t("install.notRunHere")} />}
      {err && <Banner tone="danger" title={err} />}
      <div className="col sticky-actions" style={{ gap: 6 }}>
        <Button
          variant={runnable ? "primary" : "secondary"}
          size="lg"
          internet
          busy={busy}
          disabled={!agree || wslBlocked || (plan != null && !plan.disk_ok)}
          onClick={start}
        >
          {runnable ? t("install.start") : t("install.startAnyway")} · {bytes(total)}
        </Button>
        {!agree && <span className="t-caption muted">{t("install.agreeFirst")}</span>}
      </div>
    </div>
  );
}

export function LicenseConsent({ e, agree, setAgree }: { e: Engine; agree: boolean; setAgree: (v: boolean) => void }) {
  const [text, setText] = useState<{ text: string | null; restrictions: string | null } | null>(null);
  const [full, setFull] = useState(false);
  const summary = loc(e).license_summary;

  useEffect(() => {
    if (e.license.has_text) api<{ text: string; restrictions: string }>(`/hub/engines/${e.id}/license`).then(setText).catch(() => undefined);
  }, [e.id, e.license.has_text]);

  return (
    <div className="col" style={{ gap: 8 }}>
      <span className="t-h3">{t("install.licenseTitle")}</span>
      <ul style={{ margin: 0, paddingLeft: 18 }} className="col">
        {summary.slice(0, 2).map((x, i) => (
          <li key={i} style={{ listStyle: "disc" }}>{x}</li>
        ))}
      </ul>
      {(summary.length > 2 || text?.restrictions) && (
        <details className="more">
          <summary>{t("common.details")}</summary>
          <ul style={{ margin: "4px 0 8px", paddingLeft: 18 }} className="col">
            {summary.slice(2).map((x, i) => (
              <li key={i} style={{ listStyle: "disc" }}>{x}</li>
            ))}
          </ul>
          {text?.restrictions && (
            <div className="license-box" tabIndex={0} lang="en" aria-label={t("install.restrictionsTitle")}>{text.restrictions}</div>
          )}
        </details>
      )}
      <div className="row row-wrap" style={{ gap: 12 }}>
        <Button variant="link" onClick={() => setFull(true)} disabled={!text?.text}>
          {t("detail.licenseOriginal", { name: e.license.name })}
        </Button>
      </div>
      <label className="check">
        <input type="checkbox" checked={agree} onChange={(ev) => setAgree(ev.target.checked)} />
        <span>{t("install.agree")}</span>
      </label>
      {full && text?.text && (
        <Dialog
          wide
          title={e.license.name}
          onClose={() => setFull(false)}
          foot={
            <>
              <Button variant="ghost" internet onClick={() => openExternal(e.license.url)}>{t("common.readOriginal")}</Button>
              <Button variant="primary" onClick={() => setFull(false)}>{t("common.close")}</Button>
            </>
          }
        >
          <div className="logview" lang="en" style={{ maxHeight: "60vh" }}>{text.text}</div>
        </Dialog>
      )}
    </div>
  );
}

// ---------- 받는 중·멈춤·실패 ----------
function Running({ e }: { e: Engine }) {
  const { refresh } = useHub();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [del, setDel] = useState(false);
  const [log, setLog] = useState<string[] | null>(null);
  const s = e.install.status;
  const p = e.install.progress;
  const err = e.install.error;

  const done = p?.bytes_done ?? 0;
  const total = p?.bytes_total ?? e.download_bytes;
  const left = useLeft(done, total, s === "installing" && p?.step === "weights");

  async function act(kind: "pause" | "resume" | "delete") {
    setBusy(kind);
    try {
      if (kind === "pause") await api(`/hub/engines/${e.id}/install/stop`, { method: "POST" });
      if (kind === "resume") await api(`/hub/engines/${e.id}/install`, { method: "POST", json: { accept_license: e.license.id } });
      if (kind === "delete") {
        await api(`/hub/engines/${e.id}/install/stop`, { method: "POST" });
        for (let i = 0; i < 20; i++) {
          const v = await api<Engine>(`/hub/engines/${e.id}`);
          if (v.install.status !== "installing") break;
          await new Promise((r) => setTimeout(r, 500));
        }
        const r = await api<{ freed_bytes: number }>(`/hub/engines/${e.id}?part=all`, { method: "DELETE" });
        toast(t("install.removed", { name: e.name, size: bytes(r.freed_bytes) }));
      }
      await refresh();
    } catch (x) {
      toast(errorText(x));
    } finally {
      setBusy(null);
      setDel(false);
    }
  }

  const failedStep = s === "failed" ? (err?.step as InstallStep | undefined) : undefined;
  const phaseState = (ph: (typeof PHASES)[number]) => {
    if (ph.steps.every((x) => x === "code" ? !e.has_code || e.install.done.includes(x) : e.install.done.includes(x))) return "done";
    if (failedStep && ph.steps.includes(failedStep)) return "fail";
    if (s === "installing" && p?.step && ph.steps.includes(p.step)) return "run";
    if (s === "paused" && PHASES.find((x) => x.steps.some((st) => !e.install.done.includes(st) && (st !== "code" || e.has_code))) === ph) return "pause";
    return "wait";
  };
  const pct = total ? done / total : 0;

  return (
    <div className="col" style={{ gap: 16 }} aria-live="polite">
      <ol className="steps">
        {PHASES.map((ph) => {
          const st = phaseState(ph);
          return <StepRow key={ph.key} state={st} label={t(`install.phase.${ph.key}`)} value={ph.key === "weights" && (st === "run" || st === "pause") ? `${Math.floor(pct * 100)}%` : undefined} />;
        })}
      </ol>

      {s === "installing" && p?.step && ["env", "code", "packages"].includes(p.step) && (
        <div className="col" style={{ gap: 6 }}>
          <div className="progress indet" role="progressbar" aria-label={t("install.phase.prepare")}><i /></div>
          <span className="t-caption muted">{t("install.preparing")}</span>
        </div>
      )}
      {s === "installing" && p?.step === "selftest" && (
        <span className="t-caption muted row"><span className="spinner" style={{ color: "var(--accent)" }} />{t("install.selftestRunning")}</span>
      )}
      {((s === "installing" && p?.step === "weights") || s === "paused") && (
        <div className="col" style={{ gap: 6 }}>
          <Progress value={pct} paused={s === "paused"} label={t("install.phase.weights")} />
          <div className="t-caption muted num row">
            <span>{bytes(done)} / {bytes(total)}</span>
            {s === "installing" && left != null && <span className="right">{t("install.remaining", { t: secs(left) })}</span>}
          </div>
        </div>
      )}

      {s === "paused" && <p className="note">{t("install.pausedNote")}</p>}
      {s === "failed" && err && <FailBox e={e} onRetry={() => act("resume")} busy={busy === "resume"} onLog={async () => setLog((await api<{ log: string[] }>(`/hub/engines/${e.id}/install/log`)).log)} />}

      {s === "installing" && (
        <div className="row">
          <span className="t-caption muted grow">{t("install.keepsGoing")}</span>
          <Button variant="ghost" busy={busy === "pause"} onClick={() => act("pause")}>{t("common.cancel")}</Button>
        </div>
      )}
      {s === "paused" && (
        <div className="row">
          <Button variant="primary" internet busy={busy === "resume"} onClick={() => act("resume")}>{t("install.resume")}</Button>
          <Button variant="ghost" className="right" onClick={() => setDel(true)}>{t("install.deleteDownloaded")}</Button>
        </div>
      )}

      {del && (
        <Dialog
          title={t("install.deleteTitle")}
          onClose={() => setDel(false)}
          foot={
            <>
              <Button variant="ghost" onClick={() => setDel(false)}>{t("common.cancel")}</Button>
              <Button variant="danger-fill" busy={busy === "delete"} onClick={() => act("delete")}>{t("install.deleteDownloaded")}</Button>
            </>
          }
        >
          <p>{t("install.deleteBody")}</p>
        </Dialog>
      )}
      {log && <LogDialog title={t("run.logTitle", { name: e.name })} lines={log} onClose={() => setLog(null)} />}
    </div>
  );
}

// 남은 시간 - 최근 8초 속도로 재고, 5초 넘게 바뀔 때만 고쳐 써요(components.md 10)
function useLeft(done: number, total: number, active: boolean): number | null {
  const samples = useRef<{ t: number; b: number }[]>([]);
  const last = useRef<number | null>(null);
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    if (!active) {
      samples.current = [];
      return;
    }
    const now = Date.now() / 1000;
    const xs = (samples.current = [...samples.current.filter((x) => now - x.t < 8), { t: now, b: done }]);
    if (xs.length < 2) return;
    const speed = (xs[xs.length - 1].b - xs[0].b) / Math.max(0.5, xs[xs.length - 1].t - xs[0].t);
    const v = speed > 0 ? (total - done) / speed : null;
    if (last.current == null || v == null || Math.abs(last.current - v) >= 5) {
      last.current = v;
      setLeft(v);
    }
  }, [done, total, active]);
  return active ? left : null;
}

function FailBox({ e, onRetry, busy, onLog }: { e: Engine; onRetry: () => void; busy: boolean; onLog: () => void }) {
  const kind = e.install.error?.kind ?? "unknown";
  const known = ["disk", "network", "dependency", "permission", "source", "selftest", "license", "driver", "wsl"].includes(kind) ? kind : "unknown";
  return (
    <div className="col" style={{ gap: 10 }}>
      <Banner tone="danger" title={t(`install.fail.${known}`)} body={has_help(known) ? t(`install.failHelp.${known}`) : undefined} />
      <div className="row">
        {known === "disk" ? (
          <Button variant="primary" onClick={() => go({ name: "installed", tab: "engines" })}>{t("install.failAction.disk")}</Button>
        ) : (
          <Button variant="primary" internet={known !== "selftest"} busy={busy} onClick={onRetry}>{t(`install.failAction.${known === "license" ? "unknown" : known}`)}</Button>
        )}
        <Button variant="link" className="right" onClick={onLog}>{t("common.showLog")}</Button>
      </div>
    </div>
  );
}

function has_help(kind: string) {
  return ["permission", "driver", "wsl", "dependency"].includes(kind);
}

function StepRow({ state, label, value }: { state: string; label: string; value?: string }) {
  return (
    <li className={state === "wait" ? "wait" : ""}>
      <span className={`step-ic ${state}`} aria-hidden>
        {state === "done" && <Check size={13} strokeWidth={3} />}
        {state === "fail" && <X size={13} strokeWidth={3} />}
        {state === "pause" && <Pause size={11} />}
      </span>
      <span className="grow">
        {label}
        <span className="sr-only"> · {t(`install.stepState.${state}`)}</span>
      </span>
      {value && <span className="num muted">{value}</span>}
    </li>
  );
}

// ---------- 설치됨 ----------
function Installed({ e, inWizard }: { e: Engine; inWizard?: boolean }) {
  const [rm, setRm] = useState(false);
  return (
    <div className="col" style={{ gap: 14 }}>
      <Banner tone="ok" title={t("install.installedTitle")} body={t("install.installedMeta", { disk: bytes(e.disk_bytes) })} />
      {!inWizard && <SelftestLines e={e} />}
      {!inWizard && (
        <div className="row">
          <Button variant="primary" onClick={() => go({ name: "try", engine: e.id })}>{t("install.tryIt")}</Button>
          <Button variant="ghost" className="right" onClick={() => setRm(true)}>{t("install.remove")}</Button>
        </div>
      )}
      {rm && <RemoveDialog e={e} onClose={() => setRm(false)} />}
    </div>
  );
}

export function SelftestLines({ e }: { e: Engine }) {
  const st = e.install.selftest;
  if (!st) return null;
  const texts = loc(e).selftest;
  return (
    <div className="col" style={{ gap: 10 }}>
      <div>
        <div className="t-h3">{t("install.selftestTitle")}</div>
        <div className="t-caption muted">{t("install.selftestNote")}</div>
      </div>
      {st.lines.map((l, i) => (
        <div key={i} className="col" style={{ gap: 4 }}>
          <div className="row t-body">
            <Check size={14} color="var(--success)" aria-hidden />
            <span lang="ko">{l.text}</span>
          </div>
          {texts?.[i] && <span className="t-caption muted">{texts[i]}</span>}
          <Player src={`/hub/engines/${e.id}/selftest/${i}.wav`} size="sm" label={l.text} bars={56} />
        </div>
      ))}
    </div>
  );
}

export function RemoveDialog({ e, onClose }: { e: Engine; onClose: () => void }) {
  const { refresh } = useHub();
  const toast = useToast();
  const [size, setSize] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ env: number; weights: number }>(`/hub/engines/${e.id}/disk`).then((d) => setSize(d.env + d.weights));
  }, [e.id]);
  return (
    <Dialog
      title={t("install.removeTitle", { name: e.name })}
      onClose={onClose}
      foot={
        <>
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            variant="danger-fill"
            busy={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await api<{ freed_bytes: number }>(`/hub/engines/${e.id}?part=all`, { method: "DELETE" });
                toast(t("install.removed", { name: e.name, size: bytes(r.freed_bytes) }));
                await refresh();
                onClose();
              } catch (x) {
                toast(errorText(x));
                setBusy(false);
              }
            }}
          >
            {t("install.removeConfirm", { size: size == null ? "…" : bytes(size) })}
          </Button>
        </>
      }
    >
      <p>{t("install.removeBody")}</p>
    </Dialog>
  );
}

export function LogDialog({ title, lines, onClose }: { title: string; lines: string[]; onClose: () => void }) {
  return (
    <Dialog
      wide
      title={title}
      onClose={onClose}
      foot={
        <>
          <Button variant="ghost" onClick={() => navigator.clipboard.writeText(lines.join("\n"))}>{t("common.copy")}</Button>
          <Button variant="primary" onClick={onClose}>{t("common.close")}</Button>
        </>
      }
    >
      <p className="t-caption muted" style={{ marginTop: 0 }}>{t("run.logNote")}</p>
      <div className="logview">
        {lines.length === 0
          ? t("run.eventsEmpty")
          : lines.map((l, i) => (
              <div key={i} className={/error|traceback|exception|failed|실패/i.test(l) ? "err" : ""}>{l}</div>
            ))}
      </div>
    </Dialog>
  );
}
