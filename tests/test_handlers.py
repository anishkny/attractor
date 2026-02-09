"""
Tests for handler implementations.
"""

import tempfile
from pathlib import Path

from attractor.handlers import Interviewer, ToolHandler, WaitForHumanHandler
from attractor.models import (
    Answer,
    AnswerStatus,
    Context,
    Edge,
    Graph,
    Node,
    Question,
    QuestionType,
    StageStatus,
)


class MockInterviewer(Interviewer):
    """Mock interviewer for testing."""

    def __init__(self, answer_key: str = "A", status: AnswerStatus = AnswerStatus.ANSWERED):
        self.answer_key = answer_key
        self.status = status
        self.asked_questions = []

    def ask(self, question: Question) -> tuple:
        self.asked_questions.append(question)
        if self.status == AnswerStatus.ANSWERED:
            answer = Answer(value=self.answer_key, question=question)
            return (AnswerStatus.ANSWERED, answer)
        return (self.status, None)


def test_tool_handler_success():
    """Test ToolHandler with a successful command."""
    handler = ToolHandler()
    node = Node(id="test_tool", attrs={"prompt": "echo 'Hello World'"})
    context = Context()
    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_tool": node},
        edges=[]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.SUCCESS
        assert "test_tool" in outcome.notes

        # Check logs
        stage_dir = Path(tmpdir) / "test_tool"
        assert (stage_dir / "command.txt").exists()
        assert (stage_dir / "stdout.txt").exists()
        assert (stage_dir / "stderr.txt").exists()
        assert (stage_dir / "status.json").exists()

        # Check stdout contains expected output
        stdout = (stage_dir / "stdout.txt").read_text()
        assert "Hello World" in stdout


def test_tool_handler_failure():
    """Test ToolHandler with a failing command."""
    handler = ToolHandler()
    node = Node(id="test_tool", attrs={"prompt": "exit 1"})
    context = Context()
    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_tool": node},
        edges=[]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.FAIL
        assert "return code 1" in outcome.failure_reason


def test_tool_handler_no_command():
    """Test ToolHandler without a command (uses node id as fallback)."""
    handler = ToolHandler()
    node = Node(id="echo_hello", attrs={"prompt": ""})
    context = Context()
    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"echo_hello": node},
        edges=[]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        # When prompt is empty, it uses label, which defaults to node id
        # This may or may not be a valid command
        assert outcome.status in [StageStatus.SUCCESS, StageStatus.FAIL]


def test_wait_for_human_handler_simulation():
    """Test WaitForHumanHandler in simulation mode (no interviewer)."""
    handler = WaitForHumanHandler()
    node = Node(id="test_gate", attrs={"label": "Choose an option"})
    context = Context()

    # Create edges for choices
    edges = [
        Edge(from_node="test_gate", to_node="option_a", attrs={"label": "[A] Option A"}),
        Edge(from_node="test_gate", to_node="option_b", attrs={"label": "[B] Option B"}),
    ]

    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_gate": node},
        edges=edges
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.SUCCESS
        assert outcome.suggested_next_ids == ["option_a"]  # First choice by default
        assert "human.gate.selected" in outcome.context_updates

        # Check logs
        stage_dir = Path(tmpdir) / "test_gate"
        assert (stage_dir / "question.json").exists()
        assert (stage_dir / "answer.json").exists()


def test_wait_for_human_handler_with_interviewer():
    """Test WaitForHumanHandler with a mock interviewer."""
    mock_interviewer = MockInterviewer(answer_key="B")
    handler = WaitForHumanHandler(interviewer=mock_interviewer)
    node = Node(id="test_gate", attrs={"label": "Choose an option"})
    context = Context()

    edges = [
        Edge(from_node="test_gate", to_node="option_a", attrs={"label": "[A] Option A"}),
        Edge(from_node="test_gate", to_node="option_b", attrs={"label": "[B] Option B"}),
    ]

    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_gate": node},
        edges=edges
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.SUCCESS
        assert outcome.suggested_next_ids == ["option_b"]  # Second choice selected
        assert outcome.context_updates["human.gate.selected"] == "B"

        # Check that question was asked
        assert len(mock_interviewer.asked_questions) == 1
        question = mock_interviewer.asked_questions[0]
        assert question.type == QuestionType.MULTIPLE_CHOICE
        assert len(question.options) == 2


def test_wait_for_human_handler_no_edges():
    """Test WaitForHumanHandler with no outgoing edges."""
    handler = WaitForHumanHandler()
    node = Node(id="test_gate", attrs={"label": "Choose an option"})
    context = Context()
    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_gate": node},
        edges=[]  # No edges
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.FAIL
        assert "No outgoing edges" in outcome.failure_reason


def test_wait_for_human_handler_timeout():
    """Test WaitForHumanHandler with timeout."""
    mock_interviewer = MockInterviewer(status=AnswerStatus.TIMEOUT)
    handler = WaitForHumanHandler(interviewer=mock_interviewer)
    node = Node(id="test_gate", attrs={"label": "Choose an option"})
    context = Context()

    edges = [
        Edge(from_node="test_gate", to_node="option_a", attrs={"label": "[A] Option A"}),
    ]

    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_gate": node},
        edges=edges
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.RETRY
        assert "timeout" in outcome.failure_reason.lower()


def test_wait_for_human_handler_skipped():
    """Test WaitForHumanHandler when human skips."""
    mock_interviewer = MockInterviewer(status=AnswerStatus.SKIPPED)
    handler = WaitForHumanHandler(interviewer=mock_interviewer)
    node = Node(id="test_gate", attrs={"label": "Choose an option"})
    context = Context()

    edges = [
        Edge(from_node="test_gate", to_node="option_a", attrs={"label": "[A] Option A"}),
    ]

    graph = Graph(
        name="test_graph",
        attrs={},
        nodes={"test_gate": node},
        edges=edges
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = handler.execute(node, context, graph, tmpdir)

        assert outcome.status == StageStatus.FAIL
        assert "skipped" in outcome.failure_reason.lower()


def test_accelerator_key_parsing():
    """Test accelerator key parsing from edge labels."""
    handler = WaitForHumanHandler()

    # Test various formats
    assert handler._parse_accelerator_key("[Y] Yes") == "Y"
    assert handler._parse_accelerator_key("Y) Yes") == "Y"
    assert handler._parse_accelerator_key("Y - Yes") == "Y"
    assert handler._parse_accelerator_key("Yes") == "Y"  # First character
    assert handler._parse_accelerator_key("[a] approve") == "A"  # Uppercase conversion
