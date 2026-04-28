#!/usr/bin/env python3
"""
vllm_install.py — 폐쇄망 오프라인 패키지 관리자

사용 시나리오
─────────────
① 인터넷 환경 (Mac/PC) 에서 USB에 다운로드:
    python3 vllm_install.py download
    python3 vllm_install.py download rich httpx   # 추가 패키지

② USB를 Ubuntu에 꽂고 설치:
    python3 /media/usb/home/ai/cli/vllm_install.py install
    python3 vllm_install.py install --path /media/usb/home/ai/cli

③ 설치 없이 sys.path에 vendor/packages 등록:
    python3 vllm_install.py inject               # ~/.pth 파일 생성

④ 상태 확인:
    python3 vllm_install.py list
    python3 vllm_install.py check

명령 요약:
  download [pkg ...]   wheels/ 에 다운로드 (인터넷 필요)
  install  [--path P]  wheels/ → packages/ 에 오프라인 설치
  inject               packages/ 를 sys.path 영구 등록
  list                 wheels/ 및 packages/ 목록
  check                필수 패키지 설치 여부 확인
  clean                wheels/ packages/ 삭제
"""
import sys, os, json, subprocess, argparse, shutil
from pathlib import Path
from datetime import datetime

# ── 경로 ─────────────────────────────────────
ROOT     = Path(__file__).resolve().parent
WHEELS   = ROOT / "vendor" / "wheels"
PACKAGES = ROOT / "vendor" / "packages"
META     = ROOT / "vendor" / "meta.json"

# ── 필수 패키지 목록 ───────────────────────────
# stdlib only 이므로 현재 CLI 자체는 의존성 없음
# vllm 서버는 Ubuntu 에 별도 설치 필요
REQUIRED: list[str] = []          # CLI 의존 없음 (stdlib only)

OPTIONAL: dict[str, str] = {
    "rich":     "컬러 터미널 출력",
    "httpx":    "HTTP/2 클라이언트 (대안)",
    "tqdm":     "진행바",
    "pydantic": "설정 유효성 검사",
}

VLLM_SERVER_DEPS: list[str] = [
    "vllm",
    "torch",
    "transformers",
    "accelerate",
    "sentencepiece",
]

# ─────────────────────────────────────────────
def _run(cmd, **kw) -> int:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.call(cmd, **kw)

def _pip(*args) -> int:
    return _run([sys.executable, "-m", "pip", *args])

def _ensure_dirs():
    WHEELS.mkdir(parents=True, exist_ok=True)
    PACKAGES.mkdir(parents=True, exist_ok=True)

def _save_meta(data: dict):
    META.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(META.read_text()) if META.exists() else {}
    existing.update(data)
    META.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

# ─────────────────────────────────────────────
# download
# ─────────────────────────────────────────────
def cmd_download(packages: list[str], python_ver: str, platform: str):
    """인터넷 환경에서 wheels/ 에 wheel 파일 다운로드"""
    _ensure_dirs()
    targets = packages or REQUIRED
    if not targets:
        print("[download] 필수 패키지 없음 (stdlib only). 추가 패키지를 지정하세요.")
        print("  예) python3 vllm_install.py download rich tqdm")
        print(f"\n옵션 패키지:")
        for k, v in OPTIONAL.items():
            print(f"  {k:12s}  {v}")
        print(f"\nvllm 서버 deps:")
        for p in VLLM_SERVER_DEPS:
            print(f"  {p}")
        return

    print(f"[download] → {WHEELS}")
    extra = []
    if python_ver:
        extra += ["--python-version", python_ver]
    if platform:
        extra += ["--platform", platform, "--only-binary=:all:"]

    for pkg in targets:
        _pip("download", pkg, "-d", str(WHEELS), *extra)

    _save_meta({
        "last_download": datetime.now().isoformat(),
        "downloaded": targets,
        "python_ver": python_ver or "current",
        "platform":   platform   or "current",
    })
    print(f"\n완료. USB에 담아 오프라인 Ubuntu 에서 install 실행하세요.")


# ─────────────────────────────────────────────
# install
# ─────────────────────────────────────────────
def cmd_install(usb_path: str):
    """오프라인 Ubuntu 에서 wheels/ → packages/ 설치"""
    base = Path(usb_path).resolve() if usb_path else ROOT
    wheels   = base / "vendor" / "wheels"
    packages = base / "vendor" / "packages"
    packages.mkdir(parents=True, exist_ok=True)

    whl_files = list(wheels.glob("*.whl")) + list(wheels.glob("*.tar.gz"))
    if not whl_files:
        print(f"[install] wheel 파일 없음: {wheels}")
        print("  인터넷 환경에서 먼저: python3 vllm_install.py download <pkg>")
        return

    print(f"[install] {len(whl_files)}개 패키지 → {packages}")
    ret = _pip(
        "install",
        "--no-index",
        f"--find-links={wheels}",
        f"--target={packages}",
        *(f.stem.split("-")[0] for f in whl_files if f.suffix == ".whl"),
    )
    if ret == 0:
        _save_meta({"last_install": datetime.now().isoformat(),
                    "install_path": str(packages)})
        print(f"\n설치 완료. 사용:")
        print(f"  python3 {base}/vllm_cli2.py")
    else:
        print("\n[오류] 설치 실패. pip 오류 확인 후 개별 설치 시도:")
        print(f"  pip install --no-index --find-links={wheels} <package>")


# ─────────────────────────────────────────────
# inject
# ─────────────────────────────────────────────
def cmd_inject():
    """vendor/packages 를 site-packages 의 .pth 파일로 영구 등록"""
    import site
    sp = site.getsitepackages()
    if not sp:
        print("[inject] site-packages 경로를 찾을 수 없습니다.")
        return
    target = Path(sp[0])
    pth = target / "vllm_cli_vendor.pth"
    pth.write_text(str(PACKAGES) + "\n")
    print(f"[inject] 등록: {pth}")
    print(f"  → {PACKAGES}")
    print("  이후 python3 import 시 vendor/packages 가 자동 포함됩니다.")


# ─────────────────────────────────────────────
# list
# ─────────────────────────────────────────────
def cmd_list():
    """wheels/ 및 packages/ 내용 표시"""
    print(f"=== wheels ({WHEELS}) ===")
    whl = sorted(WHEELS.glob("*")) if WHEELS.exists() else []
    if whl:
        for f in whl:
            sz = f"{f.stat().st_size//1024}KB"
            print(f"  {f.name:<50s} {sz:>8s}")
    else:
        print("  (없음)")

    print(f"\n=== packages ({PACKAGES}) ===")
    pkgs = sorted(PACKAGES.iterdir()) if PACKAGES.exists() else []
    dirs = [p for p in pkgs if p.is_dir() and not p.name.startswith(".")]
    if dirs:
        for d in dirs:
            print(f"  {d.name}")
    else:
        print("  (없음)")

    if META.exists():
        print(f"\n=== meta ===")
        print(META.read_text())


# ─────────────────────────────────────────────
# check
# ─────────────────────────────────────────────
def cmd_check():
    """필수/옵션 패키지 설치 여부 확인"""
    def _chk(name):
        try:
            __import__(name.replace("-", "_").split("[")[0])
            return "✓"
        except ImportError:
            return "✗"

    print("=== CLI 필수 패키지 (stdlib only) ===")
    for mod in ["json", "http.client", "pathlib", "subprocess", "argparse"]:
        print(f"  {_chk(mod)} {mod}")

    print("\n=== 옵션 패키지 ===")
    for pkg, desc in OPTIONAL.items():
        print(f"  {_chk(pkg)} {pkg:<12s} {desc}")

    print("\n=== vLLM 서버 패키지 ===")
    for pkg in VLLM_SERVER_DEPS:
        print(f"  {_chk(pkg)} {pkg}")

    print(f"\n=== vendor 경로 ===")
    print(f"  wheels:   {WHEELS}  ({'존재' if WHEELS.exists() else '없음'})")
    print(f"  packages: {PACKAGES}  ({'존재' if PACKAGES.exists() else '없음'})")

    # Python 버전
    v = sys.version_info
    print(f"\nPython {v.major}.{v.minor}.{v.micro}  ({sys.executable})")


# ─────────────────────────────────────────────
# clean
# ─────────────────────────────────────────────
def cmd_clean(target: str):
    choices = {"wheels": WHEELS, "packages": PACKAGES, "all": None}
    if target not in choices:
        print(f"[clean] 대상: wheels | packages | all"); return
    paths = [WHEELS, PACKAGES] if target == "all" else [choices[target]]
    for p in paths:
        if p.exists():
            ans = input(f"  '{p}' 삭제? [y/N] ").strip().lower()
            if ans == "y":
                shutil.rmtree(p)
                print(f"  삭제: {p}")
        else:
            print(f"  없음: {p}")


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="폐쇄망 오프라인 패키지 관리자",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    # download
    dl = sub.add_parser("download", help="wheels/ 에 패키지 다운로드 (인터넷 필요)")
    dl.add_argument("packages", nargs="*", help="패키지명 (생략 시 REQUIRED 목록)")
    dl.add_argument("--python-version", default="", metavar="VER",
                    help="대상 Python 버전 예) 3.11")
    dl.add_argument("--platform", default="", metavar="PLAT",
                    help="대상 플랫폼 예) manylinux2014_x86_64")

    # install
    ins = sub.add_parser("install", help="오프라인 설치 (USB → Ubuntu)")
    ins.add_argument("--path", default="", metavar="USB_PATH",
                     help="USB 마운트 경로 (기본: 현재 스크립트 위치)")

    # inject
    sub.add_parser("inject", help="vendor/packages 를 sys.path 에 영구 등록")

    # list
    sub.add_parser("list", help="wheels/packages 목록")

    # check
    sub.add_parser("check", help="패키지 설치 여부 확인")

    # clean
    cl = sub.add_parser("clean", help="캐시 삭제")
    cl.add_argument("target", choices=["wheels", "packages", "all"])

    args = ap.parse_args()

    if   args.cmd == "download": cmd_download(args.packages, args.python_version, args.platform)
    elif args.cmd == "install":  cmd_install(args.path)
    elif args.cmd == "inject":   cmd_inject()
    elif args.cmd == "list":     cmd_list()
    elif args.cmd == "check":    cmd_check()
    elif args.cmd == "clean":    cmd_clean(args.target)


if __name__ == "__main__":
    main()
