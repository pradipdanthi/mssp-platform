/** Compact service health ribbon — capability names only. */
export default function EngineStatusRibbon() {
  return (
    <div className="engine-status-ribbon" aria-label="Security service status">
      <span>
        SIEM: <span className="engine-ok">OK</span>
      </span>
      <span className="engine-sep">|</span>
      <span>
        Incident Response: <span className="engine-ok">OK</span>
      </span>
      <span className="engine-sep">|</span>
      <span>
        Automation: <span className="engine-ok">Active</span>
      </span>
      <span className="engine-sep">|</span>
      <span>
        Vuln Mgmt: <span className="engine-ok">OK</span>
      </span>
    </div>
  );
}
