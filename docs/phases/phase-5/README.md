# Phase 5 — Quality Gate & Regression Suite

## Objective

기능 고도화 이후에도 안정적으로 배포 가능한 품질 게이트를 구축한다.

## Scope

- 정적 검사, 컴파일 검사, 회귀 테스트 표준화
- 리포트 산출 자동화
- 실패 기준/차단 기준 명문화

## Detailed Tasks

1. 필수 게이트 정의
2. OCR 회귀 샘플셋 구성(정답 라벨 포함)
3. smoke/integration/regression 분리
4. 결과 리포트 경로 표준화(`.agent/*.md`)
5. 릴리스 차단 조건 운영 문서화

## Required CLI

```bash
python3 -m py_compile vllm_cli2.py
python3 -m py_compile vllm_cli2.py core/*.py
```

## Deliverables

- 품질 게이트 체크리스트
- 회귀 리포트 템플릿
- 실패 triage 가이드

## Exit Criteria

- 모든 필수 게이트 green
- 회귀 실패 0 또는 예외 승인 기록

## Risks

- 테스트 데이터 편향
- 성능 저하가 기능 테스트에만 묻히는 문제

## Change Log

- 2026-05-15: phase 생성
