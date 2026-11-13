# Desktop IPC v1

Only the Tauri process can write the Python sidecar's stdin. There is no local
HTTP server, shared token file, or shell-command endpoint. The existing desktop
control socket still authenticates the peer UID and serves the existing CLI and
compositor shortcuts.

Request: `{"v":1,"id":1,"method":"status","params":{}}`.
Response: `{"v":1,"id":1,"result":{…}}` or a sanitized `error` string.
Event: `{"v":1,"event":"status","data":{…}}`.
Rust emits allowlisted `engine:status`, `engine:microphone`, and
`engine:status-error` events. On EOF it rejects pending requests and emits
`engine:disconnected`. Request IDs are monotonic per desktop process. Incoming
frames are bounded at 1 MiB and outgoing results at 16 MiB; overly large history
results ask the user to narrow search. Requests time out after 180 seconds, with
transport entries removed on success/error/timeout. There is no automatic replay
of recording/deletion/credential mutations following a disconnect.

`src/lib/ipc.ts` defines every frontend method's parameters and result. Python
configuration fields are generated from dataclasses with
`scripts/generate-contracts.py`; the regression test detects contract drift.
The backend validates saved TOML again before atomically replacing the old file.

Read methods: bootstrap, status, devices, history, summary, updates.pending.
Mutation families: control, service.start/stop, settings.save, history.delete/export,
credentials.store/delete, setup.validate/finish, microphone.test, practice,
sample.cancel, shortcut.check, launcher, updates.check/stage/apply/discard.

Mutations are serialized except cancellable audio tests and read operations.
A microphone test and regular recording cannot own capture at the same time.
Pause/stop/shutdown check active work unless explicit discard is provided. Settings
may be persisted while a recording is active but idle-only reload reports a warning.
No stored fields are silently removed when the frontend edits only a subset.

Provider setup stages typed keys in memory, verifies all configured model access,
then saves keys. Cancellation before storage saves nothing. The UI explicitly
reports Secret Service versus unencrypted private-file fallback. Practice is an
independent five-second sample with explicit upload consent; no practice text is
inserted or stored in history. EOF cancels active samples before service shutdown.

The sidecar starts the existing daemon only on explicit startup/setup completion
or normal post-setup app launch. Daemon stdout is redirected to stderr so it
cannot corrupt protocol framing. The owned daemon monitors its parent PID;
sidecar death stops capture through its normal shutdown path. Standalone services
have no parent monitor. A disconnect requires explicit app restart, avoiding
accidental replay or repeated audio uploads.
