/**
 * Wake matching and end-of-speech settle times. Kept free of mic/STT imports so
 * the wait can be unit-tested in node.
 */

const TIA_NAME = String.raw`(?:tia|tea|teah|thea|tiya|tiaa|tiaah|tia'|t\.?\s*i\.?\s*a)`;
const GREET = String.raw`(?:hey|hi|hello|ok|okay|yo|ah|oh)`;
const WAKE_RE = new RegExp(String.raw`\b${GREET}\s+${TIA_NAME}\b|\b${TIA_NAME}\b[,!]?(?:\s|$)`, "i");

export function matchWake(text: string): { woke: boolean; remainder: string } {
  const raw = (text || "").trim();
  if (!raw) return { woke: false, remainder: "" };
  const norm = raw.replace(/[^\w\s']/g, " ").replace(/\s+/g, " ").trim();

  const greeter = new RegExp(String.raw`^\s*${GREET}\s+${TIA_NAME}\b[,!. ]*`, "i");
  if (greeter.test(norm)) {
    return { woke: true, remainder: norm.replace(greeter, "").trim() };
  }

  const bare = new RegExp(String.raw`^\s*${TIA_NAME}\b[,!. ]*`, "i");
  if (bare.test(norm) && norm.length <= 80) {
    return { woke: true, remainder: norm.replace(bare, "").trim() };
  }

  const fuzzyName = /\b(tia|tea|teah|thea|tiya|tiaa|dear|tier|chia|dia|sia|via)\b/i;
  const fuzzyGreet = /\b(hi|hey|hello|ok|okay|yo)\b/i;
  if (norm.length <= 48 && fuzzyGreet.test(norm) && fuzzyName.test(norm)) {
    const remainder = norm
      .replace(fuzzyGreet, " ")
      .replace(fuzzyName, " ")
      .replace(/\s+/g, " ")
      .trim();
    return { woke: true, remainder };
  }

  if (WAKE_RE.test(norm)) {
    const remainder = norm
      .replace(new RegExp(String.raw`${GREET}\s+${TIA_NAME}`, "ig"), " ")
      .replace(new RegExp(String.raw`\b${TIA_NAME}\b`, "ig"), " ")
      .replace(/\s+/g, " ")
      .trim();
    return { woke: true, remainder };
  }

  return { woke: false, remainder: raw };
}

/** Soft openers that often arrive as a Chrome "final" before the real question. */
const LEAD_IN = /^(can you|could you|would you|will you|please|hey|ok|okay|so|um|uh)\b/i;

export function looksIncompleteUtterance(text: string): boolean {
  const t = (text || "").trim();
  if (!t) return true;

  const { woke, remainder } = matchWake(t);
  const body = (woke ? remainder : t).trim();
  const words = body.split(/\s+/).filter(Boolean);
  if (woke && words.length === 0) return false;
  if (/[.!?…]["')\]]?\s*$/.test(t)) return false;
  if (/[,;:…]\s*$/.test(t)) return true;
  if (/\.{2,}\s*$/.test(t)) return true;

  const lower = t.toLowerCase().replace(/['']/g, "'");
  // "Can you check" / "whether" alone are mid-thought, not commands.
  if (LEAD_IN.test(body) && words.length <= 5 && !/[.!?]$/.test(body)) return true;
  if (/\b(whether|if|about|regarding)\s*$/i.test(lower)) return true;
  if (
    /\b(and|or|but|so|because|if|when|while|that|which|who|whom|whose|what|where|how|why|to|for|of|the|a|an|my|your|our|their|its|is|are|was|were|am|be|been|being|have|has|had|do|does|did|can|could|would|should|will|shall|may|might|must|with|about|from|into|onto|on|in|at|as|than|then|also|just|please|tell|give|show|list|check|look|need|want|get|make|take|see|find|open|close|update|set|mark|run|start|stop|processing)\s*$/i.test(
      lower
    )
  ) {
    return true;
  }
  if (woke && words.length === 1 && words[0].length < 4) return true;
  return false;
}

export function settleWaitMs(text: string, inConversation: boolean): number {
  const incomplete = looksIncompleteUtterance(text);
  const { woke, remainder } = matchWake(text);
  const bareWake = woke && !(remainder || "").trim();
  if (bareWake && !inConversation) return 280;
  // Hold long enough for a natural 1–3 s breath without blocking finished commands.
  if (incomplete) return inConversation ? 2600 : 2200;
  return inConversation ? 280 : 220;
}
