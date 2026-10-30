import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { interruptPlayback, looksLikeEcho } from "./tiaBargeIn.ts";

describe("tiaBargeIn", () => {
  it("drops TIA's own spoken line as echo", () => {
    const spoken = "This is a critical alert, Ransomware-like file renames on HOST-A2, for E2EA. Shall I open it?";
    assert.equal(looksLikeEcho("this is a critical alert ransomware like file renames", spoken), true);
    assert.equal(looksLikeEcho("Shall I open it", spoken), true);
  });

  it("does not treat a real follow-up as echo", () => {
    assert.equal(looksLikeEcho("Yes, please open it.", "Shall I open it?"), false);
    assert.equal(looksLikeEcho("Why did this trigger, and what have you checked?", "Opening it now."), false);
    assert.equal(looksLikeEcho("stop", "This is a long spoken line about an alert"), false);
    assert.equal(
      looksLikeEcho(
        "Critical",
        "Across all customers, 53 critical and 489 high are open. The most urgent is malware."
      ),
      false
    );
    assert.equal(looksLikeEcho("yes", "Shall I open it?"), false);
    assert.equal(looksLikeEcho("Stop it", "Across all customers, 53 critical alerts are open."), false);
  });

  it("measures interrupt-to-stop as the stop call itself", () => {
    let stopped = false;
    const ms = interruptPlayback(() => {
      stopped = true;
    });
    assert.equal(stopped, true);
    assert.ok(ms >= 0);
    assert.ok(ms < 50, `stop() itself should be well under 50ms, was ${ms}`);
  });
});
