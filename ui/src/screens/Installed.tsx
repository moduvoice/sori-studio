// H3 내 모델 - 받은 모델 목록(이름·상태·용량·소리 만들기·지우기)만.
// UX 리뷰(2026-11-17): 켜기/끄기·메모리·최근 일·디스크 탭은 뺐어요. 모델은 소리를 만들 때 저절로 켜져요.
import { useEffect, useState } from "react";
import { Download, HardDrive } from "lucide-react";
import { api, errorText, type Drive, type Engine } from "../lib/api";
import { bytes } from "../lib/format";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub, useToast } from "../lib/store";
import { Banner, Button, EmptyState } from "../components/ui";
import { installedOk } from "../components/engine";
import { LogDialog, RemoveDialog } from "../components/install";

export default function Installed() {
  const { engines, loaded } = useHub();
  const mine = engines.filter((e) => e.install.status !== "none");
  return (
    <div className="page narrow">
      <div className="page-head">
        <h1 className="t-h1 grow">{t("installed.title")}</h1>
      </div>
      {loaded && mine.length === 0 ? (
        <EmptyState
          icon={<Download size={20} />}
          title={t("installed.empty")}
          body={t("installed.emptyBody")}
          action={<Button variant="primary" size="lg" onClick={() => go({ name: "models" })}>{t("installed.goModels")}</Button>}
        />
      ) : (
        <>
          <List list={mine} />
          <FolderNote />
        </>
      )}
    </div>
  );
}

function List({ list }: { list: Engine[] }) {
  const { refresh } = useHub();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<{ name: string; lines: string[] } | null>(null);
  const [rm, setRm] = useState<Engine | null>(null);

  async function restart(e: Engine) {
    setBusy(e.id);
    try {
      await api(`/hub/engines/${e.id}/start`, { method: "POST" });
      await refresh();
    } catch (x) {
      toast(errorText(x));
    } finally {
      setBusy(null);
    }
  }
  const showLog = async (e: Engine) => setLog({ name: e.name, lines: (await api<{ log: string[] }>(`/hub/engines/${e.id}/log`)).log });

  return (
    <section className="card">
      {list.map((e, i) => {
        const ok = installedOk(e);
        const dead = e.run.state === "dead";
        const pctDone = e.install.progress?.bytes_total ? Math.floor((e.install.progress.bytes_done / e.install.progress.bytes_total) * 100) : 0;
        return (
          <div key={e.id} className="col" style={{ padding: "14px 20px", borderTop: i ? "1px solid var(--line)" : "none", gap: 8 }}>
            <div className="row" style={{ gap: 12 }}>
              <div className="grow col" style={{ gap: 2 }}>
                <strong>{e.name}</strong>
                <span className="t-caption muted num">
                  {ok
                    ? bytes(e.disk_bytes)
                    : e.install.status === "installing"
                      ? t("installed.installing", { pct: pctDone })
                      : t(`install.status.${e.install.status}`)}
                </span>
              </div>
              {ok ? (
                <>
                  <Button size="sm" variant="primary" onClick={() => go({ name: "try", engine: e.id })}>{t("install.tryIt")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setRm(e)}>{t("install.remove")}</Button>
                </>
              ) : (
                <Button size="sm" onClick={() => go({ name: "model", id: e.id })}>{t("common.details")}</Button>
              )}
            </div>
            {dead && (
              <Banner tone="danger" title={t("run.deadTitle")}>
                <Button variant="primary" busy={busy === e.id} onClick={() => restart(e)}>{t("run.restart")}</Button>
                <Button variant="link" onClick={() => showLog(e)}>{t("common.showLog")}</Button>
              </Banner>
            )}
          </div>
        );
      })}
      {log && <LogDialog title={t("run.logTitle", { name: log.name })} lines={log.lines} onClose={() => setLog(null)} />}
      {rm && <RemoveDialog e={rm} onClose={() => setRm(null)} />}
    </section>
  );
}

function FolderNote() {
  const [d, setD] = useState<{ drives: Drive[]; current: string } | null>(null);
  useEffect(() => {
    api<{ drives: Drive[]; current: string }>("/hub/drives").then(setD).catch(() => undefined);
  }, []);
  if (!d) return null;
  const drive = d.drives.find((x) => d.current.toUpperCase().startsWith(x.root.toUpperCase()));
  return (
    <p className="t-caption muted row" style={{ gap: 6, marginTop: 12 }}>
      <HardDrive size={14} aria-hidden />
      <span style={{ wordBreak: "break-all" }}>
        {t("installed.folder", { path: d.current })}
        {drive ? ` · ${t("installed.free", { size: bytes(drive.free_bytes) })}` : ""}
      </span>
    </p>
  );
}
