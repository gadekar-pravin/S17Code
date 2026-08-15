---
paths:
  - "s17code/economics/**/*"
  - "config/*.yaml"
---

# Economics: config decides, Python enforces

`config/tiers.yaml` (capability ladder + role→tier map), `config/pricing.yaml` (per-model prices) and
`config/budgets.yaml` (allowances and every policy threshold) own all of it. The directory resolves from
`S17_CONFIG_DIR` when set, else `config/` beside the package.

**Nothing in `s17code` may name a provider, a model, a price or a threshold.** Adding a model, tier, role
or budget must be a YAML edit with no Python change. If a change tempts you to write `"gemini-..."` or
`0.002` into Python, it belongs in config.

## Structural invariants — do not weaken these into prompt instructions

- **No unmetered spend.** `BudgetedGateway` (`controller.py`) is the only object holding the transport,
  and it charges the run budget from the response's real token counts *before* returning. Never add a
  second path to the transport.
- **No run exceeds its ceiling.** `BudgetPolicy.decide` is consulted *before* the transport is touched.
  A refusal raises `BudgetRefused`, which surfaces as an ordinary failed graph node — visible in the
  journal, never swallowed.
- `RunBudget.charge` is the only writer to the ledger; `RunBudget.charges` is the whole audit trail.
- `BudgetPolicy.decide` is pure with respect to the budget: it reads state, it never spends. Keep it
  deterministic. A soft "please stay under $X" prompt does not hold — models are token-elastic, which is
  the exact failure this module exists to prevent.
- An unlisted model falls back to `pricing.yaml`'s own `default` row. An unknown model must never be
  silently free.
- Attribution rides a `ContextVar` set per graph node, so every worker keeps the signature
  `llm(prompt, system)`. Do not thread a budget parameter through skill signatures.

## The four policy outcomes are all load-bearing

`proceed` (tier fits the node's allowance) · `downgrade` (cheaper rung, graph keeps its shape) ·
`branch` (no rung fits the node's *allocation* but the run still has room — re-plan and re-allocate the
frontier) · `refuse` (nothing fits; the node fails as a visible outcome, nothing is truncated).

A node declares a **tier**, never a model; `tiers.yaml` maps the tier name to gateway request fields.
Downgrading is one step toward the head of the configured `order`. A slice of the allowance is held back
(`reserve_fraction`) so the terminal answering node is never starved by its own upstream research.
