---
name: commits-standards
description: When creating a commit, first add a brief summary on the AGENT_LOG.md of all of the implemented changes, then the commit message will be a 60 characters maximum and the commit description will describe all of the changes in a list.
---

## Overview

This skill enforces a consistent commit workflow for this repository. Every commit follows two steps:

1. **Log first** — append a summary of all changes to `AGENT_LOG.md` under a new `## AC:` section before touching `git`.
2. **Commit second** — write a subject line (≤ 60 characters) followed by a bullet-list description of every change.

The goal is a traceable history where `AGENT_LOG.md` maps each prompt or acceptance criterion to the exact code that implements it, and `git log` gives a concise summary of what changed.

---

## Step 1 — Update AGENT_LOG.md

Before running any `git` command, open `AGENT_LOG.md` and append a new section at the bottom:

```markdown
---

## AC: <short title that matches the acceptance criterion or prompt>

**Prompt:** "<exact or paraphrased user request>"

### Changes

| File | What changed |
|---|---|
| `src/task_manager/models/task.py` | Added `due_date` column |
| `src/task_manager/services/task_service.py` | Added `due_date` to `create` and `update` |
| `tests/test_services.py` | Added `test_create_with_due_date` |

### Result

One sentence describing the outcome (e.g. "80/80 tests passing").
```

Keep entries factual and terse. The table is the most important part — it lets a future reader jump straight to the relevant file.

---

## Step 2 — Write the commit

### Subject line rules

| Rule | Example |
|---|---|
| ≤ 60 characters | `feat: add due_date to tasks` ✓ |
| Imperative mood | `add`, not `added` or `adds` |
| Lowercase after prefix | `fix: correct elapsed accumulator` ✓ |
| Conventional prefix | `feat:` `fix:` `refactor:` `test:` `docs:` `chore:` |

### Description rules

- One bullet per logical change (not per file).
- Group related file edits under a single bullet.
- End with the test result line.
- Always add the `Co-Authored-By` trailer.

### Full example

```bash
git commit -m "$(cat <<'EOF'
feat: add due_date field to tasks

- Added due_date DateTime column to Task model and updated __init__
- Added due_date parameter to task_service.create and .update
- Exposed due_date in TaskCreate, TaskUpdate, TaskResponse schemas
- Added --due CLI option to `add` and `update` commands
- Updated test_services, test_api, test_cli with due_date assertions
- 82/82 tests passing

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### Prefix cheat-sheet

| Prefix | Use when |
|---|---|
| `feat:` | New user-visible behaviour |
| `fix:` | Bug correction |
| `refactor:` | Internal restructure with no behaviour change |
| `test:` | Adding or fixing tests only |
| `docs:` | README, AGENT_LOG, or docstring changes only |
| `chore:` | Tooling, CI, dependencies, `.gitignore` |

---

## What NOT to do

- Do not skip the AGENT_LOG update — it is part of the commit, not optional.
- Do not write `git add .` — stage files explicitly to avoid committing secrets or build artefacts.
- Do not amend a previous commit to add new work — create a new commit.
- Do not exceed 60 characters on the subject line; break long descriptions into the body.
