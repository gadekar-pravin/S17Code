---
paths:
  - "s17code/core/a2a/**/*"
---

# A2A interop

- **Never hand-edit `a2a_s13_pb2.py` or `a2a_s13_pb2_grpc.py`.** They are generated verbatim from
  `proto/a2a_s13.proto` and are ruff-excluded for that reason. Regenerate; don't patch.
- Agent Cards validate against the official Linux Foundation A2A SDK type via
  `ParseDict(card, AgentCard(), ignore_unknown_fields=False)`. Keep `ignore_unknown_fields=False` — it is
  what makes an unrecognised field an error rather than a silent drop. `name`, `description` and
  `version` are required.
- Card trust is a **detached JWS**, deliberately kept outside discovery and task execution: protected
  header and signature live in `card.signatures`, the canonicalised card is the payload. Don't fold
  trust checks into the discovery or task-execution path.
- `server.py` is a small local JSON-RPC/SSE server over a sqlite task db. `official.py` is the A2A 1.0
  protobuf adapter and graph-facing remote-task facade. `grpc_binding.py` mirrors the
  `lf.a2a.v1.A2AService` core task operations over real `grpc.aio` with `google.protobuf.Struct` keeping
  the local harness small. Swapping the local contract for the full official `a2a.proto` is an additive
  interoperability upgrade — not a graph or runtime redesign. Preserve that property.
- Tests live in `s17code/core/a2a/tests/` and are inside `testpaths`, so `pytest tests/` alone misses
  them. `test_hardening.py` carries a per-file `F401` ignore in `pyproject.toml`.

## Environment

All optional and unset by default: `S17_A2A_GRPC_ENABLED`, `S17_A2A_GRPC_PORT` (8114),
`S17_A2A_BEARER_TOKENS`, `S17_A2A_API_KEYS`, `S17_A2A_PRIVATE_KEY_FILE`, `S17_A2A_SIGNING_KID`,
`S17_A2A_TRUSTED_KEYS_DIR`, `S17_A2A_SELF_TRUST`, `S17_A2A_ALLOW_UNSIGNED`,
`S17_A2A_PUSH_SIGNING_SECRET`. None appear in `.env.example`.
