# agents/ — the coordination board

_Structure adapted from Yaseen Abdelal's AgroTwin repo. AI-generated (Claude) under human review._

| File | Purpose | Who writes |
|---|---|---|
| `STATUS.md` | one-screen snapshot: version, what works, what's blocked | lead, after each session |
| `TASKS.md` | the task board (ID, owner, priority, status) | lead; agents update their own rows |
| `DECISIONS.md` | append-only log of decisions that change scope, data or method | whoever decides, with the reason |
| `MESSAGES.md` | requests across ownership lines, blockers, handoffs | anyone; newest at the bottom |

Status words: `TODO` · `IN_PROGRESS` · `REVIEW` (built, waiting for a human check) · `DONE` (command green) · `CUT`.
One `IN_PROGRESS` task per agent. P0 before P1.
