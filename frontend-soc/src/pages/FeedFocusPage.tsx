import { useCallback, useState } from "react";
import ActivityFeed from "../components/ActivityFeed";
import ChatPanel from "../components/ChatPanel";
import type { SocKpis } from "../components/SocTiles";

type Focus = "event" | "vulnerability" | "patch_gap";

export default function FeedFocusPage({ focus }: { focus: Focus }) {
  const [, setKpis] = useState<SocKpis | null>(null);
  const onKpis = useCallback((k: Record<string, number>) => {
    setKpis(k as SocKpis);
  }, []);

  const title =
    focus === "event" ? "Events" : focus === "vulnerability" ? "Vulnerabilities" : "Patch Gaps";

  return (
    <div className="ops-main ops-main-fill">
      <aside className="ops-chat-pane">
        <ChatPanel />
      </aside>
      <div className="ops-feed-wrap">
        <div className="feed-focus-banner muted">Filtered live feed · {title}</div>
        <ActivityFeed focus={focus} onKpis={onKpis} />
      </div>
    </div>
  );
}
