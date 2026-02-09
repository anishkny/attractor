"""
Tests for the HTTP server module.
"""

import os
import sys
import threading
from types import SimpleNamespace
import types

import pytest


class FakeRequest:
    def __init__(self, json_data=None):
        self._json = json_data

    def get_json(self):
        return self._json


class FakeResponse:
    def __init__(self, json_data=None, response=None, status_code=200, mimetype=None):
        self._json = json_data
        self.response = response if response is not None else []
        self.status_code = status_code
        self.mimetype = mimetype

    def get_json(self):
        return self._json


class FakeFlask:
    def __init__(self, name):
        self.name = name
        self._routes = []

    def route(self, path, methods=None):
        methods = methods or ["GET"]

        def decorator(func):
            self._routes.append((path, methods, func))
            return func

        return decorator

    def test_client(self):
        return FakeClient(self)

    def run(self, host=None, port=None, threaded=None):
        return None


class FakeClient:
    def __init__(self, app):
        self.app = app

    def get(self, path, json=None):
        return self._request("GET", path, json)

    def post(self, path, json=None):
        return self._request("POST", path, json)

    def _request(self, method, path, json_data):
        flask_stub.request._json = json_data

        sorted_routes = sorted(self.app._routes, key=lambda r: len(r[0]), reverse=True)

        for route_path, methods, func in sorted_routes:
            if method not in methods:
                continue

            params = _match_route(route_path, path)
            if params is None:
                continue

            result = func(**params)
            return _normalize_response(result)

        return FakeResponse({"error": "not found"}, status_code=404)


def _match_route(route_path, path):
    if "<pipeline_id>" not in route_path:
        return {} if route_path == path else None

    prefix, suffix = route_path.split("<pipeline_id>")
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None

    trimmed = path[len(prefix) : len(path) - len(suffix)]
    trimmed = trimmed.strip("/")
    return {"pipeline_id": trimmed}


def _normalize_response(result):
    if isinstance(result, tuple):
        body, status = result
        if isinstance(body, FakeResponse):
            body.status_code = status
            return body
        if isinstance(body, Response):
            body.status_code = status
            return body
        return FakeResponse(body, status_code=status)

    if isinstance(result, (FakeResponse, Response)):
        return result

    return FakeResponse(result)


def jsonify(payload):
    return FakeResponse(payload)


class Response(FakeResponse):
    def __init__(self, response=None, mimetype=None):
        super().__init__(json_data=None, response=response, mimetype=mimetype)


request_instance = FakeRequest()

flask_stub = types.SimpleNamespace(
    Flask=FakeFlask,
    Response=Response,
    jsonify=jsonify,
    request=request_instance,
)
sys.modules.setdefault("flask", flask_stub)

import attractor.server as server_module
from attractor.events import StageStartedEvent
from attractor.models import Context, Graph, Node, Outcome, StageStatus


class FakeEngine:
    def __init__(self, graph, logs_root=None, event_emitter=None, handler_registry=None):
        self.graph = graph
        self.logs_root = logs_root
        self.event_emitter = event_emitter

    def run(self, context):
        if self.event_emitter:
            self.event_emitter.emit(StageStartedEvent("task", 0))
        return Outcome(status=StageStatus.SUCCESS, notes="ok")


def _simple_graph() -> Graph:
    nodes = {
        "start": Node(id="start", attrs={"shape": "Mdiamond"}),
        "exit": Node(id="exit", attrs={"shape": "Msquare"}),
    }
    return Graph(name="test", nodes=nodes, edges=[], attrs={})


def test_server_routes_basic(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "PipelineEngine", FakeEngine)
    monkeypatch.setattr(server_module, "parse_dot_string", lambda _s: _simple_graph())

    class InlineThread:
        def __init__(self, target=None, daemon=None):
            self._target = target
            self.daemon = daemon

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(threading, "Thread", InlineThread)

    server = server_module.PipelineServer(logs_root=str(tmp_path))
    client = server.app.test_client()

    response = client.post("/pipelines", json={"dot_source": "digraph g {}"})
    assert response.status_code == 201

    pipeline_id = response.get_json()["id"]

    status_response = client.get(f"/pipelines/{pipeline_id}")
    assert status_response.status_code == 200
    assert status_response.get_json()["status"] in ["completed", "failed"]

    server.pipelines[pipeline_id].context.set("answer", "42")
    context_response = client.get(f"/pipelines/{pipeline_id}/context")
    assert context_response.status_code == 200
    assert context_response.get_json()["answer"] == "42"

    events_response = client.get(f"/pipelines/{pipeline_id}/events")
    chunks = list(events_response.response)
    assert any("done" in chunk for chunk in chunks)

    cancel_response = client.post(f"/pipelines/{pipeline_id}/cancel")
    assert cancel_response.status_code == 400

    health = client.get("/health")
    assert health.status_code == 200


def test_server_missing_dot_source(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "PipelineEngine", FakeEngine)
    monkeypatch.setattr(server_module, "parse_dot_string", lambda _s: _simple_graph())

    server = server_module.PipelineServer(logs_root=str(tmp_path))
    client = server.app.test_client()

    response = client.post("/pipelines", json={})
    assert response.status_code == 400


def test_server_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "PipelineEngine", FakeEngine)
    monkeypatch.setattr(server_module, "parse_dot_string", lambda _s: _simple_graph())

    server = server_module.PipelineServer(logs_root=str(tmp_path))
    client = server.app.test_client()

    status_response = client.get("/pipelines/missing")
    assert status_response.status_code == 404

    events_response = client.get("/pipelines/missing/events")
    assert events_response.status_code == 404


def test_server_cancel_running(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "PipelineEngine", FakeEngine)
    monkeypatch.setattr(server_module, "parse_dot_string", lambda _s: _simple_graph())

    server = server_module.PipelineServer(logs_root=str(tmp_path))
    client = server.app.test_client()

    pipeline_run = server_module.PipelineRun(
        id="p1",
        name="test",
        status="running",
        outcome=None,
        context=Context(),
        engine=None,
        thread=None,
        event_queue=server_module.queue.Queue(),
        start_time=0.0,
        end_time=None,
        pending_questions={},
    )

    server.pipelines["p1"] = pipeline_run

    cancel_response = client.post("/pipelines/p1/cancel")
    assert cancel_response.status_code == 200
    assert server.pipelines["p1"].status == "cancelled"


def test_server_events_dict_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "PipelineEngine", FakeEngine)
    monkeypatch.setattr(server_module, "parse_dot_string", lambda _s: _simple_graph())

    server = server_module.PipelineServer(logs_root=str(tmp_path))
    client = server.app.test_client()

    pipeline_run = server_module.PipelineRun(
        id="p2",
        name="test",
        status="completed",
        outcome=Outcome(status=StageStatus.SUCCESS),
        context=Context(),
        engine=None,
        thread=None,
        event_queue=server_module.queue.Queue(),
        start_time=0.0,
        end_time=1.0,
        pending_questions={},
    )
    pipeline_run.event_queue.put({"type": "error", "message": "boom"})

    server.pipelines["p2"] = pipeline_run

    events_response = client.get("/pipelines/p2/events")
    chunks = list(events_response.response)
    assert any("error" in chunk for chunk in chunks)


def test_server_run_and_main(monkeypatch, tmp_path):
    server = server_module.PipelineServer(logs_root=str(tmp_path))

    called = {"run": False}

    def fake_run(*_a, **_k):
        called["run"] = True

    monkeypatch.setattr(server.app, "run", fake_run)
    server.run()
    assert called["run"] is True

    fake_server = SimpleNamespace(run=lambda: None)

    def fake_create_server(host="127.0.0.1", port=8080, logs_root=None):
        return fake_server

    monkeypatch.setattr(server_module, "create_server", fake_create_server)
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("LOGS_ROOT", str(tmp_path))

    server_module.main()
