// H1 모델(카탈로그) - 목록 줄(rebuild-2026-11.md 3-4): 이름·한 줄 설명·배지·크기·[받기]. 펼치면 평·사용 조건, 줄을 누르면 상세.
import { useMemo, useState } from "react";
import { AudioLines, Check, ChevronRight, Download, Search } from "lucide-react";
import type { Engine } from "../lib/api";
import { bytes } from "../lib/format";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub } from "../lib/store";
import { Badge, Button, EmptyState, IconButton, Progress } from "../components/ui";
import { Avatar } from "../components/art";
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
          <p>{t("catalog.sub")}</p>
        </div>
      </div>

      <div className="toolbar">
        <Chip on={onlyHere} set={setOnlyHere}>{t("catalog.onlyHere")}</Chip>
        <label className="search right">
          <Search size={15} aria-hidden />
          <input className="field" placeholder={t("catalog.search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("catalog.search")} />
        </label>
      </div>

      {!loaded ? (
        <div className="list">{[0, 1, 2].map((i) => <div key={i} className="lrow" style={{ height: 72 }} />)}</div>
      ) : shown.length === 0 ? (
        <div className="list">
          <EmptyState
            icon={<Search size={22} />}
            title={t("catalog.empty")}
            action={<Button onClick={() => { setOnlyHere(false); setQ(""); }}>{t("catalog.clearFilters")}</Button>}
          />
        </div>
      ) : (
        <div className="list">
          {shown.map((e) => <EngineRow key={e.id} e={e} />)}
        </div>
      )}
      {hidden > 0 && (
        <Button variant="link" style={{ marginTop: 14 }} onClick={() => setOnlyHere(false)}>
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

function EngineRow({ e }: { e: Engine }) {
  const [more, setMore] = useState(false);
  const s = e.install.status;
  const p = e.install.progress;
  const runnable = isRunnable(e.this_pc);
  const L = loc(e);
  const open = () => go({ name: "model", id: e.id });
  const pctDone = p && p.bytes_total ? Math.floor((p.bytes_done / p.bytes_total) * 100) : 0;
  return (
    <div className="lrow-wrap">
      <div
        className={`lrow click ${s === "failed" ? "failed" : ""} ${runnable ? "" : "dim"}`}
        onClick={open}
        onKeyDown={(ev) => ev.key === "Enter" && ev.target === ev.currentTarget && open()}
        tabIndex={0}
        role="link"
        aria-label={e.name}
      >
        <span onClick={(ev) => ev.stopPropagation()}>
          <IconButton label={t("catalog.more")} aria-expanded={more} onClick={() => setMore(!more)}>
            <ChevronRight size={16} className={`chev ${more ? "open" : ""}`} />
          </IconButton>
        </span>
        <Avatar name={e.name} seed={e.id} />
        <div className="lrow-main">
          <div className="lrow-title">
            <span>{e.name}</span>
            <EvidenceBadge e={e} />
            <LicenseBadge e={e} />
            <MaintBadge e={e} />
            <RuntimeBadge e={e} />
          </div>
          <div className="lrow-sub">{[e.maker, ...(L.good_for ?? [])].filter(Boolean).join(" · ")}</div>
          <div className="lrow-sub"><VerdictStatus v={e.this_pc} /></div>
        </div>
        <div className="lrow-side" onClick={(ev) => ev.stopPropagation()}>
          {s === "installing" ? (
            <div className="col" style={{ gap: 4, width: 160 }}>
              <Progress value={p && p.bytes_total ? p.bytes_done / p.bytes_total : 0} label={t("install.status.installing")} />
              <span className="t-caption muted num">{t("installed.installing", { pct: pctDone })}</span>
            </div>
          ) : s === "installed" || s === "update" ? (
            <>
              <Badge tone="ok" icon={<Check size={13} aria-hidden />}>{t("badge.installed")}</Badge>
              <span className="lrow-size">{bytes(e.disk_bytes)}</span>
              <Button variant="primary" size="sm" icon={<AudioLines size={14} />} onClick={() => go({ name: "try", engine: e.id })}>{t("install.tryIt")}</Button>
            </>
          ) : s === "paused" || s === "failed" ? (
            <>
              <span className="t-caption" style={{ color: s === "failed" ? "var(--danger)" : "var(--ink-500)" }}>
                {s === "failed" ? t("catalog.failedCard") : t("install.status.paused")}
              </span>
              <Button size="sm" onClick={open}>{t("catalog.resume")}</Button>
            </>
          ) : (
            <>
              <span className="lrow-size">{bytes(e.download_bytes)}</span>
              <Button size="sm" icon={runnable ? <Download size={14} /> : undefined} onClick={open}>{runnable ? t("catalog.download") : t("common.details")}</Button>
            </>
          )}
        </div>
      </div>
      {more && (
        <div className="lrow-more">
          {L.human_eval_line ? <p className="quote">“{L.human_eval_line}”</p> : <p className="muted" style={{ margin: 0 }}>{L.summary}</p>}
          <div className="col" style={{ gap: 4 }}>
            <span className="t-label muted">{t("install.licenseTitle")} · {e.license.name}</span>
            <ul>
              {L.license_summary.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
