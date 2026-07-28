import type { ProcessTreeNode } from "../../api/edr";

type Props = {
  root?: ProcessTreeNode | null;
  message?: string | null;
};

function Node({ node, depth }: { node: ProcessTreeNode; depth: number }) {
  const label = node.process_name || node.command_line || `PID ${node.pid ?? "?"}`;
  return (
    <li className="edr-process-node" style={{ marginLeft: depth * 12 }}>
      <span className="cell-mono">{label}</span>
      {node.user ? <span className="muted"> — {node.user}</span> : null}
      {node.child_processes?.length ? (
        <ul className="edr-process-children">
          {node.child_processes.map((child, idx) => (
            <Node key={`${child.pid}-${idx}`} node={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export default function ProcessTreeWidget({ root, message }: Props) {
  if (!root) {
    return <p className="muted">{message ?? "No process tree available."}</p>;
  }
  return (
    <div className="edr-process-tree card-surface">
      <ul className="edr-process-children" style={{ listStyle: "none", paddingLeft: 0 }}>
        <Node node={root} depth={0} />
      </ul>
    </div>
  );
}
