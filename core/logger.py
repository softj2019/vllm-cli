"""
중앙 로거 — 프로젝트 루트 logs/ 에 회전 로그 파일 생성

로그 파일: <project_root>/logs/vllm_cli.log
  - DEBUG 이상 전부 파일 기록 (트레이스백 포함)
  - WARNING 이상만 콘솔 출력
  - 5MB × 최대 5개 회전 보관
  - USB/FAT32 쓰기 실패 시 /tmp/vllm_cli.log 로 자동 폴백

사용:
  from .logger import get_logger
  log = get_logger(__name__)
  log.debug("msg")
  log.error("msg", exc_info=True)   # 트레이스백 포함
"""
import logging
import logging.handlers
from pathlib import Path

# ── 경로 설정 ────────────────────────────────
_ROOT     = Path(__file__).resolve().parent.parent   # cli/
_LOG_DIR  = _ROOT / "logs"
_LOG_FILE = _LOG_DIR / "vllm_cli.log"
_FALLBACK = Path("/tmp/vllm_cli.log")               # USB 쓰기 실패 시 폴백

_MAX_BYTES  = 5 * 1024 * 1024   # 5MB
_BACKUP_CNT = 5

# ── 포맷 ────────────────────────────────────
_FMT_FILE = "%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d  %(message)s"
_FMT_CON  = "%(levelname)-8s %(message)s"
_DATEFMT  = "%Y-%m-%d %H:%M:%S"

# ── 루트 로거 초기화 (1회) ───────────────────
_initialized = False
_active_log_file = _LOG_FILE   # 실제 사용 중인 경로 (폴백 반영)


def _try_file_handler(path: Path):
    """로그 파일 핸들러 생성 시도. 실패 시 None 반환."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_CNT, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATEFMT))
        return fh
    except Exception as e:
        print(f"[logger] 파일 핸들러 실패 ({path}): {e}")
        return None


def _init():
    global _initialized, _active_log_file
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger("vllm_cli")
    root.setLevel(logging.DEBUG)

    # 파일 핸들러 — 기본 경로 시도 → 실패 시 /tmp 폴백
    fh = _try_file_handler(_LOG_FILE)
    if fh is None:
        print(f"[logger] USB 쓰기 불가 — /tmp 폴백 사용")
        fh = _try_file_handler(_FALLBACK)
        if fh:
            _active_log_file = _FALLBACK

    if fh:
        root.addHandler(fh)
    else:
        print("[logger] 경고: 파일 로깅 불가 — 콘솔만 사용")

    # 콘솔 핸들러 (WARNING+)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter(_FMT_CON))
    root.addHandler(ch)

    root.propagate = False

    # 초기화 완료 로그
    logging.getLogger("vllm_cli").info(
        "로거 초기화 완료: %s", _active_log_file
    )


def get_logger(name: str) -> logging.Logger:
    """모듈별 named logger 반환. __name__ 을 전달하세요."""
    _init()
    clean = name.replace("__main__", "main")
    if not clean.startswith("vllm_cli"):
        clean = "vllm_cli." + clean.lstrip(".")
    return logging.getLogger(clean)


def log_path() -> Path:
    """현재 실제 로그 파일 경로 반환 (폴백 포함)"""
    _init()
    return _active_log_file
