"""The offline proof transport must satisfy the same caller contracts as a model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proofs"))

from harness import OfflineTransport  # noqa: E402


@pytest.mark.asyncio
async def test_offline_transport_drives_a_valid_planner_frontier() -> None:
    transport = OfflineTransport()
    prompt = json.dumps({"goal": "compare two options", "respond_as": "text",
                         "graph": {"nodes": [], "edges": []}})
    result = await transport.chat(
        prompt=prompt,
        system="You are the decision core of a live-graph agent.",
        request={"max_tokens": 4096},
    )
    patch = json.loads(result["text"])
    assert patch["add"] == [{
        "id": "content", "capability": "content",
        "arguments": {"query": "compare two options"}, "depends_on": [],
    }]
    assert result["output_tokens"] == (len(result["text"]) + 3) // 4


@pytest.mark.asyncio
async def test_offline_transport_advances_to_the_terminal_capability() -> None:
    transport = OfflineTransport()
    prompt = json.dumps({
        "goal": "compare two options", "respond_as": "text",
        "graph": {"nodes": [{"id": "content", "capability": "content",
                              "state": "succeeded", "outcome": {"offline": True}}], "edges": []},
    })
    result = await transport.chat(
        prompt=prompt,
        system="You are the decision core of a live-graph agent.",
        request={"max_tokens": 4096},
    )
    assert json.loads(result["text"])["add"][0]["capability"] == "answer_with_evidence"


@pytest.mark.asyncio
async def test_offline_transport_satisfies_the_evidence_review_contract() -> None:
    result = await OfflineTransport().chat(
        prompt="{}", system="You are an evidence-readiness critic.", request={"max_tokens": 512}
    )
    assert json.loads(result["text"]) == {
        "ready": True, "missing": [], "reason": "offline evidence is ready",
    }
