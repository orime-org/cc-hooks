#!/usr/bin/env python3
"""Exercise the offline model fixture without listening on a network socket."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location("panel_e2e", Path(__file__).with_name("e2e-codex-task-panel.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def user(text):
    return {"role": "user", "content": [{"type": "input_text", "text": text}]}


def output():
    return {"type": "function_call_output", "call_id": "cc-hooks-panel-test", "output": "Plan updated"}


def events(payload):
    return [json.loads(block.removeprefix("data: ")) for block in payload.decode().strip().split("\n\n")]


class Connection:
    def __init__(self, data):
        self.input = io.BytesIO(data)
        self.output = bytearray()

    def makefile(self, *_args):
        return self.input

    def sendall(self, data):
        self.output.extend(data)


class Acceptance:
    def __init__(self, fail=False):
        self.entries = []
        self.fail = fail

    def record(self, entry):
        self.entries.append(entry)

    def inspect(self, action):
        if self.fail:
            raise RuntimeError("Task pane is not visible")
        return {"action": action, "result": "passed"}


class FixtureTests(unittest.TestCase):
    def test_chinese_commands_produce_native_plan_calls(self):
        for command, action, count in [("开始验收", "initial", 3), ("推进任务", "advance", 3),
                                       ("清空计划", "clear", 0), ("长列表", "long", 25),
                                       ("恢复列表", "initial", 3)]:
            with self.subTest(command=command):
                self.assertEqual(fixture.request_action({"input": [user(command)]}), (action, False))
                response = events(fixture.response_events(action, False))
                self.assertEqual([event["type"] for event in response],
                                 ["response.created", "response.output_item.done", "response.completed"])
                call = response[1]["item"]
                self.assertEqual(call["name"], "update_plan")
                self.assertEqual(len(json.loads(call["arguments"])["plan"]), count)

    def test_tool_followup_finishes_the_turn(self):
        self.assertEqual(fixture.request_action({"input": [user("推进任务"), output()]}), ("advance", True))
        item = events(fixture.response_events("advance", True))[1]["item"]
        self.assertEqual(item["type"], "message")
        self.assertEqual(item["role"], "assistant")

    def test_previous_turn_output_does_not_finish_a_new_turn(self):
        self.assertEqual(fixture.request_action({"input": [user("开始验收"), output(), user("清空计划")]}),
                         ("clear", False))

    def test_unrelated_tool_output_does_not_finish_the_fixture_call(self):
        unrelated = dict(output(), call_id="another-tool")
        self.assertEqual(fixture.request_action({"input": [user("开始验收"), unrelated]}), ("initial", False))

    def test_unknown_input_returns_instructions(self):
        self.assertEqual(fixture.request_action({"input": [user("hello")]}), ("help", False))
        self.assertEqual(events(fixture.response_events("help", False))[1]["item"]["type"], "message")

    def test_invalid_input_is_rejected(self):
        for value in [{}, {"input": "开始验收"}, {"input": [output()]}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                fixture.request_action(value)

    def test_state_changes_do_not_mutate_the_initial_plan(self):
        self.assertEqual(fixture.plan_for("advance")[0]["status"], "completed")
        self.assertEqual(fixture.plan_for("initial")[0]["status"], "in_progress")
        self.assertEqual(fixture.plan_for("advance")[1]["status"], "in_progress")

    def request(self, acceptance, body, path="/v1/responses"):
        payload = json.dumps(body).encode()
        connection = Connection(f"POST {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {len(payload)}\r\n\r\n".encode() + payload)
        fixture.handler_for(acceptance)(connection, ("127.0.0.1", 1), object())
        return bytes(connection.output)

    def test_http_fixture_emits_real_sse_shape(self):
        acceptance = Acceptance()
        response = self.request(acceptance, {"input": [user("开始验收")]})
        self.assertIn(b"200 OK", response)
        self.assertIn(b"text/event-stream", response)
        call = events(response.split(b"\r\n\r\n", 1)[1])[1]["item"]
        self.assertEqual(call["name"], "update_plan")
        self.assertFalse(acceptance.entries[0]["tool_output_received"])

    def test_http_followup_records_inspection(self):
        acceptance = Acceptance()
        response = self.request(acceptance, {"input": [user("开始验收"), output()]})
        self.assertIn(b"200 OK", response)
        self.assertEqual(acceptance.entries[-1], {"action": "initial", "result": "passed"})

    def test_failed_inspection_returns_an_error(self):
        acceptance = Acceptance(fail=True)
        response = self.request(acceptance, {"input": [user("开始验收"), output()]})
        self.assertIn(b"500 Internal Server Error", response)
        self.assertEqual(acceptance.entries[-1]["result"], "failed")

    def test_unknown_endpoint_returns_an_error(self):
        acceptance = Acceptance()
        self.assertIn(b"500 Internal Server Error", self.request(acceptance, {}, "/other"))
        self.assertEqual(acceptance.entries[-1]["result"], "failed")

    def test_binding_lookup_uses_the_production_store_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(fixture.os.environ, {"WEZTERM_PANE": "42", "WEZTERM_UNIX_SOCKET": "/tmp/终端.sock"}):
                acceptance = fixture.Acceptance(Path(directory))
            bindings = acceptance.data / "bindings"
            bindings.mkdir(parents=True)
            key = fixture.binding_key("/tmp/终端.sock", "42")
            (bindings / (key + ".json")).write_text('{"session_id":"root-session"}')
            self.assertEqual(acceptance.binding(), {"session_id": "root-session"})

    def test_existing_unowned_home_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "new, empty"):
            fixture.prepare(Path("/unused/codex"), Path(directory))

    def test_missing_actions_prevent_a_passing_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps({"at": 2, "action": "initial", "result": "passed"}) + "\n")
            summary = fixture.summarize(path, 1, False)
            self.assertEqual(summary["result"], "incomplete")
            self.assertEqual(summary["missing_actions"], ["advance", "clear", "long", "startup"])

    def test_current_failures_prevent_a_passing_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            entries = [{"at": 2, "action": action, "result": "passed"}
                       for action in ["initial", "advance", "clear", "long", "startup"]]
            entries.append({"at": 3, "result": "failed", "error": "stale pane"})
            path.write_text("\n".join(json.dumps(entry) for entry in entries))
            self.assertEqual(fixture.summarize(path, 1, False)["result"], "incomplete")

    def test_previous_runs_cannot_satisfy_current_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps({"at": 1, "action": "resume", "result": "passed"}) + "\n")
            self.assertEqual(fixture.summarize(path, 2, True)["result"], "incomplete")

    def test_resume_summary_requires_actual_resume_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps({"at": 2, "action": "resume", "result": "passed"}) + "\n")
            self.assertEqual(fixture.summarize(path, 1, True)["result"], "passed")

    def inspection_fixture(self, directory, plan=None):
        acceptance = fixture.Acceptance(Path(directory))
        acceptance.wezterm = "/fixture/wezterm"
        acceptance.parent, acceptance.socket = "42", "/tmp/fixture.sock"
        bindings = acceptance.data / "bindings"
        bindings.mkdir(parents=True)
        binding = {"session_id": "root-session", "attachment_id": "attach-1",
                   "panel_pane": "43", "state": "visible"}
        (bindings / (fixture.binding_key(acceptance.socket, acceptance.parent) + ".json")).write_text(json.dumps(binding))
        if plan is not None:
            plans = acceptance.data / "plans"
            plans.mkdir()
            (plans / "root-session.json").write_text(json.dumps({"plan": plan}))
        return acceptance

    def test_inspection_requires_saved_plan_and_visible_text(self):
        with tempfile.TemporaryDirectory() as directory:
            acceptance = self.inspection_fixture(directory, fixture.plan_for("initial"))
            frame = SimpleNamespace(stdout="任务 0/3 · 验收项目\n核对真实计划同步")
            with patch.object(fixture.subprocess, "run", return_value=frame) as process:
                result = acceptance.inspect("initial")
            self.assertEqual(result["result"], "passed")
            self.assertEqual(process.call_args.args[0][-2:], ["--pane-id", "43"])

    def test_stale_visible_text_prevents_passing(self):
        with tempfile.TemporaryDirectory() as directory:
            acceptance = self.inspection_fixture(directory, fixture.plan_for("advance"))
            frame = SimpleNamespace(stdout="任务 0/3\n核对真实计划同步")
            with patch.object(fixture.subprocess, "run", return_value=frame), \
                    patch.object(fixture.time, "monotonic", side_effect=[0, 1, 6]), \
                    patch.object(fixture.time, "sleep"), self.assertRaisesRegex(RuntimeError, "count"):
                acceptance.inspect("advance")

    def test_saved_empty_plan_is_distinct_from_initial_waiting(self):
        with tempfile.TemporaryDirectory() as directory:
            acceptance = self.inspection_fixture(directory, [])
            with patch.object(fixture.subprocess, "run", return_value=SimpleNamespace(stdout="任务 0/0\n已保存计划")):
                self.assertEqual(acceptance.inspect("clear")["result"], "passed")
            with patch.object(fixture.subprocess, "run", return_value=SimpleNamespace(stdout="任务 0/0\n等待首次计划更新")), \
                    patch.object(fixture.time, "monotonic", side_effect=[0, 1, 6]), \
                    patch.object(fixture.time, "sleep"), self.assertRaisesRegex(RuntimeError, "saved snapshot"):
                acceptance.inspect("clear")

    def test_initial_empty_pane_has_no_saved_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            acceptance = self.inspection_fixture(directory)
            with patch.object(fixture.subprocess, "run", return_value=SimpleNamespace(stdout="任务 0/0\n等待首次计划更新")):
                result = acceptance.inspect("startup")
            self.assertEqual(result["result"], "passed")
            self.assertIsNone(result["snapshot"])

    def test_resume_must_keep_the_saved_session_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            acceptance = self.inspection_fixture(directory, fixture.plan_for("initial"))
            with patch.object(fixture.time, "monotonic", side_effect=[0, 1, 6]), \
                    patch.object(fixture.time, "sleep"), self.assertRaisesRegex(RuntimeError, "different session"):
                acceptance.inspect("resume", "different-session")


if __name__ == "__main__":
    unittest.main()
