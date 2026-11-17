// 주소 # 뒤로 화면을 고르는 작은 길잡이(파일·서버 설정 없이 Electron·브라우저 모두에서 같게 돌아요).
import { useEffect, useState } from "react";

export type Route =
  | { name: "wizard" }
  | { name: "home" }
  | { name: "models" }
  | { name: "model"; id: string }
  | { name: "installed"; tab: "engines" | "disk"; id?: string }
  | { name: "try"; engine?: string }
  | { name: "settings"; section: string };

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  switch (parts[0]) {
    case "wizard":
      return { name: "wizard" };
    case "home":
      return { name: "home" };
    case "models":
      return parts[1] ? { name: "model", id: parts[1] } : { name: "models" };
    case "installed":
      return { name: "installed", tab: parts[1] === "disk" ? "disk" : "engines", id: parts[2] };
    case "try":
      return { name: "try", engine: parts[1] };
    case "settings":
      return { name: "settings", section: parts[1] || "general" };
    default:
      return { name: "models" };
  }
}

export function href(r: Route): string {
  switch (r.name) {
    case "wizard":
      return "#/wizard";
    case "home":
      return "#/home";
    case "models":
      return "#/models";
    case "model":
      return `#/models/${encodeURIComponent(r.id)}`;
    case "installed":
      return `#/installed/${r.tab}${r.id ? `/${encodeURIComponent(r.id)}` : ""}`;
    case "try":
      return `#/try${r.engine ? `/${encodeURIComponent(r.engine)}` : ""}`;
    case "settings":
      return `#/settings/${r.section}`;
  }
}

export function go(r: Route) {
  window.location.hash = href(r);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
