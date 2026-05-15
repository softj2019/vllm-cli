# LocalAI Offline Monorepo (Air-gapped)

폐쇄망 환경에서 `압축 해제 -> 즉시 실행`을 목표로 한 LocalAI 운영 템플릿입니다.

## 1) 디렉토리 구조

- `runtime/bin/local-ai`: LocalAI 실행 바이너리 (사전 반입)
- `runtime/models/`: GGUF/모델 파일 저장소
- `runtime/backends/`: LocalAI backend asset 저장소
- `configs/localai/models.yaml`: 모델 매핑
- `scripts/run.sh`: 백그라운드 실행
- `scripts/stop.sh`: 종료
- `scripts/healthcheck.sh`: 헬스체크
- `scripts/bundle-create.sh`: 오프라인 배포 번들 생성
- `scripts/bundle-verify.sh`: 번들 무결성 점검

## 2) 최초 준비

```bash
cd localai-monorepo
cp .env.example .env
```

필수 반입:

1. `runtime/bin/local-ai` (Linux 실행 바이너리)
2. `runtime/models/*.gguf` (사용 모델)
3. `runtime/backends/*` (필요 시)

```bash
chmod +x runtime/bin/local-ai
```

## 3) 실행

```bash
./scripts/run.sh
./scripts/healthcheck.sh
```

정상 시 `http://127.0.0.1:8080/v1/models` 응답.

## 4) 중지

```bash
./scripts/stop.sh
```

## 5) 오프라인 번들 생성

```bash
./scripts/bundle-create.sh
```

생성물: `artifacts/localai-offline-bundle-<timestamp>.tar.gz`

대상 서버에서:

```bash
tar -xzf localai-offline-bundle-<timestamp>.tar.gz
cd localai-monorepo
cp .env.example .env
./scripts/bundle-verify.sh
./scripts/run.sh
```

## 6) GPU 호환 운영 팁 (A40/3090/4090/5090)

- 모델은 먼저 7B~8B 양자화(Q4_K_M)로 표준화
- 카드별 차이는 `.env`의 thread/context 값으로 미세 조정
- 장애 대비로 경량 모델 1개(`ocr-chat-fast`)를 항상 유지
