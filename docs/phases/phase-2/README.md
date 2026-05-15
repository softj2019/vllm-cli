# Phase 2 — Offline Binary & Model Intake Validation

## Objective

폐쇄망 환경에서 LocalAI 바이너리, 백엔드 아티팩트, 모델 파일을 반입하고 `압축 해제 후 즉시 실행`을 실제로 검증한다.

## Scope

- `runtime/bin/local-ai` 실바이너리 반입
- `runtime/models/*.gguf` 반입
- `runtime/backends/*` 반입(필요 시)
- `scripts/bundle-verify.sh`, `scripts/run.sh`, `scripts/healthcheck.sh` 실제 실행

## Detailed Tasks

1. 반입 체크리스트 작성 및 해시 검증
2. 파일 권한 정리(`chmod +x runtime/bin/local-ai`)
3. `configs/localai/models.yaml` 파일명 매핑 정합성 확인
4. 부팅/헬스체크/중지 시나리오 검증
5. 실패 케이스(모델 누락/권한 오류) 재현 및 대응 절차 기록

## Deliverables

- intake 검증 로그
- 수정된 `models.yaml` 최종본
- 장애 대응 메모(known issues)

## Exit Criteria

- `./scripts/run.sh` 성공
- `./scripts/healthcheck.sh` 성공
- `./scripts/stop.sh` 정상 종료

## Risks

- LocalAI 릴리스와 backend 아티팩트 버전 미스매치
- 모델 파일명 오타/경로 불일치

## Change Log

- 2026-05-15: phase 생성
