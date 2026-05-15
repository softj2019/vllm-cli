# Phase Index — vllm-cli / LocalAI Air-Gap

| Phase | Title | Status | Owner | Gate |
|-------|-------|--------|-------|------|
| 1 | LocalAI Air-Gap Monorepo Bootstrap | Completed | Builder | 템플릿/스크립트 구성 완료 |
| 2 | Offline Binary & Model Intake Validation | Pending | Builder | 바이너리+모델 실기동 성공 |
| 3 | Multi-GPU Runtime Profile (A40/3090/4090/5090) | Pending | Builder | GPU별 프로파일 검증 |
| 4 | Realtime Chat + OCR Tool Integration | Pending | Builder | 실시간 대화 + OCR 툴콜 E2E |
| 5 | Quality Gate & Regression Suite | Pending | QA Lead | 품질게이트 green |
| 6 | Air-Gap Release Packaging & Rollback | Pending | Builder + QA | 배포/롤백 리허설 완료 |
| 7 | Ops Runbook & Handover | Pending | Architect + Ops | 운영 인수인계 완료 |

## Execution Rule

- 각 Phase는 완료 전 다음 Phase로 승격하지 않는다.
- Scope/architecture 변경 시 해당 phase README의 `Change Log`를 먼저 갱신한다.
