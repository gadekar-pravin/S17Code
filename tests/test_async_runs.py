"""Phase 0: durable acceptance before tracked asynchronous execution."""
from __future__ import annotations

import asyncio
import json
import threading

import s17code.ui.routes as ui_routes
from s17code.core.live_graph import GraphPatch, TaskSpec
from s17code.core.memory import MemoryKind

RUN_BODY = {
    "tenant_id": "physics-toy-factory",
    "project_id": "demo",
    "user_id": "browser",
    "prompt": "Create a gravity toy.",
    "allowed_side_effects": ["edit_code", "run_command"],
}


class TrackingTasks(set):
    """A task registry with a synchronization seam for deterministic assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.removed = threading.Event()

    def discard(self, task) -> None:
        super().discard(task)
        self.removed.set()


def _stream_events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def test_async_acceptance_is_durable_before_blocked_execution_and_streams_later_events(
    app_client, monkeypatch
) -> None:
    runtime = app_client.app.state.runtime
    entered = threading.Event()
    release_ready = threading.Event()
    release: dict[str, object] = {}
    finished = threading.Event()
    attached = threading.Event()
    registry = TrackingTasks()
    app_client.app.state.background_tasks = registry

    writes = []
    original_write = runtime.memory.write

    def counted_write(record, **kwargs):
        writes.append(record)
        return original_write(record, **kwargs)

    async def blocked_execution(prepared, **_kwargs):
        release["loop"] = asyncio.get_running_loop()
        release["event"] = asyncio.Event()
        release_ready.set()
        entered.set()
        await release["event"].wait()
        started = runtime.graph.latest_event(prepared.run_id)
        assert started is not None
        runtime.graph.apply_patch(
            prepared.run_id,
            GraphPatch(finish=True, reason="deterministic fake completed"),
            trigger_event=started.sequence,
        )
        finished.set()
        return {"run_id": prepared.run_id, "status": "completed"}

    monkeypatch.setattr(runtime.memory, "write", counted_write)
    monkeypatch.setattr(runtime, "execute_prepared", blocked_execution)
    response = app_client.post("/v1/agent/runs/async", json=RUN_BODY)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert entered.wait(2), "post-response execution did not start"
    assert release_ready.is_set()
    assert not finished.is_set()
    run_id = response.json()["run_id"]
    assert run_id.startswith("run-")

    immediate = app_client.get(f"/v1/agent/runs/{run_id}")
    assert immediate.status_code == 200
    assert immediate.json()["finished"] is False
    assert [event["kind"] for event in immediate.json()["events"]] == ["run_started"]
    inbound = [record for record in writes
               if record.kind is MemoryKind.EPISODE and record.metadata.get("run_id") == run_id]
    assert len(inbound) == 1

    original_read_run = ui_routes._read_run

    def observed_read_run(request, candidate):
        result = original_read_run(request, candidate)
        if candidate == run_id:
            attached.set()
        return result

    monkeypatch.setattr(ui_routes, "_read_run", observed_read_run)
    streamed: dict[str, object] = {}

    def consume_stream() -> None:
        with app_client.stream("GET", f"/v1/runs/{run_id}/events") as event_response:
            streamed["status"] = event_response.status_code
            streamed["body"] = "\n".join(event_response.iter_lines())

    consumer = threading.Thread(target=consume_stream, daemon=True)
    consumer.start()
    assert attached.wait(2), "SSE client did not attach"
    release["loop"].call_soon_threadsafe(release["event"].set)
    assert finished.wait(2), "fake execution did not finish"
    consumer.join(2)
    assert not consumer.is_alive(), "SSE stream did not close after the run finished"
    assert registry.removed.wait(2), "completed task stayed in the application registry"
    assert not registry

    events = _stream_events(str(streamed["body"]))
    assert streamed["status"] == 200
    assert [event["type"] for event in events] == ["RUN_STARTED", "STATE_DELTA", "RUN_FINISHED"]
    journal = app_client.get(f"/v1/agent/runs/{run_id}").json()
    assert journal["finished"] is True
    assert [event["kind"] for event in journal["events"]].count("run_started") == 1


def test_post_acceptance_exception_becomes_sanitized_terminal_stream_evidence(
    app_client, monkeypatch
) -> None:
    runtime = app_client.app.state.runtime
    registry = TrackingTasks()
    app_client.app.state.background_tasks = registry
    monkeypatch.setenv("S17_PROVIDER_TOKEN", "provider-secret-value")

    async def explode_after_nodes(prepared, **_kwargs):
        started = runtime.graph.latest_event(prepared.run_id)
        assert started is not None
        tasks = (
            TaskSpec("pending", "read_code"),
            TaskSpec("running", "edit_code"),
            TaskSpec("waiting", "run_command"),
        )
        runtime.graph.apply_patch(
            prepared.run_id,
            GraphPatch(add=tasks, reason="install active test nodes"),
            trigger_event=started.sequence,
        )
        runtime.graph.mark_running(prepared.run_id, [tasks[1], tasks[2]])
        runtime.graph.record_waiting(
            prepared.run_id, "waiting", {"handle": "job-secret", "event_type": "job.completed"}
        )
        raise RuntimeError(
            "provider failed Authorization: Bearer exposed token=provider-secret-value " + "x" * 3_000
        )

    monkeypatch.setattr(runtime, "execute_prepared", explode_after_nodes)
    response = app_client.post("/v1/agent/runs/async", json=RUN_BODY)
    assert response.status_code == 202
    assert registry.removed.wait(2), "failed task stayed in the application registry"
    assert not registry

    run_id = response.json()["run_id"]
    journal = app_client.get(f"/v1/agent/runs/{run_id}").json()
    assert journal["finished"] is True
    assert {node["state"] for node in journal["nodes"].values()} == {"cancelled"}
    assert journal["events"][-1]["kind"] == "run_failed"
    failure = journal["events"][-1]["payload"]
    assert failure["error_type"] == "RuntimeError"
    assert len(failure["error"]) <= runtime.graph.MAX_ERROR_MESSAGE
    assert "provider-secret-value" not in failure["error"]
    assert "exposed" not in failure["error"]

    stream = app_client.get(f"/v1/runs/{run_id}/events")
    assert stream.status_code == 200
    events = _stream_events(stream.text)
    types = [event["type"] for event in events]
    assert types[-2:] == ["RUN_ERROR", "RUN_FINISHED"]
    assert events[-2]["errorType"] == "RuntimeError"


def test_synchronous_run_route_keeps_completed_response_contract(app_client, monkeypatch) -> None:
    expected = {"run_id": "legacy-run", "status": "completed", "answer": "done"}

    async def synchronous_contract(**_kwargs):
        return expected

    monkeypatch.setattr(app_client.app.state.runtime, "run", synchronous_contract)
    response = app_client.post("/v1/agent/runs", json=RUN_BODY)
    assert response.status_code == 200
    assert response.json() == expected


def test_background_failure_cannot_overwrite_a_normally_finished_graph(app_client) -> None:
    runtime = app_client.app.state.runtime
    run_id = "normally-finished"
    assert runtime.graph.start(run_id, context={}) is True
    started = runtime.graph.latest_event(run_id)
    assert started is not None
    runtime.graph.apply_patch(
        run_id,
        GraphPatch(finish=True, reason="normal completion"),
        trigger_event=started.sequence,
    )
    before = runtime.graph.events(run_id)
    assert runtime.graph.fail_run(
        run_id, error_type="LateError", message="arrived after completion"
    ) is False
    assert runtime.graph.events(run_id) == before
