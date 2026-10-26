import type { ProcessTreeNode } from "../../api/edr";

type Props = {
  root?: ProcessTreeNode | null;
  message?: string | null;
};

function signedLabel(status?: string | null): string | null {
  if (!status) return null;
  if (status === "signed" || status === "likely_signed") return "Signed";
  if (status === "unsigned") return "Unsigned";
  return null;
}

function Node({ node, depth }: { node: ProcessTreeNode; depth: number }) {
  const label = node.process_name || node.command_line || `PID ${node.pid ?? "?"}`;
  const signed = signedLabel(node.signed_status);
  return (
    <li className="edr-process-node" style={{ marginLeft: depth * 14 }}>
      <div className="edr-process-line">
        <span className="cell-mono">{label}</span>
        {node.pid != null ? <span className="muted"> pid={node.pid}</span> : null}
        {node.user ? <span className="muted"> — {node.user}</span> : null}
        {signed ? (
          <span className={`edr-signed-badge edr-signed-${signed.toLowerCase()}`}>{signed}</span>
        ) : null}
      </div>
      {node.command_line && node.process_name ? (
        <div className="edr-process-cmdline muted cell-mono">{node.command_line}</div>
      ) : null}
      {node.mitre_techniques && node.mitre_techniques.length > 0 ? (
        <div className="edr-mitre-tags">
          {node.mitre_techniques.map((t) => (
            <span key={t} className="edr-mitre-tag">
              {t}
            </span>
          ))}
        </div>
      ) : null}
      {node.child_processes?.length ? (
        <ul className="edr-process-children">
          {node.child_processes.map((child, idx) => (
            <Node key={`${child.process_guid || child.pid}-${idx}`} node={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export default function ProcessTreeWidget({ root, message }: Props) {
  if (!root) {
    return (
      <p className="muted">
        {message ??
          "No process-creation telemetry found for this incident. This usually means Sysmon/process auditing is not flowing yet — not that the attack had no process chain."}
      </p>
    );
  }
  return (
    <div className="edr-process-tree card-surface">
      <ul className="edr-process-children" style={{ listStyle: "none", paddingLeft: 0 }}>
        <Node node={root} depth={0} />
      </ul>
    </div>
  );
}
