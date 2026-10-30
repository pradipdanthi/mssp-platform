import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  ApprovalItem,
  CommandCenterPayload,
  decideApproval,
  getCommandCenter,
  patchRoutine,
  RoutineItem,
  runRoutine,
} from "../api/soc";
import { useAuth } from "../auth/AuthContext";
import { TiaDockSlot } from "../components/TiaDock";
import TiaGlobe from "../components/TiaGlobe";

const VOICE_KEY = "tia_voice_settings_v1";

type VoiceSettings = {
  speakResponses: boolean;
  freeHand: boolean;
  autoApprove: boolean;
};

function loadVoice(): VoiceSettings {
  try {
    const raw = localStorage.getItem(VOICE_KEY);
    if (raw) return { speakResponses: true, freeHand: true, autoApprove: false, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { speakResponses: true, freeHand: true, autoApprove: false };
}

function saveVoice(v: VoiceSettings) {
  localStorage.setItem(VOICE_KEY, JSON.stringify(v));
  localStorage.setItem("tia_always_listen", v.freeHand ? "1" : "0");
  window.dispatchEvent(new CustomEvent("tia-voice-settings", { detail: v }));
}

function Gauge({ label, value }: { label: string; value?: number | null }) {
  const v = value == null || Number.isNaN(Number(value)) ? null : Math.max(0, Math.min(100, Number(value)));
  const deg = v == null ? 0 : Math.round((v / 100) * 360);
  return (
    <div className="cc-gauge">
      <div className="cc-gauge-wrap">
        <div className="cc-gauge-ring" style={{ ["--deg" as string]: `${deg}deg` }} />
        <div className="cc-gauge-val">{v == null ? "—" : Math.round(v)}</div>
      </div>
      <div className="cc-gauge-label">{label}</div>
    </div>
  );
}

type FocusTile = {
  id: string;
  label: string;
  path: string;
  value: number;
  tone: string;
};

export default function CommandCenter() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<CommandCenterPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [voice, setVoice] = useState<VoiceSettings>(() => loadVoice());
  const [panel, setPanel] = useState<"ops" | "voice" | "routines">("ops");
  const [clock, setClock] = useState(() => new Date());
  const [toast, setToast] = useState<string | null>(null);

  function flash(msg: string) {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3500);
  }

  const refresh = useCallback(() => {
    getCommandCenter()
      .then((r) => {
        setData(r);
        setErr(null);
        const ran = r.routines_ran_now || [];
        for (const item of ran) {
          const spoken = (item.spoken_answer || "").trim();
          const rid = item.id || "routine";
          if (!spoken) continue;
          // Never auto-speak the Hello-boss brief on dashboard load — that stacked
          // with Hi Tia wake and caused 2–3 repeats. Toast only; user can Run now.
          const guardKey = `tia_routine_spoken_${rid}_${new Date().toDateString()}`;
          try {
            if (sessionStorage.getItem(guardKey) === "1") continue;
            sessionStorage.setItem(guardKey, "1");
          } catch {
            /* ignore */
          }
          setToast(`Routine ready: ${item.name || rid} (open Routines → Run now to hear)`);
          window.setTimeout(() => setToast(null), 4500);
        }
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Command Center failed to load");
      });
  }, [logout]);

  useEffect(() => {
    refresh();
    saveVoice(loadVoice());
    const poll = window.setInterval(refresh, 30000);
    const tick = window.setInterval(() => setClock(new Date()), 1000);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(tick);
    };
  }, [refresh]);

  const statusClass = useMemo(() => {
    const s = (data?.system_status || "").toUpperCase();
    if (s === "OPTIMAL" || s === "CLEAR") return "ok";
    if (s === "URGENT") return "bad";
    return "warn";
  }, [data?.system_status]);

  const enginesOnline = data?.gauges?.engines_online;
  const enginesTotal = data?.gauges?.engines_total;
  const enginePct =
    enginesOnline != null && enginesTotal
      ? Math.round((Number(enginesOnline) / Number(enginesTotal)) * 100)
      : null;

  const kpis = data?.kpis || {};
  const focusTiles: FocusTile[] = [
    { id: "alerts", label: "Security Alerts", path: "/alerts", value: Number(kpis.alerts ?? data?.urgency?.open_alerts ?? 0), tone: "tone-red" },
    { id: "incidents", label: "Incidents", path: "/incidents", value: Number(kpis.incidents ?? data?.urgency?.open_incidents ?? 0), tone: "tone-amber" },
    { id: "vuln", label: "Vulnerabilities", path: "/vulnerabilities", value: Number(kpis.vulnerabilities ?? 0), tone: "tone-purple" },
    { id: "patches", label: "Patch Gaps", path: "/patch-gaps", value: Number(kpis.patch_gaps ?? 0), tone: "tone-green" },
    {
      id: "waf",
      label: "Secure Edge WAF",
      path: "/events",
      value: Number(kpis.events ?? 0),
      tone: "tone-blue",
    },
    { id: "customers", label: "Customers", path: "/customers", value: Number(kpis.customers ?? 0), tone: "tone-cyan" },
  ];

  const missionTiles: FocusTile[] = [
    { id: "m-alerts", label: "Alerts", path: "/alerts", value: Number(kpis.alerts ?? 0), tone: "tone-red" },
    { id: "m-incidents", label: "Incidents", path: "/incidents", value: Number(kpis.incidents ?? 0), tone: "tone-amber" },
    { id: "m-vuln", label: "Vuln", path: "/vulnerabilities", value: Number(kpis.vulnerabilities ?? 0), tone: "tone-purple" },
    { id: "m-patches", label: "Patch gaps", path: "/patch-gaps", value: Number(kpis.patch_gaps ?? 0), tone: "tone-green" },
    { id: "m-waf", label: "Secure Edge WAF", path: "/events", value: Number(kpis.events ?? 0), tone: "tone-blue" },
    { id: "m-customers", label: "Customers", path: "/customers", value: Number(kpis.customers ?? 0), tone: "tone-cyan" },
  ];

  async function onDecide(item: ApprovalItem, decision: "approve" | "decline") {
    setBusyId(item.id);
    try {
      await decideApproval(item.id, decision);
      flash(decision === "approve" ? "Approved — ticket updated" : "Declined — no change");
      refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) logout();
      else flash("Approval action failed");
    } finally {
      setBusyId(null);
    }
  }

  async function onToggleRoutine(r: RoutineItem, enabled: boolean) {
    setBusyId(r.id);
    try {
      await patchRoutine(r.id, { enabled });
      refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) logout();
      else flash("Could not update routine");
    } finally {
      setBusyId(null);
    }
  }

  async function onRunRoutine(r: RoutineItem) {
    setBusyId(r.id);
    try {
      const res = await runRoutine(r.id);
      const spoken = res.briefing?.spoken_answer;
      if (spoken) {
        window.dispatchEvent(new CustomEvent("tia-speak", { detail: spoken }));
      }
      flash(`Ran ${r.name || r.id}`);
      refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) logout();
      else flash("Routine run failed");
    } finally {
      setBusyId(null);
    }
  }

  function updateVoice(patch: Partial<VoiceSettings>) {
    const next = { ...voice, ...patch };
    setVoice(next);
    saveVoice(next);
  }

  const pending = data?.approvals || [];
  const agents = data?.agents || [];

  return (
    <div className="cc-root">
      <header className="cc-top cc-top-slim">
        <div className="cc-brand-row">
          <strong>{data?.version || "TIA COMMAND CENTER"}</strong>
          <span className={`cc-sys-pill ${statusClass}`}>
            SYSTEM STATUS: {data?.system_status || "…"}
            {(data?.pending_approvals || 0) > 0 ? ` · ${data?.pending_approvals} NEED YOU` : ""}
          </span>
        </div>
        <div className="cc-clock-slim">
          <span className="cc-time">
            {clock.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
          <span className="cc-date">
            {clock.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}
          </span>
        </div>
        <div className="cc-top-right">
          <span className="cc-op-name">{user?.full_name || user?.email || "SOC"}</span>
          <button type="button" className={`cc-tab ${panel === "ops" ? "on" : ""}`} onClick={() => setPanel("ops")}>
            Ops
          </button>
          <button type="button" className={`cc-tab ${panel === "routines" ? "on" : ""}`} onClick={() => setPanel("routines")}>
            Routines
          </button>
          <button type="button" className={`cc-tab ${panel === "voice" ? "on" : ""}`} onClick={() => setPanel("voice")}>
            AI Voice
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => navigate("/reviews")}>
            Reviews
          </button>
          <button type="button" className="btn btn-ghost cc-signout" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      {err && <div className="err cc-err">{err}</div>}
      {toast && <div className="cc-toast">{toast}</div>}

      <section className="cc-focus-tiles" aria-label="SOC navigation tiles">
        {focusTiles.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`cc-focus-tile ${t.tone}`}
            onClick={() => navigate(t.path)}
            title={`Open ${t.label}`}
          >
            <div className="cc-focus-tile-label">{t.label}</div>
            <div className="cc-focus-tile-value">{t.value.toLocaleString()}</div>
          </button>
        ))}
      </section>

      <div className="cc-grid">
        <section className="cc-panel cc-agents">
          <h3>
            Active Stack Agents{" "}
            <span className="muted">
              {enginesOnline ?? "—"}/{enginesTotal ?? "—"} online
            </span>
          </h3>
          <div className="cc-agent-cards">
            {agents.map((a) => (
              <div key={a.id} className={`cc-agent-card ${a.reachable ? "on" : "off"}`}>
                <div className="cc-agent-card-top">
                  <strong>{a.label}</strong>
                  <span>{a.reachable ? "Active" : "Offline"}</span>
                </div>
                <div className="cc-agent-card-meta">
                  {a.vm || "—"}
                  {a.latency_ms != null ? ` · ${a.latency_ms}ms` : ""}
                  {` · pulse ${a.pulse_24h ?? 0}`}
                </div>
                <div className="cc-mini-wave" aria-hidden>
                  <i /><i /><i /><i /><i />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="cc-panel cc-core">
          <TiaGlobe live={(data?.core?.status || "") === "active"} version="v1.0" />
          <ul className="cc-kv cc-core-kv">
            <li>
              <span>Voice</span>
              <b className="ok">{voice.freeHand ? "Free-hand · Hi Tia" : "Dock only"}</b>
            </li>
            <li>
              <span>Needs You</span>
              <b className={(data?.pending_approvals || 0) > 0 ? "warn" : "ok"}>{data?.pending_approvals ?? 0}</b>
            </li>
            <li>
              <span>Provider</span>
              <b>{data?.core?.provider || "—"}</b>
            </li>
            <li>
              <span>Auto-approve</span>
              <b className={voice.autoApprove ? "warn" : "ok"}>{voice.autoApprove ? "ON" : "OFF"}</b>
            </li>
          </ul>
          <div className="cc-gauges">
            <Gauge label="CPU" value={data?.gauges?.cpu_pct as number | null} />
            <Gauge label="RAM" value={data?.gauges?.ram_used_pct as number | null} />
            <Gauge label="Engines" value={enginePct} />
          </div>
        </section>

        <section className="cc-panel cc-focus">
          {panel === "ops" && (
            <>
              <h3>Needs You · Approvals</h3>
              {pending.length === 0 ? (
                <div className="muted cc-empty-note">
                  No pending ticket actions. Crit {data?.urgency?.critical_open ?? 0} · High{" "}
                  {data?.urgency?.high_open ?? 0} · Incidents {data?.urgency?.open_incidents ?? 0}.
                </div>
              ) : (
                <div className="cc-approvals">
                  {pending.map((item) => (
                    <div key={item.id} className="cc-approval">
                      <div className="cc-approval-sum">{item.summary || "Ticket update"}</div>
                      <div className="cc-approval-q muted">{item.question}</div>
                      <div className="cc-approval-actions">
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busyId === item.id}
                          onClick={() => void onDecide(item, "approve")}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          disabled={busyId === item.id}
                          onClick={() => void onDecide(item, "decline")}
                        >
                          Decline
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <h3 className="cc-subh">Live Intelligence</h3>
              <div className="cc-feed">
                {(data?.needs_attention || []).length === 0 && (data?.top_alerts || []).length === 0 ? (
                  <div className="cc-feed-item tip">
                    <span>CLEAR</span>
                    No urgent alerts — say Hi Tia for a briefing.
                  </div>
                ) : null}
                {(data?.needs_attention || []).slice(0, 2).map((n, i) => (
                  <div key={`n-${i}`} className="cc-feed-item warn">
                    <span>NEED</span>
                    {n}
                  </div>
                ))}
                {(data?.top_alerts || []).slice(0, 3).map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className="cc-feed-item live"
                    onClick={() => navigate(`/alerts/${a.id}`)}
                  >
                    <span>{(a.severity || "info").toUpperCase()}</span>
                    {a.short_code}: {a.title}
                  </button>
                ))}
              </div>
              <div className="cc-quick">
                <h4>Ask Tia</h4>
                <div className="cc-quick-row">
                  {(data?.quick_commands || []).map((q) => (
                    <button
                      key={q.id}
                      type="button"
                      className="cc-chip"
                      title={q.prompt}
                      onClick={() => {
                        window.dispatchEvent(new CustomEvent("tia-quick-command", { detail: q.prompt }));
                      }}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              </div>
              <h3 className="cc-subh">Mission Ops</h3>
              <div className="cc-mission-grid">
                {missionTiles.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`cc-mission-tile ${t.tone}`}
                    onClick={() => navigate(t.path)}
                    title={`Open ${t.label}`}
                  >
                    <span>{t.label}</span>
                    <strong>{t.value.toLocaleString()}</strong>
                  </button>
                ))}
              </div>
            </>
          )}

          {panel === "routines" && (
            <>
              <h3>Scheduled Routines</h3>
              <p className="muted cc-empty-note">Morning SOC brief fires once per local day when this console is open.</p>
              <div className="cc-routines">
                {(data?.routines || []).map((r) => (
                  <div key={r.id} className="cc-routine">
                    <div className="cc-routine-head">
                      <strong>{r.name}</strong>
                      <label className="cc-switch">
                        <input
                          type="checkbox"
                          checked={Boolean(r.enabled)}
                          disabled={busyId === r.id}
                          onChange={(e) => void onToggleRoutine(r, e.target.checked)}
                        />
                        {r.enabled ? "On" : "Off"}
                      </label>
                    </div>
                    <div className="cc-routine-meta">
                      {String(r.hour_local).padStart(2, "0")}:{String(r.minute_local || 0).padStart(2, "0")} {r.timezone}
                      {r.last_run_at ? ` · last ${new Date(r.last_run_at).toLocaleString()}` : " · never run"}
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={busyId === r.id}
                      onClick={() => void onRunRoutine(r)}
                    >
                      Run now
                    </button>
                    {r.last_spoken && <div className="cc-routine-spoken muted">{r.last_spoken}</div>}
                  </div>
                ))}
              </div>
            </>
          )}

          {panel === "voice" && (
            <>
              <h3>AI Voice</h3>
              <p className="muted cc-empty-note">
                Wake: <strong>Hi Tia</strong> · STT {data?.voice?.server_stt ? "ready" : "offline"} · TTS{" "}
                {data?.voice?.neural_tts ? "neural" : "browser"}
              </p>
              <ul className="cc-voice-opts">
                <li>
                  <label>
                    <input
                      type="checkbox"
                      checked={voice.freeHand}
                      onChange={(e) => updateVoice({ freeHand: e.target.checked })}
                    />
                    Free Hand (always listen for Hi Tia)
                  </label>
                </li>
                <li>
                  <label>
                    <input
                      type="checkbox"
                      checked={voice.speakResponses}
                      onChange={(e) => updateVoice({ speakResponses: e.target.checked })}
                    />
                    Speak responses aloud
                  </label>
                </li>
                <li>
                  <label>
                    <input
                      type="checkbox"
                      checked={voice.autoApprove}
                      onChange={(e) => {
                        if (
                          e.target.checked &&
                          !window.confirm("Auto-approve applies ticket updates without Needs You. Continue?")
                        ) {
                          return;
                        }
                        updateVoice({ autoApprove: e.target.checked });
                      }}
                    />
                    Auto-approve ticket actions (off by default)
                  </label>
                </li>
              </ul>
            </>
          )}
        </section>
      </div>

      <div className="cc-dock">
        <div className="cc-dock-status">
          <span className="cc-dock-pill">{voice.freeHand ? "FREE HAND" : "DOCK"}</span>
          <span>Wake phrase: Hi Tia</span>
          {(data?.pending_approvals || 0) > 0 && (
            <button type="button" className="cc-chip" onClick={() => setPanel("ops")}>
              {data?.pending_approvals} need you
            </button>
          )}
        </div>
        <div className="cc-dock-chat">
          <TiaDockSlot />
        </div>
      </div>
    </div>
  );
}
