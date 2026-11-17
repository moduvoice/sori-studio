// H4 소리 만들기 - 모델·목소리를 골라 글을 바로 소리로(UX 리뷰 2026-11-17: 앱의 중심 화면, 이름을 "빠른 시험"에서 바꿈).
import { useEffect, useMemo, useState } from "react";
import { Download, Zap } from "lucide-react";
import { errorText, speech } from "../lib/api";
import { dec } from "../lib/format";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub } from "../lib/store";
import { Banner, Button, EmptyState } from "../components/ui";
import { installedOk, loc } from "../components/engine";
import { Player } from "../components/player";

type Made = { id: number; engine: string; voice: string; text: string; blob: Blob; genS: number; audioS: number; retries: number; suspect: string };

const recent: Made[] = []; // 화면을 옮겨 다녀도 이번 실행 동안은 남아요
let lastText: string | null = null; // 입력도 같이 남겨 "만든 소리" 와 어긋나지 않게(리뷰)
const MAX_INPUT = 5000;
type Pace = "slow" | "normal" | "fast";
const PACE: Record<Pace, number> = { slow: 0.85, normal: 1, fast: 1.15 };

export default function QuickTry({ engineId }: { engineId?: string }) {
  const { engines, refresh } = useHub();
  const ready = engines.filter(installedOk);
  const [eid, setEid] = useState(engineId ?? ready[0]?.id ?? "");
  const e = ready.find((x) => x.id === eid) ?? ready[0];
  const [voice, setVoice] = useState(e?.default_voice ?? "");
  const [text, setTextState] = useState(lastText ?? t("try.sample"));
  const setText = (v: string) => {
    lastText = v;
    setTextState(v);
  };
  const [busy, setBusy] = useState(false);
  const [pace, setPace] = useState<Pace>("normal");
  const [err, setErr] = useState<string | null>(null);
  const [made, setMade] = useState<Made | null>(recent[0] ?? null);
  const [, bump] = useState(0);

  useEffect(() => {
    if (engineId) setEid(engineId);
  }, [engineId]);
  useEffect(() => {
    if (e && !e.voices?.some((v) => v.id === voice)) setVoice(e.default_voice ?? e.voices?.[0]?.id ?? "");
  }, [e, voice]);

  const tooLong = text.length > MAX_INPUT;

  async function make() {
    if (!e || busy || !text.trim() || tooLong) return;
    setBusy(true);
    setErr(null);
    try {
      // 속도는 엔진 기본 빠르기에 곱해요(엔진마다 "보통"이 달라요)
      const sp = e.speed ? Math.min(e.speed.max, Math.max(e.speed.min, e.speed.default * PACE[pace])) : undefined;
      const r = await speech(e.id, text.trim(), voice, 0, sp);
      const v = e.voices?.find((x) => x.id === voice);
      const m: Made = { id: Date.now(), engine: e.name, voice: v ? loc(e).voice(v) : voice, text: text.trim(), ...r };
      recent.unshift(m);
      recent.splice(5);
      setMade(m);
      bump((n) => n + 1);
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
      refresh();
    }
  }

  // 저장 단추용 주소 - 그릴 때마다 새로 만들지 않고, 바뀌면 옛 주소를 풀어요(리뷰: 메모리 누수)
  const madeUrl = useMemo(() => (made ? URL.createObjectURL(made.blob) : null), [made]);
  useEffect(() => () => { if (madeUrl) URL.revokeObjectURL(madeUrl); }, [madeUrl]);

  if (!e)
    return (
      <div className="page narrow">
        <h1 className="t-h1">{t("try.title")}</h1>
        <EmptyState
          icon={<Zap size={20} />}
          title={t("try.empty")}
          body={t("try.emptyBody")}
          action={<Button variant="primary" size="lg" icon={<Download size={16} />} onClick={() => go({ name: "models" })}>{t("try.goModels")}</Button>}
        />
      </div>
    );

  const L = loc(e);
  const main = e.voices?.filter((v) => !v.extra) ?? [];
  const extra = e.voices?.filter((v) => v.extra) ?? [];
  const cold = e.run.state !== "ready";
  return (
    <div className="page narrow">
      <div className="page-head">
        <h1 className="t-h1 grow">{t("try.title")}</h1>
      </div>
      <section className="card card-pad col" style={{ gap: 16 }}>
        <div className="row row-wrap" style={{ gap: 16 }}>
          <label className="col" style={{ gap: 4 }}>
            <span className="t-label">{t("try.engine")}</span>
            <select className="field" value={e.id} onChange={(ev) => setEid(ev.target.value)}>
              {ready.map((x) => (
                <option key={x.id} value={x.id}>{x.name}</option>
              ))}
            </select>
          </label>
          <label className="col" style={{ gap: 4 }}>
            <span className="t-label">{t("try.voice")}</span>
            <select className="field" value={voice} onChange={(ev) => setVoice(ev.target.value)}>
              {main.map((v) => (
                <option key={v.id} value={v.id}>{L.voice(v)}</option>
              ))}
              {extra.length > 0 && (
                <optgroup label={t("try.extraVoices")}>
                  {extra.map((v) => (
                    <option key={v.id} value={v.id}>{L.voice(v)}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
          {e.speed && (
            <label className="col" style={{ gap: 4 }}>
              <span className="t-label">{t("try.speed")}</span>
              <select className="field" value={pace} onChange={(ev) => setPace(ev.target.value as Pace)}>
                {(["slow", "normal", "fast"] as Pace[]).map((p) => (
                  <option key={p} value={p}>{t(`try.pace.${p}`)}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        <label className="col" style={{ gap: 4 }}>
          <span className="t-label">{t("try.text")}</span>
          <textarea
            className={`field ${tooLong ? "err" : ""}`}
            rows={5}
            lang="ko"
            value={text}
            placeholder={t("try.placeholder")}
            onChange={(ev) => setText(ev.target.value)}
            onKeyDown={(ev) => {
              if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
                ev.preventDefault();
                make();
              }
            }}
          />
          {tooLong && <span className="t-caption" style={{ color: "var(--danger)" }}>{t("try.tooLong", { max: MAX_INPUT })}</span>}
        </label>
        <div className="row">
          <Button variant="primary" size="lg" busy={busy} disabled={!text.trim() || tooLong} onClick={make} title={t("try.shortcut")}>
            {busy ? t("try.making") : t("try.make")}
          </Button>
          {busy && cold && <span className="t-caption muted">{e.runtime === "wsl" && e.devices.cpu === "no" ? t("try.serverLoad") : t("try.firstLoad")}</span>}
        </div>
        {err && <Banner tone="danger" title={err} />}
      </section>

      {made && (
        <section className="card card-pad col" style={{ gap: 12 }} aria-live="polite">
          <div className="row">
            <h2 className="t-h3">{t("try.result")}</h2>
            <span className="t-caption muted num right">{t("try.resultMeta", { audio: dec(made.audioS), gen: dec(made.genS) })}</span>
          </div>
          <Player src={made.blob} size="lg" label={made.text} bars={96} />
          {made.suspect ? (
            <Banner tone="warning" title={t("try.suspect")} />
          ) : made.retries > 0 ? (
            <span className="t-caption muted">{t("try.retried", { n: made.retries })}</span>
          ) : null}
          <div className="row">
            <span className="t-caption muted grow ellipsis">{made.engine} · {made.voice} · “{made.text}”</span>
            <a className="btn btn-secondary btn-sm" href={madeUrl ?? undefined} download={`sori-${made.engine}-${made.voice}.wav`.replace(/\s+/g, "_")}>
              {t("common.save")}
            </a>
          </div>
        </section>
      )}

      {recent.length > 1 && (
        <section className="card card-pad col" style={{ gap: 8 }}>
          <h2 className="t-h3">{t("try.recent")}</h2>
          {recent.slice(1).map((m) => (
            <div key={m.id} className="col" style={{ gap: 2 }}>
              <span className="t-caption muted ellipsis">{m.engine} · {m.voice} · “{m.text}”</span>
              <Player src={m.blob} size="sm" label={m.text} bars={64} />
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
