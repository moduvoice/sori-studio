// H1 모델(카탈로그) - design.md 5절 H1, components.md 4
import { useMemo, useState } from "react";
import { Check, Search } from "lucide-react";
import type { Engine } from "../lib/api";
import { bytes } from "../lib/format";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub } from "../lib/store";
import { Badge, Button, EmptyState, Progress } from "../components/ui";
import { EvidenceBadge, LicenseBadge, MaintBadge, RuntimeBadge, VerdictStatus, isRunnable, loc } from "../components/engine";

export default function Catalog() {
  const { engines, loaded } = useHub();
  const [onlyHere, setOnlyHere] = useState(true);
  const [q, setQ] = useState("");

  const { shown, hidden } = useMemo(() => {
    const k = q.trim().toLowerCase();
    const ok = (e: Engine) =>
      !k || `${e.name} ${e.maker ?? ""} ${loc(e).summary ?? ""}`.toLowerCase().includes(k);
    const base = engines.filter(ok);
    const here = base.filter((e) => isRunnable(e.this_pc));
    return onlyHere ? { shown: here, hidden: base.length - here.length } : { shown: base, hidden: 0 };
  }, [engines, q, onlyHere]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="grow">
          <h1 className="t-h1">{t("catalog.title")}</h1>
          <p className="muted" style={{ margin: "4px 0 0" }}>{t("catalog.sub")}</p>
        </div>
      </div>

      <div className="row row-wrap" style={{ marginBottom: 20, gap: 8 }}>
        <Chip on={onlyHere} set={setOnlyHere}>{t("catalog.onlyHere")}</Chip>
        <label className="row right" style={{ gap: 6 }}>
          <Search size={16} className="muted" aria-hidden />
          <input className="field" placeholder={t("catalog.search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("catalog.search")} style={{ width: 200 }} />
        </label>
      </div>

      {!loaded ? (
        <div className="grid-cards">{[0, 1].map((i) => <div key={i} className="card card-pad" style={{ height: 220, background: "var(--sunken)" }} />)}</div>
      ) : shown.length === 0 ? (
        <EmptyState
          icon={<Search size={20} />}
          title={t("catalog.empty")}
          action={<Button onClick={() => { setOnlyHere(false); setQ(""); }}>{t("catalog.clearFilters")}</Button>}
        />
      ) : (
        <div className="grid-cards">
          {shown.map((e) => <EngineCard key={e.id} e={e} />)}
        </div>
      )}
      {hidden > 0 && (
        <Button variant="link" style={{ marginTop: 12 }} onClick={() => setOnlyHere(false)}>
          {t("catalog.hidden", { n: hidden })}
        </Button>
      )}
    </div>
  );
}

function Chip({ on, set, children }: { on: boolean; set: (v: boolean) => void; children: string }) {
  return (
    <button className="chip" aria-pressed={on} onClick={() => set(!on)}>
      {on && <Check size={14} aria-hidden />}
      {children}
    </button>
  );
}

function EngineCard({ e }: { e: Engine }) {
  const s = e.install.status;
  const p = e.install.progress;
  const runnable = isRunnable(e.this_pc);
  const open = () => go({ name: "model", id: e.id });
  return (
    <article
      className={`card engine-card ${s === "failed" ? "failed" : ""} ${runnable ? "" : "dim"}`}
      onClick={open}
      onKeyDown={(ev) => ev.key === "Enter" && ev.target === ev.currentTarget && open()}
      tabIndex={0}
      aria-label={e.name}
    >
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="grow">
          <h2 className="t-h2">{e.name}</h2>
          <div className="t-caption muted">{[e.maker, ...(loc(e).good_for ?? [])].filter(Boolean).join(" · ")}</div>
        </div>
        <EvidenceBadge e={e} />
      </div>
      <VerdictStatus v={e.this_pc} />
      {loc(e).human_eval_line ? <p className="quote">“{loc(e).human_eval_line}”</p> : <p className="t-caption muted" style={{ margin: 0 }}>{loc(e).summary}</p>}
      <div className="row row-wrap" style={{ gap: 6 }}>
        <LicenseBadge e={e} />
        <MaintBadge e={e} />
        <RuntimeBadge e={e} />
      </div>
      <div className="card-foot" onClick={(ev) => ev.stopPropagation()}>
        {s === "installing" ? (
          <div className="col grow" style={{ gap: 4 }}>
            <Progress value={p && p.bytes_total ? p.bytes_done / p.bytes_total : 0} label={t("install.status.installing")} />
            <span className="t-caption muted num">
              {t("installed.installing", { pct: p && p.bytes_total ? Math.floor((p.bytes_done / p.bytes_total) * 100) : 0 })}
            </span>
          </div>
        ) : s === "installed" || s === "update" ? (
          <>
            <Badge tone="ok" icon={<Check size={13} aria-hidden />}>{t("badge.installed")}</Badge>
            <span className="t-caption muted num">{bytes(e.disk_bytes)}</span>
            <Button className="right" size="sm" onClick={() => go({ name: "try", engine: e.id })}>{t("install.tryIt")}</Button>
          </>
        ) : s === "paused" || s === "failed" ? (
          <>
            <span className={`t-caption ${s === "failed" ? "" : "muted"}`} style={s === "failed" ? { color: "var(--danger)" } : undefined}>
              {s === "failed" ? t("catalog.failedCard") : t("install.status.paused")}
            </span>
            <Button className="right" size="sm" onClick={open}>{t("catalog.resume")}</Button>
          </>
        ) : (
          <>
            <span className="t-caption muted num">{bytes(e.download_bytes)}</span>
            <Button className="right" size="sm" onClick={open}>{runnable ? t("catalog.download") : t("common.details")}</Button>
          </>
        )}
      </div>
    </article>
  );
}
