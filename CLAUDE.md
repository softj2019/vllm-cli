# vllm-cli -- Claude Code Team Config

## Project Overview
- **Purpose**: 폐쇄망 Ubuntu 환경 vLLM 서버 통신 에이전트 CLI (Python stdlib only)
- **Tech Stack**: Python 3.x (stdlib only), vLLM
- **Repository**: local git (no remote)

## Coding Principles
See `skills/karpathy-guidelines/SKILL.md` for mandatory coding behavior guidelines (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution).

---

## Role Enforcement (HARD RULES)

> These rules apply without exception. When a trigger keyword is detected, the corresponding role's Agent MUST be invoked.

### Delegation Rules

| Task Type | Trigger Keywords | Required Handler | Violation |
|-----------|-----------------|------------------|-----------|
| Explore/Diagnose | check, find, search, status, why, where, how many | `Agent(subagent_type="Explore", model="haiku")` | Direct handling forbidden |
| Design/Plan | plan, design, analyze, **design review**, **architecture review**, scenario, strategy | `Agent(subagent_type="Plan", model="opus")` | Direct handling forbidden |
| Implement | build, implement, create, modify, fix, deploy, code, write | Direct (Sonnet) | -- |
| QA/Review | **code review**, quality, issue, QA, test, verify, audit, security | `Agent(subagent_type="general-purpose", model="sonnet")` or direct | -- |

### Builder (Sonnet) Direct Handling Scope

```
ALLOWED:
  - File read/write/modify (for implementation purposes)
  - Build/test command execution
  - git add/commit
  - Implementation when Phase document exists

FORBIDDEN (must delegate):
  - Directory structure exploration --> Scout/Haiku
  - Architecture decisions / implementation strategy --> Architect/Opus
  - Code quality assessment --> QA Lead/Sonnet
  - Phase plan creation --> Architect/Opus
```

### Role Invocation Patterns

```
Scout     --> Agent(subagent_type="Explore",         model="haiku")
Architect --> Agent(subagent_type="Plan",             model="opus")
QA Lead   --> Agent(subagent_type="general-purpose",  model="sonnet")
```

---

## Team Roles & Positioning

### Scout (Haiku) -- Exploration, Diagnosis, Status
**Trigger Keywords:** check, find, search, status, why, where, diagnose
**Responsibilities:**
- Project status checks
- File/directory structure exploration
- Error source identification
- Cache/artifact existence verification

### Architect (Opus) -- Design, Planning, Analysis
**Trigger Keywords:** plan, design, analyze, design review, architecture review, scenario, strategy
**Responsibilities:**
- Feature design and component architecture
- Phase document creation (`docs/phases/phase-{N}/README.md`)
- API design and data model planning
- Completion criteria definition

### Builder (Sonnet) -- Implementation, Build, Infrastructure
**Trigger Keywords:** build, implement, create, modify, fix, deploy, code, write
**Responsibilities:**
- Source code implementation based on Architect phase documents
- Build verification: `python -m py_compile vllm_cli2.py`
- Deployment execution
- Post-implementation QA handoff

### QA Lead (Sonnet) -- Quality Management, Issue Tracking
**Trigger Keywords:** review, quality, issue, QA, test, verify, audit
**Responsibilities:**
- Execute QA tool: `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py`
- Security issue detection
- Issue severity classification
- Phase completion verification

---

## Workflow Trigger Protocols

### 1. Explore/Status Request
- **Worker**: Scout (Haiku)
- **Commands**: `python syscheck.py`, `curl -s localhost:8100/health`
- **Output**: Status summary + file listing + blockers

### 2. Design/Plan Request
- **Worker**: Architect (Opus)
- **Prerequisite**: Scout results (if available)
- **Output**: Phase document (`docs/phases/phase-{N}/README.md`)

### 3. Implementation Request
- **Worker**: Builder (Sonnet, direct)
- **Prerequisite**: Architect phase document MUST exist
- **Commands**: `python -m py_compile vllm_cli2.py`, `python -m py_compile vllm_cli2.py core/*.py`
- **Post-step**: QA Lead review

### 4. QA/Review Request
- **Worker**: QA Lead (Sonnet)
- **Commands**: `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py`
- **Output**: Issue list + severity + fix recommendations

### 5. Deploy Request
1. `python -m py_compile vllm_cli2.py` -- verify success
2. `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` -- no CRITICAL issues
3. `python -m py_compile vllm_cli2.py core/*.py` -- all tests pass
4. If CRITICAL: **BLOCK** and report
5. Create PR or deploy via project-specific process

### 6. Phase Document Trigger
When new work scope is not covered by an existing Phase document:
1. Create `docs/phases/phase-{N}/README.md`
2. Update `docs/phases/README.md` index
3. Specify completion criteria, risks, owner role
4. Update status: `PLANNED --> IN_PROGRESS --> COMPLETE`

### Prohibitions
- No implementation without Phase document (for non-trivial changes)
- No completion without QA review
- No Phase document gaps for large features

---

## Document Structure

### Single Source of Truth

| Document Type | Location | Rule |
|---------------|----------|------|
| Phase plans | `docs/phases/phase-{N}/README.md` | One phase, one location |
| Phase index | `docs/phases/README.md` | Single master index |
| Tech debt | `docs/issues/TECH_DEBT_DASHBOARD.md` | QA Lead owned |
| ADR | `docs/decisions/ADR-*.md` | Immutable after acceptance |

### Phase Document Required Header

```markdown
# Phase {N}: {Title}
**Status**: PLANNED | IN_PROGRESS | COMPLETE
**Created**: YYYY-MM-DD
**Owner**: Role(Model)
**Priority**: P0 | P1 | P2 | P3
```

---

## Infrastructure

### Commands

| Purpose | Command |
|---------|---------|
| Build | `python -m py_compile vllm_cli2.py` |
| Dev server | `python vllm_cli2.py` |
| Test | `python -m py_compile vllm_cli2.py core/*.py` |
| QA check | `python -m py_compile vllm_cli2.py && python -m py_compile core/*.py` |
| Lint | `python -m py_compile vllm_cli2.py core/*.py` |
| Deploy | `rsync -av . user@target:/path/to/cli` |

### Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Development (all work here) |
| `main` | Production (PR merge only) |

### Ports

| Service | Port |
|---------|------|
| Dev server | `8100` |
| vLLM Server | `8100` |

### External Services

| Service | Details |
|---------|---------|
| vLLM API | localhost:8100 |

---

## User Collaboration Patterns
- Proceed without asking, report results only
- Terse responses, no unnecessary explanations
- Fix errors immediately, report what was fixed
- Commit messages follow project convention (e.g., `feat:`, `fix:`, `refactor:`)

---

## Wiki System

### Three-Layer Knowledge Architecture
```
Schema  --> CLAUDE.md + AGENT_SYSTEM.md    (rules/roles/protocols)
Wiki    --> docs/wiki/                      (structured project knowledge)
Raw     --> docs/phases/, .agent/, caches   (source data)
```

### Wiki Triggers
| Condition | Action |
|-----------|--------|
| Phase doc created/modified | `echo "no wiki system"` |
| New architecture decision | Create ADR, then ingest |
| Before deployment | `echo "no wiki system"` (zero errors required) |

---

## System Reference Documents

> 작업 전 반드시 숙지. 에이전트는 아래 문서를 권위 있는 지침으로 취급한다.

| 문서 | 위치 | 내용 |
|------|------|------|
| **기능 개요** | `docs/FUNCTIONAL_OVERVIEW.md` | 전체 아키텍처, 컴포넌트 카탈로그, 토큰 절감 전략 |
| **운영 매뉴얼** | `docs/OPERATIONS_MANUAL.md` | 일상 작업 프로토콜, QA Gate, 금지 사항(H-01~H-10) |
| **4-Role 규칙** | `.claude/AGENT_SYSTEM.md` | 역할 정의, 트리거, 워크플로우 전체 |
| **OMC 브릿지** | `.claude/CLAUDE.md` | OMC-프로젝트 역할 매핑, Tier-0 QA 게이트 |
| **모노레포 규칙** | `shared/rules/monorepo/` | 구조, 경계, Turborepo 설정, 토큰 격리 |
| **팀 분장표** | `docs/TEAM_BREAKDOWN.md` | 스킬/에이전트/역할별 업무 매트릭스 |

### 운영 HARD RULES (요약)

| # | 금지 | 이유 |
|---|------|------|
| H-01 | Opus로 탐색 | 50배 비용 |
| H-02 | Phase 문서 없이 대규모 구현 | 아키텍처 통제 불가 |
| H-03 | QA Gate 없이 완료 선언 | 품질 보장 불가 |
| H-04 | Builder+QA 병렬 실행 | QA는 전체 완료 후 직렬 |
| H-05 | pre-commit --no-verify | 긴급 외 절대 금지 |
| H-07 | apps/* 간 직접 의존 | 모노레포 경계 파괴 |
| H-09 | GateGuard 비활성화 | 환각 방지 파괴 |
| H-10 | offset/limit 없이 전체 Read | 불필요 토큰 소비 |

전체 규칙: `docs/OPERATIONS_MANUAL.md` Section 7


---

# Karpathy LLM Coding Guidelines

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
