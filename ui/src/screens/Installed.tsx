// H3 내 모델 - 받은 모델 목록(이름·상태·용량·소리 만들기·지우기)만.
// UX 리뷰(2026-11-17): 켜기/끄기·메모리·최근 일·디스크 탭은 뺐어요. 모델은 소리를 만들 때 저절로 켜져요.
import { useEffect, useState } from "react";
import { AudioLines, HardDrive, HardDriveDownload, Trash2 } from "lucide-react";
import { api, errorText, type Drive, type Engine } from "../lib/api";
import { bytes } from "../lib/format";
import { t } from "../lib/i18n";
import { go } from "../lib/router";
import { useHub, useToast } from "../lib/store";
import { Banner, Button, EmptyState } from "../components/ui";
import { Avatar, GIcon } from "../components/art";
import { installedOk } from "../components/engine";
import { LogDialog, RemoveDialog } from "../components/install";

export default function Installed() {
  const { engines, loaded } = useHub();
  const mine = engines.filter((e) => e.install.status !== "none");
  return (
    <div className="page">
      {loaded && mine.length === 0 ? (
        <EmptyState
          icon={<GIcon size="lg" hue="green"><HardDriveDownload size={24} /></GIcon>}
          title={t("installed.empty")}
          body={t("installed.emptyBody")}
          action={<Button variant="primary" size="lg" onClick={() => go({ name: "models" })}>{t("installed.goModels")}</Button>}
        />
      ) : (
        <>
          <div className="page-head">
            <div className="grow">
              <h1 className="t-h1">{t("installed.title")}</h1>
              <FolderNote />
            </div>
          </div>
          <List list={mine} />
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
    <section className="list">
      {list.map((e) => {
        const ok = installedOk(e);
        const dead = e.run.state === "dead";
        const pctDone = e.install.progress?.bytes_total ? Math.floor((e.install.progress.bytes_done / e.install.progress.bytes_total) * 100) : 0;
        return (
          <div key={e.id} className="lrow-wrap">
            <div className="lrow">
              <Avatar name={e.name} seed={e.id} />
              <div className="lrow-main">
                <span className="lrow-title">{e.name}</span>
                <span className="lrow-sub num">
                  {ok
                    ? bytes(e.disk_bytes)
                    : e.install.status === "installing"
                      ? t("installed.installing", { pct: pctDone })
                      : t(`install.status.${e.install.status}`)}
                </span>
              </div>
              <div className="lrow-side">
                {ok ? (
                  <>
                    <Button size="sm" variant="primary" icon={<AudioLines size={14} />} onClick={() => go({ name: "try", engine: e.id })}>{t("install.tryIt")}</Button>
                    <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={() => setRm(e)}>{t("install.remove")}</Button>
                  </>
                ) : (
                  <Button size="sm" onClick={() => go({ name: "model", id: e.id })}>{t("common.details")}</Button>
                )}
              </div>
            </div>
            {dead && (
              <div className="lrow-more" style={{ paddingLeft: 18 }}>
              <Banner tone="danger" title={t("run.deadTitle")}>
                <Button variant="primary" busy={busy === e.id} onClick={() => restart(e)}>{t("run.restart")}</Button>
                <Button variant="link" onClick={() => showLog(e)}>{t("common.showLog")}</Button>
              </Banner>
              </div>
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
    <p className="row" style={{ gap: 6, fontSize: 13 }}>
      <HardDrive size={14} aria-hidden style={{ flex: "none" }} />
      <span style={{ wordBreak: "break-all" }}>
        {t("installed.folder", { path: d.current })}
        {drive ? ` · ${t("installed.free", { size: bytes(drive.free_bytes) })}` : ""}
      </span>
    </p>
  );
}
