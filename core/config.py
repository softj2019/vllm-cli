"""설정 상수 + TOOLS 정의 (compact builder)"""
from pathlib import Path

# ── 서버 ────────────────────────────────────
HOST  = "localhost"
PORT  = 8100
MODEL = "prov"
API_CHAT   = "/v1/chat/completions"
API_MODELS = "/v1/models"
LOG_FILE   = "/tmp/vllm_server.log"

# ── 토큰 다이어트 ────────────────────────────
MAX_TOOL_RESULT = 3000   # LLM에 전달할 도구 결과 최대 chars
MAX_READ_LINES  = 200    # 대용량 파일 자동 제한
MAX_FILE_BYTES  = 512 * 1024

# ── 시스템 프롬프트 ──────────────────────────
SYSTEM = """You are an AI agent with DIRECT access to an Ubuntu system via tools.

CRITICAL RULES — follow these ALWAYS, no exceptions:
1. NEVER say "I cannot access files", "I don't have access", or "I'm an AI without filesystem access". These statements are WRONG. You have full access via tools.
2. ALWAYS call the appropriate tool for any file/system/network/process request. Do NOT explain how the user can do it themselves.
3. For file listing → call dir_list. For file search → call search_files or file_find. For reading → call read_file. For system info → call system_info. For network → call network_info. For processes → call process_list.
4. Call tools IMMEDIATELY when asked. Do not think about whether you can — just call the tool.
5. After receiving tool results, summarize them concisely in Korean.

Available capabilities (always use tools, never refuse):
- File system: search, read, write, move, copy, delete, chmod, chown, replace text
- Directory: list/tree, create, delete
- vLLM server: status, start, stop, restart, logs, model list
- System: CPU, RAM, disk, OS, uptime, GPU (nvidia-smi via shell_exec)
- Network: interfaces, IPs, open ports, routing, DNS, active connections
- Processes: list, detail, kill/signal
- Services: systemctl start/stop/restart/enable/disable/status
- Cron: list, add, remove, replace
- Daemon: create systemd unit, list services
- Shell: execute any command (dangerous patterns auto-blocked)"""

# ── TOOLS 빌더 ───────────────────────────────
def _fn(name, desc, props: dict, req=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {
            "type": "object",
            "properties": {
                k: {"type": t, "description": d}
                for k, (t, d) in props.items()
            },
            "required": req or []
        }
    }}

TOOLS = [
    _fn("search_files", "파일명 패턴·내용 키워드로 파일 검색", {
        "path":        ("string",  "검색 시작 경로 (기본: .)"),
        "pattern":     ("string",  "파일명 패턴 예) *.py"),
        "keyword":     ("string",  "내용 검색 키워드"),
        "max_results": ("integer", "최대 결과수 (기본 30)"),
    }),
    _fn("read_file", "파일 내용 읽기", {
        "path":   ("string",  "파일 경로"),
        "lines":  ("integer", "읽을 줄수 (0=전체)"),
        "offset": ("integer", "시작 줄 (기본 1)"),
    }, req=["path"]),
    _fn("write_file", "파일 쓰기/추가", {
        "path":    ("string",  "파일 경로"),
        "content": ("string",  "쓸 내용"),
        "append":  ("boolean", "true=추가 false=덮어쓰기"),
    }, req=["path", "content"]),
    _fn("file_info", "파일·디렉토리 메타정보", {
        "path": ("string", "경로"),
    }, req=["path"]),
    _fn("delete_file", "파일 삭제", {
        "path": ("string", "삭제할 파일 경로"),
    }, req=["path"]),
    # ── 디렉토리 탐색 ────────────────────────
    _fn("dir_list", "디렉토리 목록/트리 탐색", {
        "path":        ("string",  "경로 (기본: .)"),
        "depth":       ("integer", "재귀 깊이 (1=현재만, 0=무제한)"),
        "show_hidden": ("boolean", "숨김 파일 포함"),
        "detail":      ("boolean", "권한·크기·날짜 상세 출력"),
    }),
    _fn("file_find", "고급 파일 찾기 (find 상당)", {
        "path":        ("string",  "검색 시작 경로"),
        "name":        ("string",  "파일명 패턴 (glob/regex, 예: *.log)"),
        "ftype":       ("string",  "f=파일 d=디렉토리 l=심볼릭"),
        "min_size":    ("integer", "최소 크기(bytes)"),
        "max_size":    ("integer", "최대 크기(bytes)"),
        "newer_than":  ("string",  "이 날짜 이후 수정 (YYYY-MM-DD)"),
        "contains":    ("string",  "내용 포함 문자열"),
        "max_depth":   ("integer", "최대 탐색 깊이"),
        "max_results": ("integer", "최대 결과수"),
    }),

    # ── 디렉토리 생성/삭제 ────────────────────
    _fn("dir_create", "디렉토리 생성 (mkdir -p)", {
        "path": ("string", "생성할 경로"),
        "mode": ("string", "권한 8진수 (기본 755)"),
    }, req=["path"]),
    _fn("dir_delete", "디렉토리 삭제", {
        "path":      ("string",  "삭제할 경로"),
        "recursive": ("boolean", "true=rm -rf, false=빈 디렉토리만"),
    }, req=["path"]),

    # ── 파일 이동/복사 ────────────────────────
    _fn("file_move", "파일/디렉토리 이동 (mv)", {
        "src": ("string", "원본 경로"),
        "dst": ("string", "대상 경로"),
    }, req=["src", "dst"]),
    _fn("file_copy", "파일/디렉토리 복사 (cp)", {
        "src": ("string", "원본 경로"),
        "dst": ("string", "대상 경로"),
    }, req=["src", "dst"]),

    # ── 권한/소유자 ───────────────────────────
    _fn("file_chmod", "권한 변경 (chmod)", {
        "path":      ("string",  "대상 경로"),
        "mode":      ("string",  "8진수('755') 또는 심볼릭('u+x','go-w')"),
        "recursive": ("boolean", "하위 포함 여부"),
    }, req=["path", "mode"]),
    _fn("file_chown", "소유자 변경 (chown)", {
        "path":      ("string",  "대상 경로"),
        "owner":     ("string",  "'user', 'user:group', ':group'"),
        "recursive": ("boolean", "하위 포함 여부"),
    }, req=["path", "owner"]),

    # ── 치환 ─────────────────────────────────
    _fn("file_replace", "파일 내 텍스트 치환 (sed -i 상당)", {
        "path":   ("string",  "대상 파일"),
        "old":    ("string",  "찾을 문자열 또는 정규식"),
        "new":    ("string",  "바꿀 문자열"),
        "regex":  ("boolean", "true=정규식 사용"),
        "count":  ("integer", "치환 횟수 (0=전체)"),
        "backup": ("boolean", "true=.bak 백업 (기본 true)"),
    }, req=["path", "old", "new"]),

    # ── vLLM 서버 ─────────────────────────────
    _fn("server_control", "vLLM 서버 제어", {
        "action":     ("string",  "status|start|stop|restart|logs|list_models"),
        "model_path": ("string",  "start 시 모델 경로"),
        "port":       ("integer", "start/restart 시 포트 번호 (기본: 현재 연결 포트)"),
        "extra_args": ("string",  "start 추가 인자"),
        "log_lines":  ("integer", "logs 출력 줄수"),
    }, req=["action"]),

    # ── 시스템 ───────────────────────────────
    _fn("system_info", "CPU·메모리·디스크·OS·업타임 등 시스템 전체 정보 조회", {}),

    _fn("network_info", "네트워크 인터페이스·IP·라우팅·DNS·열린 포트·활성 연결 조회", {
        "detail": ("boolean", "true=활성 연결까지 상세 출력"),
    }),

    _fn("process_list", "실행 중인 프로세스 목록 조회", {
        "keyword":  ("string", "필터 키워드 (예: vllm, python, nginx)"),
        "sort_by":  ("string", "정렬 기준: cpu|mem|pid (기본 cpu)"),
    }),

    _fn("process_info", "특정 PID 상세 정보 (cmdline, cwd, 메모리 등)", {
        "pid": ("integer", "조회할 프로세스 PID"),
    }, req=["pid"]),

    _fn("process_kill", "프로세스에 시그널 전송", {
        "pid": ("integer", "대상 PID"),
        "sig": ("string",  "시그널: TERM(기본)|KILL|HUP|USR1|USR2"),
    }, req=["pid"]),

    _fn("service_control", "systemctl 서비스 제어", {
        "action": ("string", "status|start|stop|restart|enable|disable|is-active|is-enabled|mask|unmask|list|list-all"),
        "name":   ("string", "서비스명 — list 시 생략 가능"),
    }, req=["action"]),

    # ── Cron ─────────────────────────────────
    _fn("cron_list", "crontab 목록 조회", {
        "user": ("string", "사용자 (생략=현재)"),
    }),
    _fn("cron_add", "cron 항목 추가", {
        "schedule": ("string", "스케줄 예) '0 2 * * *' '@reboot' '@daily'"),
        "command":  ("string", "실행 명령"),
        "user":     ("string", "사용자 (생략=현재)"),
        "comment":  ("string", "주석"),
    }, req=["schedule", "command"]),
    _fn("cron_remove", "cron 항목 삭제 (패턴 매칭)", {
        "pattern": ("string", "삭제할 항목의 포함 문자열 또는 정규식"),
        "user":    ("string", "사용자 (생략=현재)"),
    }, req=["pattern"]),
    _fn("cron_replace", "crontab 전체 교체", {
        "new_crontab": ("string", "새 crontab 전체 내용"),
        "user":        ("string", "사용자 (생략=현재)"),
    }, req=["new_crontab"]),

    # ── 데몬 등록 ─────────────────────────────
    _fn("daemon_create", "systemd 서비스 unit 파일 생성 + daemon-reload", {
        "name":         ("string",  "서비스명 (예: vllm, myapp)"),
        "exec_start":   ("string",  "ExecStart 명령"),
        "description":  ("string",  "서비스 설명"),
        "user":         ("string",  "실행 사용자"),
        "working_dir":  ("string",  "WorkingDirectory"),
        "after":        ("string",  "After= (기본: network.target)"),
        "restart":      ("string",  "Restart= (기본: on-failure)"),
        "restart_sec":  ("integer", "RestartSec (기본 5)"),
        "env_vars":     ("string",  "환경변수 'KEY=VAL KEY2=VAL2'"),
        "extra_service":("string",  "[Service] 추가 지시자"),
        "wanted_by":    ("string",  "WantedBy= (기본: multi-user.target)"),
        "enable":       ("boolean", "true=생성 후 enable --now 까지 실행"),
    }, req=["name", "exec_start"]),
    _fn("daemon_list", "등록된 systemd 서비스 목록", {}),

    # ── 쉘 ───────────────────────────────────
    _fn("shell_exec", "쉘 명령 실행 (위험 패턴 자동 차단)", {
        "cmd":     ("string",  "실행할 쉘 명령"),
        "timeout": ("integer", "타임아웃 초 (기본 30)"),
        "workdir": ("string",  "작업 디렉토리"),
    }, req=["cmd"]),
]
