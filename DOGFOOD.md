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
