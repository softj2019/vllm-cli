"""core package — vendor path auto-inject"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_pkg  = _root / "vendor" / "packages"
if _pkg.exists() and str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))
