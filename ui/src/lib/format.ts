// 숫자 표기(components.md 0): 용량은 GB 소수 한 자리(1 GB 아래는 MB), 시간은 "3.2초"·"약 8분", 비율은 "0.9%".
// 단위 말(초·분)은 언어 표에서, 소수점은 화면 언어 표기로.
import { locale, t } from "./i18n";

function num(v: number, digits: number): string {
  return v.toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function bytes(n: number | null | undefined): string {
  if (n == null) return "-";
  if (n >= 1e9) return `${num(n / 1e9, 1)} GB`;
  if (n >= 1e6) return `${num(n / 1e6, 0)} MB`;
  if (n >= 1e3) return `${num(n / 1e3, 0)} KB`;
  return `${n} B`;
}

export function pct(v: number | undefined | null, digits = 1): string {
  if (v == null) return "-";
  return `${num(v * 100, digits)}%`;
}

export function dec(v: number, digits = 1): string {
  return num(v, digits);
}

export function secs(s: number): string {
  if (s < 10) return t("common.seconds", { n: num(s, 1) });
  if (s < 90) return t("common.seconds", { n: Math.round(s) });
  return t("common.aboutMinutes", { n: Math.round(s / 60) });
}

export function clock(epochS: number): string {
  const d = new Date(epochS * 1000);
  return d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function date(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(locale(), { year: "numeric", month: "2-digit", day: "2-digit" });
}
