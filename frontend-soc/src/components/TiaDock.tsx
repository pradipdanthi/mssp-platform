import { createContext, useContext, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import ChatPanel from "./ChatPanel";

/**
 * One TIA panel for the whole console. The panel renders into a detached DOM node that
 * is moved between hosts, so changing route never unmounts it: the microphone session,
 * the pending "Shall I open it?" and the conversation survive opening a case.
 */
type Dock = { node: HTMLDivElement; park: () => void };
const DockContext = createContext<Dock | null>(null);

export function TiaDockProvider({ floating, children }: { floating: boolean; children: ReactNode }) {
  const [node] = useState(() => {
    const el = document.createElement("div");
    el.className = "tia-dock-node";
    return el;
  });
  const floatRef = useRef<HTMLDivElement | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const park = () => {
    if (floatRef.current && node.parentElement !== floatRef.current) floatRef.current.appendChild(node);
  };

  useLayoutEffect(() => {
    if (!node.parentElement) park();
  });

  return (
    <DockContext.Provider value={{ node, park }}>
      {children}
      <aside className={`tia-float-dock ${floating ? "" : "tia-float-dock-hidden"} ${collapsed ? "collapsed" : ""}`} aria-label="Tia">
        <button type="button" className="tia-float-toggle" onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? "Tia ▴" : "Tia ▾"}
        </button>
        <div className="tia-float-host" ref={floatRef} />
      </aside>
      {createPortal(<ChatPanel />, node)}
    </DockContext.Provider>
  );
}

/** Place the shared panel here while this component is mounted. */
export function TiaDockSlot() {
  const dock = useContext(DockContext);
  const hostRef = useRef<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    if (!dock || !hostRef.current) return;
    hostRef.current.appendChild(dock.node);
    return () => dock.park();
  }, [dock]);
  return <div className="tia-dock-slot" ref={hostRef} />;
}
