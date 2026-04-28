#!/usr/bin/env python3
"""
model_download.py — 하드웨어 사양 확인 후 최적 모델을 USB에 다운로드

실행:
  python3 model_download.py               # 사양 확인 + 추천 모델 선택 → 다운로드
  python3 model_download.py --check       # 사양 확인만 (다운로드 없음)
  python3 model_download.py --list        # 추천 모델 목록만 출력
  python3 model_download.py --model ID    # 모델 직접 지정
  python3 model_download.py --dest PATH   # 저장 경로 지정 (기본: ./models)
  python3 model_download.py --resume      # 이어받기 (이미 있는 파일 건너뜀)

의존성:
  huggingface_hub  (pip install huggingface_hub)
  또는 wget/aria2c (폴백)
"""
import argparse, json, os, platform, re, shutil, socket, subprocess, sys
from pathlib import Path

# ── 유틸 ─────────────────────────────────────────
def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, text=True, timeout=timeout,
                           capture_output=True)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"(오류: {e})"

SEP  = "─" * 60
SEP2 = "━" * 60

# ── 추천 모델 카탈로그 ────────────────────────────
# (model_id, name, vram_req_gb, parser, reason, extra_args)
CATALOG = [
    # ≥ 20GB VRAM
    ("Qwen/Qwen2.5-14B-Instruct",
     "Qwen2.5-14B-Instruct", 15, "hermes",
     "균형잡힌 성능 + Tool Calling 우수, 한국어 강점", ""),
    ("meta-llama/Llama-3.1-8B-Instruct",
     "Llama-3.1-8B-Instruct", 8, "llama3",
     "Tool Calling 검증 모델, 영어 최고", ""),
    # ≥ 10GB VRAM
    ("Qwen/Qwen2.5-7B-Instruct",
     "Qwen2.5-7B-Instruct", 8, "hermes",
     "7B 최고수준 Tool Calling + 한국어", ""),
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
     "DeepSeek-R1-Distill-Qwen-7B", 8, "hermes",
     "추론·분석 특화 (tool call 미지원)", ""),
    # ≥ 6GB VRAM
    ("Qwen/Qwen2.5-3B-Instruct",
     "Qwen2.5-3B-Instruct", 4, "hermes",
     "경량 — Tool Calling 가능", ""),
    # ≥ 4GB VRAM
    ("Qwen/Qwen2.5-1.5B-Instruct",
     "Qwen2.5-1.5B-Instruct", 2, "hermes",
     "초경량 — 폐쇄망 최소 사양", ""),
    # CPU 전용
    ("Qwen/Qwen2.5-0.5B-Instruct",
     "Qwen2.5-0.5B-Instruct", 0, "hermes",
     "GPU 없음 — CPU 추론 가능", "--device cpu"),
]


# ── 하드웨어 사양 조회 ────────────────────────────
def get_hw():
    """GPU VRAM 합계(MB), 여유 VRAM(MB), RAM 합계(MB) 반환"""
    total_vram = 0
    free_vram  = 0
    smi = _run(
        "nvidia-smi --query-gpu=memory.total,memory.free "
        "--format=csv,noheader,nounits", timeout=10
    )
    for line in smi.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[0].isdigit():
            total_vram += int(parts[0])
            free_vram  += int(parts[1])

    ram_mb = 0
    free_out = _run("free -m")
    m = re.search(r"Mem:\s+(\d+)", free_out)
    if m:
        ram_mb = int(m.group(1))

    # 디스크 여유 (저장 경로 기준)
    return total_vram, free_vram, ram_mb


def get_disk_free(path: Path) -> int:
    """경로의 여유 디스크 공간(MB) 반환"""
    try:
        stat = shutil.disk_usage(str(path))
        return int(stat.free / 1024 / 1024)
    except Exception:
        return 0


# ── 추천 필터링 ──────────────────────────────────
def filter_catalog(total_vram_mb: int) -> list:
    """VRAM 기준으로 실행 가능한 모델만 반환 (우선순위 순)"""
    result = []
    for entry in CATALOG:
        model_id, name, vram_req_gb, parser, reason, extra = entry
        req_mb = vram_req_gb * 1024
        if req_mb == 0 or total_vram_mb >= req_mb:
            result.append({
                "model_id": model_id,
                "name":     name,
                "vram_req_gb": vram_req_gb,
                "parser":   parser,
                "reason":   reason,
                "extra":    extra,
            })
    return result


# ── 다운로드 크기 추정 ───────────────────────────
# Hugging Face 모델 일반적 크기 (safetensors 기준, 대략)
_SIZE_HINT = {
    "Qwen2.5-14B": 28_000,   # ~28GB
    "Qwen2.5-7B":  15_000,   # ~15GB
    "Qwen2.5-3B":   6_000,
    "Qwen2.5-1.5B": 3_000,
    "Qwen2.5-0.5B": 1_000,
    "Llama-3.1-8B": 16_000,
    "DeepSeek-R1-Distill-Qwen-7B": 15_000,
}

def size_hint_mb(model_id: str) -> int:
    for key, mb in _SIZE_HINT.items():
        if key.lower() in model_id.lower():
            return mb
    return 10_000  # 기본 10GB 추정


# ── 다운로드 엔진 탐지 ───────────────────────────
def detect_downloader():
    """사용 가능한 다운로더 반환: 'hf' | 'huggingface-cli' | 'wget' | None"""
    # huggingface_hub Python 패키지
    try:
        import importlib
        importlib.import_module("huggingface_hub")
        return "hf"
    except ImportError:
        pass
    # huggingface-cli
    if shutil.which("huggingface-cli"):
        return "huggingface-cli"
    # wget
    if shutil.which("wget"):
        return "wget"
    return None


# ── 실제 다운로드 ────────────────────────────────
def download_hf(model_id: str, dest: Path, resume: bool = True, token: str = "") -> bool:
    """huggingface_hub.snapshot_download 사용"""
    try:
        from huggingface_hub import snapshot_download
        model_dir = dest / model_id.replace("/", "--")
        kwargs = {
            "repo_id":    model_id,
            "local_dir":  str(model_dir),
            "local_dir_use_symlinks": False,
        }
        if token:
            kwargs["token"] = token
        if resume:
            kwargs["ignore_patterns"] = []  # 이어받기는 기본 동작
        print(f"  다운로드 중: {model_id}")
        print(f"  저장 경로  : {model_dir}")
        snapshot_download(**kwargs)
        return True
    except Exception as e:
        print(f"  [오류] huggingface_hub: {e}")
        return False


def download_cli(model_id: str, dest: Path, resume: bool = True, token: str = "") -> bool:
    """huggingface-cli download 사용"""
    model_dir = dest / model_id.replace("/", "--")
    model_dir.mkdir(parents=True, exist_ok=True)
    tok_arg = f"--token {token}" if token else ""
    cmd = (
        f"huggingface-cli download {model_id} "
        f"--local-dir {model_dir} "
        f"--local-dir-use-symlinks False "
        f"{tok_arg}"
    )
    print(f"  다운로드 중: {model_id}")
    print(f"  명령       : {cmd}")
    ret = subprocess.run(cmd, shell=True)
    return ret.returncode == 0


def download_wget(model_id: str, dest: Path, token: str = "") -> bool:
    """wget으로 모델 파일 직접 다운로드 (safetensors 파일 목록 API 사용)"""
    import urllib.request, urllib.error
    import json as _json

    model_dir = dest / model_id.replace("/", "--")
    model_dir.mkdir(parents=True, exist_ok=True)

    # HF API로 파일 목록 조회
    api_url = f"https://huggingface.co/api/models/{model_id}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            meta = _json.loads(resp.read())
    except Exception as e:
        print(f"  [오류] 파일 목록 조회 실패: {e}")
        return False

    siblings = meta.get("siblings", [])
    files = [f["rfilename"] for f in siblings
             if not f["rfilename"].endswith((".msgpack", ".h5"))]

    print(f"  다운로드 대상 파일: {len(files)}개")
    ok_count = 0
    for fname in files:
        out_path = model_dir / fname
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"    건너뜀 (이미 있음): {fname}")
            ok_count += 1
            continue
        url = f"https://huggingface.co/{model_id}/resolve/main/{fname}"
        cmd = f"wget -q --show-progress -O {out_path} {url}"
        if token:
            cmd = f"wget -q --show-progress --header='Authorization: Bearer {token}' -O {out_path} {url}"
        print(f"    {fname}")
        ret = subprocess.run(cmd, shell=True)
        if ret.returncode == 0:
            ok_count += 1
        else:
            print(f"    [경고] 다운로드 실패: {fname}")

    print(f"  완료: {ok_count}/{len(files)} 파일")
    return ok_count == len(files)


def download_model(model_id: str, dest: Path, resume: bool,
                   token: str, downloader: str) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    if downloader == "hf":
        return download_hf(model_id, dest, resume, token)
    elif downloader == "huggingface-cli":
        return download_cli(model_id, dest, resume, token)
    elif downloader == "wget":
        return download_wget(model_id, dest, token)
    else:
        print("  [오류] 다운로더 없음. 아래 중 하나를 설치하세요:")
        print("    pip install huggingface_hub")
        print("    pip install huggingface_hub[cli]")
        print("    apt install wget")
        return False


# ── 메뉴 ─────────────────────────────────────────
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


# ── main ─────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="vLLM 개발 환경에 최적 모델 다운로드")
    ap.add_argument("--check",  action="store_true", help="사양 확인만 (다운로드 없음)")
    ap.add_argument("--list",   action="store_true", help="추천 모델 목록만 출력")
    ap.add_argument("--model",  default="",          help="모델 ID 직접 지정")
    ap.add_argument("--dest",   default="",          help="저장 경로 (기본: ./models)")
    ap.add_argument("--resume", action="store_true", default=True,
                    help="이어받기 (기본 ON)")
    ap.add_argument("--no-resume", action="store_true", help="이어받기 비활성화")
    ap.add_argument("--token",  default=os.environ.get("HF_TOKEN",""),
                    help="Hugging Face 토큰 (비공개 모델)")
    args = ap.parse_args()

    resume = args.resume and not args.no_resume

    # ── 저장 경로 결정 ──────────────────────────
    if args.dest:
        dest = Path(args.dest)
    else:
        # USB 경로 자동 탐지
        script_dir = Path(__file__).resolve().parent
        usb_models = script_dir / "models"
        dest = usb_models

    # ── 하드웨어 조회 ───────────────────────────
    print("하드웨어 사양 확인 중...", flush=True)
    total_vram, free_vram, ram_mb = get_hw()
    total_vram_gb = round(total_vram / 1024, 1)
    free_vram_gb  = round(free_vram  / 1024, 1)
    ram_gb        = round(ram_mb     / 1024, 1)
    disk_free_mb  = get_disk_free(dest.parent if not dest.exists() else dest)
    disk_free_gb  = round(disk_free_mb / 1024, 1)

    print(f"\n{SEP2}")
    print(" 하드웨어 사양")
    print(SEP2)
    if total_vram > 0:
        print(f"  GPU VRAM : 전체 {total_vram_gb}GB  여유 {free_vram_gb}GB")
    else:
        print(f"  GPU      : 없음 (CPU 전용)")
    print(f"  RAM      : {ram_gb}GB")
    print(f"  저장경로 : {dest}")
    print(f"  여유공간 : {disk_free_gb}GB")

    # ── 다운로더 확인 ───────────────────────────
    dl = detect_downloader()
    print(f"  다운로더 : {dl or '없음 — pip install huggingface_hub 권장'}")

    # ── 추천 목록 ───────────────────────────────
    catalog = filter_catalog(total_vram)
    if args.model:
        # 직접 지정 모델을 카탈로그 앞에 삽입
        catalog.insert(0, {
            "model_id": args.model,
            "name": args.model.split("/")[-1],
            "vram_req_gb": 0,
            "parser": "hermes",
            "reason": "직접 지정",
            "extra": "",
        })

    print(f"\n{SEP2}")
    print(" 추천 모델 목록 (VRAM 기준 필터)")
    print(SEP2)
    for i, m in enumerate(catalog, 1):
        vram_s = f"{m['vram_req_gb']}GB" if m["vram_req_gb"] else "CPU"
        size_s = f"~{round(size_hint_mb(m['model_id'])/1024,0):.0f}GB"
        # 다운로드 여부 확인
        model_dir = dest / m["model_id"].replace("/", "--")
        status = " [완료]" if (model_dir.exists() and any(model_dir.iterdir())) else ""
        print(f"  [{i}] {m['name']}{status}")
        print(f"       VRAM {vram_s}  다운로드크기 {size_s}  parser: {m['parser']}")
        print(f"       {m['reason']}")

    if args.check or args.list:
        return

    # ── 디스크 공간 경고 ────────────────────────
    if disk_free_gb < 20:
        print(f"\n  ⚠  저장 경로 여유 공간이 {disk_free_gb}GB 밖에 없습니다.")
        print(f"     대용량 모델(14B: ~28GB)은 충분한 공간이 필요합니다.")

    # ── 모델 선택 ───────────────────────────────
    print(f"\n{SEP}")
    idx = _pick("다운로드할 모델 선택 (0=취소)", len(catalog), default=1)
    if idx == 0:
        print("취소.")
        return

    selected = catalog[idx - 1]
    model_id = selected["model_id"]
    size_mb  = size_hint_mb(model_id)

    print(f"\n선택: {selected['name']}")
    print(f"  모델 ID    : {model_id}")
    print(f"  예상 크기  : ~{round(size_mb/1024,1)}GB")
    print(f"  저장 경로  : {dest / model_id.replace('/', '--')}")
    print(f"  이어받기   : {'ON' if resume else 'OFF'}")

    if disk_free_mb < size_mb * 1.05:
        print(f"\n  ⚠  공간 부족: 필요 {round(size_mb/1024,1)}GB, 여유 {disk_free_gb}GB")
        ans = input("  계속하시겠습니까? [y/N] ").strip().lower()
        if ans != "y":
            print("취소.")
            return

    if not dl:
        print("\n  [오류] 다운로더가 없습니다.")
        print("  설치: pip install huggingface_hub")
        return

    ans = input(f"\n  다운로드를 시작하시겠습니까? [Y/n] ").strip().lower()
    if ans in ("n", "no"):
        print("취소.")
        return

    # ── 다운로드 실행 ───────────────────────────
    print(f"\n{SEP2}")
    ok = download_model(model_id, dest, resume, args.token, dl)

    print(f"\n{SEP2}")
    if ok:
        model_dir = dest / model_id.replace("/", "--")
        print(f"  ✓ 완료: {model_dir}")
        print(f"\n  vLLM 서버 시작 명령:")
        parser = selected["parser"]
        extra  = selected["extra"] or f"--enable-auto-tool-choice --tool-call-parser {parser}"
        print(f"    python3 -m vllm.entrypoints.openai.api_server \\")
        print(f"      --model {model_dir} \\")
        print(f"      --port 8200 \\")
        print(f"      {extra}")
    else:
        print(f"  ✗ 다운로드 실패 — 로그를 확인하세요.")
    print(SEP2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n강제 종료.")
        sys.exit(1)
