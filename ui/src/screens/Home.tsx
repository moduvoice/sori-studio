// 홈(rebuild-2026-11.md 3-2) - 받은 모델이 있으면 첫 화면. 허브에 이미 있는 것(모델 목록·이번 실행에 만든 소리)만 보여요.
import type { ReactNode } from "react";
import { ArrowRight, AudioLines, Box, HardDriveDownload } from "lucide-react";
import { bytes } from "../lib/format";
import { t } from "../lib/i18n";
import { go, href, type Route } from "../lib/router";
import { recent } from "../lib/made";
import { useHub } from "../lib/store";
import { Button } from "../components/ui";
import { Avatar, EmptyWave, FeatureArt, GIcon, HeroWave, type Hue } from "../components/art";
import { installedOk } from "../components/engine";
import { Player } from "../components/player";

const CARDS: { key: string; route: Route; hue: Hue; art: "wave" | "stack" | "curve"; icon: ReactNode }[] = [
  { key: "try", route: { name: "try" }, hue: "violet", art: "wave", icon: <AudioLines size={20} /> },
  { key: "models", route: { name: "models" }, hue: "blue", art: "stack", icon: <Box size={20} /> },
  { key: "installed", route: { name: "installed", tab: "engines" }, hue: "green", art: "curve", icon: <HardDriveDownload size={20} /> },
];

export default function Home() {
  const { engines } = useHub();
  const mine = engines.filter(installedOk);
  const [first, ...rest] = t("app.name").split(" ");
  return (
    <div className="page">
      <header className="hero">
        <HeroWave />
        <h1>
          {first} <em>{rest.join(" ")}</em>
        </h1>
        <p>{t("home.tagline")}</p>
      </header>

      <div className="features">
        {CARDS.map((c) => (
          <a key={c.key} className={`feature hue-${c.hue}`} href={href(c.route)}>
            <GIcon hue={c.hue}>{c.icon}</GIcon>
            <FeatureArt kind={c.art} />
            <h3>{t(`home.cards.${c.key}.title`)}</h3>
            <p>{t(`home.cards.${c.key}.body`)}</p>
            <ArrowRight className="go" size={18} aria-hidden />
          </a>
        ))}
      </div>

      <div className="home-cols">
        <section aria-labelledby="home-mine">
          <div className="sec-head">
            <h2 id="home-mine">{t("home.myModels")}</h2>
            {mine.length > 0 && <span className="count">{mine.length}</span>}
            <a className="btn btn-link right" href={href({ name: "installed", tab: "engines" })}>{t("home.all")}</a>
          </div>
          <div className="list">
            {mine.length === 0 ? (
              <div className="home-empty">
                <span className="grow">{t("try.emptyBody")}</span>
                <Button variant="primary" onClick={() => go({ name: "models" })}>{t("try.goModels")}</Button>
              </div>
            ) : (
              mine.map((e) => (
                <div key={e.id} className="lrow">
                  <Avatar name={e.name} seed={e.id} />
                  <div className="lrow-main">
                    <div className="lrow-title">{e.name}</div>
                    <div className="lrow-sub num">
                      {[t("home.voices", { n: e.voices?.length ?? 0 }), bytes(e.disk_bytes)].join(" · ")}
                    </div>
                  </div>
                  <div className="lrow-side">
                    <Button variant="primary" size="sm" icon={<AudioLines size={14} />} onClick={() => go({ name: "try", engine: e.id })}>
                      {t("install.tryIt")}
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section aria-labelledby="home-recent">
          <div className="sec-head">
            <h2 id="home-recent">{t("home.recent")}</h2>
            {recent.length > 0 && <span className="count">{recent.length}</span>}
          </div>
          <div className="list">
            {recent.length === 0 ? (
              <div className="home-empty">
                <EmptyWave />
                <span>{t("home.recentEmpty")}</span>
              </div>
            ) : (
              recent.map((m) => (
                <div key={m.id} className="made-row">
                  <span className="t-caption muted ellipsis">{m.engine} · {m.voice} · “{m.text}”</span>
                  <Player src={m.blob} size="sm" label={m.text} bars={64} />
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
