# vLLM CLI v2

폐쇄망 Ubuntu 환경에서 vLLM 서버와 통신하는 에이전트 CLI.  
파일시스템 전체 조작 · 서버/프로세스/서비스/cron/데몬 제어 · Tool Calling 지원.  
**외부 라이브러리 불필요 — Python stdlib only.**

---

## 프로젝트 구조

```
cli/
├── vllm_cli2.py          메인 실행 파일 (엔트리포인트)
├── syscheck.py           환경 조사 + vLLM 모델 추천 (단독 실행 가능)
├── vllm_install.py       오프라인 패키지 관리자
├── vllm_cli.py           구버전 채팅 전용 CLI (참고용)
├── config.json           마지막 서버/모델 선택 자동 저장
├── README.md             이 문서
├── logs/
│   ├── vllm_cli.log      디버그 로그 (자동 생성, 최대 5MB × 5개 회전)
│   └── out.txt           직접 실행 출력 캡처 (선택적)
├── core/
│   ├── __init__.py       vendor/packages 자동 경로 등록
│   ├── config.py         설정 상수 + 전체 Tool 정의 + 시스템 프롬프트
│   ├── logger.py         중앙 로거 (RotatingFileHandler + /tmp 폴백)
│   ├── discovery.py      서버 자동 탐색 + 인터랙티브 선택
│   ├── model_detect.py   모델 계열 감지 + tool-call-parser 매핑
│   ├── client.py         HTTP 스트리밍 + Tool Calling + ToolExecutor
│   ├── files.py          파일/디렉토리 전체 조작
│   ├── server.py         vLLM 프로세스 제어
│   └── system.py         시스템·네트워크·프로세스·서비스·cron·데몬
└── vendor/
    ├── wheels/           pip download 결과 (인터넷 환경에서 준비)
    └── packages/         pip install --target 결과 (USB → Ubuntu 설치)
```

---

## 빠른 시작

```bash
# Ubuntu — USB 꽂고 바로 실행 (추가 설치 없음)
python3 /media/archiv/B3E8-304F/home/ai/cli/vllm_cli2.py
```

실행 시 서버를 자동 탐색하고 선택 메뉴가 나타납니다.

```
┌─ vLLM 서버 탐색 ──────────────────────────────┐
  localhost 스캔 (12개 포트) .......  1개 발견
└───────────────────────────────────────────────┘

발견된 서버 1개:
────────────────────────────────────────────────
  [1] localhost:8100     12ms   prov  ← 이전
  [0] 직접 입력
서버 선택 [0-1] (Enter=1):

모델 선택:
  [1] prov  ← 이전
  [0] 직접 입력
모델 선택 [0-1] (Enter=1):

  모델: prov (ARCH OCR PRO) | OCR 전용 모델 → tools=OFF (정상)

━━━ vLLM CLI v2  localhost:8100  model=prov  tools=OFF ━━━
  로그: /media/archiv/B3E8-304F/home/ai/cli/logs/vllm_cli.log
  ↑↓ 이력 탐색 활성화
/file /server /sys /syscheck /rescan /clear /notool /q  (Ctrl+D 종료)

User >
```

---

## 실행 옵션

```bash
python3 vllm_cli2.py [옵션]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `-m, --model MODEL` | 저장값 | 모델명 직접 지정 |
| `--host IP` | 저장값 | 서버 IP 직접 지정 |
| `-p, --port PORT` | 저장값 | 서버 포트 직접 지정 |
| `--no-discover` | — | 탐색 생략, 저장된 값 즉시 사용 |
| `--subnet` | — | 서브넷 /24 까지 탐색 (느림, LAN 전체) |
| `--no-tools` | — | Tool Calling 비활성화 (순수 채팅) |
| `--temp FLOAT` | 0.7 | temperature |
| `--server-status` | — | 서버 상태만 출력 후 종료 |
| `--server-models` | — | 모델 목록만 출력 후 종료 |
| `--server-logs N` | — | 로그 N줄 출력 후 종료 |
| `--file-search PAT` | — | 파일명 패턴 검색 후 종료 |
| `--file-read PATH` | — | 파일 읽기 후 종료 |

---

## 슬래시 명령

대화 중 직접 실행하는 명령어. AI를 거치지 않고 즉시 동작합니다.

### /file — 파일 조작

```
/file search <패턴> [경로]      파일명 패턴 검색     예) /file search *.log /var
/file grep <키워드> [경로]      내용 키워드 검색     예) /file grep ERROR /var/log
/file read <경로> [줄수]        파일 읽기            예) /file read /etc/hosts 50
/file write <경로> <내용>       파일 쓰기 (덮어쓰기)
/file append <경로> <내용>      파일 끝에 내용 추가
/file info <경로>               파일/디렉토리 상세 정보
/file delete <경로>             파일 삭제 (확인 프롬프트)
```

### /server — vLLM 서버

```
/server status                  서버 상태 + PID 확인
/server start [모델경로]        vLLM 서버 시작
/server stop                    vLLM 서버 중지 (SIGTERM)
/server restart                 서버 재시작
/server logs [N]                로그 마지막 N줄 (기본 50)
/server models                  사용 가능 모델 목록
/server tool-info               Tool Calling 지원 여부 진단 + 재시작 명령 제안
/server find-vllm               vLLM 설치 경로 탐색 (가상환경·Docker 포함)
```

### /sys — 서버 사양 조회

```
/sys                            전체 시스템 정보 (CPU·RAM·디스크·OS)
/sys check                      환경 조사 + vLLM 모델 추천 (syscheck.py 실행)
/sys gpu                        nvidia-smi 출력
/sys disk                       df -h 출력
/sys mem                        free -h 출력
/sys cpu                        lscpu 요약
/sys net                        네트워크 인터페이스·포트·라우팅 상세
/sys ps [키워드]                프로세스 목록 (키워드 필터)
```

### /syscheck — 환경 조사 + 모델 추천

```
/syscheck                       전체 리포트 (OS·CPU·RAM·GPU·CUDA·Python·모델 추천)
/syscheck brief                 요약만 출력
/sc                             /syscheck 단축키
```

`syscheck.py` 는 단독 실행도 가능합니다:

```bash
python3 syscheck.py             전체 리포트
python3 syscheck.py --brief     요약
python3 syscheck.py --json      JSON 출력 (스크립트 연동)
```

### 기타

```
/rescan                         서버 재탐색 + 서버/모델 재선택
/rescan --subnet                서브넷 /24 포함 재탐색
/clear                          대화 이력 초기화
/notool                         Tool Calling ON/OFF 토글
/q  /quit  /exit                종료
Ctrl+D                          종료 (입력 이력 자동 저장)
Ctrl+C                          현재 입력 취소 (루프 유지)
↑ / ↓                           이전/다음 입력 이력 탐색
```

---

## AI 자연어 요청 예시 (Tool Calling)

AI가 대화 내용을 분석해 아래 도구를 자율 호출합니다.

> **주의:** Tool Calling은 범용 LLM(Qwen2.5-Instruct, Llama-3.1-Instruct 등)에서만 동작합니다.  
> OCR 전용 모델(`prov`, `ARCH_OCR_PRO` 등)은 tools=OFF 로 자동 전환됩니다.

### 파일시스템 탐색

```
User > /home/ai 아래 구조 트리로 2단계까지 보여줘
User > /var/log 에서 오늘 수정된 파일 찾아줘
User > 500MB 이상 파일이 어디 있는지 찾아줘
User > .py 파일 중 "import torch" 포함된 것 모두 찾아줘
```

### 파일 읽기 / 수정 / 치환

```
User > /etc/nginx/nginx.conf 내용 보여줘
User > core/config.py 의 MAX_TOOL_RESULT 를 5000으로 수정해줘
User > vllm_cli2.py 에서 PORT=8100 을 PORT=8200 으로 전부 바꿔줘
User > /tmp/result.txt 에 현재 시간 써줘
```

### 디렉토리 / 권한 / 소유자

```
User > /data/models 디렉토리 만들어줘
User > script.sh 에 실행 권한 줘
User > /home/ai/cli 전체 소유자를 ubuntu:ubuntu 로 바꿔줘
User > /data 아래 모든 파일 권한 644 로 바꿔줘
```

### vLLM 서버 제어

```
User > 현재 vLLM 서버 상태 확인해줘
User > 사용 가능한 모델 목록 보여줘
User > vLLM 서버 재시작해줘
User > 서버 로그 마지막 100줄 보여줘
User > /data/models/llama3 모델로 서버 시작해줘
```

### 시스템 정보

```
User > CPU, 메모리, 디스크 상태 알려줘
User > 메모리 얼마나 남았어?
User > 시스템 업타임과 OS 버전 알려줘
User > GPU 상태 확인해줘    (→ nvidia-smi 자동 실행)
```

### 네트워크 환경

```
User > 현재 IP 주소와 인터페이스 목록 보여줘
User > 열린 포트 목록 보여줘
User > 라우팅 테이블 확인해줘
User > DNS 설정 어떻게 돼있어?
User > 현재 활성 TCP 연결 보여줘
```

### 프로세스 제어

```
User > vllm 관련 프로세스 목록 보여줘
User > CPU 많이 쓰는 프로세스 상위 10개 보여줘
User > PID 1234 가 어떤 프로세스인지 알려줘
User > PID 1234 종료해줘
User > python 프로세스 중 메모리 가장 많이 쓰는 것 종료해줘
```

### 서비스 관리 (systemctl)

```
User > 현재 실행 중인 서비스 목록 보여줘
User > nginx 서비스 상태 확인해줘
User > ssh 서비스 재시작해줘
User > vllm 서비스 부팅 시 자동 시작 설정해줘
```

### Cron 스케줄

```
User > 현재 crontab 목록 보여줘
User > 매일 새벽 2시에 /home/ai/backup.sh 실행하도록 cron 등록해줘
User > 서버 부팅 시 /home/ai/start.sh 자동 실행 등록해줘  (@reboot)
User > backup 관련 cron 항목 삭제해줘
```

### 데몬 등록 (systemd)

```
User > vLLM을 systemd 서비스로 등록하고 자동 시작 설정해줘
User > 등록된 systemd 서비스 목록 보여줘
```

데몬 등록 예시 — AI가 자동 생성하는 unit 파일:
```ini
[Unit]
Description=vLLM OpenAI API Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=python3 -m vllm.entrypoints.openai.api_server --model /data/models/llama3
Restart=on-failure
RestartSec=5
Environment=CUDA_VISIBLE_DEVICES=0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 쉘 명령 직접 실행

```
User > nvidia-smi 실행해줘
User > pip show vllm 결과 알려줘
User > df -h && free -h 실행해줘
User > journalctl -u vllm -n 50 보여줘
User > which python3 && python3 --version
```

> **안전장치:** `rm -rf`, `mkfs`, `dd if`, fork bomb 등 파괴적 패턴은 자동 차단됩니다.

---

## 전체 Tool 목록

### 파일 탐색

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `dir_list` | 디렉토리 트리 탐색 | `path` `depth` `show_hidden` `detail` |
| `file_find` | 고급 파일 찾기 (find 상당) | `name` `ftype` `min_size` `max_size` `newer_than` `contains` `max_depth` |
| `search_files` | 파일명 패턴 + 내용 키워드 검색 | `path` `pattern` `keyword` `max_results` |

### 파일 조작

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `read_file` | 파일 읽기 | `path` `lines` `offset` |
| `write_file` | 파일 쓰기/추가 | `path` `content` `append` |
| `file_replace` | 텍스트 치환 (sed -i 상당) | `path` `old` `new` `regex` `count` `backup` |
| `file_move` | 파일/디렉토리 이동 (mv) | `src` `dst` |
| `file_copy` | 파일/디렉토리 복사 (cp) | `src` `dst` |
| `delete_file` | 파일 삭제 | `path` |
| `file_info` | 상세 메타정보 | `path` |

### 디렉토리 조작

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `dir_create` | 디렉토리 생성 (mkdir -p) | `path` `mode` |
| `dir_delete` | 디렉토리 삭제 | `path` `recursive` |

### 권한 / 소유자

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `file_chmod` | 권한 변경 (chmod) | `path` `mode` `recursive` |
| `file_chown` | 소유자 변경 (chown) | `path` `owner` `recursive` |

### vLLM 서버

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `server_control` | vLLM 프로세스 제어 | `action`: status\|start\|stop\|restart\|logs\|list_models\|find_vllm |

### 시스템 / 네트워크

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `system_info` | CPU·RAM·디스크·OS·업타임 | — |
| `network_info` | IP·포트·라우팅·DNS·연결 | `detail` |

### 프로세스

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `process_list` | 프로세스 목록 | `keyword` `sort_by` (cpu\|mem\|pid) |
| `process_info` | PID 상세 정보 | `pid` |
| `process_kill` | 시그널 전송 | `pid` `sig` (TERM\|KILL\|HUP\|USR1\|USR2) |

### 서비스 (systemctl)

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `service_control` | systemctl 제어 | `action`: status\|start\|stop\|restart\|enable\|disable\|is-active\|is-enabled\|mask\|unmask\|list\|list-all |

### Cron

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `cron_list` | crontab 조회 | `user` |
| `cron_add` | 항목 추가 | `schedule` `command` `user` `comment` |
| `cron_remove` | 패턴 매칭 삭제 | `pattern` `user` |
| `cron_replace` | 전체 교체 | `new_crontab` `user` |

### 데몬 (systemd)

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `daemon_create` | .service 파일 생성 + daemon-reload | `name` `exec_start` `user` `working_dir` `env_vars` `enable` |
| `daemon_list` | 등록된 서비스 목록 | — |

### 쉘

| Tool | 설명 | 주요 인자 |
|------|------|-----------|
| `shell_exec` | 쉘 명령 직접 실행 | `cmd` `timeout` `workdir` |

---

## 오프라인 패키지 관리 (vllm_install.py)

현재 CLI는 **stdlib only** — 추가 설치 없이 바로 실행 가능합니다.  
향후 `rich` 등 추가 패키지가 필요할 때 아래 절차를 사용합니다.

```bash
# ① 인터넷 환경 (Mac/PC) — USB에 wheel 다운로드
python3 vllm_install.py download rich tqdm
python3 vllm_install.py check                       # 설치 상태 확인

# Ubuntu 전용 wheel 다운로드 (플랫폼 지정)
python3 vllm_install.py download rich \
  --python-version 3.11 \
  --platform manylinux2014_x86_64

# ② Ubuntu — USB 꽂고 설치
python3 vllm_install.py install
python3 vllm_install.py inject    # sys.path 영구 등록 (선택)
```

| 명령 | 설명 |
|------|------|
| `download [pkg ...]` | `vendor/wheels/` 에 wheel 다운로드 (인터넷 필요) |
| `install [--path P]` | `wheels/ → packages/` 오프라인 설치 |
| `inject` | `vendor/packages/` 를 sys.path 에 영구 등록 (.pth) |
| `list` | wheels / packages 목록 확인 |
| `check` | 필수·옵션·vLLM 패키지 설치 여부 확인 |
| `clean wheels\|packages\|all` | 캐시 삭제 |

---

## 설정 파일 (config.json)

서버/모델 선택 시 자동 저장. 다음 실행 시 기본값으로 사용됩니다.

```json
{
  "host": "localhost",
  "port": 8100,
  "model": "prov",
  "known_servers": ["localhost:8100", "localhost:8200"]
}
```

---

## 서버 탐색 포트

localhost 기본 스캔 (12개):
`8000, 8001, 8080, 8090, 8100, 8200, 8300, 8500, 8888, 11434, 5000, 7860`

`--subnet` 옵션 추가 시: `8000, 8080, 8100, 8200, 8300` × 로컬 서브넷 /24 전체 (병렬 64 스레드)

---

## 토큰 다이어트 설계

| 항목 | 값 | 설명 |
|------|----|------|
| `MAX_TOOL_RESULT` | 3000자 | 도구 결과를 LLM에 전달 시 자동 절단 |
| `MAX_READ_LINES` | 200줄 | 대용량 파일 자동 제한 |
| `MAX_FILE_BYTES` | 512KB | 이 이상이면 MAX_READ_LINES 적용 |
| Tool Calling 라운드 | 최대 5회 | 무한 루프 방지 |

---

## 디버그 로그

모든 모듈은 `core/logger.py` 를 통해 `logs/vllm_cli.log` 에 로그를 기록합니다.  
**FAT32 USB에 쓰기 불가 시 `/tmp/vllm_cli.log` 로 자동 폴백합니다.**

### 로그 파일 위치

```
cli/logs/vllm_cli.log          현재 로그 (USB 정상 시)
cli/logs/vllm_cli.log.1 ~ .5   최근 5개 회전 보관
/tmp/vllm_cli.log              FAT32 쓰기 불가 시 폴백
```

### 로그 정책

| 대상 | 레벨 | 설명 |
|------|------|------|
| 파일 | DEBUG 이상 전부 | 트레이스백 포함, 5MB 초과 시 자동 회전 |
| 콘솔 | WARNING 이상만 | 화면에 표시되는 오류/경고 |

### 주요 로그 항목

| 모듈 | 로그 내용 |
|------|-----------|
| `vllm_cli.main` | 시작/종료, 미처리 예외 (`sys.excepthook`) |
| `vllm_cli.core.io` | REQUEST/RESPONSE 전체 페이로드 (DEBUG) |
| `vllm_cli.core.client` | 세션 시작, tool 호출/결과, 400 자동 폴백 |
| `vllm_cli.core.model_detect` | 모델 감지 결과, tool 지원 여부 probe |
| `vllm_cli.core.discovery` | 서버 탐색 결과, 설정 저장 |
| `vllm_cli.core.server` | 서버 start/stop/restart, tool_support_info, find_vllm |
| `vllm_cli.core.files` | 파일 조작 예외 전체 |
| `vllm_cli.core.system` | 차단된 명령, cron/데몬 오류 |

### REQUEST / RESPONSE 로그 (core.io)

매 turn 마다 요청과 응답 전체가 기록됩니다:

```
DEBUG  core.io  REQUEST #1 → localhost:8200
  model      : Qwen2.5-7B-Instruct
  tools      : ON
  tool_choice: auto
  temperature: 0.7  max_tokens: 4096
  messages   : 2개 [...]
  last_user  : {"role": "user", "content": "현재 디렉토리 보여줘"}

DEBUG  core.io  RESPONSE #1 스트림 완료
  content    : 0자
  tool_calls : 1개  [{"name": "dir_list", "arguments": {"path": "."}}]
  events(key): [...]
```

### 로그 확인 방법

```bash
# 전체 실시간 확인
tail -f logs/vllm_cli.log

# 오류만 필터
grep -E "ERROR|CRITICAL" logs/vllm_cli.log

# REQUEST/RESPONSE 페이로드 확인
grep -A 8 "REQUEST #" logs/vllm_cli.log

# tool 호출 이력
grep "tool 호출" logs/vllm_cli.log

# 오늘 날짜만
grep "$(date +%Y-%m-%d)" logs/vllm_cli.log
```

### Tool Calling 미지원 오류 진단

서버가 `--enable-auto-tool-choice` 없이 실행된 경우 자동으로 감지하고 `tools=OFF` 로 전환합니다.  
로그에는 다음과 같이 기록됩니다:

```
WARNING  chat: 400 Tool Calling 미지원 → tools=OFF 재시도
```

수동 진단:
```bash
/server tool-info       # 슬래시 명령으로 진단
```

권장 재시작 명령을 자동 생성해 출력합니다:
```
python3 -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --host localhost \
  --port 8200 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

---

## 모델 계열 자동 감지 (`model_detect.py`)

서버 접속 시 모델명을 분석해 적합한 `--tool-call-parser` 를 자동 선택합니다.

### 범용 LLM (Tool Calling 지원)

| 모델 계열 | parser | 해당 모델 예 |
|-----------|--------|-------------|
| Llama 3.x | `llama3` | Llama-3-8B, Llama-3.1-70B |
| Mistral / Mixtral | `mistral` | Mistral-7B, Mixtral-8x7B |
| InternLM 2+ | `internlm` | InternLM2-7B |
| DeepSeek V3 | `deepseekv3` | DeepSeek-V3 |
| DeepSeek (기타) | `hermes` | DeepSeek-R1-Distill, DeepSeek-Coder |
| Qwen 3 | `hermes` | Qwen3-8B, Qwen3-14B |
| Qwen 2/2.5 | `hermes` | Qwen2-7B, Qwen2.5-14B |
| NousHermes / Yi / Phi-3 | `hermes` | NousHermes-2, Yi-34B |
| 기타 / 미인식 | `hermes` | 폴백 기본값 |

### OCR 전용 모델 (Tool Calling 미지원 — 정상)

아래 모델은 이미지 OCR 처리 전용입니다. 함수 호출 학습이 없어 `tools=OFF` 가 정상 동작입니다.

| 모델 ID | 설명 |
|---------|------|
| `prov` | ARCH OCR PRO (arch-ocr-engine 기본 모델) |
| `ARCH_OCR_PRO` | ARCH OCR PRO 전체 경로 참조 시 |
| `olmocr-*` | olmOCR 계열 |
| `PaddleOCR-VL-*` | PaddleOCR Vision-Language |
| `Nanonets-OCR-*` | Nanonets OCR 계열 |
| `lite` | ARCH OCR Lite |

OCR 모델로 서버 접속 시 자동으로 `tools=OFF` 전환되며 재시작 안내 없이 정상 동작합니다.

---

## 현재 서버 환경 (2026-04-27 기준)

`syscheck.py` 실행 결과 (`/syscheck` 또는 `python3 syscheck.py`):

| 항목 | 값 |
|------|-----|
| OS | Ubuntu 24.04.4 LTS |
| CPU | Intel i7-8700K (12코어) |
| RAM | 31.3GB |
| GPU | NVIDIA RTX 5090 — VRAM 31.8GB |
| CUDA | 드라이버 13.0 / nvcc 12.6 |
| Python | 3.12.3 (`/usr/bin/python3`) |
| vLLM | Docker `engine-ai` 컨테이너 내부 설치 |
| 현재 모델 | `prov` (ARCH OCR PRO, 40GB) — 포트 8100 |

### 권장 Tool Calling 모델 (VRAM 기준)

현재 GPU 여유 VRAM 약 **2.9GB** (engine-ai 점유 중).  
범용 LLM을 별도 포트(예: 8200)에 띄우려면 엔진 컨테이너 중지 또는 추가 GPU 필요.

| VRAM 필요 | 모델 | parser | 포트 예시 |
|-----------|------|--------|-----------|
| ~15GB | Qwen2.5-14B-Instruct | hermes | 8200 |
| ~8GB | Qwen2.5-7B-Instruct | hermes | 8200 |
| ~8GB | Llama-3.1-8B-Instruct | llama3 | 8200 |
| ~4GB | Qwen2.5-3B-Instruct | hermes | 8200 |
| ~2GB | Qwen2.5-1.5B-Instruct | hermes | 8200 |

vLLM 서버 기동 예시 (Docker 외부에서 vllm 설치 후):
```bash
python3 -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --port 8200 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

기동 후 CLI에서 재탐색:
```
/rescan
# 또는
python3 vllm_cli2.py --host localhost --port 8200 --model Qwen/Qwen2.5-7B-Instruct
```
