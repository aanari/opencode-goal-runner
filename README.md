# opencode-goal-runner

[![CI](https://github.com/aanari/opencode-goal-runner/actions/workflows/ci.yml/badge.svg)](https://github.com/aanari/opencode-goal-runner/actions/workflows/ci.yml)
[![Release](https://github.com/aanari/opencode-goal-runner/actions/workflows/release.yml/badge.svg)](https://github.com/aanari/opencode-goal-runner/actions/workflows/release.yml)

`opencode-goal-runner` is a self-contained Rust sidecar that approximates Codex goal mode for OpenCode without forking or modifying OpenCode.

It owns a persistent goal record, watches an OpenCode session over server mode, and injects continuation prompts only when the session is idle and unblocked. The optional `/goal` command launches the runner and loads the prompt contract. The Rust binary owns the runtime loop, and the installed runner has no Node.js, Bun, or OpenCode JS SDK runtime dependency.

## Status

Local sidecar, still external to OpenCode.

Implemented:

- single Rust CLI binary, no Node.js, Bun, or OpenCode JS SDK runtime dependency
- direct OpenCode HTTP client
- SQLite goal store under `~/.config/opencode-goal-runner/goals.sqlite3` by default
- config file support at `~/.config/opencode-goal-runner/config.toml`
- `launch`, `start`, `create`, `run`, `pause`, `resume`, `clear`, `inspect`, `logs`, `list`, `sessions`, `doctor`, and `inject-once`
- idle polling through `GET /session/status`
- pending permission and question blocker checks
- async continuation injection through `POST /session/{sessionID}/prompt_async`
- hidden continuation steering through the OpenCode prompt `system` field
- per-session SQLite locks with stale-lock recovery
- persisted injection events with submitted and completed timestamps
- restart-safe in-flight continuation recovery
- no-progress backoff and pause protection
- completion detection when an assistant response starts with `GOAL_COMPLETE:`
- copyable self-contained `/goal` command template at `opencode/command/goal.md` that starts the runner from inside OpenCode
- `doctor` diagnostics for server reachability, API endpoints, and model behavior

Known limitations:

- continuation turns still appear as real user messages in OpenCode history, usually as `continue`
- no native OpenCode goal object, lifecycle, or UI integration
- no semantic completion proof beyond the model's `GOAL_COMPLETE:` marker and your inspection
- OpenCode API changes can break the sidecar because this intentionally avoids vendoring or forking OpenCode

## Codex alignment

Codex goal mode has native runtime support: persisted thread goals, `create_goal` and `update_goal` tools, token and elapsed-time accounting, budget-limited status, queued-input checks, plan-mode suppression, and hidden developer continuation turns. This sidecar cannot reproduce those native hooks without OpenCode changes.

The transferable parts are the prompt contract and conservative loop policy. The runner follows the Codex-style shape: an untrusted objective block, explicit stale-context isolation, an audit against actual current state, prompt-to-artifact checklist language, blocker waiting, no-progress protection, and completion only when the active goal has real evidence. Because OpenCode does not expose native goal tools, completion is represented by an assistant response that starts with `GOAL_COMPLETE:` instead of a Codex `update_goal` call.

## Install

Build and install to a user-writable bin directory:

```sh
./install.sh
```

By default this installs:

```text
~/.local/bin/opencode-goal-runner
```

If `~/.local/bin` is not on `PATH`, `install.sh` prints the shell line to add. You can override the destination:

```sh
BINDIR="$HOME/bin" ./install.sh
```

Check the installed binary from a mostly clean shell:

```sh
env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin:/opt/homebrew/bin" \
  opencode-goal-runner --version
```

Manual build only:

```sh
cargo build --release
./target/release/opencode-goal-runner --version
```

Uninstall the installed binary:

```sh
./install.sh --uninstall
```

For local development, install a symlink to the release binary instead of copying it:

```sh
./install.sh --symlink
```

The installed runner is a Rust binary. The target machine does not need Node.js, Bun, or the OpenCode JS SDK for the runner itself.

## License

MIT. See [LICENSE](LICENSE).

## Release binaries

Build named release artifacts into `./dist`:

```sh
./build-release.sh
```

Artifacts:

```text
dist/opencode-goal-runner-aarch64-apple-darwin
dist/opencode-goal-runner-x86_64-unknown-linux-musl
```

Use `--mac-only` to build only the Apple Silicon binary, or `--check` to run `cargo test` before building:

```sh
./build-release.sh --check
./build-release.sh --mac-only
```

Linux amd64 cross-builds from macOS require Zig and cargo-zigbuild:

```sh
brew install zig
cargo install cargo-zigbuild
rustup target add x86_64-unknown-linux-musl
```

`dist/` is ignored by git. Do not commit built binaries.

## OpenCode setup

Start OpenCode server mode in the project you want the agent to work on:

```sh
opencode serve --hostname 127.0.0.1 --port 4096
```

If you bind the server anywhere except localhost, protect it with an OpenCode server password and pass the same value to the runner:

```sh
OPENCODE_SERVER_PASSWORD=... opencode serve --hostname 127.0.0.1 --port 4096
OPENCODE_GOAL_PASSWORD=... opencode-goal-runner doctor
```

Copy the OpenCode `/goal` command into your OpenCode config if you want to control goals from inside OpenCode:

```sh
mkdir -p ~/.config/opencode/command
cp ./opencode/command/goal.md ~/.config/opencode/command/goal.md
```

The sidecar still supports direct CLI use without this command, but `/goal` is the normal inside-OpenCode entry point.

The product surface is just the binary plus this copyable command file. There is no skill, plugin, or hidden setup requirement.

## Daily use

Normal workflow:

```sh
opencode serve --hostname 127.0.0.1 --port 4096
opencode-goal-runner doctor
```

Inside OpenCode:

```text
/goal Fix the docs, test, and finish with GOAL_COMPLETE: DOCS_DONE.
```

Then inspect from any shell:

```sh
opencode-goal-runner list
opencode-goal-runner inspect --goal goal_xxx
opencode-goal-runner logs --goal goal_xxx
```

The `/goal` command runs `opencode-goal-runner launch`, which starts a detached worker, waits for the marked command message to appear in OpenCode, extracts the objective from that message, and starts the goal loop. `start --latest` remains available for scripts or manual CLI use.

## Config file

Default path:

```text
~/.config/opencode-goal-runner/config.toml
```

Missing config is fine. Defaults are used.

Example:

```toml
base_url = "http://127.0.0.1:4096"
provider = "openai"
model = "gpt-5.4-mini"
agent = "build"
visible_continue_text = "continue"
poll_interval_ms = 2000
min_injection_interval_ms = 1000
max_no_progress_turns = 3
lock_ttl_ms = 30000
in_flight_timeout_ms = 600000
```

Loop timing and count settings must be greater than zero. The runner rejects zero or negative values instead of spinning, instantly timing out, or creating immediately stale locks.

Precedence is:

```text
CLI flag > environment variable > config file > built-in default
```

Global flags:

```text
--config <path>
--base-url <url>
--password <password>
--db <path>
```

Environment variables:

```text
OPENCODE_GOAL_CONFIG
OPENCODE_GOAL_BASE_URL
OPENCODE_GOAL_PASSWORD
OPENCODE_GOAL_DB
OPENCODE_GOAL_AGENT
OPENCODE_GOAL_PROVIDER
OPENCODE_GOAL_MODEL
OPENCODE_GOAL_VISIBLE_CONTINUE_TEXT
OPENCODE_GOAL_POLL_INTERVAL_MS
OPENCODE_GOAL_MIN_INJECTION_INTERVAL_MS
OPENCODE_GOAL_MAX_NO_PROGRESS_TURNS
OPENCODE_GOAL_LOCK_TTL_MS
OPENCODE_GOAL_IN_FLIGHT_TIMEOUT_MS
```

CLI examples:

```sh
opencode-goal-runner --config ./goal-runner.toml doctor
opencode-goal-runner launch

opencode-goal-runner start --latest \
  --provider openai \
  --model gpt-5.4-mini \
  --objective "Make the smallest safe change, verify it, then finish with GOAL_COMPLETE."
```

Shell-friendly helpers:

```sh
alias ogr='opencode-goal-runner'
alias ogrd='opencode-goal-runner doctor'
alias ogrl='opencode-goal-runner list'
```

## Doctor

Run this before trusting an unattended goal loop:

```sh
opencode-goal-runner doctor
```

It checks:

- OpenCode server reachability
- `/session`, `/session/status`, `/permission`, and `/question`
- selected model behavior unless `--skip-model-check` is passed

Useful variants:

```sh
opencode-goal-runner doctor --provider openai --model gpt-5.4-mini
opencode-goal-runner doctor --skip-model-check
```

`doctor` prints warnings for model problems where the HTTP server itself is still usable.

## Starting a goal from the CLI

Use an existing OpenCode session, or ask the runner to select the most recently updated session.

List sessions:

```sh
opencode-goal-runner sessions
```

Start and run immediately against the latest session:

```sh
opencode-goal-runner start --latest \
  --objective "Update README.md with the new install steps, verify the diff, then finish with GOAL_COMPLETE: README_UPDATED."
```

Start against a known session:

```sh
opencode-goal-runner start --session ses_xxx \
  --objective "Run the focused test, fix the failure, rerun it, and finish with GOAL_COMPLETE."
```

Create without running, then run later:

```sh
opencode-goal-runner create --latest --objective "..."
opencode-goal-runner run --goal goal_xxx
```

Limit continuation attempts for a smoke test:

```sh
opencode-goal-runner run --goal goal_xxx --max-injections 1
```

A good objective should include concrete success criteria and the exact verification you expect. The runner will stop automatically only when the assistant response begins with `GOAL_COMPLETE:`.

## Inspecting and controlling goals

List goals:

```sh
opencode-goal-runner list
```

Inspect current state:

```sh
opencode-goal-runner inspect --goal goal_xxx
opencode-goal-runner inspect --goal goal_xxx --json
```

Pause, resume, or clear:

```sh
opencode-goal-runner pause --goal goal_xxx
opencode-goal-runner resume --goal goal_xxx
opencode-goal-runner clear --goal goal_xxx
```

`clear` is terminal for that goal record. It does not delete OpenCode messages or repository files.

## Logs

Show recent injection events:

```sh
opencode-goal-runner logs --goal goal_xxx
opencode-goal-runner logs --goal goal_xxx --limit 50
opencode-goal-runner logs --goal goal_xxx --limit 50 --json
```

Human output formats timestamps as local RFC3339 time plus the raw epoch milliseconds in parentheses. JSON output keeps the stored fields unchanged for scripts.

Each injection entry includes:

```text
injection_id
status
created timestamp
updated timestamp
submitted timestamp
completed timestamp
pre-message ID
post-message ID
error
```

Common statuses:

```text
attempted   recorded before prompt_async is submitted
submitted   OpenCode accepted the async prompt
completed   a later assistant message was observed
failed      prompt_async failed or the in-flight turn timed out
```

Use `logs` after dogfooding or unattended runs to confirm whether the runner injected, whether OpenCode accepted the turn, and which messages bracketed the continuation.

## How the loop decides to inject

The runner injects only when all of these are true:

1. the goal status is `active`
2. the OpenCode session is idle or absent from `/session/status`
3. there are no pending permission requests for the session
4. there are no pending question requests for the session
5. this runner owns the per-session SQLite lock
6. no continuation is already in flight
7. no newer user-authored message is waiting for an assistant response
8. the minimum injection interval and no-progress backoff allow another turn

The visible continuation text defaults to:

```text
continue
```

The durable instructions go into the hidden `system` field. The model is asked to inspect actual state, avoid repeating completed work, and only finish when it can provide evidence.

## Common failure modes

`doctor` cannot reach the server:

- for TUI-driven use, start OpenCode with `opencode --port 4096`
- for a headless API-only server, start OpenCode with `opencode serve --hostname 127.0.0.1 --port 4096`
- check `base_url` in config or pass `--base-url`
- if the server has a password, set `OPENCODE_GOAL_PASSWORD`
- expected error: `failed to GET /session from http://127.0.0.1:4096`

Model check fails:

- pass an explicit provider/model that works in your OpenCode session
- with ChatGPT account auth, `openai/gpt-5.4-mini` has worked in local spikes
- use `doctor --skip-model-check` only when you have already verified the model manually
- expected warning: `warn model <provider>/<model> check failed: ...`

Authentication fails:

- set `OPENCODE_GOAL_PASSWORD` to the same value as `OPENCODE_SERVER_PASSWORD`
- expected hint: `OpenCode rejected authentication. Set OPENCODE_GOAL_PASSWORD...`

OpenCode endpoint shape changed:

- upgrade or downgrade OpenCode to a version with the expected server API
- expected error: `OpenCode did not expose this endpoint. Check the OpenCode server version.`

The runner says `waiting_on_permission` or `waiting_on_question`:

- answer the permission or question in OpenCode
- the runner intentionally does not auto-approve or auto-answer

The runner pauses with `paused_no_progress_limit`:

- inspect the OpenCode conversation and `logs`
- improve the objective or give the agent new information
- resume with `opencode-goal-runner resume --goal goal_xxx`

The runner reports an in-flight timeout:

- check whether OpenCode is still busy, retrying, or disconnected
- inspect `logs --goal goal_xxx`
- resume only after deciding the previous continuation will not produce a useful response

A second runner cannot attach:

- a per-session lock is active
- stop the other runner, or wait for the stale lock TTL if that process crashed

Continuation messages feel noisy:

- set `visible_continue_text` to a short stable string
- true invisible continuations require native OpenCode runtime support

## Safe unattended-use guidance

Use the sidecar for bounded tasks first:

- docs updates
- focused bug fixes
- small refactors with clear tests
- investigation tasks with a concrete report

Avoid unattended loops for destructive or broad tasks:

- large rewrites
- dependency upgrades across many packages
- production deploys
- permission-heavy tasks
- tasks that need product judgment or secrets

Recommended settings for early daily use:

```toml
poll_interval_ms = 2000
min_injection_interval_ms = 1000
max_no_progress_turns = 3
lock_ttl_ms = 30000
in_flight_timeout_ms = 600000
```

Start with low-risk objectives and inspect the logs afterward. Prefer clear `GOAL_COMPLETE:` instructions in the objective so the runner stops as soon as the bounded task is done.

## No-fork architecture

```text
+-------------------------+
| user / shell / scripts  |
+-----------+-------------+
            |
            v
+-------------------------+       +----------------------+
| opencode-goal-runner    | <---> | local SQLite store   |
| Rust sidecar            |       | goals, logs, locks   |
+-----------+-------------+       +----------------------+
            |
            | HTTP
            v
+-------------------------+
| OpenCode server mode    |
+-----------+-------------+
            |
            v
+-------------------------+
| OpenCode session / LLM  |
+-------------------------+
```

The sidecar talks directly to these OpenCode endpoints:

```text
GET  /session
GET  /session/status
GET  /permission
GET  /question
GET  /session/{sessionID}/message
POST /session/{sessionID}/prompt_async
```

It intentionally does not import the OpenCode JS SDK at runtime.

## OpenCode command

The optional `/goal` command starts the runner and sends the same goal contract that the sidecar injects on continuations. The binary intentionally does not install or manage this file.

```sh
mkdir -p ~/.config/opencode/command
cp ./opencode/command/goal.md ~/.config/opencode/command/goal.md
```

Inside OpenCode:

```text
/goal Update the docs, verify the diff, and finish with GOAL_COMPLETE: DOCS_DONE.
```

That command invokes `opencode-goal-runner launch` through OpenCode command shell interpolation. `launch` returns quickly after spawning a detached worker, so OpenCode does not wait on the whole goal loop. The worker finds the marked `/goal` message, extracts the objective, persists a goal, and continues through the normal runner loop.

## Development verification

Run local tests:

```sh
cargo test
```

Current coverage:

```text
cargo llvm-cov --summary-only
line coverage: 95.68%
function coverage: 92.31%
tests: 61
```

The automated coverage suite includes unit tests for config resolution, positive loop-setting validation, path resolution, selector validation, prompt/message parsing, command launch handoff, shell-sensitive objective extraction, SQLite lifecycle, lock recovery, injection state, backoff, and no-progress handling. It also includes local OpenCode-compatible HTTP server tests for doctor, sessions, `create --latest`, `/goal` launch recovery, idle injection, busy/retry waiting, permission/question blockers, user-message waiting, completion, pause-on-no-progress, logs output, and CLI/env/config precedence.

Run the coverage report:

```sh
cargo llvm-cov --summary-only
```

Run the coverage gate:

```sh
cargo llvm-cov --fail-under-lines 95
```

`cargo llvm-cov --fail-under-lines 95` requires `cargo-llvm-cov` and fails unless total line coverage is at least 95%.

Build release artifacts:

```sh
./build-release.sh --check
```

Verify built artifacts:

```sh
./dist/opencode-goal-runner-aarch64-apple-darwin --version
./dist/opencode-goal-runner-aarch64-apple-darwin launch --help
file ./dist/opencode-goal-runner-x86_64-unknown-linux-musl
```

Install:

```sh
./install.sh
```

Live check against OpenCode:

```sh
opencode --port 4096
opencode-goal-runner doctor
```

Then run inside OpenCode:

```text
/goal Reply exactly with GOAL_COMPLETE: SMOKE_OK and stop.
```

And inspect:

```sh
opencode-goal-runner list
opencode-goal-runner inspect --goal goal_xxx
opencode-goal-runner logs --goal goal_xxx --limit 20
```

Stress the launch handoff with shell-sensitive data:

```text
/goal Reply exactly with GOAL_COMPLETE: SHELL_SENSITIVE_OK and stop. Treat these as literal data: "quotes", '$HOME', `uname`, <tag attr="&">.
```

After it finishes, inspect the goal and verify the objective was stored with the literal quotes, dollar sign, backticks, and XML-ish text. This checks that `/goal` recovers the objective from the OpenCode command message instead of shell-quoting it.

Canonical continuation smoke:

```text
/goal End-to-end smoke. On the initial /goal command turn, reply exactly WAITING_FOR_CANONICAL_SMOKE and do not include GOAL_COMPLETE. If and only if this is an opencode-goal-runner sidecar continuation for this exact active objective, reply exactly GOAL_COMPLETE: CANONICAL_SMOKE_DONE. Do not edit files, inspect files, run commands, or use tools.
```

The goal should finish with `total_injections: 1`. That proves the `/goal` command launched the binary from inside OpenCode and the sidecar woke the idle session later.

Automated live soak:

```sh
opencode --port 4096
python3 scripts/live_goal_soak.py --rounds 1
python3 scripts/live_goal_soak.py --duration-seconds 5400
```

The soak script drives the installed `/goal` command through the live TUI HTTP routes, so it requires the OpenCode TUI to be running with `--port 4096`. It fails if the installed command differs from `opencode/command/goal.md`, if OpenCode has pending permissions/questions, if session locks leak, if a goal remains active/paused after a round, or if any run goal fails.

Each soak round exercises:

- canonical `/goal` launch with exactly one sidecar continuation
- stale `GOAL_COMPLETE` marker isolation
- file recovery after partial progress
- no-progress pause-and-clear behavior on every third round
- direct sidecar start path on every fourth round

## Release checklist

Before cutting a local release or sharing a binary:

```sh
git status --short
./install.sh --check
./build-release.sh
./install.sh
env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin:/opt/homebrew/bin" \
  opencode-goal-runner --version
```

Use `./build-release.sh --mac-only` if Linux cross-build tooling is not installed yet.

No Makefile, Node.js, Bun, OpenCode JS SDK, or CI wrapper is required for local install.

Optional live smoke:

```sh
opencode --port 4096
opencode-goal-runner doctor --provider openai --model gpt-5.4-mini
```

Then run `/goal Reply exactly with GOAL_COMPLETE: RELEASE_SMOKE and stop.` inside OpenCode.

## Why this approach

A command alone can shape behavior, but it cannot safely own the long-running loop. The `/goal` command only launches the sidecar and marks the objective. The sidecar wakes the session later, and it can respect blockers, locks, user input, and in-flight turns.

The sidecar is the best no-fork tradeoff for now: OpenCode remains unmodified, the runner is packaged as a standalone binary, and the loop is conservative enough to dogfood safely on bounded tasks. Native OpenCode goal mode would still be cleaner long term.
