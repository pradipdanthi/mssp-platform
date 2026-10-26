import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ActivityItem, AlertRow } from "../api/soc";

export type SeverityFilter = "critical" | "high" | "medium" | "low";

type OpsState = {
  query: string;
  selectedAlertId: string | null;
  selectedAlert: AlertRow | null;
  tab: "alerts" | "incidents";
  feedPaused: boolean;
  activity: ActivityItem[];
  setQuery: (q: string) => void;
  selectAlert: (a: AlertRow | null) => void;
  selectAlertId: (id: string | null) => void;
  setTab: (t: "alerts" | "incidents") => void;
  setFeedPaused: (p: boolean) => void;
  mergeActivity: (items: ActivityItem[], mode: "snapshot" | "prepend") => void;
};

const Ctx = createContext<OpsState | undefined>(undefined);

export function OpsProvider({ children }: { children: React.ReactNode }) {
  const [query, setQuery] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<AlertRow | null>(null);
  const [tab, setTab] = useState<"alerts" | "incidents">("alerts");
  const [feedPaused, setFeedPaused] = useState(false);
  const [activity, setActivity] = useState<ActivityItem[]>([]);

  const mergeActivity = useCallback((items: ActivityItem[], mode: "snapshot" | "prepend") => {
    setActivity((prev) => {
      if (mode === "snapshot") return items.slice(0, 250);
      const map = new Map<string, ActivityItem>();
      for (const it of [...items, ...prev]) map.set(it.id, it);
      return Array.from(map.values())
        .sort((a, b) => (a.ts < b.ts ? 1 : -1))
        .slice(0, 250);
    });
  }, []);

  const value = useMemo<OpsState>(
    () => ({
      query,
      selectedAlertId,
      selectedAlert,
      tab,
      feedPaused,
      activity,
      setQuery,
      selectAlert: (a) => {
        setSelectedAlert(a);
        setSelectedAlertId(a?.id ?? null);
      },
      selectAlertId: (id) => {
        setSelectedAlertId(id);
        if (!id) setSelectedAlert(null);
      },
      setTab,
      setFeedPaused,
      mergeActivity,
    }),
    [query, selectedAlertId, selectedAlert, tab, feedPaused, activity, mergeActivity]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useOps(): OpsState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useOps outside OpsProvider");
  return v;
}
