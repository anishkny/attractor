"""
HTTP server mode for Attractor pipelines.

Exposes the pipeline engine as an HTTP service for web-based management,
remote human interaction, and integration with external systems.
"""

import json
import os
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, Response, jsonify, request, send_file

from .engine import PipelineEngine, run_pipeline
from .events import Event, EventEmitter
from .handlers import HandlerRegistry
from .models import Context, Graph, Outcome, Question, Answer, AnswerStatus
from .parser import parse_dot_string


@dataclass
class PipelineRun:
    """Information about a running pipeline."""

    id: str
    name: str
    status: str  # running, completed, failed
    outcome: Optional[Outcome]
    context: Context
    engine: Optional[PipelineEngine]
    thread: Optional[threading.Thread]
    event_queue: queue.Queue
    start_time: float
    end_time: Optional[float]
    pending_questions: Dict[str, Question]


class PipelineServer:
    """HTTP server for pipeline management."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        logs_root: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.logs_root = logs_root or "logs"
        self.app = Flask(__name__)
        self.pipelines: Dict[str, PipelineRun] = {}
        self.lock = threading.Lock()

        self._setup_routes()

    def _setup_routes(self):
        """Set up Flask routes."""

        @self.app.route("/pipelines", methods=["POST"])
        def submit_pipeline():
            """Submit a DOT source and start execution."""
            try:
                data = request.get_json()
                if not data or "dot_source" not in data:
                    return jsonify({"error": "Missing dot_source in request"}), 400

                dot_source = data["dot_source"]
                graph = parse_dot_string(dot_source)

                # Create pipeline run
                pipeline_id = str(uuid.uuid4())[:8]
                event_queue = queue.Queue()
                context = Context()

                # Set up event emitter
                event_emitter = EventEmitter()
                event_emitter.on_event(lambda event: event_queue.put(event))

                # Create pipeline run
                logs_dir = Path(self.logs_root) / pipeline_id
                logs_dir.mkdir(parents=True, exist_ok=True)

                pipeline_run = PipelineRun(
                    id=pipeline_id,
                    name=graph.name,
                    status="running",
                    outcome=None,
                    context=context,
                    engine=None,
                    thread=None,
                    event_queue=event_queue,
                    start_time=time.time(),
                    end_time=None,
                    pending_questions={},
                )

                # Start pipeline in background thread
                def run_pipeline_thread():
                    try:
                        engine = PipelineEngine(
                            graph,
                            logs_root=str(logs_dir),
                            event_emitter=event_emitter,
                        )
                        pipeline_run.engine = engine
                        outcome = engine.run(context)
                        pipeline_run.outcome = outcome
                        pipeline_run.status = (
                            "completed" if outcome.status.value == "success" else "failed"
                        )
                        pipeline_run.end_time = time.time()
                    except Exception as e:
                        pipeline_run.status = "failed"
                        pipeline_run.end_time = time.time()
                        # Add error to event queue
                        event_queue.put(
                            {"type": "error", "message": str(e)}
                        )

                thread = threading.Thread(target=run_pipeline_thread, daemon=True)
                pipeline_run.thread = thread

                with self.lock:
                    self.pipelines[pipeline_id] = pipeline_run

                thread.start()

                return (
                    jsonify(
                        {
                            "id": pipeline_id,
                            "name": graph.name,
                            "status": "running",
                        }
                    ),
                    201,
                )

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/pipelines/<pipeline_id>", methods=["GET"])
        def get_pipeline_status(pipeline_id):
            """Get pipeline status and progress."""
            with self.lock:
                if pipeline_id not in self.pipelines:
                    return jsonify({"error": "Pipeline not found"}), 404

                pipeline_run = self.pipelines[pipeline_id]

            # Build status response
            status = {
                "id": pipeline_run.id,
                "name": pipeline_run.name,
                "status": pipeline_run.status,
                "start_time": pipeline_run.start_time,
                "end_time": pipeline_run.end_time,
                "duration": (
                    (pipeline_run.end_time or time.time()) - pipeline_run.start_time
                ),
            }

            if pipeline_run.outcome:
                status["outcome"] = {
                    "status": pipeline_run.outcome.status.value,
                    "notes": pipeline_run.outcome.notes,
                    "failure_reason": pipeline_run.outcome.failure_reason,
                }

            return jsonify(status)

        @self.app.route("/pipelines/<pipeline_id>/events", methods=["GET"])
        def get_pipeline_events(pipeline_id):
            """SSE stream of pipeline events in real-time."""
            with self.lock:
                if pipeline_id not in self.pipelines:
                    return jsonify({"error": "Pipeline not found"}), 404

                pipeline_run = self.pipelines[pipeline_id]

            def generate():
                """Generate SSE events."""
                try:
                    while True:
                        try:
                            # Get event from queue with timeout
                            event = pipeline_run.event_queue.get(timeout=1.0)

                            if isinstance(event, Event):
                                # Format as SSE
                                data = {
                                    "type": event.event_type.value,
                                    "description": event.description,
                                }
                                yield f"data: {json.dumps(data)}\n\n"
                            elif isinstance(event, dict):
                                # Custom event (e.g., error)
                                yield f"data: {json.dumps(event)}\n\n"

                        except queue.Empty:
                            # Send heartbeat
                            yield ": heartbeat\n\n"

                        # Check if pipeline is done
                        if pipeline_run.status in ["completed", "failed"]:
                            # Send final status and exit
                            yield f"data: {json.dumps({'type': 'done', 'status': pipeline_run.status})}\n\n"
                            break

                except GeneratorExit:
                    pass

            return Response(generate(), mimetype="text/event-stream")

        @self.app.route("/pipelines/<pipeline_id>/cancel", methods=["POST"])
        def cancel_pipeline(pipeline_id):
            """Cancel a running pipeline."""
            with self.lock:
                if pipeline_id not in self.pipelines:
                    return jsonify({"error": "Pipeline not found"}), 404

                pipeline_run = self.pipelines[pipeline_id]

            if pipeline_run.status != "running":
                return jsonify({"error": "Pipeline is not running"}), 400

            # Update status
            pipeline_run.status = "cancelled"
            pipeline_run.end_time = time.time()

            # Note: We can't actually stop the thread cleanly in Python
            # But we mark it as cancelled

            return jsonify({"message": "Pipeline cancelled", "id": pipeline_id})

        @self.app.route("/pipelines/<pipeline_id>/context", methods=["GET"])
        def get_pipeline_context(pipeline_id):
            """Get current context key-value store."""
            with self.lock:
                if pipeline_id not in self.pipelines:
                    return jsonify({"error": "Pipeline not found"}), 404

                pipeline_run = self.pipelines[pipeline_id]

            context_snapshot = pipeline_run.context.snapshot()
            return jsonify(context_snapshot)

        @self.app.route("/health", methods=["GET"])
        def health_check():
            """Health check endpoint."""
            return jsonify({"status": "ok", "pipelines": len(self.pipelines)})

    def run(self):
        """Start the HTTP server."""
        self.app.run(host=self.host, port=self.port, threaded=True)


def create_server(
    host: str = "0.0.0.0", port: int = 8080, logs_root: Optional[str] = None
) -> PipelineServer:
    """Create a pipeline HTTP server."""
    return PipelineServer(host=host, port=port, logs_root=logs_root)


def main():
    """Main entry point for the server."""
    import sys

    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")
    logs_root = os.environ.get("LOGS_ROOT", "logs")

    server = create_server(host=host, port=port, logs_root=logs_root)
    print(f"Starting Attractor HTTP server on {host}:{port}")
    print(f"Logs directory: {logs_root}")
    server.run()


if __name__ == "__main__":
    main()
