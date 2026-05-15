# Phase 6 — Air-Gap Release Packaging & Rollback

## Objective

폐쇄망 배포 산출물과 롤백 절차를 표준화하여 운영 리스크를 낮춘다.

## Scope

- 번들 생성/검증/배포 리허설
- 버전 태깅 규칙
- 롤백 패키지 유지 전략

## Detailed Tasks

1. `scripts/bundle-create.sh` 산출물 버전명 규칙 확정
2. 배포 전 무결성 검증(sha256)
3. 대상 서버 압축해제/기동 리허설
4. 이전 버전 복구 절차 테스트
5. 배포 체크리스트 최종화

## Deliverables

- 릴리스 패키지 샘플
- 롤백 런북
- 배포 검증 로그

## Exit Criteria

- 신규 배포 성공 + 롤백 성공 각각 1회 이상

## Risks

- 번들 누락 파일
- 운영 서버 경로/권한 차이

## Change Log

- 2026-05-15: phase 생성
