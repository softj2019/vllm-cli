"""FileManager — 파일/디렉토리 전체 조작 (stdlib only)"""
import os, re, shutil, stat
from pathlib import Path
from datetime import datetime
from typing import List
from .config import MAX_FILE_BYTES, MAX_READ_LINES
from .logger import get_logger

log = get_logger(__name__)


def _p(path: str) -> Path:
    return Path(path).expanduser().resolve()


class FileManager:

    # ══════════════════════════════════════════
    # 디렉토리 탐색
    # ══════════════════════════════════════════

    def dir_list(self, path=".", depth=1, show_hidden=False, detail=False) -> str:
        base = _p(path)
        if not base.exists():
            log.warning("dir_list: 경로 없음 %s", path)
            return f"[오류] 없음: {path}"
        try:
            lines = []
            self._tree(base, "", depth, 0, show_hidden, detail, lines)
            return f"{base}/\n" + "\n".join(lines) if lines else f"{base}/ (비어 있음)"
        except Exception:
            log.error("dir_list 실패: %s", path, exc_info=True)
            return f"[오류] 디렉토리 탐색 실패: {path}"

    def _tree(self, d: Path, prefix: str, max_depth: int, cur: int,
              hidden: bool, detail: bool, out: list):
        try:
            entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            out.append(prefix + "  [권한 없음]"); return
        except Exception:
            log.error("_tree iterdir 실패: %s", d, exc_info=True)
            return
        entries = [e for e in entries if hidden or not e.name.startswith(".")]
        for i, e in enumerate(entries):
            last  = i == len(entries) - 1
            conn  = "└── " if last else "├── "
            child = "    " if last else "│   "
            if detail:
                try:
                    s    = e.stat()
                    perm = oct(s.st_mode)[-4:]
                    sz   = f"{s.st_size:>8,}" if e.is_file() else "       -"
                    dt   = datetime.fromtimestamp(s.st_mtime).strftime("%m-%d %H:%M")
                    row  = f"{perm} {sz} {dt}  {e.name}{'/' if e.is_dir() else ''}"
                except Exception:
                    log.debug("stat 실패: %s", e, exc_info=True)
                    row = e.name
            else:
                row = e.name + ("/" if e.is_dir() else "")
            out.append(prefix + conn + row)
            if e.is_dir() and (max_depth == 0 or cur + 1 < max_depth):
                self._tree(e, prefix + child, max_depth, cur + 1, hidden, detail, out)

    # ══════════════════════════════════════════
    # 디렉토리 생성 / 삭제
    # ══════════════════════════════════════════

    def dir_create(self, path: str, mode: str = "755") -> str:
        fp = _p(path)
        try:
            fp.mkdir(parents=True, exist_ok=True)
            fp.chmod(int(mode, 8))
            log.info("dir_create: %s (mode=%s)", fp, mode)
            return f"생성: {fp}  권한: {mode}"
        except Exception:
            log.error("dir_create 실패: %s", path, exc_info=True)
            return f"[오류] 디렉토리 생성 실패: {path}"

    def dir_delete(self, path: str, recursive: bool = False) -> str:
        fp = _p(path)
        if not fp.exists():
            return f"[오류] 없음: {path}"
        if not fp.is_dir():
            return f"[오류] 디렉토리 아님: {path}"
        try:
            if recursive:
                shutil.rmtree(fp)
            else:
                fp.rmdir()
            log.info("dir_delete: %s (recursive=%s)", fp, recursive)
            return f"{'재귀 ' if recursive else ''}삭제: {fp}"
        except OSError:
            log.error("dir_delete 실패: %s", path, exc_info=True)
            return f"[오류] 삭제 실패: {path}  (비어 있지 않으면 recursive=true 사용)"

    # ══════════════════════════════════════════
    # 파일 이동 / 복사 / 삭제
    # ══════════════════════════════════════════

    def file_move(self, src: str, dst: str) -> str:
        s, d = _p(src), _p(dst)
        if not s.exists():
            return f"[오류] 원본 없음: {src}"
        try:
            if d.is_dir():
                d = d / s.name
            shutil.move(str(s), str(d))
            log.info("file_move: %s → %s", s, d)
            return f"이동: {s} → {d}"
        except Exception:
            log.error("file_move 실패: %s → %s", src, dst, exc_info=True)
            return f"[오류] 이동 실패: {src} → {dst}"

    def file_copy(self, src: str, dst: str) -> str:
        s, d = _p(src), _p(dst)
        if not s.exists():
            return f"[오류] 원본 없음: {src}"
        try:
            if s.is_dir():
                shutil.copytree(str(s), str(d))
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(s), str(d))
            log.info("file_copy: %s → %s", s, d)
            return f"복사: {s} → {d}"
        except Exception:
            log.error("file_copy 실패: %s → %s", src, dst, exc_info=True)
            return f"[오류] 복사 실패: {src} → {dst}"

    def delete_file(self, path: str) -> str:
        fp = _p(path)
        if not fp.exists():
            return f"[오류] 없음: {path}"
        if fp.is_dir():
            return f"[오류] 디렉토리는 dir_delete 사용: {path}"
        try:
            fp.unlink()
            log.info("delete_file: %s", fp)
            return f"삭제: {fp}"
        except Exception:
            log.error("delete_file 실패: %s", path, exc_info=True)
            return f"[오류] 삭제 실패: {path}"

    # ══════════════════════════════════════════
    # 권한 / 소유자
    # ══════════════════════════════════════════

    def file_chmod(self, path: str, mode: str, recursive: bool = False) -> str:
        fp = _p(path)
        if not fp.exists():
            return f"[오류] 없음: {path}"
        try:
            m = self._parse_mode(fp, mode)
            targets = list(fp.rglob("*")) + [fp] if recursive and fp.is_dir() else [fp]
            for t in targets:
                t.chmod(m)
            log.info("file_chmod: %s mode=%s recursive=%s", fp, mode, recursive)
            return f"chmod {mode} ({oct(m)[-4:]}) 적용: {len(targets)}개 → {fp}"
        except ValueError as e:
            log.warning("file_chmod mode 파싱 오류: %s", e)
            return f"[오류] mode 형식: {e}"
        except Exception:
            log.error("file_chmod 실패: %s", path, exc_info=True)
            return f"[오류] chmod 실패: {path}"

    def file_chown(self, path: str, owner: str, recursive: bool = False) -> str:
        import subprocess
        flag = "-R" if recursive else ""
        cmd  = f"chown {flag} {owner} {path}".strip()
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if r.returncode == 0:
                log.info("file_chown: %s owner=%s recursive=%s", path, owner, recursive)
                return f"chown {owner} 완료: {path}"
            log.warning("file_chown 실패: %s — %s", path, r.stderr.strip())
            return f"[오류] {r.stderr.strip()}"
        except Exception:
            log.error("file_chown 예외: %s", path, exc_info=True)
            return f"[오류] chown 실패: {path}"

    @staticmethod
    def _parse_mode(fp: Path, mode: str) -> int:
        if re.fullmatch(r"[0-7]{3,4}", mode):
            return int(mode, 8)
        cur      = fp.stat().st_mode
        who_map  = {"u": 0o700, "g": 0o070, "o": 0o007, "a": 0o777}
        perm_map = {"r": 0o444, "w": 0o222, "x": 0o111,
                    "s": 0o6000, "t": 0o1000}
        for part in mode.split(","):
            m = re.fullmatch(r"([ugoa]*)([+\-=])([rwxst]+)", part.strip())
            if not m:
                raise ValueError(f"알 수 없는 mode 형식: {mode}")
            who, op, perms = m.groups()
            mask = 0
            for w in (who or "a"):
                mask |= who_map.get(w, 0)
            bits = 0
            for p in perms:
                bits |= perm_map.get(p, 0)
            bits &= mask
            if op == "+":   cur |= bits
            elif op == "-": cur &= ~bits
            elif op == "=": cur = (cur & ~mask) | bits
        return cur

    # ══════════════════════════════════════════
    # 고급 파일 찾기
    # ══════════════════════════════════════════

    def file_find(self, path=".", name=None, ftype=None,
                  min_size=None, max_size=None, newer_than=None,
                  contains=None, max_depth=None, max_results=50) -> str:
        base = _p(path)
        if not base.exists():
            return f"[오류] 없음: {path}"

        cutoff = None
        if newer_than:
            try:
                cutoff = datetime.strptime(newer_than, "%Y-%m-%d").timestamp()
            except ValueError:
                return "[오류] newer_than 형식: YYYY-MM-DD"

        results = []

        def _walk(d: Path, depth: int):
            if max_depth is not None and depth > max_depth:
                return
            try:
                for e in sorted(d.iterdir()):
                    if len(results) >= max_results:
                        return
                    type_ok = (ftype is None) or \
                        {"f": e.is_file, "d": e.is_dir, "l": e.is_symlink}.get(ftype, lambda: True)()
                    name_ok = (name is None) or \
                        bool(re.search(name.replace("*", ".*").replace("?", "."), e.name))
                    try:
                        s = e.stat()
                        size_ok = (min_size is None or s.st_size >= min_size) and \
                                  (max_size is None or s.st_size <= max_size)
                        time_ok = cutoff is None or s.st_mtime >= cutoff
                    except Exception:
                        log.debug("stat 실패 (file_find): %s", e, exc_info=True)
                        size_ok = time_ok = True

                    content_ok = True
                    if contains and e.is_file():
                        try:
                            content_ok = contains.lower() in \
                                e.read_text(encoding="utf-8", errors="ignore").lower()
                        except Exception:
                            log.debug("내용 읽기 실패 (file_find): %s", e, exc_info=True)
                            content_ok = False

                    if type_ok and name_ok and size_ok and time_ok and content_ok:
                        try:
                            sz    = e.stat().st_size
                            mtime = datetime.fromtimestamp(e.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                            results.append(f"{str(e):<60s} {sz:>10,}B  {mtime}")
                        except Exception:
                            results.append(str(e))

                    if e.is_dir() and not e.is_symlink():
                        _walk(e, depth + 1)
            except PermissionError:
                log.debug("권한 없음 (file_find): %s", d)

        try:
            _walk(base, 0)
        except Exception:
            log.error("file_find 실패: %s", path, exc_info=True)
            return f"[오류] 파일 찾기 실패: {path}"

        if not results:
            return f"조건에 맞는 항목 없음 ({base})"
        return f"검색 {len(results)}건 ({base}):\n" + "\n".join(results)

    # ══════════════════════════════════════════
    # 파일 읽기 / 쓰기 / 치환
    # ══════════════════════════════════════════

    def read_file(self, path, lines=0, offset=1) -> str:
        fp = _p(path)
        if not fp.exists():
            return f"[오류] 파일 없음: {path}"
        if not fp.is_file():
            return f"[오류] 디렉토리: {path}"
        sz, note = fp.stat().st_size, ""
        if sz > MAX_FILE_BYTES and lines == 0:
            lines = MAX_READ_LINES
            note  = f"[{sz//1024}KB — 앞 {lines}줄만]\n"
        try:
            all_lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            s = max(0, offset - 1)
            e = s + lines if lines > 0 else len(all_lines)
            chunk = all_lines[s:e]
            body  = "\n".join(f"{s+i+1:4d}  {l}" for i, l in enumerate(chunk))
            log.debug("read_file: %s (lines=%d offset=%d)", fp, lines, offset)
            return f"{note}# {fp} ({len(all_lines)}줄)\n{body}"
        except Exception:
            log.error("read_file 실패: %s", path, exc_info=True)
            return f"[오류] 읽기 실패: {path}"

    def write_file(self, path, content, append=False) -> str:
        fp = _p(path)
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            if append:
                with fp.open("a", encoding="utf-8") as f:
                    f.write(content)
            else:
                fp.write_text(content, encoding="utf-8")
            log.info("write_file: %s (%dB append=%s)", fp, len(content), append)
            return f"{'추가' if append else '작성'}: {fp} ({len(content)}B)"
        except Exception:
            log.error("write_file 실패: %s", path, exc_info=True)
            return f"[오류] 쓰기 실패: {path}"

    def file_replace(self, path: str, old: str, new: str,
                     regex: bool = False, count: int = 0,
                     backup: bool = True) -> str:
        fp = _p(path)
        if not fp.exists():
            return f"[오류] 없음: {path}"
        if not fp.is_file():
            return f"[오류] 디렉토리: {path}"
        try:
            original = fp.read_text(encoding="utf-8", errors="replace")
            if regex:
                new_content, n = re.subn(old, new, original, count=count or 0)
            else:
                new_content, n = re.subn(
                    re.escape(old), new.replace("\\", "\\\\"),
                    original, count=count or 0
                )
            if n == 0:
                return f"치환 대상 없음: '{old}' in {fp}"
            if backup:
                fp.with_suffix(fp.suffix + ".bak").write_text(original, encoding="utf-8")
            fp.write_text(new_content, encoding="utf-8")
            log.info("file_replace: %s '%s'→'%s' %d건 (backup=%s)", fp, old, new, n, backup)
            return f"치환 완료: {n}건{' (.bak 백업)' if backup else ''}\n  {fp}"
        except re.error as e:
            log.warning("file_replace 정규식 오류: %s", e)
            return f"[오류] 정규식: {e}"
        except Exception:
            log.error("file_replace 실패: %s", path, exc_info=True)
            return f"[오류] 치환 실패: {path}"

    # ══════════════════════════════════════════
    # 검색 / 정보
    # ══════════════════════════════════════════

    def search_files(self, path=".", pattern="*", keyword=None, max_results=30) -> str:
        base = _p(path)
        if not base.exists():
            return f"[오류] 경로 없음: {path}"
        try:
            hits: List[Path] = []
            for p in base.rglob(pattern):
                if p.is_file():
                    hits.append(p)
                    if len(hits) >= max_results * 5:
                        break
        except PermissionError:
            log.warning("search_files 권한 없음: %s", path)
            return f"[오류] 권한 없음: {path}"
        except Exception:
            log.error("search_files 실패: %s", path, exc_info=True)
            return f"[오류] 검색 실패: {path}"

        if keyword:
            kw, out = keyword.lower(), []
            for f in hits:
                try:
                    all_lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                    found = [f"  L{i+1}: {l.rstrip()}"
                             for i, l in enumerate(all_lines) if kw in l.lower()]
                    if found:
                        out.append(f"{f}\n" + "\n".join(found[:3]))
                        if len(out) >= max_results:
                            break
                except Exception:
                    log.debug("search_files 내용 읽기 실패: %s", f, exc_info=True)
            return (f"'{keyword}' 검색: {len(out)}건\n\n" + "\n\n".join(out)) if out \
                else f"'{keyword}' 없음 ({base})"

        limited = hits[:max_results]
        if not limited:
            return f"'{pattern}' 없음 ({base})"
        extra = f"\n+{len(hits)-max_results}개 더" if len(hits) > max_results else ""
        return f"검색 {len(limited)}건:\n" + "\n".join(str(p) for p in limited) + extra

    def file_info(self, path) -> str:
        fp = _p(path)
        if not fp.exists():
            return f"[오류] 없음: {path}"
        try:
            s    = fp.stat()
            kind = "dir" if fp.is_dir() else ("symlink" if fp.is_symlink() else "file")
            mtime = datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            info  = (f"{fp}\n"
                     f"  종류:{kind}  크기:{s.st_size:,}B\n"
                     f"  권한:{oct(s.st_mode)[-4:]}  uid:{s.st_uid}  gid:{s.st_gid}\n"
                     f"  수정:{mtime}")
            if fp.is_dir():
                try:
                    info += f"\n  항목:{len(list(fp.iterdir()))}개"
                except PermissionError:
                    pass
            if fp.is_symlink():
                info += f"\n  → {os.readlink(fp)}"
            return info
        except Exception:
            log.error("file_info 실패: %s", path, exc_info=True)
            return f"[오류] 정보 조회 실패: {path}"
