---
paths:
  - "s17code/ui/**/*"
---

# A2UI surfaces

**The component catalog is closed on purpose.** A surface may reference only the component types in
`catalog.py`, and each component only the properties its schema allows. There is no `RawHtml` type and
no free-form property, because a type or property that does not exist cannot be named by a hostile
agent. Adding an escape hatch defeats the entire layer.

23 types: the 15 A2UI Basic layout / text / input / container types adopted under their real A2UI names
(`source="a2ui-basic"`), plus clearly labelled custom extensions (`source="custom"`) for the components
A2UI Basic genuinely lacks — charts, tiles, tables, timelines, notices, and the approval card.

Property kinds: `text` (literal, never markup) · `binding` (a `/json/pointer` into the data model) ·
`enum` · `ref` (child ids) · `action` (named action + bound args — the only way a surface acts) ·
`number`.

## The three invariants in validator.py

1. **Catalog** — every component `type` is in the catalog.
2. **Data-not-code** — no property smuggles markup, a handler, or a URL.
3. **Event** — every action name is registered.

Rejections must stay specific (naming component, field, and invariant) and must drop only the offending
components, so one poisoned node cannot blank the screen. Every surface passes `validate_surface` before
it is served — including surfaces this package builds itself in `surface.py`, not just untrusted agent
output. Don't add a trusted bypass.

## Structure and data travel apart

The builder never emits markup. It emits a flat adjacency list of components linked by id with one
`root`, plus a `dataModel` the components bind into. A pointer the model invents resolves to nothing, and
no value a surface displays can ever be executed. `compose.py` decides which components to offer the
model and which pointers exist to bind them to; the model chooses structure, the harness owns the data.

## HITL: approval is bound to final parameters

A high-impact action parks its node in `waiting` recording the exact parameters it intends to run, and
the ApprovalCard binds to those parameters. On resume, the client's args are compared against the parked
params; a widened or altered set is refused and the node stays waiting. A person who approved one action
cannot be made to authorise another. This comparison is the safety — do not loosen it.

## AG-UI

`agui.py` translates the journal that already exists (`{sequence, kind, node_id, payload}`) into AG-UI's
SCREAMING_SNAKE_CASE vocabulary. Do not invent stream events. `RUN_FINISHED` is derived from the snapshot
after the last event because "finished" is a run flag rather than a journal event — emitting exactly what
the graph recorded plus one clearly derived terminal event is the honest mapping.

`S17_SURFACE_MAX_TOKENS` defaults to 4000. Static clients live in `s17code/ui/client/`
(`index.html`, `console.html`, `app.html`) — there is no build step.
