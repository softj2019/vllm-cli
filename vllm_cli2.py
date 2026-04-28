#!/usr/bin/env python3
"""
vLLM CLI v2  |  서버 자동 탐색 + 파일관리 + 서버제어 + Tool Calling

실행:
  python3 vllm_cli2.py                  시작 시 서버 자동 탐색 + 선택
  python3 vllm_cli2.py --no-discover    탐색 생략, 기본값(저장값) 사용
  python3 vllm_cli2.py --subnet         서브넷 /24 까지 탐색
  python3 vllm_cli2.py --host IP -p PORT --model NAME  직접 지정
  python3 vllm_cli2.py --no-tools       Tool Calling 끄기
  python3 vllm_cli2.py --server-status  서버 상태만 출력
  python3 vllm_cli2.py --server-models  모델 목록만 출력
  python3 vllm_cli2.py --server-logs N  로그 N줄 출력
  python3 vllm_cli2.py --file-search PAT
  python3 vllm_cli2.py --file-read PATH

슬래시 명령:
  /file search|grep|read|write|append|info|delete
  /server status|start|stop|restart|logs|models|tool-info
  /rescan [--subnet]   서버 재탐색 + 재선택
  /clear   /notool     /q

단축키:
  ↑ / ↓      이전/다음 입력 이력
  Ctrl+D     종료
"""
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "vendor" / "packages"))

import argparse

# ── readline (↑↓ 히스토리) ─────────────────────
try:
    import readline as _rl
    _HIST_FILE = Path(__file__).parent / ".vllm_history"
    _rl.set_history_length(200)
    try:
        _rl.read_history_file(_HIST_FILE)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    _READLINE_OK = True
except ImportError:
    _READLINE_OK = False   # Windows 등 readline 없는 환경

from core.config    import HOST, PORT, MODEL
from core.files     import FileManager
from core.server    import ServerManager
from core.switch    import SwitchManager
from core.system    import SystemManager, shell_exec
from core.client    import VLLMClient
from core.discovery import select_server_model, _prompt_model, load_cfg
from core.logger    import get_logger, log_path

log = get_logger("main")


# ── 최상위 예외 훅 ────────────────────────────
def _excepthook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    log.critical("처리되지 않은 예외 발생", exc_info=(exc_type, exc_value, exc_tb))
    print(f"\n[치명적 오류] {exc_type.__name__}: {exc_value}")
    print(f"  상세 내용: {log_path()}")

sys.excepthook = _excepthook


# ── 히스토리 저장 ─────────────────────────────
def _save_history():
    if not _READLINE_OK:
        return
    try:
        _rl.write_history_file(_HIST_FILE)
    except Exception:
        pass


# ── 도움말 ────────────────────────────────────
_HELP: dict = {
    "": """\
┌─ vLLM CLI v2 — 명령 목록 ──────────────────────────────────┐
│                                                             │
│  /help [항목]     상세 도움말   예) /help file              │
│                                                             │
│  /switch          OCR ↔ CLI LLM 모드 전환                  │
│  /file            파일 검색·읽기·쓰기·삭제                  │
│  /server          vLLM 서버 제어 (시작·중지·로그)           │
│  /sys             시스템 정보 (CPU·RAM·GPU·네트워크)        │
│  /syscheck (/sc)  환경 조사 + 모델 추천                     │
│  /model           모델 다운로드                             │
│  /rescan          서버 재탐색 + 재선택                      │
│  /clear           대화 이력 초기화                          │
│  /notool          Tool Calling ON/OFF 토글                  │
│  /q               종료   (Ctrl+D 도 종료)                   │
│                                                             │
│  AI 자연어: tools=ON 일 때 파일·시스템 도구 자율 호출       │
│  상세 가이드: GUIDE.md                                      │
└─────────────────────────────────────────────────────────────┘""",

    "switch": """\
/switch — OCR ↔ CLI LLM 모드 전환
  /switch status    현재 모드·컨테이너 상태 확인
  /switch cli       OCR(8100) 중지 → CLI LLM(8200) 기동 + 자동 재연결
  /switch ocr       CLI LLM 중지 → OCR(8100) 재시작 + 자동 재연결

  설정: switch.json (cli.model_path 를 실제 모델 경로로 수정 필요)
  제약: GPU VRAM 부족 시 동시 운영 불가 → 교대 사용""",

    "file": """\
/file — 파일 조작 (AI 없이 직접 실행)
  /file search <패턴> [경로]    파일명 패턴 검색   예) /file search *.log /var
  /file grep <키워드> [경로]    내용 키워드 검색   예) /file grep ERROR /var/log
  /file read <경로> [줄수]      파일 읽기          예) /file read /etc/hosts 50
  /file write <경로> <내용>     파일 쓰기 (덮어쓰기)
  /file append <경로> <내용>    파일 끝에 추가
  /file info <경로>             파일·디렉토리 상세 정보
  /file delete <경로>           파일 삭제 (확인 프롬프트)""",

    "server": """\
/server — vLLM 서버 제어
  /server status                     서버 상태·PID·모델 확인
  /server start [모델] [--port N]    서버 시작 (Docker 자동 탐색)
  /server stop                       서버 중지 (SIGTERM)
  /server restart [모델] [--port N]  서버 재시작
  /server logs [N]                   로그 마지막 N줄 (기본 50)
  /server models                     모델 목록
  /server tool-info                  Tool Calling 지원 여부 진단
  /server find-vllm                  vLLM 설치 경로 탐색 (Docker 포함)

  예) /server start /home/archiv/dev/model/Qwen2.5-7B-Instruct --port 8200""",

    "sys": """\
/sys — 시스템 정보 조회
  /sys              전체 시스템 정보 (CPU·RAM·디스크·OS·업타임)
  /sys gpu          nvidia-smi 출력
  /sys disk         df -h 출력
  /sys mem          free -h 출력
  /sys cpu          lscpu 요약
  /sys net          네트워크 인터페이스·포트·라우팅
  /sys ps [키워드]  프로세스 목록
  /sys check        환경 조사 (syscheck.py 실행)
  /syscheck (/sc)   환경 조사 + vLLM 모델 추천 전체 리포트""",

    "model": """\
/model — 모델 다운로드 관리
  /model              인터랙티브 다운로드 메뉴
  /model list         다운로드 가능한 모델 목록
  /model check        설치 상태 확인
  /model <모델ID>     특정 모델 직접 지정  예) /model Qwen/Qwen2.5-7B-Instruct

  권장 CLI LLM:
    Qwen2.5-7B-Instruct   (~8GB VRAM)  ← Tool Calling 최적
    Qwen2.5-3B-Instruct   (~4GB VRAM)
    Qwen2.5-1.5B-Instruct (~3GB VRAM)  ← 최소 사양""",
}


def _help(topic: str) -> str:
    if topic in _HELP:
        return _HELP[topic]
    keys = [k for k in _HELP if k and k.startswith(topic)]
    if keys:
        return _HELP[keys[0]]
    return f"알 수 없는 항목: {topic}\n사용 가능: " + ", ".join(k for k in _HELP if k)


# ── 슬래시 명령 ───────────────────────────────
def _slash(cmd: str, fm: FileManager, sm: ServerManager, sys_mgr: SystemManager):
    p = cmd.strip().split(None, 3)
    if not p or not p[0].startswith("/"):
        return None
    top = p[0].lower()

    # ── /help — 도움말 ───────────────────────────
    if top in ("/help", "/h", "/?"):
        topic = p[1].lower() if len(p) > 1 else ""
        return _help(topic)

    # ── /syscheck — 환경 조사 + 모델 추천 ────────
    if top in ("/syscheck", "/sc"):
        script = Path(__file__).parent / "syscheck.py"
        flag   = "--brief" if (len(p) > 1 and p[1].lower() == "brief") else ""
        return shell_exec(f"python3 {script} {flag}".strip(), timeout=90)

    # ── /model — 모델 다운로드 ───────────────────
    if top in ("/model", "/download"):
        script = Path(__file__).parent / "model_download.py"
        sub    = p[1].lower() if len(p) > 1 else ""
        if sub in ("list", "ls"):
            return shell_exec(f"python3 {script} --list", timeout=30)
        if sub == "check":
            return shell_exec(f"python3 {script} --check", timeout=30)
        # 인터랙티브 다운로드 — shell_exec 대신 직접 실행 (stdin 필요)
        import subprocess as _sp
        argv = [sys.executable, str(script)]
        if sub and sub not in ("download", "start"):
            argv += ["--model", p[1]]       # 모델 ID 직접 지정
        _sp.run(argv)
        return ""

    # ── /sys — 서버 사양 조회 ─────────────────
    if top in ("/sys", "/sysinfo"):
        if len(p) < 2 or p[1].lower() in ("all", "info"):
            return sys_mgr.system_info()
        sub = p[1].lower()
        if sub in ("check", "scan"):
            script = Path(__file__).parent / "syscheck.py"
            return shell_exec(f"python3 {script}", timeout=60)
        if sub in ("net", "network"):  return sys_mgr.network_info(detail=True)
        if sub in ("ps", "proc"):      return sys_mgr.process_list(keyword=p[2] if len(p)>2 else None)
        if sub == "gpu":               return shell_exec("nvidia-smi", timeout=10)
        if sub == "disk":              return shell_exec("df -h", timeout=5)
        if sub == "mem":               return shell_exec("free -h", timeout=5)
        if sub == "cpu":               return shell_exec("lscpu | head -30", timeout=5)
        return sys_mgr.system_info()

    if top == "/file":
        if len(p) < 2:
            return ("  search <pat> [path]  grep <kw> [path]\n"
                    "  read <path> [lines]  write <path> <content>\n"
                    "  append <path> <content>  info <path>  delete <path>")
        sub = p[1].lower()
        if sub in ("search", "find"):
            return fm.search_files(path=p[3] if len(p)>3 else ".",
                                   pattern=p[2] if len(p)>2 else "*")
        if sub == "grep":
            if len(p) < 3: return "사용법: /file grep <kw> [path]"
            return fm.search_files(path=p[3] if len(p)>3 else ".", keyword=p[2])
        if sub == "read":
            if len(p) < 3: return "사용법: /file read <path> [lines]"
            return fm.read_file(p[2], lines=int(p[3]) if len(p)>3 and p[3].isdigit() else 0)
        if sub == "write":
            if len(p) < 4: return "사용법: /file write <path> <content>"
            return fm.write_file(p[2], p[3], append=False)
        if sub == "append":
            if len(p) < 4: return "사용법: /file append <path> <content>"
            return fm.write_file(p[2], p[3], append=True)
        if sub == "info":
            if len(p) < 3: return "사용법: /file info <path>"
            return fm.file_info(p[2])
        if sub in ("delete", "rm"):
            if len(p) < 3: return "사용법: /file delete <path>"
            if input(f"  '{p[2]}' 삭제? [y/N] ").strip().lower() == "y":
                return fm.delete_file(p[2])
            return "취소."
        return f"알 수 없는 file 명령: {sub}"

    if top == "/server":
        if len(p) < 2:
            return "  status|start [model]|stop|restart|logs [N]|models|tool-info"
        sub = p[1].lower()
        if sub == "status":  return sm.status()
        if sub in ("start", "restart"):
            rest = p[2:]
            port_override = None
            if "--port" in rest:
                pi = rest.index("--port")
                if pi + 1 < len(rest):
                    try:
                        port_override = int(rest[pi + 1])
                        rest = rest[:pi] + rest[pi + 2:]
                    except ValueError:
                        pass
            model_path = rest[0] if rest else None
            if sub == "start":
                return sm.start(model_path=model_path, port=port_override)
            return sm.restart(model_path=model_path, port=port_override)
        if sub == "stop":    return sm.stop()
        if sub == "logs":
            return sm.logs(log_lines=int(p[2]) if len(p)>2 and p[2].isdigit() else 50)
        if sub in ("models", "list"):       return sm.list_models()
        if sub in ("tool", "tool-info"):    return sm.tool_support_info()
        if sub in ("find", "find-vllm"):    return sm.find_vllm()
        return f"알 수 없는 server 명령: {sub}"

    return None


# ── switch ────────────────────────────────────
def _switch(target: str, client: VLLMClient, sm: ServerManager) -> None:
    sw = SwitchManager()
    msg, host, port, model = sw.switch(target)
    print(msg)
    if host and port and model:
        client.host  = host
        client.port  = port
        client.model = model
        client.tool_ok = None
        client.messages = client.messages[:1]   # 시스템 프롬프트만 유지
        sm.host, sm.port = host, port
        log.info("switch 완료: %s:%d model=%s", host, port, model)
        print(f"\n━━━ 모드 전환 완료: {host}:{port}  model={model} ━━━")


# ── rescan ────────────────────────────────────
def _rescan(client: VLLMClient, subnet=False) -> None:
    host, port, model = select_server_model(
        default_host  = client.host,
        default_port  = client.port,
        default_model = client.model,
        subnet        = subnet,
    )
    client.host  = host
    client.port  = port
    client.model = model
    client.executor.sm.host = host
    client.executor.sm.port = port
    log.info("rescan 완료: %s:%d model=%s", host, port, model)
    print(f"\n→ {host}:{port}  모델: {model}\n")


# ── main ──────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="vLLM CLI v2", add_help=True)
    ap.add_argument("-m", "--model",      default="")
    ap.add_argument("--host",             default="")
    ap.add_argument("-p", "--port",       type=int, default=0)
    ap.add_argument("--no-tools",         action="store_true")
    ap.add_argument("--temp",             type=float, default=0.7)
    ap.add_argument("--no-discover",      action="store_true", help="탐색 생략")
    ap.add_argument("--subnet",           action="store_true", help="서브넷 /24 탐색")
    ap.add_argument("--server-status",    action="store_true")
    ap.add_argument("--server-models",    action="store_true")
    ap.add_argument("--server-logs",      type=int, metavar="N", nargs="?", const=50)
    ap.add_argument("--file-search",      metavar="PAT")
    ap.add_argument("--file-read",        metavar="PATH")
    args = ap.parse_args()

    log.info("vLLM CLI v2 시작: args=%s", vars(args))

    # 일회성 명령 — 탐색 없이 바로 실행
    if any([args.server_status, args.server_models, args.server_logs,
            args.file_search, args.file_read]):
        cfg = load_cfg()
        h = args.host or cfg.get("host", HOST)
        p = args.port or cfg.get("port", PORT)
        fm = FileManager()
        sm = ServerManager(h, p)
        if args.server_status:  print(sm.status());               return
        if args.server_models:  print(sm.list_models());          return
        if args.server_logs:    print(sm.logs(args.server_logs)); return
        if args.file_search:    print(fm.search_files(pattern=args.file_search)); return
        if args.file_read:      print(fm.read_file(args.file_read)); return

    # ── 서버/모델 선택 ────────────────────────
    host, port, model = select_server_model(
        default_host  = args.host,
        default_port  = args.port,
        default_model = args.model,
        subnet        = args.subnet,
        no_discover   = args.no_discover,
    )

    fm      = FileManager()
    sm      = ServerManager(host, port)
    sys_mgr = SystemManager()
    client  = VLLMClient(host, port, model, use_tools=not args.no_tools)
    flag    = "ON" if not args.no_tools else "OFF"

    print(f"\n━━━ vLLM CLI v2  {host}:{port}  model={model}  tools={flag} ━━━")
    print(f"  로그: {log_path()}")
    if _READLINE_OK:
        print("  ↑↓ 이력 탐색 활성화")
    print("/file /server /sys /syscheck /model /switch /rescan /clear /notool /q  (Ctrl+D 종료)\n")

    while True:
        try:
            ui = input("User > ").strip()
        except EOFError:
            # Ctrl+D
            log.info("vLLM CLI v2 종료 (Ctrl+D)")
            print("\n종료.")
            _save_history()
            break
        except KeyboardInterrupt:
            # Ctrl+C — 입력 취소, 루프 유지
            print()
            continue

        if not ui:
            continue
        if ui in ("/q", "/quit", "/exit"):
            log.info("vLLM CLI v2 종료 (/q)")
            print("종료.")
            _save_history()
            break
        if ui == "/clear":
            client.clear(); continue
        if ui == "/notool":
            client.use_tools = not client.use_tools
            log.info("tools 토글: %s", client.use_tools)
            print(f"tools={'ON' if client.use_tools else 'OFF'}"); continue

        if ui.startswith("/rescan"):
            _rescan(client, subnet="--subnet" in ui)
            sm.host, sm.port = client.host, client.port
            continue

        if ui.startswith("/switch"):
            parts  = ui.split()
            target = parts[1].lower() if len(parts) > 1 else "status"
            _switch(target, client, sm)
            continue

        if ui.startswith("/"):
            r = _slash(ui, fm, sm, sys_mgr)
            if r is not None:
                print(r); continue
            print("[알 수 없는 슬래시 명령 — LLM 전달]")

        try:
            client.chat(ui, temperature=args.temp)
        except KeyboardInterrupt:
            print("\n[중단]")
        except Exception:
            log.error("chat 루프 예외", exc_info=True)
            print(f"[오류] 상세 내용은 로그 참조: {log_path()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("강제 종료 (KeyboardInterrupt)")
        _save_history()
        print("\n강제 종료.")
        sys.exit(1)
    except Exception:
        log.critical("main() 최상위 예외", exc_info=True)
        raise
