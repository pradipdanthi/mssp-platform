# TIA latency baseline (measured 2026-10-30)

No historical "before" is invented. Sample sizes are in `n`. Percentiles from n < 20 are indicative.

Provisional targets: **2.5 s first useful audio** (simple turns); **300 ms interruption-to-stop**. Both require a physical microphone + TTS run. They are **unmet / unmeasured** on that path.

## What each number is

| Path | What was measured | What was excluded |
|---|---|---|
| Typed `/converse` on e2e rig | Control API + tools + DB | Browser paint, STT, TTS, Cursor, real engines |
| Typed `/chat` production baseline | Local snapshot (`tia-live`) | Speech, Cursor, real model |
| VM 117 `agent -p --mode ask` | Cursor CLI wall clock | Browser, STT, TTS |
| UI command issue→ack | Server timestamps on command a032c465 | Speech |
| Client `first_audio` / `interrupt_to_stop` in telemetry | **Test-injected** values from unit tests (640 ms / 210 ms), n=2 | Not a microphone or TTS measurement |

## Typed converse (e2e rig, 2026-10-30 16:09Z)

Artifact: `converse_latency.txt`. Cold vs warm not separated beyond first serial sample (all sub-120 ms).

| Path | mode | n | p50 | p95 | max | errors |
|---|---|---:|---:|---:|---:|---:|
| What's critical | serial | 8 | 21 ms | 49 ms | 49 ms | 0 |
| What's critical | concurrent x3 | 8 | 32 ms | 38 ms | 38 ms | 0 |
| How many alerts | serial | 8 | 18 ms | 20 ms | 20 ms | 0 |
| How many alerts | concurrent x3 | 8 | 32 ms | 39 ms | 39 ms | 0 |
| Engine health (live probes on rig) | serial | 8 | 69 ms | 114 ms | 114 ms | 0 |
| Engine health (cached) | serial | 8 | 15 ms | 18 ms | 18 ms | 0 |
| Model fallback (agent closed: honest unavailable) | serial | 3 | 84 ms | 87 ms | 87 ms | 0 |

Server-side stages (30 min window on that DB, mixed probe + browser): navigation p50 12 ms / p95 60 ms (n=93); status p50 15 ms (n=93); action p50 12 ms (n=29).

**Dashboard action completion (this conversation):** command issued 16:10:21.397964Z, acknowledged 16:10:21.55104Z → **153 ms** issue→verified ack. That is not first useful audio.

## Cursor CLI on production VM 117 (read-only baseline, earlier today)

Artifact: `docs/tia_measurements/2026-10-30_agent_cli_baseline/agent_chat_raw.json`.

| Path | n | p50 | p95 | max |
|---|---:|---:|---:|---:|
| `agent -p --mode ask` serial | 8 | 15.041 s | 18.506 s | 18.506 s |

`SOC_CONSOLE_CHAT_TIMEOUT_SECONDS` default **18**. Actual CLI execution p50 15.0 s, max 18.5 s: the timeout is the Cursor hop itself, not the converse tool path. Simple open/count/evidence on `/converse` do not wait for it (this round: investigate enqueue < 2 s in unit test; browser open did not wait).

## Voice

| Metric | Result | Classification |
|---|---|---|
| First useful audio (simple) vs 2.5 s | Not measured with real TTS + microphone | pending |
| Interrupt-to-stop vs 300 ms | `stopSpeaking()` itself < 50 ms in node fixture; physical barge-in not run | locally demonstrated (stop call) / pending (mic) |
| Browser fixture `__say` during TTS | Code no longer mutes STT during playback; echo filter added | implemented; fixture run of live interrupt **not captured this round** |
| Physical microphone interruption | Requires an operator at a workstation with mic permission | pending |

## Bottleneck (evidence, not a proposal to move VMs)

1. **Cursor CLI on VM 117 (~15 s p50)** dominates any turn that uses the supported Cursor chat path. That is why the 18 s timeout exists and sometimes loses.
2. **Converse tools are not the bottleneck** (tens of milliseconds).
3. **TTS / STT / browser** are unmeasured on a physical path; do not treat typed p50 as voice p50.
4. Proxmox/guest CPU correlation files from earlier today (`prod_chat_baseline/`, `agent_cli_baseline/`) sit next to the CLI times; they were captured during those runs. They do not justify resizing until a voice run is correlated with the same interval.

## Targets vs this baseline

| Target | Met? |
|---|---|
| 2.5 s first useful audio (simple) | **Unmet / unmeasured** on the voice path. Typed first token is ~20 ms and is not audio. |
| 300 ms interrupt-to-stop | **Unmet / unmeasured** on a physical microphone. Stop-call fixture is far under 300 ms and is not microphone proof. |
