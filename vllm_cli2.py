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


# ── 슬래시 명령 ───────────────────────────────
def _slash(cmd: str, fm: FileManager, sm: ServerManager, sys_mgr: SystemManager):
    p = cmd.strip().split(None, 3)
    if not p or not p[0].startswith("/"):
        return None
    top = p[0].lower()

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
    print("/file /server /sys /syscheck /model /rescan /clear /notool /q  (Ctrl+D 종료)\n")

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
