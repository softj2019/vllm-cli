#!/usr/bin/env python3
"""vLLM CLI 상태 확인 스크립트"""
import json, subprocess, socket, os

SWITCH_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "switch.json")
PORTS       = {"ocr": 8100, "cli": 8200}
CONTAINERS  = ["pro", "cli-llm", "engine-ai", "api-ai", "front-ocr", "mask-ocr"]


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


def check_port(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except Exception:
        return False


def load_switch():
    try:
        with open(SWITCH_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


def container_status(name):
    out = run(f"docker inspect --format '{{{{.State.Status}}}}' {name} 2>/dev/null")
    return out if out else "not found"


def gpu_info():
    out = run("nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits")
    if out:
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 3:
            return f"{parts[0]}MiB / {parts[1]}MiB  (GPU {parts[2]}%)"
    return "N/A"


def ram_info():
    return run("free -h | awk '/^Mem:/{print $3\"/\"$2}'") or "N/A"


def disk_info():
    return run("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\" used)\"}'") or "N/A"


def server_ip():
    return run("hostname -I | awk '{print $1}'") or "N/A"


def main():
    sw      = load_switch()
    current = sw.get("current", "?")

    print("=" * 55)
    print("  vLLM CLI 상태 확인")
    print("=" * 55)

    print(f"\n[모드]  현재: {current.upper()}")
    for mode in ("ocr", "cli"):
        mark  = "▶" if mode == current else " "
        port  = PORTS[mode]
        alive = "✓ 응답중" if check_port(port) else "✗ 미응답"
        cfg   = sw.get(mode, {})
        model = cfg.get("model") or cfg.get("model_path", "?")
        print(f"  {mark} {mode.upper():4s}  port={port}  {alive}  ({model})")

    print(f"\n[Docker 컨테이너]")
    for c in CONTAINERS:
        st   = container_status(c)
        icon = "✓" if st == "running" else "✗"
        print(f"  {icon} {c:12s}  {st}")

    print(f"\n[GPU VRAM]  {gpu_info()}")
    print(f"[RAM]       {ram_info()}")
    print(f"[디스크]    {disk_info()}")
    print(f"[서버 IP]   {server_ip()}")
    print("=" * 55)


if __name__ == "__main__":
    main()
