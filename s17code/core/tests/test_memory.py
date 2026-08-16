from __future__ import annotations

import json
import unittest
from unittest import mock

from s17code.core.memory import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStore,
    PermissionDenied,
    Principal,
    SourceRef,
)
from s17code.core.memory import embeddings as embeddings_module
from s17code.core.memory.chunking import fixed_word_chunks, semantic_chunks
from s17code.core.memory.embeddings import DeterministicEmbedder, OllamaNomicEmbedder

AGENT = Principal("researcher", "agent")
SOURCE = SourceRef("message://u1/1", "user", excerpt="original user statement")


class MemoryProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore(embedder=DeterministicEmbedder(256))
        self.scope_a = MemoryScope("tenant-a", "project", "user")
        self.scope_b = MemoryScope("tenant-b", "project", "user")

    def tearDown(self) -> None:
        self.store.close()

    def fact(self, text: str, scope: MemoryScope | None = None, **kwargs) -> MemoryRecord:
        return MemoryRecord(MemoryKind.FACT, scope or self.scope_a, text, [SOURCE], AGENT, **kwargs)

    def test_cross_tenant_recall_is_impossible(self) -> None:
        secret = self.store.write(self.fact("Vendor secret is moonstone"))
        self.assertEqual(self.store.recall("vendor secret", self.scope_b), [])
        self.assertEqual(self.store.recall("vendor secret", self.scope_a)[0].id, secret.id)

    def test_supersession_hides_old_fact_but_keeps_history(self) -> None:
        old = self.store.write(self.fact("Budget is 50000 rupees"))
        new = self.store.write(self.fact("Budget is 75000 rupees", supersedes_id=old.id))
        current = self.store.recall("budget rupees", self.scope_a, kinds=[MemoryKind.FACT])
        self.assertEqual([record.id for record in current], [new.id])
        historical = self.store.recall("budget rupees", self.scope_a, kinds=[MemoryKind.FACT], include_history=True)
        self.assertEqual({record.id for record in historical}, {old.id, new.id})
        self.assertEqual(self.store.get(old.id).status, "superseded")

    def test_agent_cannot_mutate_policy_or_audit(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.store.write(MemoryRecord(MemoryKind.POLICY, self.scope_a, "Never email", [SOURCE], AGENT))
        with self.assertRaises(PermissionDenied):
            self.store.write(MemoryRecord(MemoryKind.AUDIT, self.scope_a, "forged", [], AGENT))
        self.store.write(self.fact("normal sourced fact"))
        self.assertTrue(self.store.audit_events(self.scope_a))

    def test_semantic_chunks_keep_answer_together_while_fixed_window_splits_it(self) -> None:
        text = ("# Rate limits\nGemini requests have a per-key limit. "
                "A second Gemini key provides separate quota for parallel workers.\n\n"
                "# Browser\nThe browser worker uses Playwright to inspect websites.")
        chunks = semantic_chunks(text, DeterministicEmbedder(256), similarity_threshold=0.05, max_words=40)
        rate_limit = next(chunk for chunk in chunks if chunk.heading == "Rate limits")
        self.assertIn("second Gemini key provides separate quota", rate_limit.text)
        fixed = fixed_word_chunks(text, words=6)
        self.assertFalse(any("second Gemini key provides separate quota" in chunk for chunk in fixed))
        # The retrieval half of the proof: the semantic index returns an
        # answerable unit, rather than a window that has cut the fact in two.
        for chunk in chunks:
            self.store.write(MemoryRecord(
                MemoryKind.DOCUMENT_CHUNK, self.scope_a, chunk.text,
                [SourceRef("file://gateway.md", "indexer")], AGENT,
                metadata={"heading": chunk.heading, "ordinal": chunk.ordinal,
                          "previous": chunk.previous_ordinal, "next": chunk.next_ordinal},
            ))
        hit = self.store.recall("Does a second Gemini key provide separate quota?", self.scope_a,
                                kinds=[MemoryKind.DOCUMENT_CHUNK], limit=1)[0]
        self.assertIn("second Gemini key provides separate quota", hit.text)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None: self.payload = payload
    def read(self) -> bytes: return self.payload
    def __enter__(self) -> _FakeResponse: return self
    def __exit__(self, *exc: object) -> bool: return False


class OllamaEmbedderContextTests(unittest.TestCase):
    """nomic-embed-text advertises a 2048 context but its runner aborts past 512
    tokens, and Ollama's own default truncation targets the advertised figure. An
    oversized document therefore killed the runner: the request answered 500, the
    legacy retry hit the same fault, and the node failed with a bare HTTPError.
    Every request must pin num_ctx so the server truncates where it can survive."""

    def capture(self, primary_fails: bool = False) -> list[dict]:
        sent: list[dict] = []
        payload = json.dumps({"embeddings": [[0.5, 0.5]], "embedding": [0.5, 0.5]}).encode()

        def fake_urlopen(request: object, timeout: int | None = None) -> _FakeResponse:
            sent.append(json.loads(request.data.decode()))  # type: ignore[attr-defined]
            if primary_fails and len(sent) == 1: raise OSError("primary endpoint unavailable")
            return _FakeResponse(payload)

        with mock.patch.object(embeddings_module, "urlopen", fake_urlopen):
            OllamaNomicEmbedder().embed_document("ownership prevents data races. " * 400)
        return sent

    def test_request_pins_context_to_the_runners_real_limit(self) -> None:
        self.assertEqual(self.capture()[0]["options"]["num_ctx"], 512)

    def test_legacy_retry_pins_the_same_limit(self) -> None:
        # The fallback exists for older installs, but it reaches the same runner:
        # retrying an unbounded payload there only repeats the abort.
        self.assertEqual(self.capture(primary_fails=True)[1]["options"]["num_ctx"], 512)


if __name__ == "__main__":
    unittest.main()
