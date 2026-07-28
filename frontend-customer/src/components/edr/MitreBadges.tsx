type Props = {
  tactics: string[];
  techniques: { id: string; name: string }[];
};

export default function MitreBadges({ tactics, techniques }: Props) {
  if (!tactics.length && !techniques.length) {
    return <p className="muted">No MITRE ATT&amp;CK mapping yet.</p>;
  }
  return (
    <div className="edr-mitre-badges">
      {tactics.map((t) => (
        <span key={t} className="badge badge-medium edr-mitre-tactic">
          {t}
        </span>
      ))}
      {techniques.map((tech) => (
        <span key={tech.id} className="badge badge-low edr-mitre-technique" title={tech.name}>
          {tech.id}
          {tech.name ? ` — ${tech.name}` : ""}
        </span>
      ))}
    </div>
  );
}
