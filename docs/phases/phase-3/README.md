# Phase 3 — Multi-GPU Runtime Profile (A40/3090/4090/5090)

## Objective

A40/3090/4090/5090 환경에서 동일 모노레포를 사용해 안정적으로 기동되는 GPU 프로파일 세트를 확정한다.

## Scope

- GPU별 `.env` 프로파일 정의
- thread/context/batch 파라미터 튜닝
- 최소 성능 지표(첫 토큰 지연/토큰 처리량) 계측

## Detailed Tasks

1. `configs/profiles/`에 GPU별 예시 파일 생성
2. 공통 모델(7B/8B) 기준 부팅 성공 여부 검증
3. 각 GPU에서 지연/메모리 사용량 수집
4. 안전 기본값(default)과 고성능(profile-high) 분리
5. 장애시 fallback 모델 자동 전환 절차 정의

## Deliverables

- GPU별 프로파일 문서
- 벤치마크 결과 표
- 운영 기본 프로파일 1종 확정

## Exit Criteria

- 4개 GPU 모두 부팅 성공
- 과메모리(OOM) 없이 30분 soak test 통과

## Risks

- 드라이버/CUDA 조합 차이로 인한 편차
- 동일 파라미터의 카드별 안정성 불일치

## Change Log

- 2026-05-15: phase 생성
