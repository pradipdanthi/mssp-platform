// Run with: node --experimental-strip-types --test src/lib/tiaEars.test.ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { looksIncompleteUtterance, settleWaitMs } from "./tiaUtterance.ts";

describe("voice settle wait", () => {
  it("does not park a finished command for more than a third of a second", () => {
    assert.equal(looksIncompleteUtterance("what's critical"), false);
    assert.equal(looksIncompleteUtterance("yes, open it"), false);
    assert.equal(looksIncompleteUtterance("describe the first one"), false);
    assert.equal(looksIncompleteUtterance("investigate this"), false);
    assert.ok(settleWaitMs("what's critical", false) <= 280);
    assert.ok(settleWaitMs("yes, open it", true) <= 280);
    assert.ok(settleWaitMs("investigate this", true) <= 280);
  });

  it("still holds when the last word is clearly unfinished", () => {
    assert.equal(looksIncompleteUtterance("what's the"), true);
    assert.ok(settleWaitMs("what's the", true) >= 1600);
  });

  it("holds a lead-in like can you check through a natural pause", () => {
    assert.equal(looksIncompleteUtterance("Can you check"), true);
    assert.equal(looksIncompleteUtterance("Can you check whether"), true);
    assert.equal(
      looksIncompleteUtterance(
        "Can you check whether Wazuh and Shuffle are actually processing work?"
      ),
      false
    );
    assert.ok(settleWaitMs("Can you check", true) >= 2200);
  });
});
