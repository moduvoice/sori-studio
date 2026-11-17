// 소리 듣기 + 파형(components.md 9). 한 번에 하나만 재생해요. 사용자가 누를 때만 소리가 나요.
import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { getToken } from "../lib/api";
import { t } from "../lib/i18n";

let current: HTMLAudioElement | null = null;

async function peaksOf(blob: Blob, n: number): Promise<number[]> {
  try {
    const ctx = new AudioContext();
    const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
    ctx.close();
    const ch = buf.getChannelData(0);
    const step = Math.max(1, Math.floor(ch.length / n));
    const out: number[] = [];
    for (let i = 0; i < n; i++) {
      let m = 0;
      for (let j = i * step; j < Math.min(ch.length, (i + 1) * step); j += 8) m = Math.max(m, Math.abs(ch[j]));
      out.push(m);
    }
    const max = Math.max(...out, 0.01);
    return out.map((v) => Math.max(0.06, v / max));
  } catch {
    return Array(n).fill(0.1);
  }
}

/** src 가 Blob 이면 그대로, 문자열이면 토큰을 붙여 받아요(허브 주소). */
export function Player({ src, size = "md", label, bars = 72, onReady }: { src: Blob | string | null; size?: "sm" | "md" | "lg"; label: string; bars?: number; onReady?: (b: Blob) => void }) {
  const [blob, setBlob] = useState<Blob | null>(null);
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const audio = useRef<HTMLAudioElement | null>(null);
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);

  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  useEffect(() => {
    let dead = false;
    setPeaks(null);
    setPos(0);
    if (!src) return;
    (async () => {
      const b = typeof src === "string" ? await fetch(src, { headers: { Authorization: `Bearer ${getToken()}` } }).then((r) => (r.ok ? r.blob() : null)) : src;
      if (!b || dead) return;
      setBlob(b);
      onReady?.(b);
      setPeaks(await peaksOf(b, bars));
    })();
    return () => {
      dead = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, bars]);

  useEffect(() => () => audio.current?.pause(), []);

  function toggle(at?: number) {
    if (!url) return;
    if (!audio.current) {
      const a = new Audio(url);
      a.ontimeupdate = () => setPos(a.duration ? a.currentTime / a.duration : 0);
      a.onended = () => {
        setPlaying(false);
        setPos(0);
      };
      a.onpause = () => setPlaying(false);
      a.onplay = () => setPlaying(true);
      audio.current = a;
    }
    const a = audio.current;
    if (at != null && a.duration) a.currentTime = at * a.duration;
    if (a.paused || at != null) {
      if (current && current !== a) current.pause();
      current = a;
      a.play();
    } else a.pause();
  }

  useEffect(() => {
    audio.current?.pause();
    audio.current = null;
    setPlaying(false);
  }, [url]);

  const n = peaks?.length ?? bars;
  return (
    <div className="player">
      <button
        className={`play ${size === "sm" ? "sm" : size === "lg" ? "lg" : ""}`}
        aria-pressed={playing}
        aria-label={`${playing ? t("common.stop") : t("common.listen")} · ${label}`}
        disabled={!url}
        onClick={() => toggle()}
      >
        {!url && src ? <span className="spinner" /> : playing ? <Pause size={16} /> : <Play size={16} style={{ marginLeft: 2 }} />}
      </button>
      <div
        className={`wave ${size}`}
        aria-hidden
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          toggle((e.clientX - r.left) / r.width);
        }}
      >
        {Array.from({ length: n }, (_, i) => (
          <i key={i} className={i / n < pos ? "on" : ""} style={{ height: `${Math.round((peaks?.[i] ?? 0.08) * 100)}%`, opacity: peaks ? 1 : 0.5 }} />
        ))}
      </div>
    </div>
  );
}
