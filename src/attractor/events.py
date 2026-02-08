"""
Observability and event system for Attractor pipelines.

The engine emits typed events during execution for UI, logging, and metrics integration.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Optional


class EventType(Enum):
    """Types of events emitted during pipeline execution."""

    # Pipeline lifecycle
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"

    # Stage lifecycle
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    STAGE_RETRYING = "stage_retrying"

    # Parallel execution
    PARALLEL_STARTED = "parallel_started"
    PARALLEL_BRANCH_STARTED = "parallel_branch_started"
    PARALLEL_BRANCH_COMPLETED = "parallel_branch_completed"
    PARALLEL_COMPLETED = "parallel_completed"

    # Human interaction
    INTERVIEW_STARTED = "interview_started"
    INTERVIEW_COMPLETED = "interview_completed"
    INTERVIEW_TIMEOUT = "interview_timeout"

    # Checkpoint
    CHECKPOINT_SAVED = "checkpoint_saved"


@dataclass
class Event:
    """Base class for all events."""

    event_type: EventType
    description: str


@dataclass
class PipelineStartedEvent(Event):
    """Pipeline begins execution."""

    name: str
    id: str

    def __init__(self, name: str, id: str):
        super().__init__(
            event_type=EventType.PIPELINE_STARTED,
            description=f"Pipeline '{name}' started with ID {id}",
        )
        self.name = name
        self.id = id


@dataclass
class PipelineCompletedEvent(Event):
    """Pipeline completed successfully."""

    duration: float
    artifact_count: int

    def __init__(self, duration: float, artifact_count: int):
        super().__init__(
            event_type=EventType.PIPELINE_COMPLETED,
            description=f"Pipeline completed in {duration:.2f}s with {artifact_count} artifacts",
        )
        self.duration = duration
        self.artifact_count = artifact_count


@dataclass
class PipelineFailedEvent(Event):
    """Pipeline failed."""

    error: str
    duration: float

    def __init__(self, error: str, duration: float):
        super().__init__(
            event_type=EventType.PIPELINE_FAILED,
            description=f"Pipeline failed after {duration:.2f}s: {error}",
        )
        self.error = error
        self.duration = duration


@dataclass
class StageStartedEvent(Event):
    """Stage begins execution."""

    name: str
    index: int

    def __init__(self, name: str, index: int):
        super().__init__(
            event_type=EventType.STAGE_STARTED, description=f"Stage '{name}' started"
        )
        self.name = name
        self.index = index


@dataclass
class StageCompletedEvent(Event):
    """Stage completed successfully."""

    name: str
    index: int
    duration: float

    def __init__(self, name: str, index: int, duration: float):
        super().__init__(
            event_type=EventType.STAGE_COMPLETED,
            description=f"Stage '{name}' completed in {duration:.2f}s",
        )
        self.name = name
        self.index = index
        self.duration = duration


@dataclass
class StageFailedEvent(Event):
    """Stage failed."""

    name: str
    index: int
    error: str
    will_retry: bool

    def __init__(self, name: str, index: int, error: str, will_retry: bool):
        retry_msg = " (will retry)" if will_retry else ""
        super().__init__(
            event_type=EventType.STAGE_FAILED,
            description=f"Stage '{name}' failed: {error}{retry_msg}",
        )
        self.name = name
        self.index = index
        self.error = error
        self.will_retry = will_retry


@dataclass
class StageRetryingEvent(Event):
    """Stage is retrying after failure."""

    name: str
    index: int
    attempt: int
    delay: float

    def __init__(self, name: str, index: int, attempt: int, delay: float):
        super().__init__(
            event_type=EventType.STAGE_RETRYING,
            description=f"Stage '{name}' retrying (attempt {attempt}) after {delay:.2f}s delay",
        )
        self.name = name
        self.index = index
        self.attempt = attempt
        self.delay = delay


@dataclass
class ParallelStartedEvent(Event):
    """Parallel execution block started."""

    branch_count: int

    def __init__(self, branch_count: int):
        super().__init__(
            event_type=EventType.PARALLEL_STARTED,
            description=f"Parallel execution started with {branch_count} branches",
        )
        self.branch_count = branch_count


@dataclass
class ParallelBranchStartedEvent(Event):
    """Parallel branch started."""

    branch: str
    index: int

    def __init__(self, branch: str, index: int):
        super().__init__(
            event_type=EventType.PARALLEL_BRANCH_STARTED,
            description=f"Parallel branch '{branch}' started",
        )
        self.branch = branch
        self.index = index


@dataclass
class ParallelBranchCompletedEvent(Event):
    """Parallel branch completed."""

    branch: str
    index: int
    duration: float
    success: bool

    def __init__(self, branch: str, index: int, duration: float, success: bool):
        status = "success" if success else "failure"
        super().__init__(
            event_type=EventType.PARALLEL_BRANCH_COMPLETED,
            description=f"Parallel branch '{branch}' completed in {duration:.2f}s ({status})",
        )
        self.branch = branch
        self.index = index
        self.duration = duration
        self.success = success


@dataclass
class ParallelCompletedEvent(Event):
    """All parallel branches completed."""

    duration: float
    success_count: int
    failure_count: int

    def __init__(self, duration: float, success_count: int, failure_count: int):
        super().__init__(
            event_type=EventType.PARALLEL_COMPLETED,
            description=f"Parallel execution completed in {duration:.2f}s ({success_count} success, {failure_count} failures)",
        )
        self.duration = duration
        self.success_count = success_count
        self.failure_count = failure_count


@dataclass
class InterviewStartedEvent(Event):
    """Human interaction question presented."""

    question: str
    stage: str

    def __init__(self, question: str, stage: str):
        super().__init__(
            event_type=EventType.INTERVIEW_STARTED,
            description=f"Interview started at stage '{stage}'",
        )
        self.question = question
        self.stage = stage


@dataclass
class InterviewCompletedEvent(Event):
    """Human interaction answer received."""

    question: str
    answer: str
    duration: float

    def __init__(self, question: str, answer: str, duration: float):
        super().__init__(
            event_type=EventType.INTERVIEW_COMPLETED,
            description=f"Interview completed in {duration:.2f}s",
        )
        self.question = question
        self.answer = answer
        self.duration = duration


@dataclass
class InterviewTimeoutEvent(Event):
    """Human interaction timed out."""

    question: str
    stage: str
    duration: float

    def __init__(self, question: str, stage: str, duration: float):
        super().__init__(
            event_type=EventType.INTERVIEW_TIMEOUT,
            description=f"Interview timed out at stage '{stage}' after {duration:.2f}s",
        )
        self.question = question
        self.stage = stage
        self.duration = duration


@dataclass
class CheckpointSavedEvent(Event):
    """Checkpoint saved to disk."""

    node_id: str

    def __init__(self, node_id: str):
        super().__init__(
            event_type=EventType.CHECKPOINT_SAVED,
            description=f"Checkpoint saved for node '{node_id}'",
        )
        self.node_id = node_id


EventCallback = Callable[[Event], None]


class EventEmitter:
    """Event emitter for pipeline execution events."""

    def __init__(self):
        self.observers: List[EventCallback] = []

    def on_event(self, callback: EventCallback):
        """Register an event observer callback."""
        self.observers.append(callback)

    def emit(self, event: Event):
        """Emit an event to all registered observers."""
        for observer in self.observers:
            try:
                observer(event)
            except Exception as e:
                # Don't let observer errors crash the pipeline
                print(f"Error in event observer: {e}")

    def clear(self):
        """Clear all observers."""
        self.observers.clear()
