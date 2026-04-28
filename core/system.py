"""SystemManager — 시스템/네트워크/프로세스/서비스/cron/데몬 제어 (stdlib only)"""
import os, re, subprocess, signal, socket, time, tempfile
from pathlib import Path
from .logger import get_logger

log = get_logger(__name__)

# ── 위험 패턴 차단 ────────────────────────────
_BLOCKED = re.compile(
    r"\b(rm\s+-rf\s+/|mkfs|dd\s+if=|:(){ :|:&};:|chmod\s+777\s+/|>\s*/dev/[sh]d)\b",
    re.IGNORECASE,
)


def shell_exec(cmd: str, timeout: int = 30, workdir: str = None) -> str:
    """쉘 명령 실행. 위험 패턴 자동 차단. stdout+stderr 최대 8000자."""
    if _BLOCKED.search(cmd):
        log.warning("shell_exec 차단: %s", cmd)
        return f"[차단] 위험 명령 패턴: {cmd}"
    wd = Path(workdir).expanduser() if workdir else None
    log.debug("shell_exec: %s (timeout=%d cwd=%s)", cmd, timeout, wd)
    try:
        r = subprocess.run(
            cmd, shell=True, text=True, timeout=timeout,
            capture_output=True, cwd=wd,
        )
        out = ((r.stdout or "") + (r.stderr or ""))[:8000]
        if r.returncode != 0:
            log.debug("shell_exec 비정상 종료: code=%d cmd=%s", r.returncode, cmd)
        return out or f"(출력 없음, 종료코드 {r.returncode})"
    except subprocess.TimeoutExpired:
        log.warning("shell_exec 타임아웃: %ds  cmd=%s", timeout, cmd)
        return f"[타임아웃] {timeout}s 초과: {cmd}"
    except Exception:
        log.error("shell_exec 예외: %s", cmd, exc_info=True)
        return f"[오류] 실행 실패: {cmd}"


class SystemManager:

    # ── 시스템 정보 ───────────────────────────
    def system_info(self) -> str:
        log.debug("system_info 호출")
        parts = ["=== 시스템 ==="]
        try:
            parts.append(self._sh("uname -a"))
            parts.append(self._sh("cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION)='"))
            parts.append(f"호스트명: {socket.gethostname()}")
            parts.append(f"업타임: {self._uptime()}")
            parts += ["\n=== CPU ===", self._cpu()]
            parts += ["\n=== 메모리 ===", self._mem()]
            parts += ["\n=== 디스크 ===",
                      self._sh("df -h --output=source,size,used,avail,pcent,target 2>/dev/null || df -h")]
        except Exception:
            log.error("system_info 실패", exc_info=True)
        return "\n".join(p for p in parts if p.strip())

    def _uptime(self) -> str:
        try:
            secs = float(Path("/proc/uptime").read_text().split()[0])
            h, rem = divmod(int(secs), 3600)
            return f"{h}h {rem//60}m"
        except Exception:
            log.debug("_uptime /proc 읽기 실패", exc_info=True)
            return self._sh("uptime -p 2>/dev/null || uptime")

    def _cpu(self) -> str:
        lines = []
        try:
            txt = Path("/proc/cpuinfo").read_text()
            for l in txt.splitlines():
                if "model name" in l:
                    lines.append(l.split(":", 1)[1].strip()); break
            n = sum(1 for l in txt.splitlines() if l.startswith("processor"))
            lines.append(f"코어: {n}")
            avg = Path("/proc/loadavg").read_text().split()[:3]
            lines.append(f"load avg: {' '.join(avg)}")
        except Exception:
            log.debug("_cpu /proc 읽기 실패", exc_info=True)
            return self._sh("lscpu 2>/dev/null | head -20")
        return "\n".join(lines)

    def _mem(self) -> str:
        try:
            info = {}
            for l in Path("/proc/meminfo").read_text().splitlines():
                if ":" in l:
                    k, v = l.split(":", 1)
                    info[k.strip()] = v.strip()
            def kb(key): return int(info.get(key, "0 kB").split()[0]) // 1024
            total, avail = kb("MemTotal"), kb("MemAvailable")
            swap_t = kb("SwapTotal")
            swap_u = swap_t - kb("SwapFree")
            return (f"전체: {total}MB  사용: {total-avail}MB  가용: {avail}MB\n"
                    f"Swap: {swap_t}MB  사용: {swap_u}MB")
        except Exception:
            log.debug("_mem /proc 읽기 실패", exc_info=True)
            return self._sh("free -m")

    # ── 네트워크 ──────────────────────────────
    def network_info(self, detail=False) -> str:
        log.debug("network_info 호출 (detail=%s)", detail)
        try:
            parts = [
                "=== 네트워크 인터페이스 ===",
                self._sh("ip addr show 2>/dev/null || ifconfig"),
                "\n=== 라우팅 테이블 ===",
                self._sh("ip route 2>/dev/null || netstat -rn"),
                "\n=== DNS ===",
                self._sh("grep -v '^#' /etc/resolv.conf 2>/dev/null"),
                "\n=== 수신 대기 포트 ===",
                self._sh("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null"),
            ]
            if detail:
                parts += ["\n=== 활성 연결 ===",
                          self._sh("ss -tnp 2>/dev/null | head -30")]
            return "\n".join(p for p in parts if p.strip())
        except Exception:
            log.error("network_info 실패", exc_info=True)
            return "[오류] 네트워크 정보 조회 실패"

    # ── 프로세스 ──────────────────────────────
    def process_list(self, keyword: str = None, sort_by: str = "cpu") -> str:
        log.debug("process_list keyword=%s sort_by=%s", keyword, sort_by)
        try:
            flag = {"cpu": "-%cpu", "mem": "-%mem", "pid": "pid"}.get(sort_by, "-%cpu")
            out  = self._sh(f"ps aux --sort={flag} 2>/dev/null || ps aux")
            lines = out.splitlines()
            if keyword:
                matched = [l for l in lines[1:] if keyword.lower() in l.lower()]
                if not matched:
                    return f"'{keyword}' 프로세스 없음"
                return (lines[0] if lines else "") + "\n" + "\n".join(matched[:50])
            return "\n".join(lines[:31])
        except Exception:
            log.error("process_list 실패", exc_info=True)
            return "[오류] 프로세스 목록 조회 실패"

    def process_info(self, pid: int) -> str:
        log.debug("process_info pid=%d", pid)
        proc = Path(f"/proc/{pid}")
        if not proc.exists():
            return f"[오류] PID {pid} 없음"
        parts = [f"=== PID {pid} ==="]
        try:
            cmdline = (proc/"cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
            parts.append(f"cmdline: {cmdline}")
            parts.append(f"cwd:     {os.readlink(proc/'cwd')}")
            parts.append(f"exe:     {os.readlink(proc/'exe')}")
            status = {}
            for l in (proc/"status").read_text().splitlines():
                if ":" in l:
                    k, v = l.split(":", 1)
                    status[k.strip()] = v.strip()
            for key in ("State", "VmRSS", "VmSize", "Threads", "PPid"):
                if key in status:
                    parts.append(f"{key}: {status[key]}")
        except Exception:
            log.error("process_info 읽기 실패: pid=%d", pid, exc_info=True)
            parts.append("[일부 정보 조회 실패 — 로그 확인]")
        return "\n".join(parts)

    def process_kill(self, pid: int, sig: str = "TERM") -> str:
        sig_map = {
            "TERM": signal.SIGTERM, "KILL": signal.SIGKILL,
            "HUP":  signal.SIGHUP,  "USR1": signal.SIGUSR1, "USR2": signal.SIGUSR2,
        }
        s = sig_map.get(sig.upper())
        if s is None:
            return f"[오류] 지원 시그널: {', '.join(sig_map)}"
        try:
            os.kill(pid, s)
            log.info("process_kill: pid=%d sig=%s", pid, sig.upper())
            return f"PID {pid} → SIG{sig.upper()} 전송"
        except ProcessLookupError:
            return f"[오류] PID {pid} 없음"
        except PermissionError:
            log.warning("process_kill 권한 없음: pid=%d", pid)
            return f"[오류] 권한 없음 (sudo 필요)"
        except Exception:
            log.error("process_kill 실패: pid=%d", pid, exc_info=True)
            return f"[오류] 시그널 전송 실패: PID {pid}"

    # ── 서비스 (systemctl) ────────────────────
    def service_control(self, action: str, name: str = "") -> str:
        log.debug("service_control action=%s name=%s", action, name)
        try:
            if action in ("list", "list-all"):
                state = "" if action == "list-all" else "--state=running"
                return self._sh(
                    f"systemctl list-units --type=service {state} --no-pager 2>/dev/null | head -60"
                )
            allowed = {"status","start","stop","restart","enable","disable",
                       "is-active","is-enabled","mask","unmask"}
            if action not in allowed:
                return f"[오류] 허용 action: {', '.join(sorted(allowed))}"
            if not name:
                return "[오류] 서비스명(name) 필요"
            result = self._sh(f"systemctl {action} {name} --no-pager 2>&1")
            log.info("service_control: %s %s", action, name)
            return result
        except Exception:
            log.error("service_control 실패: %s %s", action, name, exc_info=True)
            return f"[오류] 서비스 제어 실패: {action} {name}"

    # ── Cron ─────────────────────────────────
    def cron_list(self, user: str = "") -> str:
        log.debug("cron_list user=%s", user or "(current)")
        flag = f"-u {user}" if user else ""
        out  = self._sh(f"crontab -l {flag} 2>&1")
        if "no crontab" in out.lower():
            return f"crontab 없음{(' ('+user+')') if user else ''}"
        return f"crontab{(' ('+user+')') if user else ''}:\n{out}"

    def cron_add(self, schedule: str, command: str,
                 user: str = "", comment: str = "") -> str:
        log.debug("cron_add schedule=%s cmd=%s", schedule, command)
        try:
            flag    = f"-u {user}" if user else ""
            current = self._sh(f"crontab -l {flag} 2>/dev/null")
            if "no crontab" in current.lower():
                current = ""
            if command in current:
                return f"이미 존재: {command}"
            entry   = (f"# {comment}\n" if comment else "") + f"{schedule} {command}"
            new_tab = (current.rstrip() + "\n" + entry + "\n").lstrip()
            result  = self._write_crontab(new_tab, user)
            log.info("cron_add: %s %s", schedule, command)
            return f"cron 추가:\n  {entry}\n{result}"
        except Exception:
            log.error("cron_add 실패", exc_info=True)
            return "[오류] cron 추가 실패"

    def cron_remove(self, pattern: str, user: str = "") -> str:
        log.debug("cron_remove pattern=%s user=%s", pattern, user)
        try:
            flag    = f"-u {user}" if user else ""
            current = self._sh(f"crontab -l {flag} 2>/dev/null")
            if "no crontab" in current.lower() or not current.strip():
                return "crontab 없음"
            lines  = current.splitlines()
            kept   = [l for l in lines if not re.search(pattern, l)]
            removed = [l for l in lines if re.search(pattern, l)]
            if not removed:
                return f"패턴 '{pattern}' 해당 항목 없음"
            result = self._write_crontab("\n".join(kept) + "\n", user)
            log.info("cron_remove: %d항목 삭제 pattern=%s", len(removed), pattern)
            return f"제거 {len(removed)}개:\n" + "\n".join(f"  {l}" for l in removed) + f"\n{result}"
        except re.error as e:
            log.warning("cron_remove 정규식 오류: %s", e)
            return f"[오류] 정규식: {e}"
        except Exception:
            log.error("cron_remove 실패", exc_info=True)
            return "[오류] cron 삭제 실패"

    def cron_replace(self, new_crontab: str, user: str = "") -> str:
        log.debug("cron_replace user=%s", user or "(current)")
        try:
            result = self._write_crontab(new_crontab, user)
            log.info("cron_replace 완료")
            return f"crontab 전체 교체 완료\n{result}"
        except Exception:
            log.error("cron_replace 실패", exc_info=True)
            return "[오류] crontab 교체 실패"

    @staticmethod
    def _write_crontab(content: str, user: str = "") -> str:
        flag = f"-u {user}" if user else ""
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".cron", delete=False) as tf:
                tf.write(content); tmp = tf.name
            r = subprocess.run(f"crontab {flag} {tmp}", shell=True,
                               capture_output=True, text=True)
            os.unlink(tmp)
            if r.returncode != 0:
                log.warning("_write_crontab 실패: %s", r.stderr.strip())
            return "적용 성공" if r.returncode == 0 else f"[오류] {r.stderr.strip()}"
        except Exception:
            log.error("_write_crontab 예외", exc_info=True)
            return "[오류] crontab 파일 쓰기 실패"

    # ── 데몬 (systemd) ────────────────────────
    def daemon_create(self, name: str, exec_start: str,
                      description: str = "", user: str = "",
                      working_dir: str = "", after: str = "network.target",
                      restart: str = "on-failure", restart_sec: int = 5,
                      env_vars: str = "", extra_service: str = "",
                      wanted_by: str = "multi-user.target",
                      enable: bool = False) -> str:
        log.debug("daemon_create name=%s exec=%s", name, exec_start)
        unit_path = Path(f"/etc/systemd/system/{name}.service")
        env_lines = "\n".join(
            f"Environment={e.strip()}" for e in env_vars.split() if e.strip()
        ) if env_vars else ""
        content = re.sub(r"\n{3,}", "\n\n", (
            f"[Unit]\nDescription={description or name}\nAfter={after}\n\n"
            f"[Service]\n"
            f"{'User='+user+chr(10) if user else ''}"
            f"{'WorkingDirectory='+working_dir+chr(10) if working_dir else ''}"
            f"ExecStart={exec_start}\nRestart={restart}\nRestartSec={restart_sec}\n"
            f"{env_lines+chr(10) if env_lines else ''}"
            f"{extra_service+chr(10) if extra_service else ''}"
            f"StandardOutput=journal\nStandardError=journal\n\n"
            f"[Install]\nWantedBy={wanted_by}\n"
        ))
        try:
            unit_path.write_text(content)
            log.info("daemon_create: %s 생성", unit_path)
        except PermissionError:
            tmp = Path(f"/tmp/{name}.service")
            tmp.write_text(content)
            log.warning("daemon_create 권한 없음 — /tmp 에 저장: %s", tmp)
            return (f"[권한 없음] /tmp/{name}.service 에 저장됨.\n"
                    f"  sudo cp /tmp/{name}.service /etc/systemd/system/\n"
                    f"  sudo systemctl daemon-reload\n"
                    f"  sudo systemctl enable --now {name}\n\n"
                    f"=== unit 파일 ===\n{content}")
        except Exception:
            log.error("daemon_create 실패: %s", name, exc_info=True)
            return f"[오류] unit 파일 생성 실패: {name}"

        result = [f"생성: {unit_path}",
                  f"daemon-reload: {self._sh('systemctl daemon-reload 2>&1') or 'OK'}"]
        if enable:
            r = self._sh(f"systemctl enable --now {name} 2>&1")
            log.info("daemon_create enable: %s", r)
            result.append(f"enable: {r}")
        result.append(f"\n=== {unit_path} ===\n{content}")
        return "\n".join(result)

    def daemon_list(self) -> str:
        log.debug("daemon_list 호출")
        try:
            lines = [self._sh(
                "systemctl list-unit-files --type=service --no-pager 2>/dev/null | head -60"
            )]
            sd = Path("/etc/systemd/system")
            if sd.exists():
                custom = sorted(sd.glob("*.service"))
                if custom:
                    lines.append(f"\n/etc/systemd/system 커스텀 ({len(custom)}개):")
                    lines += [f"  {p.name}" for p in custom]
            return "\n".join(lines)
        except Exception:
            log.error("daemon_list 실패", exc_info=True)
            return "[오류] 데몬 목록 조회 실패"

    @staticmethod
    def _sh(cmd: str, timeout: int = 10) -> str:
        try:
            r = subprocess.run(cmd, shell=True, text=True,
                               timeout=timeout, capture_output=True)
            return (r.stdout + r.stderr).strip()[:4000]
        except subprocess.TimeoutExpired:
            log.warning("_sh 타임아웃: %s", cmd)
            return f"[타임아웃] {cmd}"
        except Exception:
            log.error("_sh 예외: %s", cmd, exc_info=True)
            return f"[오류] {cmd}"
