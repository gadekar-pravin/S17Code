---
paths:
  - "s17code/coding/**/*"
---

# The coding surface

The agent writes the thing that then executes. Every bound below is enforced in Python, before the
action — not requested in a system prompt. Do not relax one into a prompt instruction.

## guard.py — the agent may not edit the judge

`DEFAULT_PROTECTED` refuses `tests/**`, `test/**`, `**/tests/**`, `**/test_*.py`, `**/*_test.py`,
`conftest.py`, `**/conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `.github/**`
(override via `S17_PROTECTED_PATHS`). The test suite is a free deterministic judge and stays one only
while the agent cannot delete, skip, weaken, or catch its way past it.

Do **not** normalise paths with `lstrip("./")` — it strips the leading dot and lets `.github/...` escape
the guard. There is a comment saying so; keep it true.

## exec.py — four bounds

- **No shell, ever.** The command is an argv list. Nothing interprets `;`, `&&`, or backticks.
- **Allowlisted `argv[0]`** (`S17_ALLOWED_COMMANDS`). `python -c` is refused as an unbounded shell. Git
  is limited to a subcommand allowlist with `-c`, `upload-pack` and `receive-pack` refused.
- **Inside the workspace.** cwd is forced to the workspace and cannot be changed by the caller.
- **Bounded.** Wall-clock timeout (capped at 600 s), output capped at 20k chars — a suite printing a
  million lines otherwise eats the context that was supposed to hold the fix.

`S17_EXEC_CONTAINER=1` runs the same command in `docker run --network=none` (`S17_EXEC_IMAGE`). The
allowlist is the floor beneath that, not a replacement for it.

## edit.py — two preconditions

**Read before edit**, tracked per run by `EditLedger`; a *resumed* run must read again, by design. An
edit written from memory is how an agent silently reverts work it never saw.

**Anchors must be unique.** A repeated anchor is refused, forcing enough surrounding context to prove
the agent knows where it is — a comprehension check disguised as an argument requirement. Anchors rather
than unified diffs, deliberately: models are poor at line numbers and burn iterations on patch format.

## workspace.py / search.py / validate.py

Every path resolves inside the workspace root, symlinks included; anything landing outside is refused
before it is opened. The workspace is a git repo on purpose — rejection is `git reset`, not an apology,
and git stays outside the agent's reach.

`glob_files` answers "which files exist", `grep_code` answers "where does this text appear" with file and
line so the next step is a ranged read. Both cap their results.

The validator is a **separate run**: fresh context (never sees the build conversation), hostile brief
(find what is broken, not confirm it is fine), and **no edit capability**. A thing that can fix what it
grades will eventually grade what it can fix. It returns findings; the builder's graph decides what to
do about them.

## Environment

`S17_WORKSPACE` points at a scratch repo **outside this tree**. Unset, the entire `coding` capability
family is removed from the manifest rather than failing at call time.
