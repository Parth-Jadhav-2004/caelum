# Privacy and resource policy

Microphone capture occurs only during an accepted held-hotkey session or the explicitly requested three-second input-level test in Settings. The test does not upload, play back, or save audio. Dictation audio is retained in bounded process memory for finalization and explicit retry, then references/buffers are discarded. Audio is never written to a history file. This is ordinary process-memory disposal, not a guarantee of secure erasure against swap, core dumps, or privileged inspection.

## Opt-in desktop history

`desktop.history_enabled` defaults to false. When enabled, completed final text is saved asynchronously **after** paste/clipboard dispatch, in an owner-only SQLite file beneath the user's data directory. The database records completion time, recording duration, whitespace-delimited word count, dispatch latency, model identifiers, refinement/clipboard-fallback flags, and a user-configured STT rate estimate. It never stores raw transcripts, audio, source-app identity, API keys, or prompts. Failed/cancelled/no-speech sessions are not saved. A history-write failure does not retry insertion; the dashboard reports a storage warning.

Disabling history stops future saves; existing entries remain visible until explicitly deleted or expired. Retention is applied whenever history is read or written. Caelum does not run a cleanup timer while closed. Deleting an entry or all entries recalculates statistics. SQLite secure deletion and compaction reduce recoverable content within the live database but do **not** promise erasure from SSDs, filesystem snapshots, journals, backups, or prior exports. The database is not encrypted by Caelum: use OS disk encryption for at-rest protection. Same-user processes and privileged users remain within the trust boundary.

Export is an explicit action with a sensitivity warning. Exported JSONL contains retained final transcripts and metadata in plain text, uses owner-only permissions, and refuses to overwrite an existing file. Exported files and clipboard copies are independent of later history deletion. The desktop window deliberately displays saved final transcripts, so consider screen sharing and unlocked desktops.

Groq receives captured speech; the configured cleanup provider receives the canonical transcript and conservative system prompt. Background chunking uploads before release when explicitly enabled. Credentials are environment-only, never part of HUD IPC. OpenAI cleanup requests explicitly use `store=false`; provider retention and abuse-monitoring policies remain independent of local history. Review [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data) and your Groq account policies.

The final text is placed on the Wayland clipboard for paste/recovery. **Desktop clipboard managers, including Omarchy's clipboard manager, may retain it independently of Caelum.** Caelum does not disable or clear the user's clipboard manager. The clipboard remains populated after a successful paste so manual recovery is possible; do not use dictation for content you do not want those desktop services to receive.

The HUD receives session identifiers, status enums, elapsed milliseconds, normalized energy history, output name, and fixed error codes. It never receives audio, transcript text, prompts, or credentials. IPC/control sockets are restricted to the current UID and a mode-700 runtime directory. Another process running as the same user is within the trust boundary.

Diagnostics contain numeric metrics and fixed status fields only, retained for at most 100 sessions in RAM. Benchmark reports write numeric results only when explicitly requested by the benchmark CLI; the source corpus/reference files are supplied and managed by the user. Normal logs do not contain provider response bodies or transcripts.

When cleanup uses Meta Muse Spark Contributor, submitted prompts/transcripts and responses may be used to train future Meta models under [Contributor mode](https://dev.meta.ai/docs/pricing-rate-limits). Local history settings and `store=false` do not override this provider policy.
