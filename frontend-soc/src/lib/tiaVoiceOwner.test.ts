// Run with: node --experimental-strip-types --test src/lib/tiaVoiceOwner.test.ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { newVoiceOwnerId } from "./tiaVoiceOwner.ts";

describe("tiaVoiceOwner", () => {
  it("creates distinct owner ids", () => {
    const a = newVoiceOwnerId();
    const b = newVoiceOwnerId();
    assert.notEqual(a, b);
    assert.match(a, /^vo-/);
  });
});
