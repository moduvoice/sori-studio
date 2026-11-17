// 화면 글은 모두 언어 표(i18n/<언어>.json)에서 가져와요. 새 언어는 같은 꼴의 표를 더하고 LANGS 에 넣으면 돼요.
// - {이름} 자리 채우기, 수에 따라 달라지는 말은 {"one": "...", "other": "..."} 꼴(Intl.PluralRules).
// - 지금 언어 표에 없는 글은 영어 → 한국어 순서로 찾아요.
import ko from "../i18n/ko.json";
import en from "../i18n/en.json";

type Dict = { [k: string]: unknown };
export const LANGS: Record<string, Dict> = { ko: ko as Dict, en: en as Dict };
export type Lang = keyof typeof LANGS;

let current = "ko";

/** 설정 값(system·ko·en)으로 화면 언어를 정해요. system 이면 브라우저(OS) 언어를 따라가요. */
export function setLang(pref: string | undefined) {
  const want = !pref || pref === "system" ? (navigator.language || "ko").slice(0, 2).toLowerCase() : pref;
  current = want in LANGS ? want : "en";
  document.documentElement.lang = current;
}

export function lang(): string {
  return current;
}

function lookupIn(table: Dict, key: string): unknown {
  let cur: unknown = table;
  for (const part of key.split(".")) {
    if (cur && typeof cur === "object" && part in (cur as Dict)) cur = (cur as Dict)[part];
    else return undefined;
  }
  return cur;
}

function lookup(key: string): unknown {
  for (const l of [current, "en", "ko"]) {
    const v = lookupIn(LANGS[l], key);
    if (v !== undefined) return v;
  }
  return undefined;
}

function isPlural(v: unknown): v is Record<string, string> {
  return Boolean(v && typeof v === "object" && !Array.isArray(v) && "other" in (v as Dict));
}

export function t(key: string, vars?: Record<string, string | number>): string {
  let v = lookup(key);
  if (isPlural(v)) {
    const n = Number(vars?.n ?? 0);
    const cat = new Intl.PluralRules(current).select(n);
    v = v[cat] ?? v.other;
  }
  if (typeof v !== "string") {
    if (import.meta.env.DEV) console.warn("missing string", key);
    return key;
  }
  return vars ? v.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`)) : v;
}

export function tl(key: string): string[] {
  const v = lookup(key);
  return Array.isArray(v) ? (v as string[]) : [];
}

export function has(key: string): boolean {
  const v = lookup(key);
  return typeof v === "string" || isPlural(v);
}

/** 화면 언어에 맞는 날짜·시각·숫자 표기 */
export function locale(): string {
  return current === "ko" ? "ko-KR" : current;
}
