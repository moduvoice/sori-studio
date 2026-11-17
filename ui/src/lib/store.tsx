// 허브 상태를 한곳에서 읽어 모든 화면이 같이 써요. 받는 중·불러오는 중이면 1초마다, 아니면 3초마다 새로 읽어요.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type Engine, type Hardware, type Settings } from "./api";

type Hub = {
  up: boolean; // 허브에 닿는지
  authFailed: boolean; // 토큰이 맞지 않음(serve 모드에서 토큰 넣는 화면)
  loaded: boolean;
  settings: Settings | null;
  hardware: Hardware | null;
  engines: Engine[];
  refresh: () => Promise<void>;
  saveSettings: (patch: Partial<Settings>) => Promise<void>;
  engine: (id: string) => Engine | undefined;
};

const Ctx = createContext<Hub | null>(null);

export function HubProvider({ children }: { children: ReactNode }) {
  const [up, setUp] = useState(true);
  const [authFailed, setAuthFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [hardware, setHardware] = useState<Hardware | null>(null);
  const [engines, setEngines] = useState<Engine[]>([]);
  const busy = useRef(false);

  const refresh = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const [s, e] = await Promise.all([api<Settings>("/hub/settings"), api<{ engines: Engine[] }>("/hub/engines")]);
      setSettings(s);
      setEngines(e.engines);
      setUp(true);
      setAuthFailed(false);
      setLoaded(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthFailed(true);
      else setUp(false);
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    refresh();
    api<Hardware>("/hub/hardware")
      .then(setHardware)
      .catch(() => undefined);
  }, [refresh]);

  const active = engines.some(
    (e) => e.install.status === "installing" || ["loading", "restarting"].includes(e.run.state),
  );
  useEffect(() => {
    const id = window.setInterval(refresh, active || !up ? 1000 : 3000);
    return () => window.clearInterval(id);
  }, [refresh, active, up]);

  const saveSettings = useCallback(async (patch: Partial<Settings>) => {
    const s = await api<Settings>("/hub/settings", { method: "PATCH", json: patch });
    setSettings(s);
  }, []);

  const engine = useCallback((id: string) => engines.find((e) => e.id === id), [engines]);

  return (
    <Ctx.Provider value={{ up, authFailed, loaded, settings, hardware, engines, refresh, saveSettings, engine }}>
      {children}
    </Ctx.Provider>
  );
}

export function useHub(): Hub {
  const v = useContext(Ctx);
  if (!v) throw new Error("HubProvider 밖이에요");
  return v;
}

// ---------- 토스트: 방금 한 일의 결과만(문제는 알림 띠로) ----------
type Toast = { id: number; text: string; action?: { label: string; run: () => void } };
const ToastCtx = createContext<(text: string, action?: Toast["action"]) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, action?: Toast["action"]) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-2), { id, text, action }]);
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((x) => (
          <div className="toast" key={x.id}>
            <span>{x.text}</span>
            {x.action && <button onClick={x.action.run}>{x.action.label}</button>}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
