# Voice speech-to-response stages (2026-10-30)

Simulated microphone (`?voice=fixture` + `__say`). Neural TTS is real (`edge_tts` on the throwaway API). Physical microphone is not included.

## What was measured

| Stage | How | Simulated mic? | Real TTS? | Real model? |
|---|---|---|---|---|
| End-of-speech settle | fixture `operator_speech_end` → converse HTTP | yes | n/a | n/a |
| `/converse` | server `stages.total` + client `chat_roundtrip` | n/a | n/a | no (tools) |
| TTS HTTP | client `tts_roundtrip` (`/admin/soc-console/speak`) | n/a | **yes** | n/a |
| First useful audio | client `eos_to_first_audio` / `first_audio` | playback stubbed 2 s | synthesis real | n/a |
| Interrupt-to-stop | client `interrupt_to_stop` after `stopSpeaking()` | yes | n/a | n/a |
| Worker + model | `tia-e2e-agent` ingest → production `/api/v1/chat` | n/a | n/a | **yes** (synthetic dossier) |

## Simple voice turns (tools, no Cursor)

Settle wait for a finished command was **1.3–1.7 s** before this round. That was the dominant delay (converse itself is ~20–50 ms). It is now **220–280 ms**.

| Turn | settle (fixture) | converse | TTS HTTP | eos → first audio |
|---|---:|---:|---:|---:|
| Hi Tia, what's critical | 286 ms | 47–48 ms | **878 ms** | 943 ms |
| describe the first one (barge-in) | ~280 ms | 33 ms | 884 ms | 921 ms |
| yes, open it | 320 ms | 28 ms | 776 ms | 906 ms |
| what's the host on this one | 328 ms | 34 ms | 35 ms (cache hit) | 82 ms |
| investigate this (HOST-A2) | 333 ms | 42 ms | 797 ms | 843 ms |
| investigate this (HOST-A1) | — | 109 ms | 102 ms (cache) | 216 ms |

Dashboard open-case issue→verified ack: **32 ms**. Loaded URL `/alerts/0104dd4a-2634-48e9-8be1-92c56c9c7380` matched `loaded_alert_id`.

## Dominant delay after the settle fix

For a **new** spoken answer, **neural TTS (~800–970 ms)** is now the largest stage on the simple path. Cached identical phrases drop to ~35–100 ms. Combined eos→first audio on uncached simple turns is **~0.9–1.2 s**, under the 2.5 s first-useful-audio target. Typed converse remains tens of milliseconds and is not audio.

## Interruption

Spoken barge-in during list TTS: `__say("describe the first one")` while neural audio was playing. Playback paused. Client `interrupt_to_stop` **0 ms** (`stopSpeaking()` is synchronous). Fixture `tts_audio_pause` landed **293 ms** after `__say`, of which ~280 ms is the remaining settle wait. Continued conversation then worked without a second wake phrase.

## Worker + model (not first-audio)

HOST-A1 ingest adapter → production chat: **28.862 s**. Job `c4d4e9bf-1771-4257-b9f7-9d3f871f45e7` succeeded. This path is queued; converse did not wait for it.

HOST-A2 attempt 2 on the same evidence version did not add a second ticket note (effects ledger `already_committed` / one note per evidence version). HOST-A1 wrote a new `ticket_note` on INC-E2E-001.
