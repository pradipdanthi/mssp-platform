import { ReactNode } from "react";
import "../parity/admin-parity.css";

/** Scrollable host for Admin-parity alert/incident pages (full triage + EDR Isolate). */
export default function ParityScroll({ children }: { children: ReactNode }) {
  return <div className="parity-scroll">{children}</div>;
}
