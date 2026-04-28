## Agent Mapping (Template)

This repository uses the 4-role multi-agent system defined in `.claude/AGENT_SYSTEM.md`.
Configure the commands below for your project's specific toolchain.

### 1) Dev Agent (Development Server)
- Project mapping:
  - `python vllm_cli2.py` -- start dev server
  - `python syscheck.py` -- check service status
- Skill mapping:
  - `dev-server-runner` -> prefer project commands above first.

### 2) Code Review / QA Agent
- Project mapping:
  - `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` -- run quality check
  - `python -m py_compile vllm_cli2.py core/*.py` -- run linter
  - `python -m py_compile vllm_cli2.py core/*.py` -- run tests
- Outputs:
  - `.agent/code-review-report.md`
  - `.agent/issue-tracker-report.md`
- Skill mapping:
  - `code-reviewer-agent` -> invoke `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` and review generated reports.

### 3) Build / Deploy Agent
- Project mapping:
  - `python -m py_compile vllm_cli2.py` -- production build
  - `rsync -av . user@target:/path/to/cli` -- deploy
- Skill mapping:
  - Use project deploy scripts directly.

---

## Execution Trigger Matrix

Use the matrix below whenever a task is received. Do not skip the mapped CLI step.

| Task Shape | Primary Worker | Required CLI | Expected Output |
|------------|---------------|-------------|-----------------|
| Explore current state | Scout / Explore | `python syscheck.py` | environment + blocker summary |
| Plan a feature / refactor | Architect / Plan | read `docs/phases/README.md` first | updated phase plan or checklist |
| Implement code | Builder | `python -m py_compile vllm_cli2.py` | code changes + green build |
| Review / QA | QA Lead | `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` | issue list / pass-fail |
| Deploy | Builder + QA gate | `python -m py_compile vllm_cli2.py`, `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py`, `rsync -av . user@target:/path/to/cli` | deployed + verified |

### Mandatory Phase Sync

- If work changes scope, architecture, or implementation order:
  - Update `docs/phases/README.md`
  - Update or create `docs/phases/phase-{N}/README.md`

---

## New Environment Bootstrap

Use this checklist when starting in a fresh environment:

1. **Git sync**
   - Work on `main` only.
   - `git pull origin main`
   - Confirm clean status: `git status --short --branch`

2. **Runtime checks**
   - Verify required runtimes are installed (Node, Python, Go, Rust, etc.)
   - Platform-specific notes:
     - Windows Git Bash: use `.cmd` suffixes if `.ps1` is blocked
     - WSL: ensure host networking if accessing local services

3. **Project validation**
   - Install dependencies
   - Run `python -m py_compile vllm_cli2.py`
   - Fix blocking errors immediately

4. **Agent checks**
   - Run `python syscheck.py` (if applicable)
   - Run `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py`
   - Verify `.git/hooks/pre-commit` exists and is executable

5. **Report format**
   - Output a status table: Git sync / Build / QA / Deploy readiness
   - Include changed files and remaining risks
