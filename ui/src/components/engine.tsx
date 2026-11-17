// 엔진 배지·판정·실행 상태 - design.md 8절의 말 그대로, 색만으로 뜻을 전하지 않아요.
import { Archive, FileBadge } from "lucide-react";
import type { Engine, RunState, Verdict } from "../lib/api";
import { date } from "../lib/format";
import { t, has, lang } from "../lib/i18n";
import { Badge, StatusDot, type Tone, useNow } from "./ui";

const VERDICT_TONE: Record<Verdict["verdict"], Tone> = {
  gpu_ok: "ok",
  cpu_ok: "ok",
  cpu_slow: "warn",
  tight: "warn",
  no: "bad",
  unverified: "gray",
};

export function verdictText(v: Verdict): { label: string; reason: string } {
  const key = `verdict.reason.${v.reason}`;
  // "CPU 로 느리게 돌아요 · 맞는 GPU 가 없어 CPU 로 돌아요" 처럼 같은 말을 두 번 하지 않게
  const reason = v.reason && v.reason !== "no_fitting_gpu" && has(key) ? t(key, { need: (v as { need_driver?: number }).need_driver ?? v.need_gb ?? "" }) : "";
  return { label: t(`verdict.${v.verdict}`), reason };
}

export function VerdictStatus({ v, withReason = true }: { v: Verdict; withReason?: boolean }) {
  const { label, reason } = verdictText(v);
  return (
    <StatusDot tone={VERDICT_TONE[v.verdict]} tip={v.verdict === "unverified" ? t("verdict.unverifiedTip") : reason || undefined}>
      {label}
      {withReason && reason && <span className="muted"> · {reason}</span>}
    </StatusDot>
  );
}

export function isRunnable(v: Verdict) {
  return v.verdict !== "no";
}

export function LicenseBadge({ e }: { e: Engine }) {
  const c = e.license.commercial ?? "unknown";
  const icon = <FileBadge size={13} aria-hidden />;
  if (c === "yes") return <Badge icon={icon} tip={e.license.name}>{t("badge.commercial")}</Badge>;
  if (c === "conditional")
    return (
      <Badge tone="warn" icon={icon} tip={`${e.license.name} · ${t("badge.conditionalTip")}`}>
        {t("badge.conditional")}
      </Badge>
    );
  if (c === "noncommercial") return <Badge tone="danger" icon={icon} tip={e.license.name}>{t("badge.noncommercial")}</Badge>;
  return <Badge tone="gray" icon={icon} tip={t("badge.licenseUnknownTip")}>{t("badge.licenseUnknown")}</Badge>;
}

export function MaintBadge({ e }: { e: Engine }) {
  if (e.maintenance?.status !== "archived") return null;
  return (
    <Badge tone="gray" icon={<Archive size={13} aria-hidden />} tip={t("badge.archivedTip")}>
      {t("badge.archived")}
    </Badge>
  );
}

export function RuntimeBadge({ e }: { e: Engine }) {
  if (e.runtime !== "wsl") return null;
  return <Badge tone="gray" tip={t("wsl.badgeTip")}>{t("wsl.badge")}</Badge>;
}

// 사람이 들어 본 엔진만 표시해요(측정됨·미검증 같은 구분은 첫 판에서 뺐어요 - UX 리뷰)
export function EvidenceBadge({ e }: { e: Engine }) {
  if (!e.human_eval) return null;
  return <Badge tip={t("badge.verifiedTip")}>{t("badge.verified")}</Badge>;
}

const RUN_TONE: Record<RunState, Tone> = {
  stopped: "gray",
  loading: "accent",
  ready: "ok",
  idle: "gray",
  restarting: "warn",
  stalled: "warn",
  dead: "bad",
};

export function RunStatus({ e }: { e: Engine }) {
  const now = useNow();
  const s = e.run.state;
  let extra = "";
  if (s === "restarting" && e.run.error?.attempt) {
    const left = Math.max(0, Math.round((e.run.error.retry_at ?? now) - now));
    extra = t("run.restartingDetail", { n: e.run.error.attempt, s: left });
  }
  return (
    <StatusDot tone={RUN_TONE[s]} spin={s === "loading" || s === "restarting"} tip={e.run.error?.message}>
      {t(`run.${s}`)}
      {extra && <span className="muted"> · {extra}</span>}
    </StatusDot>
  );
}

// 레시피의 사람 말(요약·평·라이선스 요약·목소리 이름)을 화면 언어로. 레시피 i18n.<언어> 에 없으면 원문(한국어).
export function loc(e: Engine) {
  const x = (e.i18n?.[lang()] ?? {}) as NonNullable<Engine["i18n"]>[string];
  return {
    summary: x.summary ?? e.summary,
    good_for: x.good_for ?? e.good_for,
    human_eval_line: x.human_eval_line ?? e.human_eval?.line,
    human_eval_by: x.human_eval_by ?? e.human_eval?.by,
    license_summary: x.license_summary ?? e.license.summary,
    maintenance_note: x.maintenance_note ?? e.maintenance?.note,
    voice: (v: { id: string; name: string; name_en?: string }) => x.voices?.[v.id] ?? ((lang() !== "ko" && v.name_en) || v.name),
    selftest: x.selftest, // 자가 시험 문장(한국어)의 뜻 - 한국어 화면에서는 없어요
  };
}

export function installedOk(e: Engine) {
  return e.install.status === "installed" || e.install.status === "update";
}

export function measuredAt(e: Engine) {
  return date(e.measured.at);
}
