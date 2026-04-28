#!/usr/bin/env python3
"""
syscheck.py — Ubuntu vLLM 개발 환경 조사 + 모델 추천
stdlib only, 외부 의존성 없음.

실행:
  python3 syscheck.py
  python3 syscheck.py --json    # JSON 출력
  python3 syscheck.py --brief   # 요약만
"""
import argparse, json, os, platform, re, shutil, socket, subprocess, sys
from pathlib import Path

# ── 유틸 ─────────────────────────────────────
def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, text=True, timeout=timeout,
                           capture_output=True)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"(오류: {e})"

def _first(text, pattern, group=1, default="unknown"):
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(group).strip() if m else default

def _mb(text, pattern):
    m = re.search(pattern, text, re.IGNORECASE)
    if not m: return 0
    v = float(m.group(1).replace(",", ""))
    u = m.group(2).upper() if len(m.groups()) >= 2 else "MB"
    return int(v * {"KB": 0.001, "MB": 1, "GB": 1024, "TB": 1024**2}.get(u, 1))

SEP  = "─" * 60
SEP2 = "━" * 60


# ── 1. OS / 커널 ──────────────────────────────
def check_os():
    info = {}
    info["os"]       = platform.platform()
    info["kernel"]   = platform.release()
    info["arch"]     = platform.machine()
    info["hostname"] = socket.gethostname()
    # /etc/os-release
    osr = Path("/etc/os-release")
    if osr.exists():
        txt = osr.read_text()
        info["distro"] = _first(txt, r'^PRETTY_NAME="?([^"\n]+)"?', default="")
    info["python"] = sys.version.split()[0]
    return info


# ── 2. CPU ────────────────────────────────────
def check_cpu():
    info = {}
    lscpu = _run("lscpu")
    info["model"]   = _first(lscpu, r"Model name\s*:\s*(.+)")
    info["cores"]   = _first(lscpu, r"CPU\(s\)\s*:\s*(\d+)")
    info["threads"] = _first(lscpu, r"Thread\(s\) per core\s*:\s*(\d+)")
    info["arch"]    = _first(lscpu, r"Architecture\s*:\s*(\S+)")
    # /proc/cpuinfo fallback
    if info["model"] == "unknown":
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            info["model"] = _first(cpuinfo.read_text(), r"model name\s*:\s*(.+)")
    return info


# ── 3. RAM ────────────────────────────────────
def check_ram():
    free = _run("free -m")
    m = re.search(r"Mem:\s+(\d+)\s+(\d+)\s+(\d+)", free)
    if m:
        total, used, avail = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return {"total_mb": total, "used_mb": used, "free_mb": avail,
                "total_gb": round(total/1024, 1)}
    # /proc/meminfo fallback
    mem = Path("/proc/meminfo")
    if mem.exists():
        txt = mem.read_text()
        total = _first(txt, r"MemTotal:\s+(\d+)")
        avail = _first(txt, r"MemAvailable:\s+(\d+)")
        try:
            total_mb = int(total) // 1024
            avail_mb = int(avail) // 1024
            return {"total_mb": total_mb, "free_mb": avail_mb,
                    "total_gb": round(total_mb/1024, 1)}
        except Exception:
            pass
    return {}


# ── 4. Disk ───────────────────────────────────
def check_disk():
    df = _run("df -h /")
    m = re.search(r"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+/\s*$", df, re.MULTILINE)
    if m:
        return {"total": m.group(2), "used": m.group(3),
                "avail": m.group(4), "pct": m.group(5)}
    return {}


# ── 5. GPU ────────────────────────────────────
def check_gpu():
    gpus = []
    smi  = _run("nvidia-smi --query-gpu=index,name,memory.total,memory.free,driver_version,compute_cap --format=csv,noheader,nounits", timeout=10)
    if "NVIDIA" in smi or re.search(r"\d+,\s*", smi):
        for line in smi.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "index":   parts[0],
                    "name":    parts[1],
                    "vram_mb": int(parts[2]) if parts[2].isdigit() else 0,
                    "vram_free_mb": int(parts[3]) if parts[3].isdigit() else 0,
                    "driver":  parts[4],
                    "compute": parts[5],
                })
    if not gpus:
        # ROCm (AMD)
        rocm = _run("rocm-smi --showmeminfo vram --csv", timeout=10)
        if "GPU" in rocm:
            gpus.append({"name": "AMD GPU (ROCm)", "vram_mb": 0, "note": rocm[:100]})
    return gpus


# ── 6. CUDA / cuDNN ───────────────────────────
def check_cuda():
    info = {}
    nvcc  = _run("nvcc --version")
    info["cuda_nvcc"] = _first(nvcc, r"release (\S+),")
    # nvidia-smi CUDA version
    smi = _run("nvidia-smi")
    info["cuda_driver"] = _first(smi, r"CUDA Version:\s*(\S+)")
    # cuDNN
    cudnn_h = Path("/usr/include/cudnn_version.h")
    if not cudnn_h.exists():
        cudnn_h = Path("/usr/local/cuda/include/cudnn_version.h")
    if cudnn_h.exists():
        txt = cudnn_h.read_text()
        major = _first(txt, r"CUDNN_MAJOR\s+(\d+)")
        minor = _first(txt, r"CUDNN_MINOR\s+(\d+)")
        info["cudnn"] = f"{major}.{minor}"
    return info


# ── 7. Python 환경 ────────────────────────────
def check_python():
    info = {"version": sys.version.split()[0], "executable": sys.executable}
    # venv / conda
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV")
    info["venv"] = venv or "없음"
    # pip packages (핵심만)
    pkgs = ["vllm", "torch", "transformers", "accelerate",
            "paddlepaddle", "paddleocr", "fastapi", "uvicorn"]
    installed = {}
    pip_list = _run(f"{sys.executable} -m pip list --format=columns", timeout=15)
    for pkg in pkgs:
        m = re.search(rf"^{re.escape(pkg)}\s+(\S+)", pip_list, re.IGNORECASE | re.MULTILINE)
        installed[pkg] = m.group(1) if m else None
    info["packages"] = installed
    # system Python 후보들 (vllm 설치 찾기)
    vllm_paths = []
    for py in ["python3", "python3.12", "python3.11", "python3.10", "python3.9"]:
        py_path = shutil.which(py)
        if py_path and py_path not in [v.split(" →")[0] for v in vllm_paths]:
            r = _run(f"{py_path} -c \"import vllm; print(vllm.__version__)\"", timeout=5)
            if re.match(r"\d+\.\d+", r):
                vllm_paths.append(f"{py_path} → vllm {r}")
    # venv / conda 경로
    for venv_root in [Path("/opt"), Path.home() / ".venv", Path.home() / "venv",
                      Path.home() / ".conda" / "envs"]:
        if not venv_root.exists():
            continue
        for py_cand in venv_root.rglob("bin/python3"):
            r = _run(f"{py_cand} -c \"import vllm; print(vllm.__version__)\"", timeout=5)
            if re.match(r"\d+\.\d+", r):
                vllm_paths.append(f"{py_cand} → vllm {r}")
    # Docker 컨테이너 내 vLLM 탐색
    docker_vllm = []
    containers_out = _run("docker ps --format '{{.Names}}' 2>/dev/null", timeout=5)
    for cname in containers_out.splitlines():
        cname = cname.strip()
        if not cname:
            continue
        r = _run(
            f"docker exec {cname} python3 -c "
            f"\"import vllm; print(vllm.__version__)\" 2>/dev/null",
            timeout=8,
        )
        if re.match(r"\d+\.\d+", r):
            py_in = _run(
                f"docker exec {cname} which python3 2>/dev/null", timeout=5
            ).strip() or "python3"
            docker_vllm.append({
                "container": cname,
                "python": py_in,
                "vllm_version": r.strip(),
            })
    info["vllm_locations"] = vllm_paths
    info["docker_vllm"] = docker_vllm
    return info


# ── 8. 모델 경로 탐색 ─────────────────────────
def check_models():
    search_roots = [
        Path("/models"), Path("/mnt"), Path("/data"),
        Path.home() / "models", Path.home() / "dev" / "model",
        Path("/home/archiv/dev/model"),
    ]
    model_dirs = []
    seen_resolved = set()
    for root in search_roots:
        if not root.exists():
            continue
        try:
            root_real = root.resolve()
            if root_real in seen_resolved:
                continue
            seen_resolved.add(root_real)
            for d in sorted(root.iterdir()):
                if not d.is_dir():
                    continue
                d_real = d.resolve()
                if d_real in seen_resolved:
                    continue
                if any((d / f).exists() for f in
                        ["config.json", "tokenizer.json", "pytorch_model.bin",
                         "model.safetensors"]):
                    seen_resolved.add(d_real)
                    size = _run(f"du -sh {d} 2>/dev/null | cut -f1", timeout=5)
                    model_dirs.append({"path": str(d), "size": size.strip()})
        except PermissionError:
            pass
    return model_dirs


# ── 9. 네트워크 / 포트 ────────────────────────
def check_network():
    info = {}
    # IP
    ip_out = _run("ip addr show 2>/dev/null || ifconfig 2>/dev/null")
    ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", ip_out)
    info["ips"] = [ip for ip in ips if not ip.startswith("127.")]
    # vLLM 관련 포트
    ss = _run("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    ports = re.findall(r":(\d{4,5})\s", ss)
    vllm_ports = [p for p in set(ports)
                  if int(p) in [8000,8001,8080,8090,8100,8200,8300,8500,11434]]
    info["listening_vllm_ports"] = sorted(vllm_ports, key=int)
    return info


# ── 10. Docker ───────────────────────────────
def check_docker():
    info = {}
    docker = _run("docker --version 2>/dev/null")
    info["installed"] = "Docker" in docker
    info["version"]   = _first(docker, r"Docker version (\S+,)", default="")
    if info["installed"]:
        info["running"] = _run("docker ps --format '{{.Names}}' 2>/dev/null")
    return info


# ── 모델 추천 ─────────────────────────────────
def recommend_models(gpus, ram, py_info):
    recs = []

    total_vram = sum(g.get("vram_mb", 0) for g in gpus)
    total_ram  = ram.get("total_mb", 0)
    vllm_ok    = bool(py_info.get("vllm_locations"))

    def add(name, model_id, vram_req, parser, reason, flags=""):
        recs.append({
            "name": name, "model_id": model_id,
            "vram_req_gb": vram_req, "parser": parser,
            "reason": reason, "flags": flags,
            "available": total_vram >= vram_req * 1024 or vram_req == 0,
        })

    if not gpus:
        add("CPU 전용 (소형)", "Qwen/Qwen2.5-0.5B-Instruct", 0,
            "hermes", "GPU 없음 — CPU 추론 가능한 최소 모델", "--device cpu")
        return recs

    # GPU 기준 추천
    if total_vram >= 80 * 1024:
        add("Llama-3.1-70B-Instruct", "meta-llama/Llama-3.1-70B-Instruct",
            70, "llama3", "대형 모델 — 최고 성능")
        add("Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-72B-Instruct",
            65, "hermes", "대형 모델 — 한국어 우수")

    if total_vram >= 40 * 1024:
        add("Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-32B-Instruct",
            35, "hermes", "중대형 — 한국어 강점, Tool Calling 우수")
        add("Llama-3.3-70B (4bit)", "bartowski/Meta-Llama-3.3-70B-Instruct-GGUF",
            40, "llama3", "70B 4비트 양자화")

    if total_vram >= 20 * 1024:
        add("Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-14B-Instruct",
            15, "hermes", "균형잡힌 성능, Tool Calling 지원")
        add("Llama-3.1-8B-Instruct (멀티GPU)", "meta-llama/Llama-3.1-8B-Instruct",
            8, "llama3", "경량 고성능")

    if total_vram >= 10 * 1024:
        add("Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-7B-Instruct",
            8, "hermes", "7B 최고수준 Tool Calling")
        add("Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-8B-Instruct",
            8, "llama3", "Tool Calling 검증 모델")
        add("DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
            8, "hermes", "추론 특화 (tool call 미지원, 분석용)")

    if total_vram >= 6 * 1024:
        add("Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-3B-Instruct",
            4, "hermes", "경량 — Tool Calling 가능")

    if total_vram >= 4 * 1024:
        add("Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct",
            2, "hermes", "초경량 — 폐쇄망 최소 사양")

    return recs


# ── 출력 ─────────────────────────────────────
def print_report(data, brief=False):
    os_i   = data["os"]
    cpu    = data["cpu"]
    ram    = data["ram"]
    disk   = data["disk"]
    gpus   = data["gpus"]
    cuda   = data["cuda"]
    py_i   = data["python"]
    models = data["models"]
    net    = data["network"]
    docker = data["docker"]
    recs   = data["recommendations"]

    print(f"\n{SEP2}")
    print(" vLLM 개발 환경 조사 리포트")
    print(SEP2)

    # OS
    print(f"\n{'[ OS / 시스템 ]'}")
    print(f"  OS      : {os_i.get('distro') or os_i.get('os')}")
    print(f"  커널    : {os_i['kernel']}  ({os_i['arch']})")
    print(f"  호스트  : {os_i['hostname']}")
    print(f"  Python  : {os_i['python']}")

    if not brief:
        # CPU
        print(f"\n[ CPU ]")
        print(f"  모델    : {cpu.get('model')}")
        print(f"  코어    : {cpu.get('cores')} (아키텍처: {cpu.get('arch')})")

    # RAM
    print(f"\n[ RAM ]")
    r = ram
    if r:
        pct = int(r.get("used_mb",0) / r.get("total_mb",1) * 100) if r.get("total_mb") else 0
        print(f"  전체    : {r.get('total_gb')}GB  사용: {r.get('used_mb',0)//1024}GB  여유: {r.get('free_mb',0)//1024}GB  ({pct}%)")

    # Disk
    if disk:
        print(f"\n[ Disk (/) ]")
        print(f"  전체: {disk.get('total')}  사용: {disk.get('used')}  여유: {disk.get('avail')}  ({disk.get('pct')})")

    # GPU
    print(f"\n[ GPU ]")
    if gpus:
        for g in gpus:
            vram_gb = round(g.get("vram_mb", 0) / 1024, 1)
            free_gb = round(g.get("vram_free_mb", 0) / 1024, 1)
            print(f"  [{g.get('index','?')}] {g.get('name')}")
            print(f"       VRAM: {vram_gb}GB  여유: {free_gb}GB"
                  f"  드라이버: {g.get('driver','')}  Compute: {g.get('compute','')}")
        total_vram = sum(g.get("vram_mb", 0) for g in gpus) / 1024
        print(f"  ─ 합계 VRAM: {round(total_vram, 1)}GB")
    else:
        print("  GPU 없음 (nvidia-smi 미응답)")

    # CUDA
    print(f"\n[ CUDA ]")
    print(f"  CUDA (드라이버) : {cuda.get('cuda_driver','unknown')}")
    print(f"  CUDA (nvcc)     : {cuda.get('cuda_nvcc','unknown')}")
    print(f"  cuDNN           : {cuda.get('cudnn','unknown')}")

    # Python / 패키지
    print(f"\n[ Python 환경 ]")
    print(f"  실행 경로  : {py_i['executable']}")
    print(f"  가상환경   : {py_i['venv']}")
    pkgs = py_i.get("packages", {})
    print(f"  패키지 현황:")
    for k, v in pkgs.items():
        mark = "✓" if v else "✗"
        print(f"    {mark} {k:<20s} {v or '미설치'}")
    if py_i.get("vllm_locations"):
        print(f"  vLLM 설치 경로:")
        for loc in py_i["vllm_locations"]:
            print(f"    → {loc}")
    if py_i.get("docker_vllm"):
        print(f"  Docker 컨테이너 내 vLLM:")
        for dv in py_i["docker_vllm"]:
            print(f"    → [{dv['container']}] {dv['python']} → vllm {dv['vllm_version']}")

    # 모델 경로
    if models:
        print(f"\n[ 발견된 모델 경로 ]")
        for m in models[:10]:
            print(f"  {m['size']:>6s}  {m['path']}")

    # 네트워크
    print(f"\n[ 네트워크 ]")
    print(f"  IP        : {', '.join(net.get('ips', [])) or '없음'}")
    vports = net.get("listening_vllm_ports", [])
    print(f"  vLLM 포트 : {', '.join(vports) if vports else '없음 (서버 미실행)'}")

    # Docker
    if not brief:
        print(f"\n[ Docker ]")
        d = docker
        print(f"  설치: {'✓ ' + d.get('version','') if d.get('installed') else '✗ 미설치'}")
        if d.get("running"):
            print(f"  실행 중 컨테이너:\n    {d['running']}")

    # ── 모델 추천 ──────────────────────────────
    print(f"\n{SEP2}")
    print(" [ vLLM 모델 추천 — Tool Calling 지원 ]")
    print(SEP2)

    avail = [r for r in recs if r["available"]]
    unavail = [r for r in recs if not r["available"]]

    # 실행 가능한 Python 경로 결정
    py_exec = "python3"
    vllm_locs = py_i.get("vllm_locations", [])
    docker_vllm = py_i.get("docker_vllm", [])
    if vllm_locs:
        # system/venv Python에 vllm 있는 경우
        py_exec = vllm_locs[0].split(" →")[0].strip()
    elif docker_vllm:
        # Docker 컨테이너에만 있는 경우
        dv = docker_vllm[0]
        print(f"\n  ⚠  vLLM이 Docker 컨테이너 [{dv['container']}] 내부에만 설치되어 있습니다.")
        print(f"     아래 명령은 컨테이너 중지 후 호스트에 vLLM 설치 시 사용 가능합니다.")
        print(f"     또는: docker exec {dv['container']} python3 -m vllm.entrypoints.openai.api_server ...")
        py_exec = dv["python"]
    else:
        print(f"\n  ⚠  vLLM 미설치 — 먼저 pip install vllm 필요")
        print(f"     (또는 Docker 컨테이너 내 python3 사용)")

    if avail:
        print("\n  ✓ 현재 환경에서 실행 가능:\n")
        for r in avail:
            vram_s = f"{r['vram_req_gb']}GB" if r['vram_req_gb'] else "CPU"
            print(f"  [{vram_s:>5s}] {r['name']}")
            print(f"         ID     : {r['model_id']}")
            print(f"         parser : {r['parser']}")
            print(f"         이유   : {r['reason']}")
            flags = r['flags'] or "--enable-auto-tool-choice --tool-call-parser " + r['parser']
            print(f"         실행   : {py_exec} -m vllm.entrypoints.openai.api_server \\")
            print(f"                    --model {r['model_id']} \\")
            print(f"                    --port 8200 \\")
            print(f"                    {flags}")
            print()

    if unavail and not brief:
        print(f"\n  ✗ VRAM 부족 (참고용):")
        for r in unavail:
            print(f"    [{r['vram_req_gb']}GB] {r['name']} — {r['reason']}")

    print(SEP2)


# ── main ─────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="vLLM 개발 환경 조사")
    ap.add_argument("--json",  action="store_true", help="JSON 출력")
    ap.add_argument("--brief", action="store_true", help="요약만 출력")
    args = ap.parse_args()

    print("환경 조사 중...", flush=True)

    data = {
        "os":      check_os(),
        "cpu":     check_cpu(),
        "ram":     check_ram(),
        "disk":    check_disk(),
        "gpus":    check_gpu(),
        "cuda":    check_cuda(),
        "python":  check_python(),
        "models":  check_models(),
        "network": check_network(),
        "docker":  check_docker(),
    }
    data["recommendations"] = recommend_models(
        data["gpus"], data["ram"], data["python"]
    )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_report(data, brief=args.brief)


if __name__ == "__main__":
    main()
