import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { listUiCommands, speakTia } from "../api/soc";
import { useToast } from "../parity/components/soc/ToastProvider";
import { uiBridge } from "../lib/tiaBridge";
import { tiaSessionId } from "../lib/tiaSession";
import { appendTranscript } from "../lib/tiaTranscript";
import { playBase64Audio, speakText } from "../lib/voice";

/**
 * Always mounted in the shell. It (1) recovers commands the server issued while this
 * tab was disconnected, (2) shows the verified confirmation or failure if no chat
 * panel is mounted, and (3) reports the command-to-
 * acknowledgement time for latency measurement.
 */
export default function TiaCommandBridge() {
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    const recover = () => {
      listUiCommands(tiaSessionId())
        .then((r) => (r.commands || []).forEach((c) => uiBridge.register(c, navigate)))
        .catch((e) => {
          // 401 is handled by the normal session flow; 404/503 mean the server has no conversation support yet.
          if (!(e instanceof ApiError)) return;
        });
    };
    recover();
    const onOnline = () => recover();
    const onVisible = () => {
      if (document.visibilityState === "visible") recover();
    };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [navigate]);

  useEffect(() => {
    return uiBridge.subscribe((e) => {
      if (e.kind === "navigating") return;
      if (uiBridge.chatMounted()) return; // the chat panel shows and speaks it
      appendTranscript({
        role: "assistant",
        text: e.text,
        meta: e.kind === "confirmed" ? "Tia · dashboard confirmed" : "Tia · not confirmed",
        error: e.kind === "failed",
      });
      toast(e.text, e.kind === "confirmed" ? "success" : "error");
      void speak(e.spoken);
    });
  }, [toast]);

  return null;
}

async function speak(line: string): Promise<void> {
  try {
    const raw = localStorage.getItem("tia_voice_settings_v1");
    if (raw && (JSON.parse(raw) as { speakResponses?: boolean }).speakResponses === false) return;
  } catch {
    /* default: speak */
  }
  try {
    const audio = await speakTia(line);
    if (audio.available && audio.audio_base64 && (await playBase64Audio(audio.audio_base64, audio.content_type || "audio/mpeg"))) return;
  } catch {
    /* fall back to the browser voice */
  }
  await speakText(line);
}

