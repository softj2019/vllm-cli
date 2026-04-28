"""Server Discovery — 폐쇄망 vLLM 서버 자동 탐색 + 인터랙티브 선택"""
import json, time, socket, subprocess, re, sys
import http.client
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from .config import API_MODELS
from .logger import get_logger

log = get_logger(__name__)

LOCAL_PORTS   = [8000, 8001, 8080, 8090, 8100, 8200, 8300, 8500, 8888, 11434, 5000, 7860]
SUBNET_PORTS  = [8100, 8000, 8080, 8200, 8300]
PROBE_TIMEOUT = 1.2
SCAN_THREADS  = 64

_CFG = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class ServerInfo:
    host: str
    port: int
    models: List[str] = field(default_factory=list)
    ms: int = -1

    @property
    def addr(self): return f"{self.host}:{self.port}"

    @property
    def label(self):
        ms_s  = f"{self.ms}ms" if self.ms >= 0 else "?"
        mlist = ", ".join(self.models[:3]) or "(모델없음)"
        trail = f" +{len(self.models)-3}" if len(self.models) > 3 else ""
        return f"{self.addr:<24s} {ms_s:>6s}   {mlist}{trail}"


def _probe(host: str, port: int, timeout=PROBE_TIMEOUT) -> Optional[ServerInfo]:
    try:
        t0   = time.monotonic()
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", API_MODELS, headers={"Authorization": "Bearer empty"})
        r  = conn.getresponse()
        ms = int((time.monotonic() - t0) * 1000)
        if r.status != 200:
            conn.close(); return None
        body = r.read().decode("utf-8", errors="replace")
        conn.close()
        try:
            models = [m.get("id", "?") for m in json.loads(body).get("data", [])]
        except Exception:
            log.debug("_probe 모델 파싱 실패: %s:%d", host, port, exc_info=True)
            models = []
        return ServerInfo(host, port, models, ms)
    except Exception:
        return None   # 연결 실패는 정상 — DEBUG 불필요


def _local_ips() -> List[str]:
    ips = []
    for cmd, pattern in [
        (["ip", "addr"],  r"inet (\d+\.\d+\.\d+)\.\d+/\d+"),
        (["ifconfig"],    r"inet (\d+\.\d+\.\d+)\.\d+"),
    ]:
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            ips += re.findall(pattern, out)
            if ips: break
        except Exception:
            pass
    if not ips:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            m  = re.match(r"(\d+\.\d+\.\d+)\.\d+", ip)
            if m: ips.append(m.group(1))
        except Exception:
            log.debug("_local_ips gethostbyname 실패", exc_info=True)
    return list({p for p in ips if not p.startswith("127.") and not p.startswith("169.")})


def _run_scan(tasks, label="  스캔", show=True) -> List[ServerInfo]:
    found, n, done = [], len(tasks), 0
    if show:
        print(f"{label} ({n}개 후보) ", end="", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=SCAN_THREADS) as ex:
            futs = {ex.submit(_probe, h, p): (h, p) for h, p in tasks}
            for fut in as_completed(futs):
                done += 1
                if show and done % max(1, n // 20) == 0:
                    print(".", end="", flush=True)
                try:
                    res = fut.result()
                    if res: found.append(res)
                except Exception:
                    log.debug("_run_scan fut.result 오류", exc_info=True)
    except Exception:
        log.error("_run_scan 실패", exc_info=True)
    if show:
        print(f" {len(found)}개 발견" if found else " 없음")
    return found


def scan_local(show_progress=True) -> List[ServerInfo]:
    return _run_scan([("localhost", p) for p in LOCAL_PORTS],
                     label="  localhost 스캔", show=show_progress)


def scan_subnet(show_progress=True) -> List[ServerInfo]:
    prefixes = _local_ips()
    if not prefixes:
        log.warning("scan_subnet: 로컬 IP 없음")
        return []
    tasks = [(f"{pfx}.{i}", port)
             for pfx in prefixes for i in range(1, 255) for port in SUBNET_PORTS]
    return _run_scan(tasks, label=f"  서브넷 스캔 ({','.join(prefixes)}.x)",
                     show=show_progress)


def discover(subnet=False, show_progress=True) -> List[ServerInfo]:
    log.info("discover 시작 (subnet=%s)", subnet)
    results = scan_local(show_progress)
    if subnet:
        results += scan_subnet(show_progress)
    seen, unique = set(), []
    for s in sorted(results, key=lambda x: x.ms):
        if s.addr not in seen:
            seen.add(s.addr); unique.append(s)
    log.info("discover 완료: %d개 서버 발견", len(unique))
    return unique


def load_cfg() -> dict:
    if _CFG.exists():
        try:
            return json.loads(_CFG.read_text())
        except Exception:
            log.warning("load_cfg 파싱 실패: %s", _CFG, exc_info=True)
    return {}


def save_cfg(host: str, port: int, model: str):
    try:
        cfg   = load_cfg()
        cfg.update({"host": host, "port": port, "model": model})
        known = cfg.get("known_servers", [])
        entry = f"{host}:{port}"
        if entry not in known:
            known.insert(0, entry)
        cfg["known_servers"] = known[:10]
        _CFG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        log.debug("save_cfg: %s:%d model=%s", host, port, model)
    except Exception:
        log.warning("save_cfg 실패 (USB 쓰기 오류?)", exc_info=True)


_SEP = "─" * 52


def _pick(prompt: str, n: int, default: int = 1) -> int:
    while True:
        try:
            raw = input(f"{prompt} [0-{n}] (Enter={default}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); sys.exit(0)
        if raw == "":
            return default
        try:
            v = int(raw)
            if 0 <= v <= n:
                return v
        except ValueError:
            pass
        print(f"  0~{n} 또는 Enter 를 입력하세요.")


def select_server_model(default_host: str, default_port: int, default_model: str,
                         subnet: bool = False, no_discover: bool = False) -> tuple:
    cfg     = load_cfg()
    d_host  = default_host  or cfg.get("host",  "localhost")
    d_port  = default_port  or cfg.get("port",  8100)
    d_model = default_model or cfg.get("model", "prov")

    if no_discover:
        log.debug("select_server_model: no_discover — 저장값 사용")
        return d_host, d_port, d_model

    print("┌─ vLLM 서버 탐색 ──────────────────────────────┐")
    servers = discover(subnet=subnet, show_progress=True)
    print("└" + _SEP[1:] + "┘")

    if not servers:
        print("\n서버를 찾지 못했습니다.")
        host, port = _prompt_host(d_host, d_port)
        log.info("수동 입력 서버: %s:%d", host, port)
        chosen = _probe(host, port, timeout=3)
        if not chosen:
            print(f"  {host}:{port} 응답 없음 — 해당 주소로 계속합니다.")
            model = _prompt_model([], d_model)
            save_cfg(host, port, model)
            return host, port, model
        servers = [chosen]

    print(f"\n발견된 서버 {len(servers)}개:")
    print(_SEP)
    for i, s in enumerate(servers, 1):
        marker = "← 이전" if s.host == cfg.get("host") and s.port == cfg.get("port") else ""
        print(f"  [{i}] {s.label}  {marker}")
    print(f"  [0] 직접 입력")
    print(_SEP)

    default_srv = 1
    for i, s in enumerate(servers, 1):
        if s.host == cfg.get("host") and s.port == cfg.get("port"):
            default_srv = i; break

    idx = _pick("서버 선택", len(servers), default=default_srv)
    if idx == 0:
        host, port = _prompt_host(d_host, d_port)
        chosen = _probe(host, port, timeout=3)
        models = chosen.models if chosen else []
    else:
        chosen = servers[idx - 1]
        host, port, models = chosen.host, chosen.port, chosen.models

    model = _prompt_model(models, cfg.get("model", d_model))
    save_cfg(host, port, model)
    log.info("선택 완료: %s:%d model=%s", host, port, model)
    return host, port, model


def _prompt_host(d_host: str, d_port: int) -> tuple:
    raw = input(f"  호스트:포트 입력 (Enter={d_host}:{d_port}): ").strip()
    if not raw:
        return d_host, d_port
    if ":" in raw:
        h, _, p = raw.rpartition(":")
        try:
            return h.strip(), int(p.strip())
        except ValueError:
            log.warning("_prompt_host 포트 파싱 실패: %s", p)
    return raw, d_port


def _prompt_model(models: List[str], default: str) -> str:
    if not models:
        raw = input(f"  모델명 입력 (Enter={default}): ").strip()
        return raw or default
    print(f"\n모델 선택:")
    print(_SEP)
    for i, m in enumerate(models, 1):
        print(f"  [{i}] {m}{'  ← 이전' if m == default else ''}")
    print(f"  [0] 직접 입력")
    print(_SEP)
    default_idx = next((i for i, m in enumerate(models, 1) if m == default), 1)
    idx = _pick("모델 선택", len(models), default=default_idx)
    if idx == 0:
        raw = input(f"  모델명 입력 (Enter={default}): ").strip()
        return raw or default
    return models[idx - 1]
