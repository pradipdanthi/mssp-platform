import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getActivity, openActivityStream, type ActivityItem } from "../api/soc";
import { relativeTime, utcStamp } from "../lib/time";
import { useOps } from "../state/OpsContext";

const CAT_LABEL: Record<string, string> = {
  alert: "ALERT",
  incident: "INCIDENT",
  event: "EVENT",
  vulnerability: "VULN",
  patch_gap: "PATCH",
  agent: "AI",
  system: "SOC",
};

export default function ActivityFeed({
  focus = "all",
  onKpis,
}: {
  focus?: string;
  onKpis?: (k: Record<string, number>) => void;
}) {
  const navigate = useNavigate();
  const { token } = useAuth();
  const { activity, mergeActivity, feedPaused, setFeedPaused, selectAlertId, setTab } = useOps();
  const [live, setLive] = useState(false);
  const [now, setNow] = useState(Date.now());
  const scroller = useRef<HTMLDivElement | null>(null);
  const pausedRef = useRef(feedPaused);
  pausedRef.current = feedPaused;

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 4000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    getActivity(80)
      .then((r) => {
        mergeActivity(r.items || [], "snapshot");
        if (r.kpis) onKpis?.(r.kpis);
      })
      .catch(() => undefined);
  }, [mergeActivity, onKpis]);

  useEffect(() => {
    if (!token) return;
    const ac = new AbortController();
    let stopped = false;
    (async () => {
      while (!stopped && !ac.signal.aborted) {
        try {
          setLive(true);
          await openActivityStream(
            token,
            {
              onSnapshot: (items, kpis) => {
                if (!pausedRef.current) mergeActivity(items, "snapshot");
                if (kpis) onKpis?.(kpis);
              },
              onActivity: (items) => {
                if (!pausedRef.current) mergeActivity(items, "prepend");
              },
              onKpis: (k) => onKpis?.(k),
            },
            ac.signal
          );
        } catch {
          if (stopped || ac.signal.aborted) break;
          setLive(false);
          await new Promise((r) => setTimeout(r, 2500));
        }
      }
    })();
    return () => {
      stopped = true;
      ac.abort();
    };
  }, [token, mergeActivity, onKpis]);

  useEffect(() => {
    if (feedPaused) return;
    const el = scroller.current;
    if (el) el.scrollTop = 0;
  }, [activity, feedPaused]);

  const visible = useMemo(() => {
    const rows = activity as ActivityItem[];
    if (!focus || focus === "all") return rows;
    return rows.filter((it) => (it.category || "").toLowerCase() === focus);
  }, [activity, focus]);

  return (
    <section className="ops-feed">
      <div className="feed-head">
        <h2>
          Active live feed
          <span className={`live-pill ${live && !feedPaused ? "" : "off"}`}>
            <i />
            {feedPaused ? "Paused" : live ? "LIVE" : "…"}
          </span>
        </h2>
        <span className="muted feed-hint">Alerts · Incidents · Events · Vulns · Patch gaps</span>
        <button type="button" className="btn btn-ghost" onClick={() => setFeedPaused(!feedPaused)}>
          {feedPaused ? "Resume" : "Pause"}
        </button>
      </div>
      <div className="feed-stream" ref={scroller}>
        {visible.length === 0 ? (
          <div className="empty">No SOC activity in this view yet.</div>
        ) : (
          visible.map((item) => (
            <div
              key={item.id}
              className={`feed-row cat-${item.category || "system"}`}
              onClick={() => {
                if (item.alert_id) {
                  setTab("alerts");
                  selectAlertId(item.alert_id);
                  navigate(`/alerts/${item.alert_id}`);
                  return;
                }
                if (item.incident_id) {
                  navigate(`/incidents/${item.incident_id}`);
                }
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                if (item.alert_id) {
                  setTab("alerts");
                  selectAlertId(item.alert_id);
                  navigate(`/alerts/${item.alert_id}`);
                } else if (item.incident_id) {
                  navigate(`/incidents/${item.incident_id}`);
                }
              }}
            >
              <div className="fr-time">
                <span>{utcStamp(item.ts)}</span>
                <span>{relativeTime(item.ts, now)}</span>
              </div>
              <span className="fr-tag">{CAT_LABEL[item.category || ""] || (item.category || "SOC").toUpperCase()}</span>
              {(item.severity || "").toLowerCase() !== "info" && (
                <span className={`sev sev-${(item.severity || "info").toLowerCase()}`}>{item.severity}</span>
              )}
              <div className="fr-body">
                <div className="fr-title">{item.title}</div>
                <div className="fr-detail">{item.detail}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
