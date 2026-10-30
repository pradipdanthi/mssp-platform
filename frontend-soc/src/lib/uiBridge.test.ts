// Run with: node --experimental-strip-types --test src/lib/uiBridge.test.ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createUiBridge, type AckResult, type BridgeEvent, type UiCommand } from "./uiBridge.ts";

const cmd = (id: string, alert: string): UiCommand => ({
  id,
  type: "open_case",
  payload: { alert_id: alert, title: "Credential dumping", short_code: "CNVA", severity: "critical" },
});

function harness(over: { ack?: (id: string, b: { loaded_alert_id?: string; failure?: string }) => Promise<AckResult> } = {}) {
  const acks: { id: string; body: { loaded_alert_id?: string; failure?: string } }[] = [];
  const nav: string[] = [];
  const events: BridgeEvent[] = [];
  const timers: { fn: () => void; ms: number; live: boolean }[] = [];
  const bridge = createUiBridge({
    ack:
      over.ack ??
      (async (id, body) => {
        acks.push({ id, body });
        return { status: "acknowledged", verified: true, text: "Confirmed: Credential dumping is open on your screen.", spoken: "Credential dumping is open." };
      }),
    detailPath: (a) => `/alerts/${a}`,
    setTimer: (fn, ms) => {
      const t = { fn, ms, live: true };
      timers.push(t);
      return t;
    },
    clearTimer: (h) => {
      (h as { live: boolean }).live = false;
    },
    retryDelayMs: 0,
  });
  bridge.subscribe((e) => events.push(e));
  const flush = () => new Promise((r) => setImmediate(r));
  return { bridge, acks, nav, events, timers, flush, navigate: (p: string) => nav.push(p) };
}

describe("uiBridge", () => {
  it("navigates, and confirms only after the page reports the loaded alert", async () => {
    const h = harness();
    assert.equal(h.bridge.register(cmd("c1", "A1"), h.navigate), "started");
    assert.deepEqual(h.nav, ["/alerts/A1"]);
    assert.equal(h.acks.length, 0, "no acknowledgement before the page loads");
    assert.equal(h.events.some((e) => e.kind === "confirmed"), false);
    h.bridge.alertLoaded("A1");
    await h.flush();
    assert.deepEqual(h.acks, [{ id: "c1", body: { loaded_alert_id: "A1" } }]);
    assert.equal(h.events.filter((e) => e.kind === "confirmed").length, 1);
  });

  it("acts once when the same command is delivered again (reconnect or retry)", async () => {
    const h = harness();
    h.bridge.register(cmd("c1", "A1"), h.navigate);
    assert.equal(h.bridge.register(cmd("c1", "A1"), h.navigate), "duplicate");
    h.bridge.alertLoaded("A1");
    h.bridge.alertLoaded("A1");
    await h.flush();
    assert.equal(h.nav.length, 1);
    assert.equal(h.acks.length, 1);
    assert.equal(h.bridge.register(cmd("c1", "A1"), h.navigate), "duplicate", "also after completion");
  });

  it("confirms immediately when that alert is already on screen, without navigating", async () => {
    const h = harness();
    h.bridge.alertLoaded("A1");
    h.bridge.register(cmd("c2", "A1"), h.navigate);
    await h.flush();
    assert.equal(h.nav.length, 0);
    assert.equal(h.acks.length, 1);
  });

  it("does not confirm when a different alert loads", async () => {
    const h = harness();
    h.bridge.register(cmd("c3", "A1"), h.navigate);
    h.bridge.alertLoaded("OTHER");
    await h.flush();
    assert.equal(h.acks.length, 0);
    assert.equal(h.bridge.pendingCount(), 1);
  });

  it("reports a load failure instead of staying silent", async () => {
    const h = harness({ ack: async () => ({ status: "failed", verified: false, text: "Your dashboard couldn't open it.", reason: "alert_load_failed" }) });
    h.bridge.register(cmd("c4", "A1"), h.navigate);
    h.bridge.alertLoadFailed("A1", "alert_load_failed");
    await h.flush();
    const failed = h.events.find((e) => e.kind === "failed");
    assert.ok(failed && failed.kind === "failed");
    assert.equal(h.events.some((e) => e.kind === "confirmed"), false);
  });

  it("reports a timeout when the page never loads", async () => {
    const seen: { failure?: string }[] = [];
    const h = harness({
      ack: async (_id, body) => {
        seen.push(body);
        return { status: "failed", verified: false, text: "The dashboard never confirmed.", reason: "expired" };
      },
    });
    h.bridge.register(cmd("c5", "A1"), h.navigate);
    h.timers.find((t) => t.live)!.fn();
    await h.flush();
    assert.deepEqual(seen, [{ failure: "page_did_not_load" }]);
    assert.ok(h.events.some((e) => e.kind === "failed"));
  });

  it("retries a failed acknowledgement and then reports that it could not confirm", async () => {
    let calls = 0;
    const h = harness({
      ack: async () => {
        calls += 1;
        throw new Error("network down");
      },
    });
    h.bridge.register(cmd("c6", "A1"), h.navigate);
    h.bridge.alertLoaded("A1");
    for (let i = 0; i < 10; i += 1) {
      await h.flush();
      h.timers.filter((t) => t.live && t.ms === 0).forEach((t) => ((t.live = false), t.fn()));
    }
    assert.equal(calls, 4, "initial try plus three retries");
    const failed = h.events.find((e) => e.kind === "failed");
    assert.ok(failed && failed.kind === "failed" && failed.reason.startsWith("ack_unreachable"));
  });

  it("recovers on the second attempt without a duplicate confirmation", async () => {
    let calls = 0;
    const h = harness({
      ack: async () => {
        calls += 1;
        if (calls === 1) throw new Error("blip");
        return { status: "acknowledged", verified: true, text: "Confirmed.", spoken: "Open." };
      },
    });
    h.bridge.register(cmd("c7", "A1"), h.navigate);
    h.bridge.alertLoaded("A1");
    for (let i = 0; i < 6; i += 1) {
      await h.flush();
      h.timers.filter((t) => t.live && t.ms === 0).forEach((t) => ((t.live = false), t.fn()));
    }
    assert.equal(h.events.filter((e) => e.kind === "confirmed").length, 1);
  });

  it("ignores command types it does not implement", () => {
    const h = harness();
    assert.equal(h.bridge.register({ id: "x", type: "isolate_host" as never, payload: { alert_id: "A1" } }, h.navigate), "unsupported");
    assert.equal(h.nav.length, 0);
  });
});
