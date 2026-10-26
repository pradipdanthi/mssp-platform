import { useEffect, useState } from "react";
import type { EngineLane, EngineWall as EngineWallData } from "../api/soc";
import { getEngines } from "../api/soc";
import { relativeTime, utcStamp } from "../lib/time";
import { useOps } from "../state/OpsContext";

function LaneCard({ lane, now }: { lane: EngineLane; now: number }) {
  const online = lane.reachable || lane.status === "online";
  return (
    <article className={`eng-lane ${online ? "is-online" : "is-offline"}`}>
      <header className="eng-head">
        <div className="eng-title-row">
          <span className={`eng-dot ${online ? "on" : "off"}`} />
          <div>
            <div className="eng-name">{lane.label}</div>
            <div className="eng-meta">
              {lane.vm} · {lane.hostname} · {lane.host}:{lane.port} · {lane.os}
            </div>
          </div>
        </div>
        <div className="eng-stats">
          <span className={`eng-status ${online ? "on" : "off"}`}>
            {online ? "ONLINE" : "OFFLINE"}
          </span>
          {lane.latency_ms != null && <span className="eng-lat">{lane.latency_ms}ms</span>}
          <span className="eng-pulse">{lane.pulse_24h}/24h</span>
        </div>
      </header>
      <div className="eng-tool">{lane.tool}</div>
      <div className="eng-stream">
        {(lane.stream || []).length === 0 ? (
          <div className="eng-idle">waiting for signals…</div>
        ) : (
          (lane.stream || []).map((row) => (
            <div key={row.id} className={`eng-row sev-line-${(row.severity || "info").toLowerCase()}`}>
              <span className="eng-ts">{utcStamp(row.ts || "")}</span>
              <span className="eng-kind">{(row.kind || "evt").toUpperCase()}</span>
              <span className="eng-msg">
                <strong>{row.title}</strong>
                <em>{row.detail}</em>
              </span>
              <span className="eng-ago">{relativeTime(row.ts || "", now)}</span>
            </div>
          ))
        )}
      </div>
    </article>
  );
}

export default function EngineWall({
  wall,
  onWall,
}: {
  wall: EngineWallData | null;
  onWall?: (w: EngineWallData) => void;
}) {
  const { feedPaused, setFeedPaused } = useOps();
  const [now, setNow] = useState(Date.now());
  const [local, setLocal] = useState<EngineWallData | null>(wall);

  useEffect(() => setLocal(wall), [wall]);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 3000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    getEngines()
      .then((w) => {
        setLocal(w);
        onWall?.(w);
      })
      .catch(() => undefined);
    const t = window.setInterval(() => {
      if (feedPaused) return;
      getEngines()
        .then((w) => {
          setLocal(w);
          onWall?.(w);
        })
        .catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(t);
  }, [feedPaused, onWall]);

  const lanes = local?.lanes || [];
  const summary = local?.summary;

  return (
    <section className="ops-feed hollywood eng-wall-wrap">
      <div className="feed-head">
        <h2>
          Active live feed
          <span className={`live-pill ${feedPaused ? "off" : ""}`}>
            <i />
            {feedPaused ? "Paused" : "LIVE STACK"}
          </span>
        </h2>
        <div className="eng-summary muted">
          {summary
            ? `${summary.engines_online}/${summary.engines_total} engines online · probing Ubuntu VMs + tool ports`
            : "Connecting to MSSP stack…"}
        </div>
        <div className="feed-ticker" aria-hidden="true">
          <span>
            WAZUH · SURICATA · ZEEK · THEHIVE · SHUFFLE · MISP · GREENBONE · VELOCIRAPTOR · SECURE
            EDGE · SOC AGENT · APPLIANCES
          </span>
          <span>
            WAZUH · SURICATA · ZEEK · THEHIVE · SHUFFLE · MISP · GREENBONE · VELOCIRAPTOR · SECURE
            EDGE · SOC AGENT · APPLIANCES
          </span>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => setFeedPaused(!feedPaused)}>
          {feedPaused ? "Resume" : "Pause"}
        </button>
      </div>

      <div className="eng-grid">
        {lanes.map((lane) => (
          <LaneCard key={lane.id} lane={lane} now={now} />
        ))}
      </div>
    </section>
  );
}
