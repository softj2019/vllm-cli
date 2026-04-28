"""VLLMClient — HTTP 스트리밍 + Tool Calling 자동 감지/폴백 + ToolExecutor"""
import json, http.client, os
from typing import List, Dict, Any, Tuple, Optional
from .config import HOST, PORT, API_CHAT, MODEL, SYSTEM, TOOLS, MAX_TOOL_RESULT
from .files        import FileManager
from .server       import ServerManager
from .system       import SystemManager, shell_exec
from .model_detect import detect_parser, fetch_models, probe_tool_support, is_ocr_only_model
from .logger       import get_logger

log = get_logger(__name__)

# 요청/응답 전용 로거 (DEBUG 레벨, 별도 네임스페이스로 필터 편의)
log_io = get_logger("core.io")

_REQ_TRUNC  = 6000   # 요청 로그 최대 길이
_RESP_TRUNC = 4000   # 응답 로그 최대 길이


def _trunc(s: str, n=MAX_TOOL_RESULT) -> str:
    return s if len(s) <= n else s[:n] + f"\n…[{len(s)-n}자 생략]"


def _dump(obj, limit: int) -> str:
    """JSON 직렬화 후 길이 제한"""
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=None)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"…[+{len(s)-limit}]"


# ── Tool Calling 지원 여부 자동 감지 ──────────
def check_tool_support(host: str, port: int, model: str) -> Tuple[bool, str, str]:
    models = fetch_models(host, port)
    actual = models[0] if models else model
    parser, desc = detect_parser(actual)
    supported = probe_tool_support(host, port, actual)
    return supported, parser, desc


# ── ToolExecutor ──────────────────────────────
class ToolExecutor:
    def __init__(self, host=HOST, port=PORT):
        self.fm  = FileManager()
        self.sm  = ServerManager(host, port)
        self.sys = SystemManager()
        self._map = {
            "search_files":  self.fm.search_files,
            "read_file":     self.fm.read_file,
            "write_file":    self.fm.write_file,
            "file_info":     self.fm.file_info,
            "delete_file":   self.fm.delete_file,
            "dir_list":      self.fm.dir_list,
            "file_find":     self.fm.file_find,
            "dir_create":    self.fm.dir_create,
            "dir_delete":    self.fm.dir_delete,
            "file_move":     self.fm.file_move,
            "file_copy":     self.fm.file_copy,
            "file_chmod":    self.fm.file_chmod,
            "file_chown":    self.fm.file_chown,
            "file_replace":  self.fm.file_replace,
            "system_info":   self.sys.system_info,
            "network_info":  self.sys.network_info,
            "process_list":  self.sys.process_list,
            "process_info":  self.sys.process_info,
            "process_kill":  self.sys.process_kill,
            "service_control": self.sys.service_control,
            "cron_list":       self.sys.cron_list,
            "cron_add":        self.sys.cron_add,
            "cron_remove":     self.sys.cron_remove,
            "cron_replace":    self.sys.cron_replace,
            "daemon_create":   self.sys.daemon_create,
            "daemon_list":     self.sys.daemon_list,
        }

    def run(self, name: str, args: Dict[str, Any]) -> str:
        log.debug("ToolExecutor.run: name=%s args=%s", name, args)
        if name == "shell_exec":
            try:
                result = shell_exec(**args)
                log.debug("shell_exec 완료: %s", result[:200])
                return result
            except TypeError as e:
                log.warning("shell_exec 인자 오류: %s", e)
                return f"[인자 오류] {e}"
            except Exception:
                log.error("shell_exec 실패", exc_info=True)
                return "[실행 오류] shell_exec 실패"

        if name == "server_control":
            return self._server(args)

        if name in self._map:
            try:
                result = self._map[name](**args)
                log.debug("tool %s 완료", name)
                return result
            except TypeError as e:
                log.warning("tool %s 인자 오류: %s", name, e)
                return f"[인자 오류] {e}"
            except Exception:
                log.error("tool %s 실패", name, exc_info=True)
                return f"[실행 오류] {name} 실패"

        log.warning("ToolExecutor: 미정의 도구 요청 name=%s", name)
        return f"[미정의 도구] {name}"

    def _server(self, args) -> str:
        act, sm = args.get("action", ""), self.sm
        log.debug("server_control action=%s", act)
        fn = {
            "status":      sm.status,
            "list_models": sm.list_models,
            "stop":        sm.stop,
            "tool_info":   sm.tool_support_info,
            "find_vllm":   sm.find_vllm,
            "start":   lambda: sm.start(args.get("model_path"), args.get("extra_args", "")),
            "restart": lambda: sm.restart(args.get("model_path"), args.get("extra_args", "")),
            "logs":    lambda: sm.logs(args.get("log_lines", 50)),
        }.get(act)
        if fn is None:
            log.warning("server_control 알 수 없는 action=%s", act)
            return f"[오류] 알 수 없는 action: {act}"
        try:
            return fn()
        except Exception:
            log.error("server_control action=%s 실패", act, exc_info=True)
            return f"[실행 오류] server_control {act}"


# ── VLLMClient ────────────────────────────────
class VLLMClient:
    def __init__(self, host=HOST, port=PORT, model=MODEL, use_tools=True):
        self.host, self.port, self.model = host, port, model
        self.use_tools   = use_tools
        self.tool_ok: Optional[bool] = None
        self.executor    = ToolExecutor(host, port)
        cwd = os.getcwd()
        system = SYSTEM + f"\n\nCurrent working directory: {cwd}\nWhen the user mentions a relative path or 'project path', resolve it against: {cwd}"
        self.messages: List[Dict] = [{"role": "system", "content": system}]
        self._turn = 0   # 요청 순번 (로그 추적용)
        log.info("VLLMClient 초기화: %s:%d model=%s tools=%s", host, port, model, use_tools)

    # ── 연결 시 tool 지원 자동 감지 ──────────
    def probe(self) -> str:
        if not self.use_tools:
            log.debug("probe: use_tools=False — 스킵")
            return "tools=OFF (--no-tools 지정)"

        log.info("probe 시작: %s:%d", self.host, self.port)
        print("  모델 감지 중...", end="", flush=True)
        try:
            models = fetch_models(self.host, self.port)
            actual = models[0] if models else self.model
            parser, desc = detect_parser(actual)
            supported = probe_tool_support(self.host, self.port, actual)
        except Exception:
            log.error("probe 실패", exc_info=True)
            print("\r  [경고] 모델 감지 실패 — tools=OFF 전환")
            self.use_tools = False
            self.tool_ok   = False
            return "tool=OFF(감지 오류)"

        self.tool_ok = supported
        log.info("probe 결과: model=%s parser=%s supported=%s", actual, parser, supported)

        if supported:
            print(f"\r  모델: {actual} ({desc}) | parser: {parser} | Tool Calling: ✓    ")
            return f"tool=ON  model={actual}  parser={parser}"
        else:
            self.use_tools = False
            if is_ocr_only_model(actual):
                # OCR 전용 모델 — tool calling 미지원이 정상, 재시작 안내 불필요
                print(f"\r  모델: {actual} ({desc}) | OCR 전용 모델 → tools=OFF (정상)    ")
                log.info("probe: OCR 전용 모델 tools=OFF 전환 (정상)")
                return f"tool=OFF(OCR전용)  model={actual}"
            else:
                msg = (
                    f"\r  모델: {actual} ({desc}) | Tool Calling: ✗ → tools=OFF 자동 전환\n"
                    f"\n  ┌─ Tool Calling 활성화 방법 ────────────────────────────────┐\n"
                    f"  │  서버를 아래 옵션으로 재시작하세요:                        │\n"
                    f"  │                                                            │\n"
                    f"  │  python3 -m vllm.entrypoints.openai.api_server \\           │\n"
                    f"  │    --model {actual[:40]:<40s} \\    │\n"
                    f"  │    --enable-auto-tool-choice \\                             │\n"
                    f"  │    --tool-call-parser {parser:<10s}                           │\n"
                    f"  └────────────────────────────────────────────────────────────┘"
                )
                print(msg)
                return f"tool=OFF(자동)  model={actual}  parser={parser}"

    # ── HTTP POST ────────────────────────────
    def _post(self, payload, turn: int):
        # ── 요청 로그 ──────────────────────────
        # messages 는 role/content 요약만 (토큰 절약), tools/기타는 전체
        msg_summary = [
            {"role": m["role"], "content_len": len(str(m.get("content") or ""))}
            for m in payload.get("messages", [])
        ]
        log_io.debug(
            "REQUEST #%d → %s:%d\n"
            "  model      : %s\n"
            "  tools      : %s\n"
            "  tool_choice: %s\n"
            "  temperature: %s  max_tokens: %s\n"
            "  messages   : %d개 %s\n"
            "  last_user  : %s",
            turn, self.host, self.port,
            payload.get("model"),
            "ON" if "tools" in payload else "OFF",
            payload.get("tool_choice", "-"),
            payload.get("temperature"), payload.get("max_tokens"),
            len(payload.get("messages", [])), msg_summary,
            _dump(payload["messages"][-1] if payload.get("messages") else {}, 500),
        )
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=600)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            conn.request("POST", API_CHAT, body=body, headers={
                "Content-Type":  "application/json; charset=utf-8",
                "Authorization": "Bearer empty",
                "Accept":        "text/event-stream",
            })
            resp = conn.getresponse()
            log_io.debug("RESPONSE #%d ← HTTP %d", turn, resp.status)
            return conn, resp
        except Exception:
            log.error("_post 연결 실패: %s:%d", self.host, self.port, exc_info=True)
            raise

    # ── SSE 라인 이터레이터 ───────────────────
    @staticmethod
    def _sse_lines(resp):
        """
        SSE 스트림을 한 줄씩 yield.
        4096 바이트 청크 경계에서 긴 줄이 잘리는 버그 수정:
        청크를 누적하여 완전한 줄이 될 때만 yield.
        """
        pending = b""
        while True:
            chunk = resp.fp.read(4096)
            if not chunk:
                break
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                yield line.rstrip(b"\r").decode("utf-8", errors="replace")
        # 남은 데이터 처리
        if pending:
            yield pending.rstrip(b"\r").decode("utf-8", errors="replace")

    # ── SSE 스트리밍 파싱 ─────────────────────
    def _stream(self, resp, turn: int) -> Tuple[str, List[Dict]]:
        buf, tc_map, done = "", {}, False
        in_think       = False
        think_buf      = ""
        header_printed = False
        raw_events: List[str] = []
        try:
            for line in self._sse_lines(resp):
                if done:
                    break
                if not line.startswith("data: "):
                    continue
                ds = line[6:]
                if ds == "[DONE]":
                    done = True; break
                if not ds:
                    continue
                try:
                    d = json.loads(ds)
                except json.JSONDecodeError:
                    log.debug("_stream JSON 파싱 실패 (%d자): %s", len(ds), ds[:200])
                    continue

                # 응답 이벤트 원문 누적 (tool_calls 또는 finish_reason 있는 것만)
                ch    = d.get("choices", [{}])[0]
                delta = ch.get("delta", {})
                fr    = ch.get("finish_reason")
                if delta.get("tool_calls") or fr:
                    raw_events.append(ds[:300])

                t = delta.get("content") or ""
                if t:
                    # <think>...</think> 블록 필터 (추론 모델)
                    tmp = t
                    while tmp:
                        if in_think:
                            end = tmp.find("</think>")
                            if end == -1:
                                think_buf += tmp; tmp = ""; break
                            else:
                                think_buf += tmp[:end]
                                log.debug("_stream <think> 블록: %d자 필터", len(think_buf))
                                in_think = False; think_buf = ""
                                tmp = tmp[end + 8:]
                        else:
                            start = tmp.find("<think>")
                            if start == -1:
                                if not header_printed:
                                    print("AI: ", end="", flush=True)
                                    header_printed = True
                                print(tmp, end="", flush=True)
                                buf += tmp; tmp = ""; break
                            else:
                                visible = tmp[:start]
                                if visible:
                                    if not header_printed:
                                        print("AI: ", end="", flush=True)
                                        header_printed = True
                                    print(visible, end="", flush=True)
                                    buf += visible
                                in_think = True
                                tmp = tmp[start + 7:]

                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index", 0)
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "type": "function",
                                       "function": {"name": "", "arguments": ""}}
                    e = tc_map[idx]; fn = tc.get("function", {})
                    if fn.get("name"):      e["function"]["name"]      += fn["name"]
                    if fn.get("arguments"): e["function"]["arguments"] += fn["arguments"]
                    if tc.get("id"):        e["id"] = tc["id"]

                if fr in ("stop", "tool_calls", "length"):
                    done = True

        except Exception:
            log.error("_stream 읽기 오류", exc_info=True)

        if header_printed or not tc_map:
            print()

        tcs = [tc_map[k] for k in sorted(tc_map)]

        # ── 응답 로그 ──────────────────────────
        log_io.debug(
            "RESPONSE #%d 스트림 완료\n"
            "  content    : %d자  %s\n"
            "  tool_calls : %d개  %s\n"
            "  events(key): %s",
            turn,
            len(buf), (buf[:200] + "…") if len(buf) > 200 else buf,
            len(tcs), _dump(tcs, _RESP_TRUNC),
            raw_events[:10],
        )

        return buf, tcs

    # ── 채팅 루프 ─────────────────────────────
    def chat(self, user_msg: str, temperature=0.7) -> str:
        if self.tool_ok is None and self.use_tools:
            self.probe()

        self.messages.append({"role": "user", "content": user_msg})
        log.info("chat 시작: msg=%s...", user_msg[:60])
        log_io.debug("USER INPUT: %s", user_msg)

        content = ""
        for turn in range(5):
            self._turn += 1
            t = self._turn

            payload = {
                "model": self.model, "messages": self.messages,
                "stream": True, "temperature": temperature,
                "max_tokens": 4096, "top_p": 0.9,
            }
            if self.use_tools:
                payload["tools"]       = TOOLS
                payload["tool_choice"] = "auto"

            try:
                conn, resp = self._post(payload, t)
            except Exception as e:
                log.error("chat _post 실패 (turn=%d): %s", turn, e)
                print(f"\n[연결 오류] {e}"); return ""

            # ── 400 tool 오류 자동 폴백 ────────
            if resp.status == 400:
                body = resp.read().decode("utf-8", errors="replace")
                conn.close()
                log_io.debug("RESPONSE #%d HTTP 400: %s", t, body[:500])
                if "enable-auto-tool-choice" in body:
                    log.warning("chat: 400 Tool Calling 미지원 → tools=OFF 재시도")
                    print("\n[자동 전환] 서버 Tool Calling 미지원 → tools=OFF 재시도")
                    self.use_tools = False
                    self.tool_ok   = False
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                    try:
                        conn, resp = self._post(payload, t)
                    except Exception as e:
                        log.error("chat 재시도 _post 실패: %s", e)
                        print(f"\n[연결 오류] {e}"); return ""
                    if resp.status != 200:
                        body2 = resp.read().decode()[:200]
                        log.error("chat 재시도 HTTP %d: %s", resp.status, body2)
                        print(f"\n[API {resp.status}] {body2}")
                        conn.close(); return ""
                else:
                    log.error("chat HTTP 400: %s", body[:300])
                    print(f"\n[API 400] {body[:300]}")
                    return ""
            elif resp.status != 200:
                body = resp.read().decode()[:200]
                log.error("chat HTTP %d: %s", resp.status, body)
                log_io.debug("RESPONSE #%d HTTP %d: %s", t, resp.status, body)
                print(f"\n[API {resp.status}] {body}")
                conn.close(); return ""

            content, tcs = self._stream(resp, t)
            conn.close()

            if not tcs:
                self.messages.append({"role": "assistant", "content": content})
                log.info("chat 완료 (turn=%d): 응답 %d자", turn, len(content))
                return content

            self.messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tcs,
            })
            for tc in tcs:
                fn, raw = tc["function"]["name"], tc["function"]["arguments"]
                try:
                    args = json.loads(raw or "{}")
                except json.JSONDecodeError:
                    log.warning("tool_call args JSON 파싱 실패: fn=%s raw=%s", fn, raw[:100])
                    args = {}
                log.info("tool 호출: %s(%s)", fn, json.dumps(args, ensure_ascii=False)[:200])
                log_io.debug("TOOL CALL: %s  args=%s", fn, _dump(args, 500))
                print(f"\n[도구] {fn}({json.dumps(args, ensure_ascii=False)})")
                result = self.executor.run(fn, args)
                log_io.debug("TOOL RESULT: %s → %s", fn, result[:_RESP_TRUNC])
                log.debug("tool 결과: %s → %s", fn, result[:200])
                print(f"[결과]\n{result}\n")
                self.messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "name": fn, "content": _trunc(result),
                })

        log.warning("chat: 최대 tool 루프 횟수(5) 초과")
        return content

    def clear(self):
        self.messages = [{"role": "system", "content": SYSTEM}]
        self.tool_ok  = None
        log.info("VLLMClient: 대화 이력 초기화")
        print("대화 이력 초기화.")
