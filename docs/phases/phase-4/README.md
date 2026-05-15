# Phase 4 — Realtime Chat + OCR Tool Integration

## Objective

대화형 실시간 응답과 OCR 서버(`/home/archiv/ai/arch-ocr-*`) 툴 호출을 통합해 E2E 동작을 완성한다.

## Scope

- 스트리밍 응답(SSE/WebSocket 중 1개 표준화)
- OCR 툴 API 명세 정리 및 연결
- 세션/타임아웃/재시도 정책 수립

## Detailed Tasks

1. 게이트웨이 엔드포인트 정의(`/chat`, `/tools/ocr`)
2. OCR 호출 어댑터 구현(요청/응답 스키마 고정)
3. 대화 중 OCR 호출 시나리오 테스트
4. 타임아웃/재시도/서킷브레이커 정책 반영
5. 장애 시 사용자 메시지 규칙 정의

## Deliverables

- 통합 API 스펙 문서
- E2E 테스트 시나리오
- OCR tool-call 동작 로그

## Exit Criteria

- 실시간 채팅 + OCR 호출 10회 연속 성공
- OCR 지연 상황에서도 세션 hang 없음

## Risks

- OCR 처리시간 변동으로 인한 대화 지연
- 툴 응답 포맷 불일치

## Change Log

- 2026-05-15: phase 생성
