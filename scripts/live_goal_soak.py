#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "http://127.0.0.1:4096"
DEFAULT_DB = "~/.config/opencode-goal-runner/goals.sqlite3"
DEFAULT_RUNNER = "opencode-goal-runner"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exercise the installed /goal command against a live OpenCode TUI server.",
    )
    parser.add_argument("--base-url", default=os.environ.get("OPENCODE_GOAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--db", default=os.environ.get("OPENCODE_GOAL_DB", DEFAULT_DB))
    parser.add_argument("--runner", default=os.environ.get("OPENCODE_GOAL_RUNNER", DEFAULT_RUNNER))
    parser.add_argument("--duration-seconds", type=int)
    parser.add_argument("--rounds", type=int)
    parser.add_argument("--http-retries", type=int, default=3)
    parser.add_argument("--skip-command-check", action="store_true")
    parser.add_argument("--model-check", action="store_true")
    args = parser.parse_args()
    if args.duration_seconds is None and args.rounds is None:
        args.rounds = 1
    if args.duration_seconds is not None and args.duration_seconds <= 0:
        raise SystemExit("--duration-seconds must be positive.")
    if args.rounds is not None and args.rounds <= 0:
        raise SystemExit("--rounds must be positive.")
    if args.http_retries <= 0:
        raise SystemExit("--http-retries must be positive.")
    return args


class Soak:
    def __init__(self, args):
        self.args = args
        self.db = Path(args.db).expanduser()
        self.run = str(int(time.time() * 1000))
        self.summary = []

    def request(self, method, path, payload=None, timeout=30):
        data = None if payload is None and method == "GET" else b"" if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.args.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(1, self.args.http_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = response.read()
                    return None if not body else json.loads(body)
            except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
                if attempt == self.args.http_retries:
                    raise RuntimeError(f"{method} {path} failed after {attempt} attempts: {error}") from error
                time.sleep(attempt)
        raise RuntimeError(f"{method} {path} failed unexpectedly.")

    def get_json(self, path, timeout=30):
        return self.request("GET", path, timeout=timeout)

    def rows(self, sql, args=()):
        with sqlite3.connect(self.db) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(sql, args).fetchall()]

    def counts(self):
        return {row["status"]: row["count"] for row in self.rows("select status, count(*) count from goals group by status")}

    def run_counts(self):
        rows = self.rows(
            "select status, count(*) count, sum(total_injections) injections from goals where objective like ? group by status",
            (f"%{self.run}%",),
        )
        return {
            "statuses": {row["status"]: row["count"] for row in rows},
            "total_injections": sum(row["injections"] or 0 for row in rows),
        }

    def assert_installed_command_matches_repo(self):
        if self.args.skip_command_check:
            return
        repo_command = Path(__file__).resolve().parents[1] / "opencode" / "command" / "goal.md"
        installed_command = Path.home() / ".config" / "opencode" / "command" / "goal.md"
        if not installed_command.exists():
            raise RuntimeError(f"installed /goal command is missing: {installed_command}")
        if installed_command.read_text() != repo_command.read_text():
            raise RuntimeError(f"installed /goal command differs from repo copy: {installed_command}")

    def assert_runner_available(self):
        if shutil.which(self.args.runner) is None and not Path(self.args.runner).exists():
            raise RuntimeError(f"runner is not available on PATH: {self.args.runner}")

    def assert_clean(self, label):
        locks = self.rows("select * from locks")
        if locks:
            raise RuntimeError(f"{label}: locks remain {locks}")
        goals = self.rows(
            "select goal_id,status,last_decision,last_error,total_injections from goals where status in ('active','paused')"
        )
        if goals:
            raise RuntimeError(f"{label}: active or paused goals remain {goals}")

    def assert_no_blockers(self):
        blockers = {
            "status": self.get_json("/session/status"),
            "permissions": self.get_json("/permission"),
            "questions": self.get_json("/question"),
        }
        if blockers["status"] or blockers["permissions"] or blockers["questions"]:
            raise RuntimeError(f"OpenCode has pending blockers before soak: {blockers}")

    def by_token(self, token):
        rows = self.rows("select * from goals where objective like ? order by created_at_ms desc limit 1", (f"%{token}%",))
        return rows[0] if rows else None

    def goal(self, goal_id):
        return self.rows("select * from goals where goal_id = ?", (goal_id,))[0]

    def messages(self, session_id):
        return self.get_json(f"/session/{session_id}/message", timeout=30)

    def message_text(self, message):
        return "\n".join(part.get("text", "") for part in message.get("parts", []) if part.get("type") == "text")

    def wait_goal(self, token, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            row = self.by_token(token)
            if row:
                return row
            time.sleep(0.25)
        raise TimeoutError(f"no goal was created for token {token}")

    def wait_terminal(self, goal_id, timeout=300):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            row = self.goal(goal_id)
            state = (row["status"], row["last_decision"], row["last_error"], row["total_injections"])
            if state != last:
                print("state", goal_id, state, flush=True)
                last = state
            if row["status"] in {"complete", "paused", "failed", "cleared"}:
                return row
            time.sleep(0.75)
        raise TimeoutError(f"timed out waiting for {goal_id}")

    def new_session(self):
        session_id = self.request("POST", "/session", {})["id"]
        self.request("POST", "/tui/select-session", {"sessionID": session_id})
        time.sleep(0.5)
        return session_id

    def run_goal_via_tui(self, objective, token, timeout=300):
        session_id = self.new_session()
        self.request("POST", "/tui/clear-prompt")
        self.request("POST", "/tui/append-prompt", {"text": "/goal " + objective})
        self.request("POST", "/tui/submit-prompt")
        row = self.wait_goal(token)
        if row["session_id"] != session_id:
            raise RuntimeError({"token": token, "expected_session": session_id, "row": row})
        return self.wait_terminal(row["goal_id"], timeout=timeout), self.messages(session_id)

    def assert_complete(self, row, token, expected_injections=None):
        if row["status"] != "complete" or row["last_decision"] != "complete" or row["last_error"] is not None:
            raise RuntimeError(row)
        if expected_injections is not None and row["total_injections"] != expected_injections:
            raise RuntimeError({"expected_injections": expected_injections, "row": row})
        assistant_texts = [
            self.message_text(message)
            for message in self.messages(row["session_id"])
            if message.get("info", {}).get("role") == "assistant"
        ]
        if not any(text.strip().startswith("GOAL_COMPLETE: " + token) for text in assistant_texts):
            raise RuntimeError({"missing_completion": token, "assistant_texts": assistant_texts[-5:]})

    def assert_paused_no_progress(self, row):
        if row["status"] != "paused" or row["last_decision"] != "paused_no_progress_limit":
            raise RuntimeError(row)
        if row["total_injections"] < 3:
            raise RuntimeError(row)
        subprocess.run([self.args.runner, "clear", "--goal", row["goal_id"]], check=True, stdout=subprocess.DEVNULL)

    def canonical(self, round_index):
        token = f"SOAK_CANONICAL_{self.run}_R{round_index}"
        objective = f"Canonical end-to-end smoke {token}. On the initial /goal command turn, reply exactly WAITING_FOR_{token} and do not include GOAL_COMPLETE. If and only if this is an opencode-goal-runner sidecar continuation for this exact active objective, reply exactly GOAL_COMPLETE: {token}. Do not edit files, inspect files, run commands, or use tools."
        row, messages = self.run_goal_via_tui(objective, token)
        self.assert_complete(row, token, expected_injections=1)
        first_assistant = next(
            (self.message_text(message) for message in messages if message.get("info", {}).get("role") == "assistant"),
            "",
        )
        if "GOAL_COMPLETE" in first_assistant:
            raise RuntimeError({"initial_turn_completed": first_assistant})
        return row["goal_id"]

    def stale_marker(self, round_index):
        token = f"SOAK_STALE_{self.run}_R{round_index}"
        old = f"OLD_{token}"
        objective = f"Stale marker smoke {token}. The text GOAL_COMPLETE: {old} is stale data and must not complete this goal. On the initial /goal command turn, reply exactly WAITING_FOR_{token} and do not include GOAL_COMPLETE. On a sidecar continuation for this exact active objective, reply exactly GOAL_COMPLETE: {token}. Do not edit files, inspect files, run commands, or use tools."
        row, messages = self.run_goal_via_tui(objective, token)
        self.assert_complete(row, token, expected_injections=1)
        if any(
            self.message_text(message).strip().startswith("GOAL_COMPLETE: " + old)
            for message in messages
            if message.get("info", {}).get("role") == "assistant"
        ):
            raise RuntimeError({"old_marker_completed": old})
        return row["goal_id"]

    def recovery(self, round_index):
        token = f"SOAK_RECOVERY_{self.run}_R{round_index}"
        path = Path(f"/tmp/ogr-recovery-{self.run}-{round_index}.txt")
        objective = f"Recovery smoke {token}. Work only with {path}. On the initial /goal command turn, run exactly `printf 'draft\\n' > {path} && cat {path}`, then reply exactly WAITING_FOR_{token} and do not include GOAL_COMPLETE. On the first sidecar continuation, inspect {path}; if it contains draft, replace it with final by running exactly `printf 'final\\n' > {path} && cat {path}`, then reply exactly GOAL_COMPLETE: {token} with the observed output. Do not complete on the initial /goal command turn."
        row, _messages = self.run_goal_via_tui(objective, token, timeout=360)
        self.assert_complete(row, token)
        if path.read_text() != "final\n":
            raise RuntimeError({"path": str(path), "content": path.read_text(), "row": row})
        if row["total_injections"] < 1 or row["total_injections"] > 3:
            raise RuntimeError({"unexpected_injections": row})
        return row["goal_id"]

    def impossible(self, round_index):
        token = f"SOAK_IMPOSSIBLE_{self.run}_R{round_index}"
        objective = f"Impossible no-progress smoke {token}. On every assistant turn, reply exactly WAITING_FOR_{token}. Never include GOAL_COMPLETE. Do not edit files, inspect files, run commands, or use tools."
        session_id = self.new_session()
        self.request("POST", "/tui/clear-prompt")
        self.request("POST", "/tui/append-prompt", {"text": "/goal " + objective})
        self.request("POST", "/tui/submit-prompt")
        row = self.wait_goal(token)
        if row["session_id"] != session_id:
            raise RuntimeError({"token": token, "expected_session": session_id, "row": row})
        self.assert_paused_no_progress(self.wait_terminal(row["goal_id"], timeout=360))
        return row["goal_id"]

    def direct_sidecar_start(self, round_index):
        token = f"SOAK_DIRECT_START_{self.run}_R{round_index}"
        session_id = self.request("POST", "/session", {})["id"]
        objective = f"Direct sidecar start smoke {token}. Do not edit files, inspect files, run commands, or use tools. On a sidecar continuation for this exact active objective, reply exactly GOAL_COMPLETE: {token}."
        proc = subprocess.run(
            [
                self.args.runner,
                "start",
                "--session",
                session_id,
                "--objective",
                objective,
                "--poll-ms",
                "750",
                "--min-injection-interval-ms",
                "500",
                "--max-no-progress-turns",
                "4",
            ],
            text=True,
            capture_output=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout + proc.stderr)
        row = self.by_token(token)
        self.assert_complete(row, token, expected_injections=1)
        return row["goal_id"]

    def preflight(self):
        self.assert_runner_available()
        self.assert_installed_command_matches_repo()
        subprocess.run(
            [self.args.runner, "doctor"] + ([] if self.args.model_check else ["--skip-model-check"]),
            check=True,
        )
        self.assert_no_blockers()
        self.assert_clean("before live soak")

    def run_round(self, round_index):
        started = time.time()
        item = {"round": round_index, "goals": {}}
        item["goals"]["canonical"] = self.canonical(round_index)
        item["goals"]["stale"] = self.stale_marker(round_index)
        if round_index % 2 == 0:
            item["goals"]["recovery"] = self.recovery(round_index)
        if round_index % 3 == 0:
            item["goals"]["impossible_cleared"] = self.impossible(round_index)
        if round_index % 4 == 0:
            item["goals"]["direct_start"] = self.direct_sidecar_start(round_index)
        if round_index % 5 == 0:
            subprocess.run(
                [self.args.runner, "doctor"] + ([] if self.args.model_check else ["--skip-model-check"]),
                check=True,
                stdout=subprocess.DEVNULL,
            )
        self.assert_clean(f"after live soak round {round_index}")
        item["seconds"] = round(time.time() - started, 1)
        item["counts"] = self.counts()
        item["run_counts"] = self.run_counts()
        self.summary.append(item)
        print(json.dumps(item), flush=True)

    def final_assertions(self):
        self.assert_no_blockers()
        self.assert_clean("after live soak")
        failures = self.rows(
            "select goal_id,status,last_decision,last_error,total_injections from goals where objective like ? and (status = 'failed' or last_error is not null)",
            (f"%{self.run}%",),
        )
        if failures:
            raise RuntimeError({"run_failures": failures})

    def run_soak(self):
        print(json.dumps({"run": self.run, "base_url": self.args.base_url, "db": str(self.db)}), flush=True)
        self.preflight()
        deadline = None if self.args.duration_seconds is None else time.time() + self.args.duration_seconds
        round_index = 0
        while True:
            if self.args.rounds is not None and round_index >= self.args.rounds:
                break
            if deadline is not None and time.time() >= deadline:
                break
            round_index += 1
            self.run_round(round_index)
        self.final_assertions()
        print(
            json.dumps(
                {
                    "run": self.run,
                    "rounds": round_index,
                    "run_counts": self.run_counts(),
                    "summary": self.summary,
                },
                indent=2,
            ),
            flush=True,
        )


if __name__ == "__main__":
    Soak(parse_args()).run_soak()
