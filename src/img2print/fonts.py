"""Finding font files by family name: bundled fonts, your own fonts, and all of Google Fonts.

    path, axes = font_file("Heebo", weight=700)      # a TTF/OTF path, and variation axes to apply
    families = list_fonts()                          # everything available, for a font picker

Fonts are looked up in this order:
- the fonts bundled with img2print (Heebo, which covers Hebrew and Latin);
- your font folder (IMG2PRINT_FONT_DIR, by default a cache folder in your home): put .ttf / .otf
  files there by hand, or add them with add_font();
- Google Fonts: any family there is downloaded on first use and kept in the font folder.
  Set IMG2PRINT_GOOGLE_FONTS=0 to stay offline.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

BUNDLED_DIR = Path(__file__).parent / "fonts"
DEFAULT_FONT = "Heebo"
FONT_SUFFIXES = {".ttf", ".otf"}
MAX_FONT_BYTES = 30 * 2**20

GOOGLE_METADATA_URL = "https://fonts.google.com/metadata/fonts"
GOOGLE_CSS_URL = "https://fonts.googleapis.com/css2"
CATALOG_MAX_AGE = 7 * 24 * 3600      # seconds before the Google catalogue is fetched again
NETWORK_TIMEOUT = 20.0


@dataclass
class FontFamily:
    """One family as a font picker shows it.

    variants  available styles as "400", "700", "400i" (weight, i for italic); a variable font
              lists the standard weights its range covers.
    source    "bundled", "local" (your font folder) or "google".
    subsets   scripts it covers, e.g. ["hebrew", "latin"]; empty when unknown.
    """

    family: str
    variants: list[str]
    source: str
    category: str = ""
    subsets: list[str] = field(default_factory=list)
    popularity: int = 0     # Google's rank, lower is more popular; 0 for other fonts

    def to_dict(self) -> dict:
        return dict(family=self.family, variants=self.variants, source=self.source,
                    category=self.category, subsets=self.subsets, popularity=self.popularity)


def font_dir() -> Path:
    """Your font folder: IMG2PRINT_FONT_DIR, or a cache folder in your home."""
    env = os.environ.get("IMG2PRINT_FONT_DIR")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "img2print" / "fonts"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "img2print" / "fonts"


def google_enabled() -> bool:
    return os.environ.get("IMG2PRINT_GOOGLE_FONTS", "1").lower() not in ("0", "false", "no", "off")


# --- local font files ------------------------------------------------------------------------------

@dataclass
class _FontInfo:
    path: Path
    family: str
    weight: int
    italic: bool
    weight_range: tuple[float, float] | None   # a variable font's wght axis
    subsets: list[str]


_scan_lock = threading.Lock()
_scanned: dict[Path, tuple[float, _FontInfo | None]] = {}


def _read_info(path: Path) -> _FontInfo | None:
    try:
        tt = TTFont(path, lazy=True)
    except (TTLibError, OSError, ValueError):
        return None
    with tt:
        names = tt["name"]
        family = names.getDebugName(16) or names.getDebugName(1)
        if not family or "glyf" not in tt and "CFF " not in tt and "CFF2" not in tt:
            return None
        os2 = tt["OS/2"] if "OS/2" in tt else None
        weight = os2.usWeightClass if os2 else 400
        italic = bool(os2 and os2.fsSelection & 1) or bool(tt["head"].macStyle & 2)
        wght = None
        if "fvar" in tt:
            axis = next((a for a in tt["fvar"].axes if a.axisTag == "wght"), None)
            if axis is not None:
                wght = (axis.minValue, axis.maxValue)
        cmap = tt.getBestCmap() or {}
    subsets = [name for name, (lo, hi) in _SCRIPTS.items() if any(lo <= c <= hi for c in cmap)]
    return _FontInfo(path, family, weight, italic, wght, subsets)


_SCRIPTS = {"hebrew": (0x05D0, 0x05EA), "latin": (0x41, 0x5A), "arabic": (0x0627, 0x064A),
            "cyrillic": (0x0410, 0x044F), "greek": (0x0391, 0x03C9)}


def _local_fonts() -> list[_FontInfo]:
    """Bundled fonts and the font folder's own files (not the Google download cache)."""
    paths = sorted(p for p in BUNDLED_DIR.iterdir() if p.suffix.lower() in FONT_SUFFIXES)
    folder = font_dir()
    if folder.is_dir():
        paths += sorted(p for p in folder.rglob("*") if p.suffix.lower() in FONT_SUFFIXES
                        and "google" not in p.relative_to(folder).parts)
    out = []
    with _scan_lock:
        for p in paths:
            mtime = p.stat().st_mtime
            if p not in _scanned or _scanned[p][0] != mtime:
                _scanned[p] = (mtime, _read_info(p))
            info = _scanned[p][1]
            if info is not None:
                out.append(info)
    return out


def _variants(infos: list[_FontInfo]) -> list[str]:
    found = set()
    for f in infos:
        if f.weight_range is None:
            weights = [min(max(round(f.weight / 100) * 100, 100), 900)]
        else:
            weights = [w for w in range(100, 1000, 100) if f.weight_range[0] <= w <= f.weight_range[1]]
        found |= {f"{w}{'i' if f.italic else ''}" for w in weights}
    return sorted(found, key=lambda v: (v.endswith("i"), int(v.rstrip("i"))))


def add_font(data: bytes, filename: str = "font") -> FontFamily:
    """Save a font file (TTF, OTF, WOFF or WOFF2) to your font folder and return its family.
    The same file added twice is kept once."""
    if len(data) > MAX_FONT_BYTES:
        raise ValueError(f"the font file is larger than {MAX_FONT_BYTES // 2**20} MB")
    try:
        tt = TTFont(io.BytesIO(data))
    except Exception as e:   # fontTools raises many kinds of errors for a bad file
        raise ValueError(f"could not read {filename!r} as a font ({e})") from None
    with tt:
        if tt.flavor is not None:          # WOFF / WOFF2: store a plain font for HarfBuzz
            tt.flavor = None
            buf = io.BytesIO()
            tt.save(buf)
            data = buf.getvalue()
        suffix = ".otf" if "CFF " in tt or "CFF2" in tt else ".ttf"
    folder = font_dir() / "added"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe(Path(filename).stem)}-{hashlib.sha256(data).hexdigest()[:12]}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    info = _read_info(path)
    if info is None:
        path.unlink()
        raise ValueError(f"{filename!r} has no outlines img2print can use")
    return next(f for f in list_fonts(google=False) if f.family == info.family)


# --- Google Fonts ----------------------------------------------------------------------------------

_catalog_lock = threading.Lock()
_catalog: list[FontFamily] | None = None


def google_catalog() -> list[FontFamily]:
    """Every Google Fonts family. Fetched once a week and kept in the font folder; offline, the
    last copy is used, or nothing."""
    global _catalog
    with _catalog_lock:
        path = font_dir() / "google" / "catalog.json"
        fresh = path.exists() and time.time() - path.stat().st_mtime < CATALOG_MAX_AGE
        if _catalog is not None and fresh:
            return _catalog
        if not fresh and google_enabled():
            try:
                families = _fetch_catalog()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps([f.to_dict() for f in families]), encoding="utf-8")
                _catalog = families
                return families
            except (OSError, ValueError, KeyError):
                pass   # offline or the format changed: fall back to the saved copy
        if path.exists():
            _catalog = [FontFamily(**d) for d in json.loads(path.read_text(encoding="utf-8"))]
        else:
            _catalog = []
        return _catalog


def _fetch_catalog() -> list[FontFamily]:
    raw = _get(GOOGLE_METADATA_URL).decode("utf-8")
    raw = raw[raw.index("{"):]       # the endpoint may start with an anti-JSON-hijacking prefix
    out = []
    for f in json.loads(raw)["familyMetadataList"]:
        variants = sorted(f["fonts"], key=lambda v: (v.endswith("i"), int(v.rstrip("i"))))
        out.append(FontFamily(f["family"], variants, "google", f.get("category") or "",
                              [s for s in f.get("subsets", []) if s != "menu"], int(f.get("popularity") or 0)))
    if not out:
        raise ValueError("empty catalogue")
    return out


def _google_file(family: FontFamily, variant: str) -> Path:
    """Download one style of a Google family (once) and return its path."""
    weight, italic = int(variant.rstrip("i")), variant.endswith("i")
    path = font_dir() / "google" / f"{_safe(family.family)}-{variant}.ttf"
    if path.exists():
        return path
    if not google_enabled():
        raise ValueError(f"font {family.family!r} is not downloaded and Google Fonts is turned off")
    spec = f"{family.family}:ital,wght@{int(italic)},{weight}"
    css = _get(f"{GOOGLE_CSS_URL}?family={urllib.parse.quote(spec)}").decode("utf-8")
    urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", css)
    if not urls:
        raise ValueError(f"Google Fonts has no file for {family.family} {variant}")
    data = _get(urls[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def _get(url: str) -> bytes:
    # A plain user agent: Google's CSS API then serves TTF files, which every library can read.
    req = urllib.request.Request(url, headers={"User-Agent": "img2print"})
    with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as r:
        data = r.read(MAX_FONT_BYTES + 1)
    if len(data) > MAX_FONT_BYTES:
        raise ValueError(f"{url} is larger than {MAX_FONT_BYTES // 2**20} MB")
    return data


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "font"


# --- lookup ----------------------------------------------------------------------------------------

def list_fonts(google: bool = True) -> list[FontFamily]:
    """All families: bundled and your own first, then Google's (when google is true)."""
    by_family: dict[str, list[_FontInfo]] = {}
    for info in _local_fonts():
        by_family.setdefault(info.family, []).append(info)
    out = []
    for family, infos in by_family.items():
        source = "bundled" if all(i.path.parent == BUNDLED_DIR for i in infos) else "local"
        subsets = sorted({s for i in infos for s in i.subsets})
        out.append(FontFamily(family, _variants(infos), source, "", subsets))
    if google:
        local = {f.family.lower() for f in out}
        out += [f for f in google_catalog() if f.family.lower() not in local]
    return out


def font_file(family: str, weight: int = 400, italic: bool = False) -> tuple[Path, dict[str, float]]:
    """The font file for a family and style, downloading it from Google Fonts if needed.

    Returns (path, axes): axes are the variation settings to apply, e.g. {"wght": 700} for a
    variable font; empty for a static one. The nearest available style is used, so asking for
    weight 650 of a family that has 400 and 700 gives 700.
    """
    key = family.strip().lower()
    infos = [i for i in _local_fonts() if i.family.lower() == key]
    if infos:
        def distance(i: _FontInfo) -> float:
            w = weight if i.weight_range is None else min(max(weight, i.weight_range[0]), i.weight_range[1])
            return (i.italic != italic) * 10000 + abs((i.weight if i.weight_range is None else w) - weight)
        best = min(infos, key=lambda i: (distance(i), i.path.parent == BUNDLED_DIR))   # yours first
        axes = {} if best.weight_range is None else \
            {"wght": float(min(max(weight, best.weight_range[0]), best.weight_range[1]))}
        return best.path, axes
    google = next((f for f in google_catalog() if f.family.lower() == key), None)
    if google is None:
        raise ValueError(f"unknown font {family!r}" + ("" if google_enabled() else
                                                        " (Google Fonts is turned off)"))
    variant = min(google.variants, key=lambda v: (v.endswith("i") != italic) * 10000
                  + abs(int(v.rstrip("i")) - weight))
    try:
        return _google_file(google, variant), {}
    except OSError as e:
        raise ValueError(f"could not download {google.family} from Google Fonts ({e})") from None
