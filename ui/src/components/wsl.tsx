// WSL2 안내(사용자 2026-11-17 "윈도우에 맞지 않으면 WSL2 를 안내, 있는지 감지해서 설치")
// 리눅스 전용 엔진은 Windows 의 WSL2 안(Sori Studio 전용 Ubuntu)에서 돌아요.
import { useEffect, useState } from "react";
import { api, type WslState } from "../lib/api";
import { t } from "../lib/i18n";
import { Banner, Button, CopyButton } from "./ui";

export function useWsl(on: boolean) {
  const [st, setSt] = useState<WslState | null>(null);
  useEffect(() => {
    if (!on) return;
    let dead = false;
    const load = () => api<WslState>("/hub/wsl").then((x) => !dead && setSt(x)).catch(() => undefined);
    load();
    const id = window.setInterval(load, 10000);
    return () => {
      dead = true;
      window.clearInterval(id);
    };
  }, [on]);
  return st;
}

/** WSL2 가 준비되지 않았으면 안내 카드를, 준비됐으면 한 줄 설명을 보여 줘요. ready 면 true. */
export function WslGate({ st }: { st: WslState | null }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  if (!st) return null;
  if (st.state === "ready" || st.state === "not_windows") return <p className="note">{t("wsl.readyNote")}</p>;
  if (st.state === "no_distro") return <p className="note">{t("wsl.noDistro")}</p>;
  const cmd = "wsl --install --no-distribution";
  return (
    <div className="col" style={{ gap: 10 }}>
      <Banner tone="info" title={t("wsl.needTitle")} body={st.virtualization_off ? t("wsl.virtOff") : t("wsl.needBody")} />
      {window.sori?.installWsl ? (
        <Button
          variant="primary"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            const r = await window.sori!.installWsl!();
            setBusy(false);
            setMsg(r.ok ? t("wsl.installedRestart") : t("wsl.installFailed"));
          }}
        >
          {t("wsl.installBtn")}
        </Button>
      ) : (
        <div className="col" style={{ gap: 4 }}>
          <span className="t-caption muted">{t("wsl.manual")}</span>
          <div className="code"><span className="copy"><CopyButton text={cmd} /></span>{cmd}</div>
        </div>
      )}
      {msg && <Banner tone="warning" title={msg} />}
    </div>
  );
}
