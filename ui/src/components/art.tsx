// 꾸밈 그림 - 얇은 선·이니셜 원. 모두 이 앱에서 직접 그린 것이고 색은 토큰(currentColor)만 써요.
import type { ReactNode } from "react";

const HUES = ["violet", "blue", "green", "pink", "amber"] as const;
export type Hue = (typeof HUES)[number];

export function hueOf(key: string): Hue {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return HUES[h % HUES.length];
}

/** 이름의 앞 글자(한글은 한 글자, 영문·숫자는 두 글자) */
export function initials(name: string) {
  const s = name.trim();
  if (!s) return "?";
  const numbered = /^(\S)\S* (\d)\d*$/.exec(s); // "여성 1" → "여1", "Female 1" → "F1"
  if (numbered) return (numbered[1] + numbered[2]).toUpperCase();
  if (s.charCodeAt(0) > 127) return s[0];
  return s.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || s[0];
}

export function Avatar({ name, seed, hue, size }: { name: string; seed?: string; hue?: Hue; size?: "sm" | "lg" }) {
  return (
    <span className={`avatar hue-${hue ?? hueOf(seed ?? name)} ${size ?? ""}`} aria-hidden>
      {initials(name)}
    </span>
  );
}

export function GIcon({ hue = "violet", size, children }: { hue?: Hue; size?: "sm" | "lg"; children: ReactNode }) {
  return (
    <span className={`gicon hue-${hue} ${size ?? ""}`} aria-hidden>
      {children}
    </span>
  );
}

/** 마법사·시작 화면 바탕의 얇은 곡선 */
export function Curves() {
  const arcs = [0, 1, 2, 3, 4, 5];
  return (
    <svg className="curves" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" fill="none" aria-hidden>
      {arcs.map((i) => (
        <path key={`a${i}`} d={`M ${900 + i * 46} -20 C ${1010 + i * 40} ${150 + i * 26}, ${1230 + i * 18} ${170 + i * 34}, 1460 ${70 + i * 44}`} stroke="currentColor" strokeWidth="1" />
      ))}
      {arcs.map((i) => (
        <path key={`b${i}`} d={`M -20 ${640 + i * 40} C ${190 + i * 24} ${650 + i * 22}, ${330 + i * 34} ${760 + i * 16}, ${420 + i * 52} 920`} stroke="currentColor" strokeWidth="1" />
      ))}
    </svg>
  );
}

// 미리 정한 높이 - 그릴 때마다 같아요
const BARS = [10, 18, 30, 22, 44, 62, 38, 54, 80, 58, 34, 70, 96, 64, 46, 84, 58, 30, 50, 72, 42, 26, 60, 88, 56, 36, 20, 44, 66, 40, 24, 52, 34, 16, 28, 46, 22, 12, 30, 18, 10, 20, 12, 8];

/** 홈 머리의 큰 파형 */
export function HeroWave() {
  return (
    <svg className="hero-art" viewBox="0 0 440 150" preserveAspectRatio="xMaxYMid meet" aria-hidden>
      <defs>
        <linearGradient id="hero-wave" x1="0" x2="440" y1="0" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" style={{ stopColor: "var(--wave-a)" }} />
          <stop offset="1" style={{ stopColor: "var(--wave-b)" }} />
        </linearGradient>
      </defs>
      {BARS.map((h, i) => (
        <rect key={i} x={i * 10} y={75 - (h * 1.3) / 2} width="4" height={h * 1.3} rx="2" fill="url(#hero-wave)" opacity={0.28 + (h / 96) * 0.5} />
      ))}
    </svg>
  );
}

/** 기능 카드 오른쪽 위의 얇은 선 그림 */
export function FeatureArt({ kind }: { kind: "wave" | "stack" | "curve" }) {
  return (
    <svg className="feature-art" viewBox="0 0 150 56" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" aria-hidden>
      {kind === "wave" &&
        [6, 14, 26, 40, 22, 48, 30, 52, 36, 18, 44, 28, 12, 20, 8].map((h, i) => <path key={i} d={`M ${8 + i * 9.5} ${28 - h / 2} V ${28 + h / 2}`} />)}
      {kind === "stack" && (
        <>
          <rect x="34" y="3" width="112" height="14" rx="7" />
          <rect x="14" y="21" width="132" height="14" rx="7" />
          <rect x="54" y="39" width="92" height="14" rx="7" />
          <path d="M 44 10 h 34 M 24 28 h 52 M 64 46 h 28" />
        </>
      )}
      {kind === "curve" && (
        <>
          <path d="M 4 44 C 30 44, 34 10, 60 10 S 90 44, 116 44 S 138 26, 148 22" />
          <path d="M 4 50 C 30 50, 38 20, 60 20 S 92 50, 116 50 S 140 34, 148 30" opacity="0.6" />
          <path d="M 4 38 C 28 38, 30 2, 60 2 S 88 38, 116 38 S 136 18, 148 14" opacity="0.35" />
        </>
      )}
    </svg>
  );
}

/** 아직 만든 소리가 없을 때의 흐린 파형 */
export function EmptyWave() {
  return (
    <svg width="132" height="52" viewBox="0 0 132 52" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden>
      {[8, 16, 28, 40, 22, 46, 30, 18, 36, 24, 12, 20, 8].map((h, i) => (
        <path key={i} d={`M ${6 + i * 10} ${26 - h / 2} V ${26 + h / 2}`} />
      ))}
    </svg>
  );
}
