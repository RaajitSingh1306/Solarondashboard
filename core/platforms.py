"""
Solaron Platform Registry — single source of truth for every inverter / monitoring portal.

Every UI selector, chart axis, badge colour, sync estimate and data contract must read
from this module instead of hard-coding platform lists. Adding a new portal only requires
registering it here (plus its extractor in ``pipeline.get_extractors``).
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class PlatformMeta(TypedDict):
    label: str          # Human readable name
    segment: str        # Typical customer segment served by the portal
    color: str          # Hex accent colour (charts / cards)
    quasar: str         # Quasar colour token (badges / chips)
    icon: str           # Material icon name
    method: str         # Extraction method
    est_sync_s: int     # Typical full-fleet live sync duration (seconds)


PLATFORMS: Dict[str, PlatformMeta] = {
    "growatt": {
        "label": "Growatt",
        "segment": "Residential",
        "color": "#818CF8",
        "quasar": "indigo-6",
        "icon": "home",
        "method": "REST API",
        "est_sync_s": 75,
    },
    "isolarcloud": {
        "label": "iSolarCloud",
        "segment": "Commercial",
        "color": "#22D3EE",
        "quasar": "cyan-7",
        "icon": "apartment",
        "method": "Browser session",
        "est_sync_s": 60,
    },
    "suryalog": {
        "label": "SuryaLog",
        "segment": "Industrial",
        "color": "#FB923C",
        "quasar": "orange-7",
        "icon": "factory",
        "method": "Browser session",
        "est_sync_s": 180,
    },
    "fronius": {
        "label": "Fronius",
        "segment": "Commercial",
        "color": "#F472B6",
        "quasar": "pink-6",
        "icon": "bolt",
        "method": "Solar.web API",
        "est_sync_s": 45,
    },
    "injectsolar": {
        "label": "InjectSolar",
        "segment": "C&I",
        "color": "#34D399",
        "quasar": "teal-6",
        "icon": "electric_meter",
        "method": "Browser session",
        "est_sync_s": 90,
    },
}

ALL_KEY = "All"
_FALLBACK_COLOR = "#9CA3AF"


def platform_keys() -> List[str]:
    """Ordered list of registered platform keys (lower-case)."""
    return list(PLATFORMS.keys())


def label(key: Optional[str]) -> str:
    """Display label for a platform key ('All' → 'All Platforms')."""
    if not key or str(key).lower() == "all":
        return "All Platforms"
    meta = PLATFORMS.get(str(key).lower())
    return meta["label"] if meta else str(key).title()


def color(key: Optional[str]) -> str:
    meta = PLATFORMS.get(str(key or "").lower())
    return meta["color"] if meta else _FALLBACK_COLOR


def quasar_color(key: Optional[str]) -> str:
    meta = PLATFORMS.get(str(key or "").lower())
    return meta["quasar"] if meta else "grey-7"


def est_sync_seconds(key: Optional[str]) -> float:
    """Expected live-sync duration. 'All' sums portals (they run sequentially)."""
    if not key or str(key).lower() == "all":
        return float(sum(m["est_sync_s"] for m in PLATFORMS.values()))
    meta = PLATFORMS.get(str(key).lower())
    return float(meta["est_sync_s"]) if meta else 60.0


def options(include_all: bool = True, counts: Optional[Dict[str, int]] = None) -> Dict[str, str]:
    """
    Options dict for ``ui.select`` → {value: label}. Values stay lower-case keys so they can be
    passed straight into SQL filters; 'All' is kept as the sentinel the rest of the app expects.
    """
    opts: Dict[str, str] = {}
    if include_all:
        total = sum(counts.values()) if counts else None
        opts[ALL_KEY] = f"All Platforms ({total})" if total is not None else "All Platforms"
    for k, meta in PLATFORMS.items():
        if counts is not None:
            opts[k] = f"{meta['label']} ({counts.get(k, 0)})"
        else:
            opts[k] = meta["label"]
    return opts


def names_sentence() -> str:
    """'Growatt, iSolarCloud, SuryaLog, Fronius & InjectSolar'."""
    names = [m["label"] for m in PLATFORMS.values()]
    return ", ".join(names[:-1]) + f" & {names[-1]}" if len(names) > 1 else names[0]


def normalize(source: Optional[str]) -> str:
    """Map raw source strings from CSVs / portals onto a registered key."""
    s = str(source or "").lower().strip()
    if not s:
        return "unknown"
    if "isolarcloud" in s or "sungrow" in s:
        return "isolarcloud"
    if "suryalog" in s:
        return "suryalog"
    if "growatt" in s:
        return "growatt"
    if "fronius" in s or "solarweb" in s or "solar.web" in s:
        return "fronius"
    if "inject" in s:
        return "injectsolar"
    return s


def vue_color_expr(field: str = "props.value") -> str:
    """Vue ternary chain that maps a platform key to its Quasar colour token (for table slots)."""
    expr = "'grey-7'"
    for k, meta in reversed(list(PLATFORMS.items())):
        expr = f"{field} === '{k}' ? '{meta['quasar']}' : ({expr})"
    return expr


def vue_label_expr(field: str = "props.value") -> str:
    """Vue ternary chain that maps a platform key to its display label."""
    expr = field
    for k, meta in reversed(list(PLATFORMS.items())):
        expr = f"{field} === '{k}' ? '{meta['label']}' : ({expr})"
    return expr
