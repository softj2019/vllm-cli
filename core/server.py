"""ServerManager — vLLM 프로세스 제어 + 모델 자동 감지"""
import os, signal, subprocess, json, http.client, time
from pathlib import Path
from typing import List, Optional
from .config import HOST, PORT, API_MODELS, LOG_FILE
from .model_detect import detect_parser, fetch_models
from .logger import get_logger

log = get_logger(__name__)


class ServerManager:
    def __init__(self, host=HOST, port=PORT):
        self.host, self.port = host, port

    def _get(self, path, timeout=3):
        try:
            c = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
            c.request("GET", path, headers={"Authorization": "Bearer empty"})
            r = c.getresponse()
            body = r.read().decode("utf-8", errors="replace")
            c.close()
            return r.status, body
        except Exception:
            log.debug("_get 실패: %s:%d%s", self.host, self.port, path, exc_info=True)
            return -1, "연결 실패"

    def _pids(self) -> List[int]:
        try:
            out = subprocess.check_output(["ps", "aux"], text=True, stderr=subprocess.DEVNULL)
            return [
                int(l.split()[1])
                for l in out.splitlines()
                if "vllm" in l.lower() and "grep" not in l and l.split()
            ]
        except Exception:
            log.debug("_pids 실패", exc_info=True)
            return []

    def status(self) -> str:
        log.debug("server status 조회")
        pids  = self._pids()
        code, body = self._get("/health")
        pid_s = ", ".join(map(str, pids)) or "없음"
        ok    = code == 200
        extra = ""
        if ok:
            try:
                models = fetch_models(self.host, self.port)
                if models:
                    parser, desc = detect_parser(models[0])
                    extra = (f"\n  모델:   {models[0]}"
                             f"\n  계열:   {desc}"
                             f"\n  parser: {parser}")
            except Exception:
                log.debug("status 모델 감지 실패", exc_info=True)
        return (f"상태: {'✓ 실행중' if ok else '✗ 응답없음'}\n"
                f"  주소: http://{self.host}:{self.port}\n"
                f"  PID:  {pid_s}\n"
                f"  HTTP: {code if code > 0 else body[:80]}{extra}")

    def list_models(self) -> str:
        log.debug("list_models 조회")
        code, body = self._get(API_MODELS)
        if code != 200:
            log.warning("list_models HTTP %d: %s", code, body[:100])
            return f"[오류] HTTP {code}: {body[:200]}"
        try:
            items = json.loads(body).get("data", [])
            if not items:
                return "모델 없음"
            lines = []
            for m in items:
                mid = m.get("id", "?")
                parser, desc = detect_parser(mid)
                lines.append(f"  {mid}\n    → 계열: {desc}  parser: {parser}")
            return "모델 목록:\n" + "\n".join(lines)
        except Exception:
            log.error("list_models 파싱 실패", exc_info=True)
            return f"[오류] 파싱 실패"

    def logs(self, log_lines=50) -> str:
        lp = Path(LOG_FILE)
        if lp.exists():
            try:
                chunk = lp.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:]
                return f"# {lp} (끝 {len(chunk)}줄)\n" + "\n".join(chunk)
            except Exception:
                log.error("logs 읽기 실패: %s", lp, exc_info=True)
                return f"[오류] 로그 읽기 실패: {lp}"
        try:
            return subprocess.check_output(
                ["journalctl", "-u", "vllm", f"-n{log_lines}", "--no-pager"],
                text=True, stderr=subprocess.DEVNULL
            )
        except Exception:
            log.debug("journalctl 없음", exc_info=True)
        pids = self._pids()
        return f"로그 파일 없음 ({LOG_FILE})" + (f"\nPID: {pids}" if pids else "")

    def stop(self) -> str:
        pids = self._pids()
        if not pids:
            return "실행 중인 프로세스 없음"
        res = []
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                log.info("server stop: PID %d SIGTERM", pid)
                res.append(f"PID {pid} → SIGTERM")
            except ProcessLookupError:
                res.append(f"PID {pid} → 이미 종료")
            except PermissionError:
                log.warning("server stop 권한 없음: PID %d", pid)
                res.append(f"PID {pid} → 권한 없음 (sudo 필요)")
            except Exception:
                log.error("server stop 실패: PID %d", pid, exc_info=True)
                res.append(f"PID {pid} → 오류")
        return "중지:\n" + "\n".join(f"  {r}" for r in res)

    # ── vLLM 설치 확인 헬퍼 ──────────────────────
    def _has_local_vllm(self) -> bool:
        try:
            r = subprocess.run(["python3", "-c", "import vllm"],
                               capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def _find_vllm_container(self) -> str:
        """vLLM이 설치된 실행 중 Docker 컨테이너 이름 반환"""
        try:
            names = subprocess.check_output(
                ["docker", "ps", "--format", "{{.Names}}"],
                text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip().splitlines()
            for name in names:
                r = subprocess.run(
                    ["docker", "exec", name, "python3", "-c", "import vllm; print('ok')"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0 and "ok" in r.stdout:
                    log.info("_find_vllm_container: %s", name)
                    return name
        except Exception:
            log.debug("_find_vllm_container 실패", exc_info=True)
        return ""

    def _start_in_docker(self, container: str, model_path: Optional[str],
                         target_port: int, extra_args: str,
                         auto_tool: bool, parser: str, desc: str) -> str:
        if not model_path:
            return (
                "[오류] Docker 실행 시 모델 경로 필수\n"
                "  사용법: /server start <모델경로> [--port N]\n"
                "  예시:   /server start /home/archiv/dev/model/Qwen2.5-1.5B-Instruct --port 8200"
            )
        vllm_cmd = (
            f"python3 -m vllm.entrypoints.openai.api_server"
            f" --model {model_path}"
            f" --host 0.0.0.0 --port {target_port}"
        )
        if auto_tool:
            vllm_cmd += f" --enable-auto-tool-choice --tool-call-parser {parser}"
        if extra_args:
            vllm_cmd += f" {extra_args}"
        try:
            subprocess.Popen(
                ["docker", "exec", "-d", container, "bash", "-c", vllm_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            log.info("_start_in_docker: container=%s port=%d model=%s parser=%s",
                     container, target_port, model_path, parser)
            return (
                f"Docker [{container}] 내부에서 vLLM 시작:\n"
                f"  모델:  {model_path}\n"
                f"  포트:  {target_port}  (--host 0.0.0.0)\n"
                f"  계열:  {desc}  →  parser: {parser}\n"
                f"  로그:  docker logs {container} -f\n\n"
                f"  ※ 컨테이너가 --network host 또는 -p {target_port}:{target_port} 로\n"
                f"    실행 중이어야 localhost:{target_port} 접근 가능.\n"
                f"  → 30~60초 후 /rescan 으로 연결 확인"
            )
        except Exception:
            log.error("_start_in_docker 실패", exc_info=True)
            return f"[오류] docker exec {container} 실패"

    def start(self, model_path: str = None, extra_args: str = "",
              auto_tool: bool = True, port: int = None) -> str:
        pids = self._pids()
        if pids:
            return f"이미 실행중 (PID: {', '.join(map(str, pids))})"
        target_port = port or self.port
        target = model_path or ""
        parser, desc = detect_parser(target) if target else ("hermes", "Unknown (기본값)")

        # vLLM 로컬 설치 확인 → 없으면 Docker 컨테이너 탐색
        if not self._has_local_vllm():
            log.warning("server start: 호스트에 vllm 없음 → Docker 컨테이너 탐색")
            container = self._find_vllm_container()
            if container:
                return self._start_in_docker(container, model_path, target_port,
                                             extra_args, auto_tool, parser, desc)
            return (
                "[오류] vLLM 미설치\n"
                "  호스트: python3 -c 'import vllm' → ModuleNotFoundError\n"
                "  Docker: vLLM 포함 컨테이너 없음\n"
                "  해결①: pip install vllm (CUDA 환경 필요)\n"
                "  해결②: Docker 컨테이너 내부에서 직접 실행\n"
                f"    docker exec -d <컨테이너> bash -c \\\n"
                f"      'python3 -m vllm.entrypoints.openai.api_server"
                f" --model {model_path or '<모델경로>'}"
                f" --host 0.0.0.0 --port {target_port}"
                f" --enable-auto-tool-choice --tool-call-parser {parser}'"
            )

        cmd = ["python3", "-m", "vllm.entrypoints.openai.api_server",
               "--host", self.host, "--port", str(target_port)]
        if model_path:
            cmd += ["--model", model_path]
        tool_note = ""
        if auto_tool:
            cmd += ["--enable-auto-tool-choice", "--tool-call-parser", parser]
            tool_note = f"\n  계열: {desc}  →  parser: {parser}"
            log.info("server start: model=%s parser=%s", target or "(미지정)", parser)
        if extra_args:
            cmd += extra_args.split()
        try:
            log_f = open(LOG_FILE, "a")
            subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT,
                             start_new_session=True)
            log.info("server start 실행: %s", " ".join(cmd))
            return f"시작: {' '.join(cmd)}{tool_note}\n로그: {LOG_FILE}"
        except FileNotFoundError:
            log.error("server start: vllm 없음")
            return "[오류] vllm 없음. pip show vllm 확인"
        except Exception:
            log.error("server start 실패", exc_info=True)
            return "[오류] 서버 시작 실패"

    def restart(self, model_path: str = None, extra_args: str = "",
                auto_tool: bool = True, port: int = None) -> str:
        log.info("server restart 시작")
        r1 = self.stop()
        time.sleep(2)
        r2 = self.start(model_path, extra_args, auto_tool, port)
        return f"{r1}\n\n{r2}"

    def find_vllm(self) -> str:
        """vLLM 설치 경로 및 실행 가능한 python 탐색"""
        log.debug("find_vllm 시작")
        lines = []

        def _run(cmd):
            try:
                return subprocess.check_output(
                    cmd, text=True, stderr=subprocess.STDOUT, timeout=5
                ).strip()
            except Exception as e:
                return f"(실패: {e})"

        # ── 1. 실행 중인 vLLM 프로세스에서 경로 추출 ──
        pids = self._pids()
        if pids:
            lines.append(f"[실행 중] PID: {', '.join(map(str, pids))}")
            for pid in pids[:2]:
                try:
                    exe = Path(f"/proc/{pid}/exe").resolve()
                    lines.append(f"  python: {exe}")
                except Exception:
                    pass
                cmdline_path = Path(f"/proc/{pid}/cmdline")
                try:
                    cmd_raw = cmdline_path.read_bytes().replace(b"\x00", b" ").decode()
                    lines.append(f"  cmdline: {cmd_raw[:200]}")
                except Exception:
                    pass
        else:
            lines.append("[실행 중인 vLLM 없음]")

        lines.append("")

        # ── 2. python 후보별 vllm 임포트 시도 ──────
        candidates = []
        for name in ["python3", "python", "python3.11", "python3.10", "python3.9"]:
            path = _run(["which", name])
            if path and not path.startswith("(실패"):
                candidates.append(path)

        # 가상환경 / conda 경로 추가
        for prefix in [
            Path.home() / "venv",
            Path.home() / ".venv",
            Path("/opt/venv"),
            Path("/opt/conda"),
            Path.home() / "miniconda3",
            Path.home() / "anaconda3",
            Path("/usr/local"),
        ]:
            for sub in ["bin/python3", "bin/python"]:
                p = prefix / sub
                if p.exists():
                    candidates.append(str(p))

        seen = []
        for py in candidates:
            if py in seen:
                continue
            seen.append(py)
            result = _run([py, "-c",
                "import vllm, sys; print(sys.executable + ' | vllm ' + vllm.__version__ + ' @ ' + vllm.__file__)"])
            if "vllm" in result and "@" in result:
                lines.append(f"✓ {result}")
            else:
                lines.append(f"✗ {py}  → vllm 없음")

        lines.append("")

        # ── 3. pip 경로 확인 ───────────────────────
        for pip in ["pip3", "pip"]:
            r = _run([pip, "show", "vllm"])
            if "Location" in r:
                for l in r.splitlines():
                    if l.startswith(("Name", "Version", "Location")):
                        lines.append(f"  {l}")
                break

        # ── 3b. Docker 컨테이너 내 vLLM 탐색 ─────
        lines.append("[Docker 컨테이너 탐색]")
        try:
            containers = subprocess.check_output(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
                text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip().splitlines()
            for cline in containers:
                cname = cline.split("\t")[0]
                r = subprocess.run(
                    ["docker", "exec", cname, "python3", "-c",
                     "import vllm, sys; print(sys.executable + ' | vllm ' + vllm.__version__)"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0:
                    lines.append(f"  ✓ [{cname}] {r.stdout.strip()}")
                else:
                    lines.append(f"  ✗ [{cname}] vllm 없음")
        except Exception:
            lines.append("  (docker 없음 또는 권한 필요)")
        lines.append("")

        # ── 4. 권장 실행 명령 ─────────────────────
        lines.append("")
        lines.append("=== 권장 실행 명령 (✓ 경로 사용) ===")
        vllm_py = next((l.split(" | ")[0].replace("✓ ", "")
                        for l in lines if l.startswith("✓")), "python3")
        models = fetch_models(self.host, self.port)
        model  = models[0] if models else "<모델경로>"
        parser, _ = detect_parser(model)
        lines.append(
            f"{vllm_py} -m vllm.entrypoints.openai.api_server \\\n"
            f"  --model {model} \\\n"
            f"  --host {self.host} --port {self.port} \\\n"
            f"  --enable-auto-tool-choice \\\n"
            f"  --tool-call-parser {parser}"
        )
        log.info("find_vllm 완료: %d줄", len(lines))
        return "\n".join(lines)

    def tool_support_info(self) -> str:
        from .model_detect import probe_tool_support, suggest_restart_cmd
        log.debug("tool_support_info 조회")
        try:
            models  = fetch_models(self.host, self.port)
            if not models:
                return "[오류] 서버 연결 불가 또는 모델 없음"
            model   = models[0]
            parser, desc = detect_parser(model)
            support = probe_tool_support(self.host, self.port, model)
            log.info("tool_support_info: model=%s parser=%s supported=%s", model, parser, support)
            status  = "✓ 지원됨" if support else "✗ 미지원"
            suggest = "" if support else (
                "\n\n=== 해결: 서버 재시작 명령 ===\n"
                + suggest_restart_cmd(self.host, self.port, model)
            )
            return (f"모델:   {model}\n계열:   {desc}\n"
                    f"parser: {parser}\nTool Calling: {status}{suggest}")
        except Exception:
            log.error("tool_support_info 실패", exc_info=True)
            return "[오류] tool 지원 여부 조회 실패"
