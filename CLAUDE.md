# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

`uv` only — never `pip`, never a bare `python`/`pytest`.

```bash
uv sync --locked --dev
uv run ruff check .
uv run pytest -q
uv run s17code serve          # uvicorn on 127.0.0.1:8113
```

CI (`.github/workflows/ci.yml`) runs those three checks and then three proof scripts. Run them before
claiming a change is green — they exercise the controller/policy/journal path that pytest does not:

```bash
uv run python proofs/p2_budget_holds.py --offline --task "summarise the attached notes" --budget 0.01
uv run python proofs/p3_denial_of_wallet.py --offline --task "keep refining the draft" --budget 0.01
uv run python proofs/p4_trace_export.py --offline --task "compare two options" --budget 0.01
```

`--task` and `--budget` are required. `--offline` swaps in a deterministic transport but keeps the real
controller, policy, ladder, journal and span export.

`testpaths = ["tests", "s17code/core"]` — tests live in **two** roots. `uv run pytest tests/` is not a
full run; it silently skips every `s17code/core/**/tests/` suite.

## Style

- **Never run `ruff format`.** The dense hand-formatting is deliberate. `uv run ruff check .` is the
  enforced gate; `uv run ruff check --fix <file>` is fine (it mainly sorts imports).
- Line length 110. Lint set pinned to `["E4", "E7", "E9", "F", "W", "I"]` — `I` means import sorting is
  enforced. `E701`/`E702` are ignored on purpose: one-line state transitions (`x, y = a, b; z += 1`) stay.
- `from __future__ import annotations` everywhere; annotate thoroughly. There is no mypy.

## Invariants

- **Config decides; Python only enforces.** No provider, model, price or threshold is named in Python —
  they live in `config/*.yaml`. This binds everywhere, not just in `s17code/economics/`.
- **No `if skill == "..."` branching outside `s17code/capabilities.py`.** Adding behaviour means declaring
  a `Capability` / `EvidenceProjection` / family, not a new branch at a call site.
- Fix the code, never the test. The coding surface refuses `tests/**`, `pyproject.toml`, `.github/**` and
  friends in `s17code/coding/guard.py`, before an edit is attempted.
- `.gitignore` entries `/runs/` and `/.s17/` are root-anchored on purpose so they don't swallow
  `proofs/runs/`. Keep the leading slash.

## Gotchas

- **Capabilities silently vanish when env vars are unset** (`s17code/runtime.py:391`): no
  `S17_SANDBOX_ROOT` removes the file/CSV/calendar capabilities, no `S17_WORKSPACE` removes the whole
  `coding` family, no `S17_SKILLS_DIR` removes `load_skill`. "The agent won't do X" is almost always a
  missing env var, not a model failure. `S17_SANDBOX_ROOT` must be an **absolute** path.
- **The control plane fails closed.** With `S17_CONTROL_TOKEN` unset, `POST /v1/agent/runs`, the resume
  route, `PUT /subscriptions/{id}` and `POST /events` return **503** — not 401, not anonymous access.
  `S17_COMPLETION_TOKEN` is a deliberately different token for job callbacks. Tests set both in
  `tests/conftest.py`; do not bypass the gates.
- Two external services are expected up locally: the **glc_v5 gateway** on `http://127.0.0.1:8111` (holds
  all provider keys — this repo holds none; `/readyz` 503s without it) and **Ollama** on `:11434`
  (`nomic-embed-text`, `phi4:latest`). Proofs and tests opt out via `DeterministicEmbedder` /
  `HeadingTopicSegmenter`.
- `S17_WORKSPACE` points at a **scratch repo outside this tree** — the agent's coding surface is not
  aimed at S17Code's own source.
- Trace export is off unless `S17_OTEL_EXPORTER_ENDPOINT` is set (the span tree is still built in memory).
  `S17_OTEL_CAPTURE_CONTENT` gates PII capture and defaults to off.
- `skills/` is **not** Claude Code skills — it is this project's own markdown-skill format loaded at
  runtime via `S17_SKILLS_DIR`. Skills are the least-trusted input in the system by design.

## Subsystem rules

`.claude/rules/` holds path-scoped detail that loads only when Claude opens a matching file:
`economics.md`, `coding-surface.md`, `a2a.md`, `ui.md`.

## Git

Branch and open a PR for every change; nothing lands on `main` directly. `origin` is a **public** repo.
Never commit real values for `S17_CHANNEL_BRIDGE_TOKEN`, `S17_CONTROL_TOKEN` or `S17_COMPLETION_TOKEN` —
`.env.example` holds placeholders only.
