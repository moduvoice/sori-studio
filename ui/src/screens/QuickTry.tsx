// H4 소리 만들기 - 세 칸 작업 화면(rebuild-2026-11.md 3-3): 왼쪽 목소리 · 가운데 대본과 [만들기] 막대 · 오른쪽 만든 소리.
// UX 리뷰(2026-11-17): 앱의 중심 화면. 하는 일은 그대로예요(모델·목소리·속도를 골라 글을 소리로, 저장, 방금 만든 것).
import { useEffect, useMemo, useState } from "react";
import { AudioLines, Box, Check, Download, Gauge, Users } from "lucide-react";
import { errorText, speech } from "../lib/api";
import { dec } from "../lib/format";
import { t } from "../lib/i18n";
import { addMade, draft, recent, type Made } from "../lib/made";
import { go } from "../lib/router";
import { useHub } from "../lib/store";
import { Banner, Button, EmptyState, Kbd } from "../components/ui";
import { Avatar, EmptyWave, GIcon, type Hue } from "../components/art";
import { installedOk, loc } from "../components/engine";
import { Player } from "../components/player";

const MAX_INPUT = 5000;
type Pace = "slow" | "normal" | "fast";
const PACE: Record<Pace, number> = { slow: 0.85, normal: 1, fast: 1.15 };
type Voice = { id: string; name: string; name_en?: string; gender?: string; extra?: boolean };
const voiceHue = (v?: Voice): Hue | undefined => (v?.gender === "f" ? "pink" : v?.gender === "m" ? "blue" : undefined);

export default function QuickTry({ engineId }: { engineId?: string }) {
  const { engines, refresh } = useHub();
  const ready = engines.filter(installedOk);
  const [eid, setEid] = useState(engineId ?? ready[0]?.id ?? "");
  const e = ready.find((x) => x.id === eid) ?? ready[0];
  const [voice, setVoice] = useState(e?.default_voice ?? "");
  const [text, setTextState] = useState(draft.text ?? t("try.sample"));
  const setText = (v: string) => {
    draft.text = v;
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
      addMade(m);
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
        <EmptyState
          icon={<GIcon size="lg"><AudioLines size={24} /></GIcon>}
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
  const cur = e.voices?.find((v) => v.id === voice);
  const curName = cur ? L.voice(cur) : voice;
  const sub = (v: Voice) => [v.gender === "f" || v.gender === "m" ? t(`try.gender.${v.gender}`) : null, e.name].filter(Boolean).join(" · ");
  const item = (v: Voice) => (
    <button key={v.id} type="button" role="radio" aria-checked={v.id === voice} className="voice" onClick={() => setVoice(v.id)}>
      <Avatar name={L.voice(v)} seed={v.id} hue={voiceHue(v)} />
      <span className="grow col" style={{ gap: 0 }}>
        <span className="nm ellipsis">{L.voice(v)}</span>
        <span className="sub ellipsis">{sub(v)}</span>
      </span>
      {v.id === voice && <Check className="tick" size={16} aria-hidden />}
    </button>
  );

  return (
    <div className="workspace">
      <section className="pane pane-voices" aria-label={t("try.voice")}>
        <div className="pane-head">
          <span className="ic" aria-hidden><Users size={16} /></span>
          <span>{t("try.voice")}</span>
          <span className="count">{e.voices?.length ?? 0}</span>
        </div>
        <div className="pane-body" role="radiogroup" aria-label={t("try.voice")}>
          {main.map(item)}
          {extra.length > 0 && (
            <>
              <div className="voice-group">{t("try.extraVoices")}</div>
              {extra.map(item)}
            </>
          )}
        </div>
      </section>

      <section className="pane pane-script" aria-label={t("try.title")}>
        <div className="script-head">
          <Avatar name={curName || "?"} seed={voice} hue={voiceHue(cur)} size="lg" />
          <div className="who">
            <small>{t("try.voice")}</small>
            <b className="ellipsis">{curName}</b>
          </div>
        </div>
        <textarea
          className="script-text"
          lang="ko"
          value={text}
          aria-label={t("try.text")}
          aria-invalid={tooLong || undefined}
          placeholder={t("try.placeholder")}
          onChange={(ev) => setText(ev.target.value)}
          onKeyDown={(ev) => {
            if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
              ev.preventDefault();
              make();
            }
          }}
        />
        <div className="script-meta">
          {busy && cold && <span>{e.runtime === "wsl" && e.devices.cpu === "no" ? t("try.serverLoad") : t("try.firstLoad")}</span>}
          {tooLong && <span className="bad">{t("try.tooLong", { max: MAX_INPUT })}</span>}
          <span className={`right num ${tooLong ? "bad" : ""}`}>{t("try.chars", { n: text.length })}</span>
        </div>
        {err && (
          <div className="script-alert">
            <Banner tone="danger" title={err} />
          </div>
        )}
        <div className="composer">
          <label className="pick" title={t("try.engine")}>
            <Box size={15} aria-hidden />
            <select value={e.id} onChange={(ev) => setEid(ev.target.value)} aria-label={t("try.engine")}>
              {ready.map((x) => (
                <option key={x.id} value={x.id}>{x.name}</option>
              ))}
            </select>
          </label>
          {e.speed && (
            <label className="pick" title={t("try.speed")}>
              <Gauge size={15} aria-hidden />
              <select value={pace} onChange={(ev) => setPace(ev.target.value as Pace)} aria-label={t("try.speed")}>
                {(["slow", "normal", "fast"] as Pace[]).map((p) => (
                  <option key={p} value={p}>{t(`try.pace.${p}`)}</option>
                ))}
              </select>
            </label>
          )}
          <Button variant="primary" size="lg" busy={busy} disabled={!text.trim() || tooLong} onClick={make} title={t("try.shortcut")} icon={<AudioLines size={16} />}>
            {busy ? t("try.making") : t("try.make")}
            {!busy && (
              <span className="row" style={{ gap: 3, marginLeft: 6 }} aria-hidden>
                <Kbd>Ctrl</Kbd>
                <Kbd>↵</Kbd>
              </span>
            )}
          </Button>
        </div>
      </section>

      <section className="pane pane-result" aria-label={t("try.result")} aria-live="polite">
        <div className="pane-head">
          <span className="ic" aria-hidden><AudioLines size={16} /></span>
          <span>{t("try.result")}</span>
        </div>
        {!made ? (
          <div className="result-empty">
            <EmptyWave />
            <span>{t("try.resultEmpty")}</span>
          </div>
        ) : (
          <div className="result-body">
            <div className="result-card">
              <div className="row" style={{ gap: 10 }}>
                <Avatar name={made.voice} size="sm" />
                <span className="grow col" style={{ gap: 0 }}>
                  <b className="ellipsis">{made.voice}</b>
                  <span className="t-caption muted ellipsis">{made.engine}</span>
                </span>
                <a className="btn btn-secondary btn-sm" href={madeUrl ?? undefined} download={`sori-${made.engine}-${made.voice}.wav`.replace(/\s+/g, "_")}>
                  <Download size={14} aria-hidden />
                  {t("common.save")}
                </a>
              </div>
              <Player src={made.blob} size="lg" label={made.text} bars={64} />
              <div className="result-text">“{made.text}”</div>
              <span className="t-caption muted num">{t("try.resultMeta", { audio: dec(made.audioS), gen: dec(made.genS) })}</span>
              {made.suspect ? (
                <Banner tone="warning" title={t("try.suspect")} />
              ) : made.retries > 0 ? (
                <span className="t-caption muted">{t("try.retried", { n: made.retries })}</span>
              ) : null}
            </div>
            {recent.length > 1 && (
              <div className="col" style={{ gap: 0 }}>
                <h2 className="t-h3" style={{ margin: "4px 0 6px" }}>{t("try.recent")}</h2>
                {recent.slice(1).map((m) => (
                  <div key={m.id} className="recent-item">
                    <span className="t-caption muted ellipsis">{m.engine} · {m.voice} · “{m.text}”</span>
                    <Player src={m.blob} size="sm" label={m.text} bars={56} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
