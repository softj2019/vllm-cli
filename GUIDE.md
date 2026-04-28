# vLLM CLI v2 — 사용 가이드

## 목차
1. [개요](#개요)
2. [빠른 시작](#빠른-시작)
3. [모드 전환 (OCR ↔ CLI)](#모드-전환)
4. [슬래시 명령 전체](#슬래시-명령-전체)
5. [AI 자연어 요청](#ai-자연어-요청)
6. [모델 다운로드](#모델-다운로드)
7. [환경 조사](#환경-조사)
8. [설정 파일](#설정-파일)
9. [서버 구성](#서버-구성)
10. [문제 해결](#문제-해결)

---

## 개요

폐쇄망 Ubuntu 서버에서 vLLM 서버와 통신하는 에이전트 CLI.
외부 라이브러리 없이 **Python stdlib만으로** 동작합니다.

| 기능 | 설명 |
|------|------|
| Tool Calling | AI가 자율적으로 파일·서버·시스템 도구 호출 |
| 슬래시 명령 | AI 없이 직접 실행 (`/file`, `/server`, `/sys` 등) |
| 모드 전환 | OCR 서버 ↔ CLI LLM 서버 Docker 컨테이너 교체 |
| 자동 탐색 | 로컬/서브넷 vLLM 서버 자동 발견 |

---

## 빠른 시작

```bash
# USB에서 바로 실행 (Ubuntu)
python3 /media/archiv/B3E8-304F/home/ai/cli/vllm_cli2.py

# 옵션
python3 vllm_cli2.py --no-discover        # 저장된 서버 즉시 사용
python3 vllm_cli2.py --host IP -p PORT   # 서버 직접 지정
python3 vllm_cli2.py --no-tools          # Tool Calling 비활성화
python3 vllm_cli2.py --subnet            # LAN 전체 탐색 (느림)
```

실행 시 서버 자동 탐색 → 서버 선택 → 모델 선택 → 대화 시작

---

## 모드 전환

서버에 OCR 전용 모델(`prov`)과 CLI LLM(Qwen 등) 두 가지 모드를 Docker로 관리합니다.

```
/switch status    현재 모드·컨테이너 상태 확인
/switch cli       OCR 서버 중지 → CLI LLM 서버 기동 (포트 8200)
/switch ocr       CLI LLM 중지 → OCR 서버 재시작 (포트 8100)
```

**전환 흐름 (`/switch cli`):**
```
[pro] 컨테이너 중지 (GPU 해방)
  ↓
[cli-llm] 컨테이너 기동 (Qwen2.5-7B, 포트 8200)
  ↓
CLI 자동 재연결 → Tool Calling 활성화
```

**설정 (`switch.json`):**
```json
{
  "current": "ocr",
  "ocr": { "container": "pro", "port": 8100, "model": "prov" },
  "cli": {
    "container": "cli-llm",
    "port": 8200,
    "model_path": "/home/archiv/dev/model/Qwen2.5-7B-Instruct",
    "tool_parser": "hermes",
    "gpu_device": "0"
  }
}
```

> GPU VRAM 여유가 2.9GB뿐이므로 두 모드 동시 운영 불가.
> `/switch` 는 GPU 자원을 교대로 사용합니다.

---

## 슬래시 명령 전체

CLI 내 `User >` 프롬프트에서 입력. AI를 거치지 않고 즉시 실행됩니다.

### /help — 도움말

```
/help              전체 명령 목록
/help file         파일 명령 상세
/help server       서버 명령 상세
/help switch       모드 전환 상세
/help sys          시스템 명령 상세
/help model        모델 다운로드 상세
```

### /switch — 모드 전환

```
/switch status     현재 모드·컨테이너 상태
/switch cli        CLI LLM 모드 전환 (Tool Calling 활성)
/switch ocr        OCR 모드 전환
```

### /file — 파일 조작

```
/file search <패턴> [경로]      파일명 패턴 검색
/file grep <키워드> [경로]      내용 키워드 검색
/file read <경로> [줄수]        파일 읽기
/file write <경로> <내용>       파일 쓰기 (덮어쓰기)
/file append <경로> <내용>      파일 끝에 추가
/file info <경로>               파일 상세 정보
/file delete <경로>             파일 삭제 (확인 프롬프트)
```

### /server — vLLM 서버 제어

```
/server status                  서버 상태·PID
/server start [모델경로] [--port N]   서버 시작
/server stop                    서버 중지
/server restart [모델경로] [--port N] 서버 재시작
/server logs [N]                로그 마지막 N줄 (기본 50)
/server models                  모델 목록
/server tool-info               Tool Calling 지원 여부 진단
/server find-vllm               vLLM 설치 경로 탐색 (Docker 포함)
```

포트 지정 예시:
```
/server start /home/archiv/dev/model/Qwen2.5-7B-Instruct --port 8200
```

### /sys — 시스템 정보

```
/sys                전체 시스템 정보
/sys gpu            nvidia-smi
/sys disk           df -h
/sys mem            free -h
/sys cpu            lscpu 요약
/sys net            네트워크 인터페이스·포트
/sys ps [키워드]    프로세스 목록
/sys check          환경 조사 (syscheck.py)
```

### /syscheck — 환경 조사 + 모델 추천

```
/syscheck           전체 리포트 (OS·CPU·RAM·GPU·CUDA·모델 추천)
/syscheck brief     요약만
/sc                 /syscheck 단축키
```

### /model — 모델 다운로드

```
/model              인터랙티브 다운로드 메뉴
/model list         다운로드 가능한 모델 목록
/model check        설치 상태 확인
/model Qwen/Qwen2.5-7B-Instruct   특정 모델 직접 지정
```

### /rescan — 서버 재탐색

```
/rescan             로컬 서버 재탐색 + 서버·모델 재선택
/rescan --subnet    서브넷 /24 포함 재탐색
```

### 기타

```
/clear              대화 이력 초기화
/notool             Tool Calling ON/OFF 토글
/q  /quit  /exit    종료
Ctrl+D              종료 (입력 이력 자동 저장)
Ctrl+C              현재 입력 취소 (루프 유지)
↑ / ↓              이전/다음 입력 이력 탐색
```

---

## AI 자연어 요청

Tool Calling 활성 상태(`tools=ON`)에서 자연어로 도구를 자율 호출합니다.

> **주의:** `prov` 같은 OCR 전용 모델은 tools=OFF. `/switch cli` 후 사용하세요.

### 파일시스템

```
/home/ai 아래 구조 트리로 2단계까지 보여줘
/var/log 에서 오늘 수정된 파일 찾아줘
500MB 이상 파일이 어디 있는지 찾아줘
core/config.py 의 MAX_TOOL_RESULT 를 5000으로 수정해줘
```

### 시스템·서버

```
CPU, 메모리, 디스크 상태 알려줘
GPU 상태 확인해줘
vLLM 서버 재시작해줘
서버 로그 마지막 100줄 보여줘
현재 열린 포트 목록 보여줘
```

### 프로세스·서비스·Cron

```
vllm 관련 프로세스 목록 보여줘
nginx 서비스 재시작해줘
매일 새벽 2시에 /home/ai/backup.sh 실행하도록 cron 등록해줘
vLLM을 systemd 서비스로 등록해줘
```

---

## 모델 다운로드

### 폐쇄망 절차

```
① 인터넷 환경 (Mac/PC) — USB에 다운로드
python3 model_download.py --model Qwen/Qwen2.5-7B-Instruct

② Ubuntu — USB 꽂고 CLI에서 실행
/model check        # 설치 상태 확인
```

### 권장 CLI LLM 모델

| VRAM | 모델 | 특징 |
|------|------|------|
| ~16GB | Qwen2.5-14B-Instruct | 최고 품질 |
| ~8GB | **Qwen2.5-7B-Instruct** | **권장 (Tool Calling 최적)** |
| ~4GB | Qwen2.5-3B-Instruct | 경량 |
| ~3GB | Qwen2.5-1.5B-Instruct | 최소 사양 |

---

## 환경 조사

```bash
# 단독 실행 (CLI 밖에서)
python3 syscheck.py           # 전체 리포트
python3 syscheck.py --brief   # 요약
python3 syscheck.py --json    # JSON 출력

# CLI 내에서
/syscheck
/sys gpu
```

현재 서버 환경 (2026-04-27 기준):
- OS: Ubuntu 24.04.4 LTS / 커널 6.17
- CPU: Intel i7-8700K (12코어)
- RAM: 31.3GB
- GPU: NVIDIA RTX 5090 — VRAM 31.8GB
- Docker: 29.3.0 / 실행 컨테이너: mask-ocr, front-ocr, api-ai, engine-ai, pro

---

## 설정 파일

| 파일 | 역할 |
|------|------|
| `config.json` | 마지막 서버·모델 자동 저장 |
| `switch.json` | OCR/CLI 모드 전환 설정 |
| `.env.local` | 환경 변수 (GitHub 토큰 등, git 제외) |
| `logs/vllm_cli.log` | 디버그 로그 (최대 5MB × 5개 회전) |

**`config.json` 예시:**
```json
{
  "host": "localhost",
  "port": 8100,
  "model": "prov",
  "known_servers": ["localhost:8100"]
}
```

---

## 서버 구성

### 현재 Docker 구성

| 컨테이너 | 포트 | 역할 | GPU |
|---------|------|------|-----|
| `pro` | 8100 | vLLM + ARCH OCR PRO (prov) | GPU 0 |
| `engine-ai` | 8000 | FastAPI + PaddleOCR | GPU 1 |
| `api-ai` | 8085 | Spring 백엔드 API | - |
| `front-ocr` | 3000 | 프론트엔드 | - |
| `mask-ocr` | 3001 | 마스킹 프론트 | - |
| `cli-llm` | 8200 | CLI Tool Calling LLM (신규) | GPU 0 |

네트워크: `arch-net` (external bridge)

### 포트 스캔 대상

localhost 기본 12개: `8000, 8001, 8080, 8090, 8100, 8200, 8300, 8500, 8888, 11434, 5000, 7860`

---

## 문제 해결

### Tool Calling이 안 됨 (tools=OFF)

```
원인: OCR 전용 모델(prov)은 Tool Calling 미지원
해결: /switch cli → Qwen 모델로 전환
```

### vLLM 모듈 없음 오류

```
ModuleNotFoundError: No module named 'vllm'

원인: 호스트 python3에 vllm 미설치 (Docker 컨테이너 내부에만 있음)
해결: /server start → Docker 컨테이너 자동 탐색·기동
     또는 /switch cli
```

### 서버 연결 실패

```
원인: 서버 미기동 또는 포트 불일치
해결:
  /rescan          서버 재탐색
  /server status   현재 서버 상태 확인
  /switch status   모드·컨테이너 상태 확인
```

### SSE 스트림 오류 (로그에 JSON 파싱 실패)

```
원인: 대용량 청크 경계에서 분할 (비치명적, 응답은 정상 수신)
해결: 무시 가능. 로그 레벨을 WARNING으로 유지
```

### 로그 확인

```bash
tail -f logs/vllm_cli.log          # 실시간
grep "ERROR\|CRITICAL" logs/vllm_cli.log  # 오류만
grep "tool 호출" logs/vllm_cli.log        # tool 호출 이력
```
