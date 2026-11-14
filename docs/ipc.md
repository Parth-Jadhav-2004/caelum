# Desktop IPC and failure handling

Only the Tauri process writes the Python child's stdin; there is no local HTTP
server, token file, or shell-command endpoint. The existing daemon control socket
continues to authenticate peer UID for CLI and compositor controls.

Example request: `{"v":1,"id":1,"method":"status","params":{}}`.
Replies carry the same ID and either `result` or `error`; events carry `event`
and `data` without a request ID. Mutations remain serialized in Python, with
explicit exceptions for cancellable samples and read operations. Settings are
merged and semantically validated before atomic TOML replacement; partial patches
preserve fields the client does not edit.

React calls the Tauri `backend` command, Rust writes a JSONL v1 request to its
managed Python child, and Python invokes existing services/HTTPX providers.
The service daemon remains responsible for capture, history callbacks, media,
shortcuts and the native HUD. These business operations have not moved to Rust.

`python/caelum/ipc_contract.py` defines request/result descriptors using the
JSON Schema vocabulary `type`, `enum`, `anyOf`, `properties`, `required`,
`additionalProperties` and `items`. This deliberately limited vocabulary has
matching small Python/TypeScript validators; it is not a general-purpose JSON
Schema implementation. Configuration property types come from Python dataclasses.
`scripts/generate-contracts.py` generates configuration types and
`src/lib/ipc-contract.generated.json`. CI checks both for drift. New methods
must define parameters/results here and frontend method types; invalid requests
are rejected before dispatch and successful results are checked on both sides.
Configuration's existing semantic/range validation remains authoritative.

The v1 envelope retains its original `error` string for older consumers and adds
`error_info: {code, message, retryable}`. Rust validates framing/version/envelopes
and returns this typed error through Tauri. The frontend uses `IpcError` and
human-readable messages. Provider authentication/permission/quota/model failures
are blocked; rate limits/offline/provider timeouts can be eligible for an explicit
retry. `retryable` never authorizes automatic replay of a mutation or paid request.
Unexpected exception details and provider response bodies are not exposed.

Transport limits:

- 1MiB requests; response lines bounded during reading to 16MiB, including newline.
- At most 64 admitted Rust calls and 64 Python response tasks.
- A single per-method deadline covers admission to the pipe mutex, writing, and
  waiting for a response: reads/cancel 10s, start/save/shortcut 20s, shutdown/stop
  12s, update download 180s, and other operations 90s.
- Pending entries and admission permits are released even if a caller is aborted.
  A cancelled/timed-out partial write poisons the pipe, since another JSON frame
  could otherwise append to an incomplete request. No requests are replayed.
- A reply timeout has an **unknown outcome**. Check status before a manual retry;
  the underlying operation may have completed. Late replies are discarded.
- Malformed frames/version mismatches disconnect the transport and reject all
  pending requests. A persistent UI error and confirmed manual restart are
  available; recovery never silently restarts capture or repeats uploads.
- Shutdown has one 10s graceful budget for cancellation/shutdown/EOF and waiting,
  followed by a 2s forced termination/reap budget. A second close is a no-op.
  Existing pending-audio confirmation remains at the UI/daemon boundary.
- Python allows accepted EOF work a short drain period, then signals cancellation
  and cancels remaining tasks. Unchanged idle status is suppressed; live meter
  updates retain real capture data. The frontend subscribes before requesting an
  initial snapshot and ignores snapshots superseded by newer events.

`sample.cancel` acknowledges a cancellation signal, not proof that an audio
thread/provider has already stopped. The native sample lock and daemon control
locks continue to prevent overlapping capture. Closing a transport cannot undo
a previously committed history write or provider request.

Rust fault tests cover malformed/bounded frames, stalled writes, reply timeouts,
request admission, aborted callers, and forced child reaping. Python and frontend
tests exercise request/result contracts, sanitized typed errors and confirmed
restart without replay. No transcript or credential diagnostic upload was added.
