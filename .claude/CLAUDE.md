<!-- AGENT-HELPER-OMC-BRIDGE:START -->
<!--
  File: .claude/CLAUDE.md
  Purpose: OMC bridge layer — maps OMC global settings to project-local 4-role system
  Note: Root CLAUDE.md (roles/triggers/protocols) is NOT duplicated here.
        This file handles ONLY OMC behavior constraints and agent remapping.
-->

# OMC Bridge Layer (Project-Agnostic)

> This file injects project-level constraints into the Claude Code session
> on top of the OMC global CLAUDE.md configuration.
> Detailed rules live in `.claude/AGENT_SYSTEM.md`. This file handles remapping only.

---

## 1. OMC Agent Type to Project Role Remapping

OMC global CLAUDE.md `delegation_rules` are **overridden** by the project 4-role system:

| OMC Agent / subagent_type | Project Role | Model | Detail |
|---------------------------|-------------|-------|--------|
| `Explore`, explore, haiku lookups | **Scout** | Haiku | AGENT_SYSTEM.md Section 2-1 |
| `Plan`, planner, architect | **Architect** | Opus | Section 2-2 + Phase document obligation |
| `general-purpose`, executor | **Builder** | Sonnet | Section 2-3 + QA handoff obligation |
| `verifier`, code-reviewer, QA | **QA Lead** | Sonnet | Section 2-4 + `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` obligation |

**Gap-filling OMC agents (not covered by 4 roles):**

| OMC Agent | Project Use Case |
|-----------|-----------------|
| `debugger` | Build failures, repeated type errors |
| `tracer` | Error origin tracing in backend/services |
| `security-reviewer` | Deep security audit (supplements QA Lead) |
| `test-engineer` | Test strategy and e2e test planning |
| `document-specialist` | External SDK/framework documentation lookup |

Gap-filling agents MUST still pass through the **QA gate** (`python -m py_compile vllm_cli2.py && python -m py_compile core/*.py`) before completion.

---

## 2. OMC Tier-0 Skill QA Gate Enforcement

When `ralph` / `autopilot` / `ultrawork` / `ultraqa` or any OMC Tier-0 skill runs,
the OMC built-in verifier does **NOT replace** the project QA gate.

### Mandatory Steps Before Tier-0 Completion Declaration

```
Before any OMC skill declares "verified" / "completion":
  1. python -m py_compile vllm_cli2.py         <-- Build must succeed
  2. python -m py_compile vllm_cli2.py && python -m py_compile core/*.py            <-- No CRITICAL issues
  3. (If Phase documents changed) Wiki ingest
  4. git commit              --> pre-commit hook runs automatically
```

**If CRITICAL issues exist, completion declaration is BLOCKED** even if OMC verifier says "pass".

### ultrawork Parallelization Constraint

When `ultrawork` parallelizes tasks:
- ALLOWED: Independent Builder tasks running simultaneously
- FORBIDDEN: QA gate running in parallel -- QA MUST run serially after ALL Builder tasks complete

---

## 3. ralplan / autopilot Phase Document Obligation

When `ralplan` or `autopilot` executes:

```
ralplan plan generated --> .omc/plans/{plan}.md saved
                           |
                    [MANDATORY link]
                           |
                           v
Architect(Opus) creates docs/phases/phase-{N}/README.md
                           |
                           v
Phase document verified --> Builder may begin
```

- `.omc/plans/` plans are **input material** for Phase documents, NOT replacements
- `autopilot` Phase 0 `spec.md` generation does NOT satisfy the Phase document requirement
- **AGENT_SYSTEM.md Section 3-7: "No large structural changes without Phase document"** is immutable

---

## 4. Keyword Conflict Resolution

OMC hooks detect keywords at the global level before project rules apply.
The following table resolves conflicts between OMC default behavior and project roles:

| Input Keyword | OMC Default | Project Override |
|---------------|-------------|------------------|
| `review`, `code review` | code-review mode | **QA Lead** (`python -m py_compile vllm_cli2.py && python -m py_compile core/*.py`) takes priority, OMC code-review optional |
| `analyze` | analyze mode | **Scout(Haiku) then Architect(Opus)** sequence takes priority |
| `plan` (large scope) | omc-plan | ralplan allowed + **Phase document creation mandatory** |
| `search`, `find`, `status` | deepsearch/explore | **Scout(Haiku)** subagent takes priority, summary only returned |
| `test`, `tdd` | TDD mode | Integrate with `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` / `python -m py_compile vllm_cli2.py core/*.py` |
| `ultrathink` | OMC extended reasoning | No conflict, use as-is |
| `ralph`, `autopilot`, `ulw` | OMC Tier-0 execution | Execution allowed + **Section 2 QA gate additionally applied** |
| `wiki` | OMC wiki skill | **Project wiki commands** take priority (see Section 5) |
| `deepsearch` | OMC codebase search | **Scout(Haiku)** takes priority for large-scope exploration |

---

## 5. Wiki Namespace Separation

| Property | OMC Wiki | Project Wiki |
|----------|---------|-------------|
| Location | `.omc/wiki/` | `docs/wiki/` |
| Management | OMC wiki skill (automatic) | Project wiki scripts / manual |
| Purpose | OMC skill/agent operational knowledge | Project domain knowledge (Phases, ADR, patterns) |
| Priority | Lower | **Higher** (project context) |

**Rules:**
- Project domain knowledge (architecture decisions, component patterns, etc.) in `.omc/wiki/` is **forbidden**
- Bare `wiki` keyword --> check project wiki commands first
- `omc wiki` or `.omc wiki` explicitly --> use OMC wiki skill

---

## 6. Pre-Commit Hook Immutability

`.git/hooks/pre-commit` **CANNOT be modified or bypassed by any OMC skill**.

- `git commit --no-verify` is allowed ONLY for emergencies (hotfix, build environment failure)
- When used, commit message MUST include reason: `[no-verify: {reason}]`
- OMC `autopilot`/`ralph` auto-commit attempts run the hook normally
- No OMC skill may alter, remove, or disable the pre-commit hook

---

## 7. .omc/ Directory Policy

```
.omc/
+-- state/              <-- OMC session state (auto-managed, git-ignored)
+-- plans/              <-- ralplan output plans (Phase document input material, commit if needed)
+-- wiki/               <-- OMC operational knowledge (git-ignored, project domain forbidden)
+-- notepad.md          <-- OMC temp notes (ephemeral within session)
+-- notepads/           <-- OMC plan-specific notepads
+-- project-memory.json <-- OMC project memory
+-- logs/               <-- OMC execution logs
+-- research/           <-- OMC research artifacts
```

**Git tracking:**
- `.omc/state/`, `.omc/wiki/` --> `.gitignore`
- `.omc/plans/` --> commit when synced with Phase documents

---

## 8. Reference Documents

- `.claude/AGENT_SYSTEM.md` -- Complete role/workflow/QA gate rules
- `CLAUDE.md` (root) -- Project-specific role assignments, triggers, infrastructure
- `AGENTS.md` (root) -- Agent command mapping
- `docs/phases/` -- Phase documents (Architect output)
- `.omc/plans/` -- ralplan plans (Phase document input)

<!-- AGENT-HELPER-OMC-BRIDGE:END -->
