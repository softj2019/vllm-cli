# Phase 1 — LocalAI Air-Gap Monorepo Bootstrap

## Goal

폐쇄망에서 압축 해제 후 즉시 실행 가능한 LocalAI 기반 모노레포 운영 템플릿 구축.

## Deliverables

1. `localai-monorepo/` 디렉토리 구조 생성
2. 실행/중지/헬스체크 스크립트
3. 오프라인 번들 생성/검증 스크립트
4. 모델 레지스트리 샘플(`configs/localai/models.yaml`)
5. 운영 README

## Status

- [x] 구조 생성
- [x] 실행 스크립트
- [x] 번들 스크립트
- [x] 문서화
- [ ] 실서버 바이너리 반입 검증

## Risks

- LocalAI 바이너리/백엔드 아티팩트 버전 불일치 가능성
- 모델 파일명과 `models.yaml` 매핑 불일치 가능성
