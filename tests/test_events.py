"""
Tests for the event system.
"""

from attractor.events import (
    CheckpointSavedEvent,
    Event,
    EventEmitter,
    EventType,
    InterviewCompletedEvent,
    InterviewStartedEvent,
    InterviewTimeoutEvent,
    ParallelBranchCompletedEvent,
    ParallelBranchStartedEvent,
    ParallelCompletedEvent,
    ParallelStartedEvent,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageRetryingEvent,
    StageStartedEvent,
)


def test_pipeline_started_event():
    event = PipelineStartedEvent("test-pipeline", "abc123")
    assert event.event_type == EventType.PIPELINE_STARTED
    assert event.name == "test-pipeline"
    assert event.id == "abc123"
    assert "test-pipeline" in event.description
    assert "abc123" in event.description


def test_pipeline_completed_event():
    event = PipelineCompletedEvent(12.5, 3)
    assert event.event_type == EventType.PIPELINE_COMPLETED
    assert event.duration == 12.5
    assert event.artifact_count == 3
    assert "12.5" in event.description or "12.50" in event.description


def test_pipeline_failed_event():
    event = PipelineFailedEvent("Test error", 5.0)
    assert event.event_type == EventType.PIPELINE_FAILED
    assert event.error == "Test error"
    assert event.duration == 5.0
    assert "Test error" in event.description


def test_stage_started_event():
    event = StageStartedEvent("task1", 0)
    assert event.event_type == EventType.STAGE_STARTED
    assert event.name == "task1"
    assert event.index == 0
    assert "task1" in event.description


def test_stage_completed_event():
    event = StageCompletedEvent("task1", 0, 2.3)
    assert event.event_type == EventType.STAGE_COMPLETED
    assert event.name == "task1"
    assert event.index == 0
    assert event.duration == 2.3


def test_stage_failed_event():
    event = StageFailedEvent("task1", 0, "Failed to execute", True)
    assert event.event_type == EventType.STAGE_FAILED
    assert event.name == "task1"
    assert event.index == 0
    assert event.error == "Failed to execute"
    assert event.will_retry is True
    assert "retry" in event.description.lower()


def test_stage_retrying_event():
    event = StageRetryingEvent("task1", 0, 2, 1.5)
    assert event.event_type == EventType.STAGE_RETRYING
    assert event.name == "task1"
    assert event.attempt == 2
    assert event.delay == 1.5


def test_parallel_events():
    start_event = ParallelStartedEvent(3)
    assert start_event.event_type == EventType.PARALLEL_STARTED
    assert start_event.branch_count == 3

    branch_start = ParallelBranchStartedEvent("branch1", 0)
    assert branch_start.event_type == EventType.PARALLEL_BRANCH_STARTED
    assert branch_start.branch == "branch1"

    branch_complete = ParallelBranchCompletedEvent("branch1", 0, 2.5, True)
    assert branch_complete.event_type == EventType.PARALLEL_BRANCH_COMPLETED
    assert branch_complete.success is True

    complete = ParallelCompletedEvent(5.0, 2, 1)
    assert complete.event_type == EventType.PARALLEL_COMPLETED
    assert complete.success_count == 2
    assert complete.failure_count == 1


def test_interview_events():
    start = InterviewStartedEvent("Continue?", "approval")
    assert start.event_type == EventType.INTERVIEW_STARTED
    assert start.question == "Continue?"
    assert start.stage == "approval"

    complete = InterviewCompletedEvent("Continue?", "Yes", 3.0)
    assert complete.event_type == EventType.INTERVIEW_COMPLETED
    assert complete.answer == "Yes"

    timeout = InterviewTimeoutEvent("Continue?", "approval", 30.0)
    assert timeout.event_type == EventType.INTERVIEW_TIMEOUT


def test_checkpoint_saved_event():
    event = CheckpointSavedEvent("task1")
    assert event.event_type == EventType.CHECKPOINT_SAVED
    assert event.node_id == "task1"


def test_event_emitter_basic():
    emitter = EventEmitter()
    events_received = []

    def observer(event: Event):
        events_received.append(event)

    emitter.on_event(observer)

    event1 = StageStartedEvent("task1", 0)
    event2 = StageCompletedEvent("task1", 0, 1.0)

    emitter.emit(event1)
    emitter.emit(event2)

    assert len(events_received) == 2
    assert events_received[0] == event1
    assert events_received[1] == event2


def test_event_emitter_multiple_observers():
    emitter = EventEmitter()
    observer1_events = []
    observer2_events = []

    def observer1(event: Event):
        observer1_events.append(event)

    def observer2(event: Event):
        observer2_events.append(event)

    emitter.on_event(observer1)
    emitter.on_event(observer2)

    event = StageStartedEvent("task1", 0)
    emitter.emit(event)

    assert len(observer1_events) == 1
    assert len(observer2_events) == 1
    assert observer1_events[0] == event
    assert observer2_events[0] == event


def test_event_emitter_observer_error_handling():
    emitter = EventEmitter()
    events_received = []

    def failing_observer(event: Event):
        raise ValueError("Observer error")

    def working_observer(event: Event):
        events_received.append(event)

    emitter.on_event(failing_observer)
    emitter.on_event(working_observer)

    event = StageStartedEvent("task1", 0)
    emitter.emit(event)  # Should not crash

    # Working observer should still receive the event
    assert len(events_received) == 1


def test_event_emitter_clear():
    emitter = EventEmitter()
    events_received = []

    def observer(event: Event):
        events_received.append(event)

    emitter.on_event(observer)
    emitter.emit(StageStartedEvent("task1", 0))
    assert len(events_received) == 1

    emitter.clear()
    emitter.emit(StageStartedEvent("task2", 1))
    # No more events should be received after clear
    assert len(events_received) == 1
