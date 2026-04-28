"""
모델 계열 자동 감지 + vLLM tool-call-parser 매핑

지원 parser (vLLM 0.4+):
  hermes     - Qwen2/2.5, NousHermes, Yi, Phi-3, DeepSeek 계열
  llama3     - Llama-3.x, Llama-Guard-3
  mistral    - Mistral, Mixtral, Pixtral
  internlm   - InternLM2+
  deepseekv3 - DeepSeek-V3
  pythonic   - 일반 pythonic tool use

OCR 전용 모델 (tool calling 미지원):
  prov / ARCH_OCR_PRO / olmocr / PaddleOCR-VL / Nanonets-OCR / lite
  → 서버를 --enable-auto-tool-choice 없이 기동하는 것이 정상
"""
import re
import json
import http.client
from typing import Tuple
from .config import API_MODELS
from .logger import get_logger

log = get_logger(__name__)

# ── OCR 전용 모델 키워드 (tool calling 지원 불가) ──────
# 이 모델들은 이미지 OCR 처리 전용 — 함수 호출 개념 없음
_OCR_ONLY_PATTERNS = [
    r"^prov?$",            # prov, pro
    r"arch.?ocr",          # ARCH_OCR_PRO, arch-ocr
    r"olmocr",             # olmOCR
    r"paddleocr",          # PaddleOCR-VL-0.9B
    r"paddle.?vl",
    r"nanonets",           # Nanonets-OCR2-3B
    r"^lite$",             # lite
    r"ocr.?pro",
]

# ── 모델명 → parser 매핑 규칙 (우선순위 순) ──
# (regex_pattern, parser, 설명)
_RULES = [
    # ── ARCH OCR 전용 모델 ─────────────────────
    (r"^prov?$",            "hermes",     "ARCH OCR PRO (OCR 전용, tool call 미지원)"),
    (r"arch.?ocr",          "hermes",     "ARCH OCR (OCR 전용, tool call 미지원)"),
    (r"olmocr",             "hermes",     "olmOCR (OCR 전용, tool call 미지원)"),
    (r"paddleocr|paddle.?vl","hermes",    "PaddleOCR-VL (OCR 전용, tool call 미지원)"),
    (r"nanonets",           "hermes",     "Nanonets-OCR (OCR 전용, tool call 미지원)"),
    (r"^lite$",             "hermes",     "ARCH OCR Lite (OCR 전용, tool call 미지원)"),
    # ── 범용 LLM ──────────────────────────────
    # Llama 3
    (r"llama[-_]?3",        "llama3",     "Llama 3.x"),
    # Mistral / Mixtral
    (r"mixtral|mistral",    "mistral",    "Mistral / Mixtral"),
    # InternLM
    (r"internlm",           "internlm",   "InternLM 2+"),
    # DeepSeek V3
    (r"deepseek[-_]?v3",    "deepseekv3", "DeepSeek V3"),
    # DeepSeek (기타)
    (r"deepseek",           "hermes",     "DeepSeek (hermes compat)"),
    # Qwen 3 (VL 포함)
    (r"qwen3",              "hermes",     "Qwen3 (hermes compat)"),
    # Qwen 2+
    (r"qwen2?[-_. ]",       "hermes",     "Qwen 2/2.5"),
    (r"qwen",               "hermes",     "Qwen (hermes compat)"),
    # NousHermes / Hermes
    (r"hermes|nous",        "hermes",     "NousHermes"),
    # Yi
    (r"\byi[-_]",           "hermes",     "Yi (hermes compat)"),
    # Phi-3
    (r"phi[-_]?3",          "hermes",     "Phi-3 (hermes compat)"),
    # Gemma
    (r"gemma",              "hermes",     "Gemma (hermes compat, 제한적)"),
    # 기본 폴백
    (r".",                  "hermes",     "Unknown → hermes 기본값"),
]


def is_ocr_only_model(model_id: str) -> bool:
    """OCR 전용 모델 여부 반환 (tool calling 미지원이 정상인 모델)"""
    name = model_id.lower().rstrip("/").split("/")[-1]
    for pattern in _OCR_ONLY_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


def detect_parser(model_id: str) -> Tuple[str, str]:
    """
    모델 ID 문자열에서 tool-call-parser 와 모델 설명을 반환.
    반환: (parser_name, description)
    """
    name = model_id.lower()
    # 경로에서 마지막 컴포넌트만 추출 (예: /data/models/Llama-3-8B → llama-3-8b)
    name = name.rstrip("/").split("/")[-1]
    for pattern, parser, desc in _RULES:
        if re.search(pattern, name, re.IGNORECASE):
            log.debug("detect_parser: model=%s → parser=%s (%s)", model_id, parser, desc)
            return parser, desc
    log.debug("detect_parser: model=%s → 폴백 hermes", model_id)
    return "hermes", "Unknown"


def fetch_models(host: str, port: int, timeout: int = 3) -> list:
    """서버에서 모델 목록 조회. 실패 시 빈 리스트."""
    try:
        c = http.client.HTTPConnection(host, port, timeout=timeout)
        c.request("GET", API_MODELS, headers={"Authorization": "Bearer empty"})
        r = c.getresponse()
        if r.status != 200:
            log.warning("fetch_models HTTP %d: %s:%d", r.status, host, port)
            c.close()
            return []
        data = json.loads(r.read().decode("utf-8", errors="replace"))
        c.close()
        models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        log.debug("fetch_models: %s:%d → %s", host, port, models)
        return models
    except Exception:
        log.debug("fetch_models 연결 실패: %s:%d", host, port, exc_info=True)
        return []


def probe_tool_support(host: str, port: int, model: str, timeout: int = 5) -> bool:
    # OCR 전용 모델은 probe 없이 즉시 False 반환
    if is_ocr_only_model(model):
        log.info("probe_tool_support: %s → OCR 전용 모델, tool call 미지원 (정상)", model)
        return False
    """
    최소 payload 로 tool_choice=auto 를 보내 400 여부 확인.
    True = 서버가 tool calling 지원
    False = 지원 안 함 (--enable-auto-tool-choice 미설정)
    """
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {
            "name": "test", "description": "test",
            "parameters": {"type": "object", "properties": {}}
        }}],
        "tool_choice": "auto",
        "max_tokens": 1,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    try:
        c = http.client.HTTPConnection(host, port, timeout=timeout)
        c.request("POST", "/v1/chat/completions", body=payload, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer empty",
        })
        r = c.getresponse()
        body = r.read().decode("utf-8", errors="replace")
        c.close()
        if r.status == 400 and "enable-auto-tool-choice" in body:
            log.info("probe_tool_support: %s:%d model=%s → 미지원 (400)", host, port, model)
            return False
        log.info("probe_tool_support: %s:%d model=%s → 지원 (HTTP %d)", host, port, model, r.status)
        return True
    except Exception:
        log.debug("probe_tool_support 연결 실패: %s:%d", host, port, exc_info=True)
        return True   # 연결 실패면 판단 보류 → 일단 시도


def suggest_restart_cmd(host: str, port: int, model: str,
                         extra_args: str = "") -> str:
    """
    현재 서버의 모델을 감지해 올바른 vLLM 재시작 명령어 제안.
    """
    models = fetch_models(host, port)
    target = models[0] if models else model
    parser, desc = detect_parser(target)
    log.debug("suggest_restart_cmd: target=%s parser=%s", target, parser)

    cmd = (
        f"python3 -m vllm.entrypoints.openai.api_server \\\n"
        f"  --model {target} \\\n"
        f"  --host {host} \\\n"
        f"  --port {port} \\\n"
        f"  --enable-auto-tool-choice \\\n"
        f"  --tool-call-parser {parser}"
    )
    if extra_args:
        cmd += f" \\\n  {extra_args}"

    return (
        f"모델: {target}\n"
        f"계열: {desc}\n"
        f"parser: {parser}\n\n"
        f"=== 권장 재시작 명령 ===\n{cmd}"
    )
