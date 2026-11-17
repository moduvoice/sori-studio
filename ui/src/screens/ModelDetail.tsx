// H2 모델 상세·설치 - 왼쪽 정보, 오른쪽 설치 패널(design.md H2)
import { useEffect } from "react";
import { Archive } from "lucide-react";
import { openExternal, type Engine } from "../lib/api";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub } from "../lib/store";
import { dec } from "../lib/format";
import { Avatar } from "../components/art";
import { EvidenceBadge, LicenseBadge, MaintBadge, RuntimeBadge, VerdictStatus, loc, measuredAt } from "../components/engine";
import { InstallPanel } from "../components/install";

export default function ModelDetail({ id }: { id: string }) {
  const { engine, loaded } = useHub();
  const e = engine(id);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape" && !document.querySelector(".scrim")) go({ name: "models" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!e) return <div className="page muted">{loaded ? t("detail.notFound") : t("common.loading")}</div>;
  return (
    <div className="page detail">
      <header className="detail-head">
        <Avatar name={e.name} seed={e.id} size="lg" />
        <div className="grow col" style={{ gap: 8 }}>
          <div className="row row-wrap" style={{ gap: 8 }}>
            <h1 style={{ marginRight: 6 }}>{e.name}</h1>
            <EvidenceBadge e={e} />
            <LicenseBadge e={e} />
            <MaintBadge e={e} />
            <RuntimeBadge e={e} />
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 15, lineHeight: "24px", maxWidth: 720 }}>{loc(e).summary}</p>
          <VerdictStatus v={e.this_pc} />
        </div>
      </header>

      <div className="detail-grid">
        <div>
          <Quality e={e} />
          <Abilities e={e} />
          {e.maintenance?.status === "archived" && <Maintenance e={e} />}
          <Source e={e} />
        </div>
        <aside>
          <InstallPanel e={e} />
        </aside>
      </div>
    </div>
  );
}

function Quality({ e }: { e: Engine }) {
  const m = e.measured;
  const L = loc(e);
  return (
    <section className="card card-pad">
      <h2 className="t-h2" style={{ marginBottom: 12 }}>{t("detail.quality")}</h2>
      {L.human_eval_line && (
        <>
          <p className="quote">“{L.human_eval_line}”</p>
          <p className="t-caption muted" style={{ margin: "6px 0 16px 16px" }}>{L.human_eval_by}</p>
        </>
      )}
      {(m.cer_ko != null || m.hallu) && (
        <>
          <div className="tiles">
            {m.cer_ko != null && <Tile label={t("detail.cerLabel")} value={`${dec(m.cer_ko * 100, 2)}%`} help={t("detail.cerHelp")} />}
            {m.hallu && <Tile label={t("detail.halluLabel")} value={t("detail.halluValue", { v: m.hallu })} help={t("detail.halluHelp")} />}
          </div>
          {m.at && <p className="t-caption muted" style={{ margin: "12px 0 0" }}>{t("detail.measuredAt", { date: measuredAt(e) })}</p>}
        </>
      )}
      {!L.human_eval_line && m.cer_ko == null && !m.hallu && <p className="muted" style={{ margin: 0 }}>{t("detail.noQuality")}</p>}
    </section>
  );
}

function Tile({ label, value, help }: { label: string; value: string; help: string }) {
  return (
    <div className="tile">
      <div className="t-caption muted">{label}</div>
      <div className="v">{value}</div>
      <div className="t-caption muted">{help}</div>
    </div>
  );
}

function Abilities({ e }: { e: Engine }) {
  const f = e.voices?.filter((v) => v.gender === "f").length ?? 0;
  const m = e.voices?.filter((v) => v.gender === "m").length ?? 0;
  const good = loc(e).good_for;
  return (
    <section className="card card-pad">
      <h2 className="t-h2" style={{ marginBottom: 8 }}>{t("detail.voices")}</h2>
      <p style={{ margin: "0 0 12px" }}>{t("detail.voicesBody", { n: e.voices?.length ?? 0, f, m })}</p>
      {good && good.length > 0 && (
        <>
          <div className="t-label muted" style={{ marginBottom: 8 }}>{t("detail.goodFor")}</div>
          <div className="row row-wrap" style={{ gap: 6 }}>
            {good.map((g) => <span key={g} className="badge badge-accent">{g}</span>)}
          </div>
        </>
      )}
    </section>
  );
}

function Maintenance({ e }: { e: Engine }) {
  const mt = e.maintenance!;
  return (
    <section className="card card-pad">
      <h2 className="t-h2 row" style={{ marginBottom: 8 }}>
        <Archive size={18} aria-hidden /> {t("detail.maintenance")}
      </h2>
      <p style={{ margin: "0 0 4px" }}>
        <strong>{t("badge.archived")}</strong> · {t("detail.archivedSince", { date: mt.since ?? "" })}
      </p>
      <p className="muted" style={{ margin: "0 0 8px" }}>{loc(e).maintenance_note}</p>
      {mt.archive_url && (
        <button className="btn btn-link" onClick={() => openExternal(mt.archive_url!)}>
          {t("detail.archiveUrl")}
        </button>
      )}
    </section>
  );
}

function Source({ e }: { e: Engine }) {
  return (
    <details className="more card card-pad">
      <summary>{t("detail.source")}</summary>
      <dl className="kv" style={{ marginTop: 8 }}>
        <dt>{t("detail.weightsFrom")}</dt>
        <dd className="t-mono">{e.weights_sources.map((s) => s.repo).join(", ")}</dd>
        {e.homepage && (
          <>
            <dt>{t("detail.homepage")}</dt>
            <dd><button className="btn btn-link" onClick={() => openExternal(e.homepage!)}>{e.homepage.replace(/^https:\/\//, "")}</button></dd>
          </>
        )}
      </dl>
    </details>
  );
}
