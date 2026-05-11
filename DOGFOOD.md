# Release-candidate dogfood

## Task

Dogfood the installed `/goal` command on a bounded OpenCode task and record the result here.

## Result

Completed a deliberate two-continuation run against `opencode serve --hostname 127.0.0.1 --port 4096`.

- Goal: `goal_55e7e826a9284fe19356d557a18fbc4c`
- Session: `ses_1f035f6c2ffewsVNMjnlp8LhoJ`
- Model: `openai/gpt-5.4-mini`
- Final status: `complete`
- Total injections: `2`

`logs --goal goal_55e7e826a9284fe19356d557a18fbc4c --limit 20` showed both injection rows as `completed`, with submitted and completed timestamps and pre/post message IDs.

Completed a later installed `/goal` launch smoke with shell-sensitive objective text and one real continuation injection.

- Goal: `goal_096d3c7ba00e4b1e9e4142b8f0f30fcb`
- Session: `ses_1eca245a3ffeyIWRNhSuqoR4X2`
- Final status: `complete`
- Total injections: `1`

`inspect` preserved literal quotes, `'$HOME'`, backticks, XML-ish text, and multiline objective content. `logs` showed `inj_db5b4d5d2d1c41ffae2970b9b3468bc3` as `completed` with no stuck in-flight injection.

Completed a release-platform pass after installing the local Linux cross-build toolchain.

- macOS artifact: `dist/opencode-goal-runner-aarch64-apple-darwin`.
- Linux artifact: `dist/opencode-goal-runner-x86_64-unknown-linux-musl`.
- Linux artifact type: statically linked x86-64 ELF.
- Clean-install simulation: temp `HOME`, temp `bin`, only the binary plus `/goal` command copied into config; `--version` and `launch --help` worked without Node.js or Bun on `PATH`.
- Live release smoke goal: `goal_054309ee504d4a83a7d69c41b5101c32`.
- Live release smoke total injections: `1`.

The Linux binary was built locally with `rustup target add x86_64-unknown-linux-musl`, `cargo install cargo-zigbuild`, and `brew install zig`. Docker was installed but the daemon was not running, so the Linux artifact was not executed inside Linux during this pass.

Completed a long-haul `/goal` dogfood pass with three fresh live OpenCode command launches against an isolated goal database.

- Shell-sensitive extraction run: `goal_33cd5cbeda1d4bb5bbafb8e69a1ecff5`, `complete`, `total_injections: 1`.
- Docs/release audit run: `goal_313b5bf19b52438c91fc951f942ba259`, `complete`, `total_injections: 1`.
- Inspect/logs UX smoke run: `goal_43d6c0314249415bbef64f64c0473609`, `complete`, `total_injections: 1`.

The shell-sensitive run preserved quotes, apostrophes, `'$HOME'`, backticks, XML-ish text, and literal `</objective>` text in the stored objective. All three runs had completed injection rows, no stuck in-flight injection, and `last_decision: complete`. The docs/release audit did not find a real issue requiring code or script changes.

Completed a 90-minute live TUI soak on 2026-05-11 through the installed `/goal` command and the installed release binary.

- Run token: `1778513929026`.
- OpenCode launch: `opencode --port 4096`.
- Rounds: `136`.
- Live goals created for the run: `419`.
- Completed goals: `374`.
- Impossible/no-progress goals paused and cleared as expected: `45`.
- Sidecar continuations injected: `552`.
- New failed goals: `0`.
- Leftover locks: `0`.
- Leftover active/paused goals: `0`.
- OpenCode blockers after the run: empty `/session/status`, `/permission`, and `/question`.

The soak mixed canonical one-continuation goals, stale marker isolation, file recovery goals, impossible no-progress goals, and direct sidecar multi-step goals. One OpenCode transient `Internal Server Error` happened during a recovery case; the runner retried and completed the goal, validating the HTTP retry path added during hardening.

Added `scripts/live_goal_soak.py` afterward so the same live product-path soak is repeatable instead of only being an ad-hoc terminal session. A one-round run of the checked-in script completed with two live `/goal` goals and two sidecar injections:

- Run token: `1778531987073`.
- Canonical goal: `goal_0adb7178fa3c4aecacf02fe88f0c89a6`, `complete`, `total_injections: 1`.
- Stale marker goal: `goal_a2fc4aa1655f40239ceffa42b03fd5a0`, `complete`, `total_injections: 1`.

A four-round run of the checked-in script completed afterward, covering every soak case:

- Run token: `1778532032932`.
- Rounds: `4`.
- Goals: `12`.
- Completed goals: `11`.
- Impossible/no-progress goals paused and cleared as expected: `1`.
- Sidecar continuations injected: `15`.
- New failed goals: `0`.
- Leftover locks: `0`.
- Leftover active/paused goals: `0`.

## What worked

- The installed release binary ran the goal loop without Node.js, Bun, or the OpenCode JS SDK.
- The first continuation created a draft note and intentionally avoided `GOAL_COMPLETE:`.
- The runner observed the non-completing assistant response, backed off, and injected a second continuation.
- The second continuation updated the note and finished with `GOAL_COMPLETE: DOGFOOD_NOTE`.
- `inspect` reported `status: complete`, `total_injections: 2`, no in-flight injection, and `last_decision: complete`.

## What hurt

- The dogfood needed an explicit two-cycle objective; otherwise a small documentation task would likely complete in one continuation.
- Running a headless file-edit task is smoother when OpenCode server permissions are configured up front for the bounded workspace.
- The logs are useful and include local timestamps plus raw epoch-millisecond values.

## Follow-ups

- Keep log output compact enough for quick post-run inspection.
- Keep the default behavior conservative: do not auto-approve permissions or auto-answer questions.
