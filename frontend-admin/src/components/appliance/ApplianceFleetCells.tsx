import { useEffect, useState } from "react";
import type { Appliance } from "../../api/admin";
import {
  formatApplianceVersion,
  formatHeartbeatTitle,
  formatRelativeHeartbeat,
  formatResourcePercent,
  heartbeatFreshness,
  pickHeartbeatTimestamp,
  resourceStressClass,
  catalogueServiceStatus,
  serviceFullLabel,
  serviceShortLabel,
  sortServiceIds,
} from "../../utils/applianceFleet";

function useRelativeClock(intervalMs = 30000) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((value) => value + 1), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
}

export function ApplianceHeartbeatCell({ appliance }: { appliance: Appliance }) {
  useRelativeClock();
  const iso = pickHeartbeatTimestamp(appliance.last_seen_at, appliance.heartbeat_at);
  const freshness = heartbeatFreshness(iso);
  return (
    <span
      className={`appliance-heartbeat-cell appliance-heartbeat-cell--${freshness}`}
      title={formatHeartbeatTitle(iso)}
    >
      {formatRelativeHeartbeat(iso)}
    </span>
  );
}

export function ApplianceVersionCell({ appliance }: { appliance: Appliance }) {
  const version = formatApplianceVersion(
    appliance.config_version,
    appliance.git_commit,
    appliance.agent_version
  );
  return (
    <span className="appliance-version-cell" title={version.title}>
      <span className="appliance-version-cell__primary">{version.primary}</span>
      {version.secondary ? (
        <span className="appliance-version-cell__secondary">{version.secondary}</span>
      ) : null}
    </span>
  );
}

export function ApplianceHealthCell({ appliance }: { appliance: Appliance }) {
  const health = appliance.health_status ?? "Unknown";
  const hasResources =
    appliance.cpu_percent != null ||
    appliance.memory_percent != null ||
    appliance.disk_percent != null;

  return (
    <div className="appliance-health-cell">
      <span className={`appliance-health-cell__status appliance-health-cell__status--${health}`}>
        {health}
      </span>
      {hasResources ? (
        <div className="appliance-health-cell__resources">
          <span className={resourceStressClass(appliance.cpu_percent)} title="CPU">
            CPU {formatResourcePercent(appliance.cpu_percent)}
          </span>
          <span className="appliance-health-cell__sep">·</span>
          <span className={resourceStressClass(appliance.memory_percent)} title="Memory">
            Mem {formatResourcePercent(appliance.memory_percent)}
          </span>
          <span className="appliance-health-cell__sep">·</span>
          <span className={resourceStressClass(appliance.disk_percent)} title="Disk">
            Disk {formatResourcePercent(appliance.disk_percent)}
          </span>
        </div>
      ) : (
        <div className="appliance-health-cell__resources appliance-health-cell__resources--empty">
          No resource metrics yet
        </div>
      )}
    </div>
  );
}

export function ApplianceServicesCell({
  services,
  showInactive = false,
}: {
  services: string[] | null | undefined;
  showInactive?: boolean;
}) {
  if (showInactive) {
    const rows = catalogueServiceStatus(services);
    return (
      <div
        className="appliance-services-cell appliance-services-cell--full"
        title="Local engines mapped to the same capability catalog as Tier Operations"
      >
        {rows.map((row) => (
          <span
            key={row.id}
            className={`appliance-service-badge${row.active ? "" : " appliance-service-badge--inactive"}`}
            title={row.full}
          >
            {row.catalogName.length > 18 ? row.label : row.catalogName}
          </span>
        ))}
      </div>
    );
  }
  const sorted = sortServiceIds(services);
  if (sorted.length === 0) {
    return (
      <span className="appliance-services-cell appliance-services-cell--empty" title="No entitled services reported">
        None
      </span>
    );
  }

  const visible = sorted.slice(0, 4);
  const overflow = sorted.length - visible.length;

  return (
    <div className="appliance-services-cell" title={sorted.map(serviceFullLabel).join(", ")}>
      {visible.map((serviceId) => (
        <span key={serviceId} className="appliance-service-badge" title={serviceFullLabel(serviceId)}>
          {serviceShortLabel(serviceId)}
        </span>
      ))}
      {overflow > 0 ? <span className="appliance-service-badge appliance-service-badge--more">+{overflow}</span> : null}
    </div>
  );
}
