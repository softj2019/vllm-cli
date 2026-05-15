"""SwitchManager — OCR / CLI LLM 모드 전환 (Docker 컨테이너 교체)"""
import json, subprocess, time
from pathlib import Path
from typing import Optional, Tuple
from .logger import get_logger

log = get_logger(__name__)

_CFG = Path(__file__).resolve().parent.parent / "switch.json"

DEFAULT_CFG: dict = {
    "current": "ocr",
    "ocr": {
        "container": "pro",
        "host": "localhost",
        "port": 8100,
        "model": "prov",
        "compose_dir": "/home/archiv/ai"
    },
    "cli": {
        "container": "cli-llm",
        "host": "localhost",
        "port": 8200,
        "model": "Qwen2.5-7B-Instruct",
        "model_path": "/home/archiv/dev/model/Qwen2.5-7B-Instruct",
        "docker_image": "vllm/vllm-openai:latest",
        "tool_parser": "hermes",
        "gpu_device": "0",
        "docker_network": "arch-net"
    }
}


class SwitchManager:
    def __init__(self):
        self.cfg = self._load()

    def _load(self) -> dict:
        if _CFG.exists():
            try:
                return json.loads(_CFG.read_text())
            except Exception:
                log.warning("switch.json 파싱 실패 — 기본값 사용")
        return DEFAULT_CFG.copy()

    def _save(self):
        try:
            _CFG.write_text(json.dumps(self.cfg, indent=2, ensure_ascii=False))
        except Exception as e:
            log.warning("switch.json 저장 실패: %s", e)

    def _docker(self, *args) -> Tuple[int, str]:
        try:
            r = subprocess.run(
                ["docker"] + list(args),
                capture_output=True, text=True, timeout=60
            )
            return r.returncode, (r.stdout + r.stderr).strip()
        except FileNotFoundError:
            return -1, "docker 명령 없음"
        except Exception as e:
            return -1, str(e)

    def _is_running(self, container: str) -> bool:
        code, out = self._docker(
            "ps", "--filter", f"name=^{container}$", "--format", "{{.Names}}"
        )
        return container in out

    def _container_exists(self, container: str) -> bool:
        code, out = self._docker(
            "ps", "-a", "--filter", f"name=^{container}$", "--format", "{{.Names}}"
        )
        return container in out

    # ── 컨테이너 중지 (GPU 전환용) ───────────────
    def _stop(self, cfg: dict) -> str:
        container = cfg.get("container", "")
        if not container:
            return "  [중지] 컨테이너 미설정"
        if not self._is_running(container):
            return f"  [{container}] 이미 중지됨"
        print(f"  [{container}] 중지 중...", end="", flush=True)
        code, out = self._docker("stop", container)
        if code == 0:
            print(" 완료")
            return f"  [{container}] 중지 완료"
        print(" 실패")
        return f"  [{container}] 중지 실패: {out[:100]}"

    # ── compose 전체 종료 (OCR 전체 스택) ────────
    def compose_down(self) -> str:
        """docker compose down — front-ocr/mask-ocr/api-ai/engine-ai 전체 종료"""
        import os
        compose_dir = self.cfg.get("ocr", {}).get("compose_dir", "")
        if not compose_dir:
            return "[오류] switch.json 의 ocr.compose_dir 미설정"
        patterns = [
            os.path.join(compose_dir, "docker-compose.yml"),
            os.path.join(compose_dir, "docker-compose.yaml"),
            os.path.join(compose_dir, "docker-compose-online.yml"),
        ]
        compose_file = next((p for p in patterns if os.path.isfile(p)), None)
        cmd = (["docker", "compose", "-f", compose_file, "down"]
               if compose_file else
               ["docker", "compose", "--project-directory", compose_dir, "down"])
        print(f"  [compose down] ...", end="", flush=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                print(" 완료")
                return "  compose down 완료"
            print(" 실패")
            return f"  compose down 실패: {(r.stdout+r.stderr).strip()[:200]}"
        except Exception as e:
            print(" 오류")
            return f"  compose down 오류: {e}"

    # ── OCR 컨테이너 시작 ─────────────────────────
    def _start_ocr(self, cfg: dict) -> str:
        container = cfg["container"]
        if self._is_running(container):
            return f"  [{container}] 이미 실행 중"

        # 중지된 컨테이너 재시작
        if self._container_exists(container):
            print(f"  [{container}] 시작 중...", end="", flush=True)
            code, out = self._docker("start", container)
            if code == 0:
                print(" 완료")
                time.sleep(3)
                return f"  [{container}] 시작 완료 → {cfg['host']}:{cfg['port']}"
            print(" 실패")
            return f"  [{container}] 시작 실패: {out[:100]}\n  수동: docker start {container}"

        # 컨테이너 없음 → start_cmd 로 재생성
        start_cmd = cfg.get("start_cmd", "")
        if start_cmd:
            print(f"  [{container}] 재생성 중...", end="", flush=True)
            try:
                r = subprocess.run(start_cmd, shell=True, capture_output=True,
                                   text=True, timeout=120)
                if r.returncode == 0:
                    print(" 완료")
                    time.sleep(5)
                    return f"  [{container}] 재생성 완료 → {cfg['host']}:{cfg['port']}"
                print(" 실패")
                return f"  [{container}] 재생성 실패: {(r.stdout+r.stderr).strip()[:150]}"
            except Exception as e:
                print(" 오류")
                return f"  [{container}] 재생성 오류: {e}"

        return (
            f"  [{container}] 컨테이너 없음\n"
            f"  switch.json 의 ocr.start_cmd 에 docker run 명령을 설정하거나\n"
            f"  수동으로 실행: docker run -d --name {container} ..."
        )

    # ── CLI LLM 컨테이너 시작 ─────────────────────
    def _start_cli(self, cfg: dict) -> str:
        container = cfg["container"]
        model_path = cfg.get("model_path", "")
        port       = cfg["port"]

        if self._is_running(container):
            return f"  [{container}] 이미 실행 중"

        # 중지된 컨테이너 재시작 시도
        if self._container_exists(container):
            print(f"  [{container}] 재시작 중...", end="", flush=True)
            code, out = self._docker("start", container)
            if code == 0:
                print(" 완료")
                time.sleep(5)
                return f"  [{container}] 재시작 완료 → {cfg['host']}:{port}"
            print(f" 실패 — 새 컨테이너로 재시도")
            self._docker("rm", container)

        if not model_path:
            return (
                f"  [오류] CLI LLM 모델 경로 미설정\n"
                f"  switch.json 의 cli.model_path 를 실제 경로로 수정하세요\n"
                f"  예: /home/archiv/dev/model/Qwen2.5-7B-Instruct"
            )

        model_dir  = str(Path(model_path).parent)
        model_name = Path(model_path).name
        parser     = cfg.get("tool_parser", "hermes")
        gpu        = cfg.get("gpu_device", "0")
        image      = cfg.get("docker_image", "vllm/vllm-openai:latest")
        network    = cfg.get("docker_network", "arch-net")

        print(f"  [{container}] 새 컨테이너 기동 중...", end="", flush=True)
        code, out = self._docker(
            "run", "-d",
            "--gpus", f"device={gpu}",
            "--name", container,
            "--network", network,
            "-p", f"{port}:{port}",
            "-v", f"{model_dir}:/models",
            "--restart", "unless-stopped",
            image,
            "--model", f"/models/{model_name}",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--enable-auto-tool-choice",
            "--tool-call-parser", parser,
        )
        if code == 0:
            print(" 완료")
            time.sleep(5)
            return f"  [{container}] 기동 완료 → {cfg['host']}:{port}"
        print(" 실패")
        return f"  [오류] 컨테이너 기동 실패:\n  {out[:200]}"

    # ── 상태 조회 ─────────────────────────────────
    def status(self) -> str:
        current  = self.cfg.get("current", "ocr")
        ocr_cfg  = self.cfg["ocr"]
        cli_cfg  = self.cfg["cli"]
        ocr_run  = self._is_running(ocr_cfg["container"])
        cli_run  = self._is_running(cli_cfg["container"])

        def mark(mode): return "▶" if current == mode else " "
        def dot(run):   return "● 실행중" if run else "○ 중지"

        return (
            f"┌─ 모드 전환 상태 ──────────────────────────────────┐\n"
            f"│ {mark('ocr')} OCR  [{ocr_cfg['container']:12s}]"
            f"  :{ocr_cfg['port']}  {ocr_cfg['model']:20s}  {dot(ocr_run)}\n"
            f"│ {mark('cli')} CLI  [{cli_cfg['container']:12s}]"
            f"  :{cli_cfg['port']}  {cli_cfg['model']:20s}  {dot(cli_run)}\n"
            f"└─────────────────────────────────────────────────────┘\n"
            f"  전환: /switch ocr  |  /switch cli  |  /switch status"
        )

    # ── 모드 전환 ─────────────────────────────────
    def switch(self, target: str) -> Tuple[str, Optional[str], Optional[int], Optional[str]]:
        """(출력메시지, host, port, model) 반환 — host/port/model 은 client 재연결용"""
        if target == "status":
            return self.status(), None, None, None
        if target not in ("ocr", "cli"):
            return (
                f"[오류] 알 수 없는 모드: {target}\n"
                "  사용법: /switch ocr | /switch cli | /switch status",
                None, None, None
            )

        current = self.cfg.get("current", "ocr")
        to_cfg  = self.cfg[target]

        if current == target:
            msg = (f"이미 {target.upper()} 모드입니다.\n"
                   f"  서버: {to_cfg['host']}:{to_cfg['port']}  모델: {to_cfg['model']}")
            return msg, to_cfg["host"], to_cfg["port"], to_cfg["model"]

        from_cfg = self.cfg[current]
        lines    = [f"=== {current.upper()} → {target.upper()} 모드 전환 ===", ""]

        # 현재 모드 컨테이너 중지
        lines.append(self._stop(from_cfg))
        time.sleep(2)

        # 대상 모드 컨테이너 시작
        if target == "ocr":
            lines.append(self._start_ocr(to_cfg))
        else:
            lines.append(self._start_cli(to_cfg))

        self.cfg["current"] = target
        self._save()

        lines += [
            "",
            f"→ 연결: {to_cfg['host']}:{to_cfg['port']}  모델: {to_cfg['model']}",
            "  서버 준비까지 30~60초 소요될 수 있습니다.",
        ]
        return "\n".join(lines), to_cfg["host"], to_cfg["port"], to_cfg["model"]
