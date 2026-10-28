# Repeatable Phase 1 benchmark

## Current evidence

Regression tests use deterministic fake providers. Native integration tests verify overlay protocol settings, compact geometry, focus preservation, reversible bindings, actual microphone cancellation without upload, and visible paste into a disposable GTK entry.

Live Groq/OpenAI accuracy and release-to-visible-output latency have **not been measured**: credentials were absent during implementation and the private credential request timed out. No ≤3 second p95 claim is made, and the default remains `single`. The benchmark runner is ready for a consented corpus once credentials are available.

The native HUD test observed roughly 20–22 ms from a warm IPC event to a correctly sized mapped surface in local runs. This excludes native hotkey delivery, microphone initialization, actual first-pixel observation, and cold process startup. It does not establish the specification's complete key-down-to-first-visible-frame criterion.

## Prepare a consented corpus

Each WAV must be mono, 16-bit PCM, 16 kHz. Convert an existing consented recording with:

```bash
ffmpeg -i input.wav -ar 16000 -ac 1 -c:a pcm_s16le fixture.wav
```

Keep recordings outside the repository, or in an ignored private directory. Example `manifest.json`:

```json
[
  {"id":"short-technical", "audio":"short.wav", "reference":"short.txt"},
  {"id":"long-pauses", "audio":"long.wav", "reference":"long.txt"}
]
```

Reference paths are relative to the manifest. Cover 1–5, 10–15, 20–30, and 60–120 seconds; repetitions, false starts, technical terms, numeric strings, URLs, pauses, quiet voices, noise, and Hindi/English mixing. Use non-sensitive synthetic fixtures first. Compare exact numeric/URL/repetition preservation manually in addition to WER. Empty and accidental recordings should also be exercised through the live capture state machine, which rejects them before provider upload.

## Run A/B

After exporting credentials and verifying model access:

```bash
.venv/bin/caelum benchmark /private/corpus/manifest.json --repeat 5 --output benchmark-results.json
```

Both strategies use identical PCM/reference inputs. The chunked path replays the *recording schedule in real time* so completed chunks can finish before release; it does not upload all chunks after release and call that background streaming. Order alternates between repetitions to reduce connection-warmth ordering bias. The first request remains a cold-client observation; report it separately for larger studies. Long fixtures make the run take their actual recording duration per chunked repetition.

The JSON contains per-run release-to-text-ready milliseconds, raw and cleaned word error rates, actual HTTP-call count, retry count, uploaded bytes, sample boundaries, response times, cleanup times, token usage when supplied, and failures. WER ignores case and Unicode punctuation while preserving combining marks. This normalization is unsuitable as the sole validator of code/numbers; use literal regression checks as well. No transcript is written into the report. Cost is not estimated without verified billing assumptions.

**Text-ready timing excludes insertion and application rendering.** To measure the primary metric, record the timestamp of physical key release and observe the target field's visible change with an instrumented application or a consented desktop recording. `caelum control status` reports `release_to_dispatch_ms` and marks `visible_insertion_observed=false`; never relabel that as visible-output latency.

## Decision rule

Keep `single` unless paired corpus runs demonstrate lower p95 release-to-visible-output latency, no degraded WER/literal preservation, no seam losses/duplicates, and no increased error rate. Inspect raw/cleaned differences in a controlled, opt-in evaluation rather than adding transcript logs to normal operation. Conservative seam repair may make chunking slower or increase uploaded bytes; that is an actionable outcome, not a reason to remove repair.

Use at least 20–30 runs per relevant duration/network bucket before treating p95 as useful. Document cold versus warm behavior, cleanup fallbacks, boundary-repair frequency, microphone, language, machine, network, provider model IDs, dates, and failures. The benchmark tool leaves the default unchanged.
