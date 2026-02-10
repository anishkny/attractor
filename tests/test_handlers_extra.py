"""
Additional tests for handlers and registry behavior.
"""

import json
import subprocess
from pathlib import Path

import pytest

from attractor.handlers import (
    CodergenBackend,
    CodergenHandler,
    ExitHandler,
    FanInHandler,
    Handler,
    HandlerRegistry,
    Interviewer,
    ManagerLoopHandler,
    ParallelHandler,
    ToolHandler,
    WaitForHumanHandler,
)
from attractor.models import (
    Answer,
    AnswerStatus,
    Context,
    Edge,
    Graph,
    Node,
    Outcome,
    Question,
    StageStatus,
)


class FakeBackend(CodergenBackend):
    def __init__(self, result=None, error: Exception = None):
        self.result = result
        self.error = error

    def run(self, node: Node, prompt: str, context: Context):
        if self.error:
            raise self.error
        return self.result


class UnmatchedInterviewer(Interviewer):
    def ask(self, question: Question):
        return (AnswerStatus.ANSWERED, Answer(value="Z", question=question))


class FakeProcess:
    def __init__(self, poll_result=None, wait_error=None, pid=123):
        self._poll_result = poll_result
        self.wait_error = wait_error
        self.pid = pid
        self.terminated = False
        self.killed = False

    def poll(self):
        return self._poll_result

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        if self.wait_error:
            raise self.wait_error
        return 0

    def kill(self):
        self.killed = True


def test_abstract_base_methods_callable():
    dummy = object()
    assert Handler.execute(dummy, None, None, None, "") is None
    assert CodergenBackend.run(dummy, None, "", None) is None
    assert Interviewer.ask(dummy, None) is None


def test_exit_handler_execute():
    handler = ExitHandler()
    node = Node(id="exit", attrs={"shape": "Msquare"})
    graph = Graph(name="g", nodes={"exit": node}, edges=[], attrs={})

    outcome = handler.execute(node, Context(), graph, ".")
    assert outcome.status == StageStatus.SUCCESS


def test_handler_registry_resolution_paths():
    registry = HandlerRegistry()

    custom_handler = WaitForHumanHandler()
    registry.register("custom", custom_handler)

    node = Node(id="node", attrs={"type": "custom"})
    assert registry.resolve(node) is custom_handler

    node = Node(id="exit", attrs={"shape": "Msquare"})
    assert registry.resolve(node).__class__.__name__ == "ExitHandler"

    registry.set_default(custom_handler)
    node = Node(id="fallback", attrs={"shape": "box"})
    assert registry.resolve(node) is custom_handler

    registry_no_default = HandlerRegistry()
    node = Node(id="unknown", attrs={"type": "missing", "shape": "box"})
    with pytest.raises(ValueError, match="No handler found"):
        registry_no_default.resolve(node)


def test_codergen_handler_backend_outcome(tmp_path: Path):
    outcome = Outcome(status=StageStatus.FAIL, failure_reason="backend-fail")
    backend = FakeBackend(result=outcome)
    handler = CodergenHandler(backend=backend)

    node = Node(id="task", attrs={"prompt": "Do it"})
    graph = Graph(name="g", nodes={"task": node}, edges=[], attrs={"goal": "g"})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL

    status_path = tmp_path / "task" / "status.json"
    assert status_path.exists()
    status = json.loads(status_path.read_text())
    assert status["failure_reason"] == "backend-fail"


def test_codergen_handler_backend_exception(tmp_path: Path):
    handler = CodergenHandler(backend=FakeBackend(error=RuntimeError("boom")))
    node = Node(id="task", attrs={"prompt": "Do it"})
    graph = Graph(name="g", nodes={"task": node}, edges=[], attrs={"goal": "g"})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL
    assert "boom" in result.failure_reason


def test_codergen_handler_backend_text(tmp_path: Path):
    handler = CodergenHandler(backend=FakeBackend(result="hello"))
    node = Node(id="task", attrs={"prompt": "Do it"})
    graph = Graph(name="g", nodes={"task": node}, edges=[], attrs={"goal": "g"})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS

    response_path = tmp_path / "task" / "response.md"
    assert response_path.exists()
    assert "hello" in response_path.read_text()


def test_codergen_handler_simulation_and_prompt_expansion(tmp_path: Path):
    handler = CodergenHandler()
    node = Node(id="task", attrs={"label": "Handle $goal"})
    graph = Graph(name="g", nodes={"task": node}, edges=[], attrs={"goal": "Target"})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS

    prompt_path = tmp_path / "task" / "prompt.md"
    assert prompt_path.exists()
    assert "Target" in prompt_path.read_text()


def test_tool_handler_no_command(tmp_path: Path):
    handler = ToolHandler()
    node = Node(id="tool", attrs={"label": "", "prompt": ""})
    graph = Graph(name="g", nodes={"tool": node}, edges=[], attrs={})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL
    assert "No command" in result.failure_reason


def test_tool_handler_timeout_and_exception(monkeypatch, tmp_path: Path):
    handler = ToolHandler()
    node = Node(id="tool", attrs={"prompt": "echo ok"})
    graph = Graph(name="g", nodes={"tool": node}, edges=[], attrs={})

    def raise_timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="echo", timeout=1)

    monkeypatch.setattr("subprocess.run", raise_timeout, raising=False)

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL
    assert "timed out" in result.failure_reason

    def raise_error(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr("subprocess.run", raise_error, raising=False)

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL
    assert "Tool execution error" in result.failure_reason


def test_tool_handler_timeout_parsing(monkeypatch, tmp_path: Path):
    handler = ToolHandler()
    node = Node(id="tool", attrs={"prompt": "echo ok", "timeout": "2s"})
    graph = Graph(name="g", nodes={"tool": node}, edges=[], attrs={})

    captured = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, shell, capture_output, text, timeout=None):
        captured["timeout"] = timeout
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run, raising=False)

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS
    assert captured["timeout"] == pytest.approx(2.0)


class TimeoutInterviewer(Interviewer):
    def ask(self, question):
        return (AnswerStatus.TIMEOUT, None)


def test_wait_for_human_timeout_with_default_choice(tmp_path: Path):
    handler = WaitForHumanHandler(interviewer=TimeoutInterviewer())

    node = Node(
        id="gate",
        attrs={"label": "Choose", "human.default_choice": "B"},
    )
    graph = Graph(
        name="g",
        nodes={"gate": node},
        edges=[
            Edge(from_node="gate", to_node="a", attrs={"label": "[A] A"}),
            Edge(from_node="gate", to_node="b", attrs={"label": "[B] B"}),
        ],
        attrs={},
    )

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS
    assert result.suggested_next_ids == ["b"]


def test_wait_for_human_choice_matching():
    handler = WaitForHumanHandler()
    choices = [{"key": "A"}, {"key": "B"}]
    assert handler._find_choice_matching("C", choices) is None


def test_wait_for_human_unmatched_answer_fallback(tmp_path: Path):
    handler = WaitForHumanHandler(interviewer=UnmatchedInterviewer())
    node = Node(id="gate", attrs={"label": "Choose"})
    graph = Graph(
        name="g",
        nodes={"gate": node},
        edges=[
            Edge(from_node="gate", to_node="a", attrs={"label": "[A] A"}),
            Edge(from_node="gate", to_node="b", attrs={"label": "[B] B"}),
        ],
        attrs={},
    )

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.suggested_next_ids == ["a"]


def test_parallel_handler_join_policies(monkeypatch, tmp_path: Path):
    handler = ParallelHandler()
    node = Node(id="parallel", attrs={"join_policy": "wait_all"})
    graph = Graph(
        name="g",
        nodes={"parallel": node},
        edges=[
            Edge(from_node="parallel", to_node="a", attrs={}),
            Edge(from_node="parallel", to_node="b", attrs={}),
        ],
        attrs={},
    )

    original_dump = json.dump

    def force_failure(data, f, indent=2):
        if isinstance(data, list) and data:
            data[0]["status"] = "fail"
        return original_dump(data, f, indent=indent)

    monkeypatch.setattr(json, "dump", force_failure)
    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.PARTIAL_SUCCESS

    node.attrs["join_policy"] = "first_success"

    def force_all_fail(data, f, indent=2):
        if isinstance(data, list):
            for item in data:
                item["status"] = "fail"
        return original_dump(data, f, indent=indent)

    monkeypatch.setattr(json, "dump", force_all_fail)
    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_parallel_handler_no_branches(tmp_path: Path):
    handler = ParallelHandler()
    node = Node(id="parallel", attrs={})
    graph = Graph(name="g", nodes={"parallel": node}, edges=[], attrs={})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_parallel_handler_wait_all_success(tmp_path: Path):
    handler = ParallelHandler()
    node = Node(id="parallel", attrs={"join_policy": "wait_all"})
    graph = Graph(
        name="g",
        nodes={"parallel": node},
        edges=[
            Edge(from_node="parallel", to_node="a", attrs={}),
            Edge(from_node="parallel", to_node="b", attrs={}),
        ],
        attrs={},
    )

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS


def test_parallel_handler_default_join_policy(tmp_path: Path):
    handler = ParallelHandler()
    node = Node(id="parallel", attrs={"join_policy": "unknown"})
    graph = Graph(
        name="g",
        nodes={"parallel": node},
        edges=[
            Edge(from_node="parallel", to_node="a", attrs={}),
        ],
        attrs={},
    )

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS


def test_fan_in_handler_no_results(tmp_path: Path):
    handler = FanInHandler()
    node = Node(id="fanin", attrs={})
    graph = Graph(name="g", nodes={"fanin": node}, edges=[], attrs={})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_fan_in_handler_success_and_fallback(tmp_path: Path):
    handler = FanInHandler()
    node = Node(id="fanin", attrs={})
    graph = Graph(name="g", nodes={"fanin": node}, edges=[], attrs={})

    context = Context()
    context.set(
        "parallel.results",
        [
            {"branch_id": "a", "status": "fail"},
            {"branch_id": "b", "status": "success"},
        ],
    )
    result = handler.execute(node, context, graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS

    context = Context()
    context.set("parallel.results", [{"branch_id": "a", "status": "fail"}])
    result = handler.execute(node, context, graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS


def test_manager_loop_missing_child_dotfile(tmp_path: Path):
    handler = ManagerLoopHandler()
    node = Node(id="manager", attrs={})
    graph = Graph(name="g", nodes={"manager": node}, edges=[], attrs={})

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_manager_loop_child_dotfile_missing(tmp_path: Path):
    handler = ManagerLoopHandler()
    node = Node(id="manager", attrs={})
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(tmp_path / "missing.dot")},
    )

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_manager_loop_child_autostart_exception(monkeypatch, tmp_path: Path):
    handler = ManagerLoopHandler()
    dot_path = tmp_path / "child.dot"
    dot_path.write_text("digraph g {}")

    node = Node(id="manager", attrs={})
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(dot_path)},
    )

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr("subprocess.Popen", boom, raising=False)

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_manager_loop_child_status_completed(tmp_path: Path):
    handler = ManagerLoopHandler()
    dot_path = tmp_path / "child.dot"
    dot_path.write_text("digraph g {}")

    node = Node(
        id="manager",
        attrs={"stack.child_autostart": "false", "manager.max_cycles": "1"},
    )
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(dot_path)},
    )

    context = Context()
    context.set("stack.child.status", "completed")
    context.set("stack.child.outcome", "success")

    result = handler.execute(node, context, graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS


def test_manager_loop_child_status_failed(tmp_path: Path):
    handler = ManagerLoopHandler()
    dot_path = tmp_path / "child.dot"
    dot_path.write_text("digraph g {}")

    node = Node(
        id="manager",
        attrs={"stack.child_autostart": "false", "manager.max_cycles": "1"},
    )
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(dot_path)},
    )

    context = Context()
    context.set("stack.child.status", "failed")
    context.set("stack.child.outcome", "failure")

    result = handler.execute(node, context, graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_manager_loop_stop_condition_and_steer(tmp_path: Path):
    handler = ManagerLoopHandler()
    dot_path = tmp_path / "child.dot"
    dot_path.write_text("digraph g {}")

    node = Node(
        id="manager",
        attrs={
            "stack.child_autostart": "false",
            "manager.max_cycles": "1",
            "manager.actions": "observe,steer",
            "manager.stop_condition": "context.stop=true",
        },
    )
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(dot_path)},
    )

    context = Context()
    context.set("stop", "true")

    result = handler.execute(node, context, graph, str(tmp_path))
    assert result.status == StageStatus.SUCCESS
    assert context.get("stack.steer.last_message")


def test_manager_loop_stop_condition_exception(monkeypatch, tmp_path: Path):
    handler = ManagerLoopHandler()
    dot_path = tmp_path / "child.dot"
    dot_path.write_text("digraph g {}")

    node = Node(
        id="manager",
        attrs={
            "stack.child_autostart": "false",
            "manager.max_cycles": "1",
            "manager.actions": "observe",
            "manager.stop_condition": "context.stop=true",
        },
    )
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(dot_path)},
    )

    import attractor.conditions as conditions

    monkeypatch.setattr(conditions, "evaluate_condition", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("boom")))

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL


def test_manager_loop_max_cycles_terminates_child(monkeypatch, tmp_path: Path):
    handler = ManagerLoopHandler()
    dot_path = tmp_path / "child.dot"
    dot_path.write_text("digraph g {}")

    node = Node(
        id="manager",
        attrs={
            "manager.max_cycles": "1",
            "manager.actions": "wait",
        },
    )
    graph = Graph(
        name="g",
        nodes={"manager": node},
        edges=[],
        attrs={"stack.child_dotfile": str(dot_path)},
    )

    fake_process = FakeProcess(
        poll_result=None,
        wait_error=subprocess.TimeoutExpired(cmd="child", timeout=5),
        pid=999,
    )

    def fake_popen(*_a, **_k):
        return fake_process

    monkeypatch.setattr("subprocess.Popen", fake_popen, raising=False)
    monkeypatch.setattr("time.sleep", lambda _s: None, raising=False)

    result = handler.execute(node, Context(), graph, str(tmp_path))
    assert result.status == StageStatus.FAIL
    assert fake_process.terminated is True
    assert fake_process.killed is True


def test_manager_loop_parse_duration_invalid():
    handler = ManagerLoopHandler()
    assert handler._parse_duration("bad") == 45.0


def test_manager_loop_ingest_child_telemetry_process_exit(tmp_path: Path):
    handler = ManagerLoopHandler()
    context = Context()
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()

    handler._ingest_child_telemetry(context, stage_dir, FakeProcess(poll_result=0))
    assert context.get("stack.child.status") == "completed"

    handler._ingest_child_telemetry(context, stage_dir, FakeProcess(poll_result=1))
    assert context.get("stack.child.status") == "failed"


def test_manager_loop_ingest_child_telemetry_checkpoint(tmp_path: Path):
    handler = ManagerLoopHandler()
    context = Context()
    stage_dir = tmp_path / "stage"
    child_logs = stage_dir / "child_logs" / "run_1"
    child_logs.mkdir(parents=True)

    checkpoint = child_logs / "checkpoint.json"
    checkpoint.write_text("{\"current_node\": \"task\", \"completed_nodes\": [\"a\", \"b\"]}")

    handler._ingest_child_telemetry(context, stage_dir, None)
    assert context.get("stack.child.current_node") == "task"
    assert context.get("stack.child.completed_nodes") == 2

def test_manager_loop_ingest_child_telemetry_bad_checkpoint(tmp_path: Path):
    """Test that bad checkpoint JSON is silently ignored."""
    handler = ManagerLoopHandler()
    context = Context()
    stage_dir = tmp_path / "stage"
    child_logs = stage_dir / "child_logs" / "run_1"
    child_logs.mkdir(parents=True)

    checkpoint = child_logs / "checkpoint.json"
    checkpoint.write_text("{NOT VALID JSON")

    # Should not raise, just silently ignore the error
    handler._ingest_child_telemetry(context, stage_dir, None)
    assert context.get("stack.child.current_node") is None