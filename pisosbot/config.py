"""Carga y validacion de config.yaml."""
from __future__ import annotations

import pathlib
from typing import Any

import yaml

from .models import slugify

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Config:
    def __init__(self, data: dict[str, Any]):
        self._d = data
        self.max_price: int = data["budget"]["max_price"]
        self.min_price: int = data["budget"]["min_price"]

        f = data["filters"]
        self.min_surface: int = f["min_surface"]
        self.max_surface: int = f.get("max_surface", 300)
        self.max_rooms: int = f["max_rooms"]
        self.exclude_temporary: bool = f["exclude_temporary"]
        self.exclude_keywords: list[str] = [slugify(k) for k in f["exclude_keywords"]]

        self.zones: dict[str, list[str]] = {
            zone: [slugify(m) for m in munis] for zone, munis in data["zones"].items()
        }
        self.allowed: set[str] = {m for munis in self.zones.values() for m in munis}

        s = data["scoring"]
        self.weights: dict[str, float] = s["weights"]
        self.hot_threshold: float = s["hot_threshold"]

        self.aliases: dict[str, str] = {
            slugify(k): slugify(v) for k, v in (data.get("aliases") or {}).items()
        }

        self.portals: dict[str, bool] = data.get("portals", {})

        r = data.get("runtime", {})
        self.min_delay: float = r.get("min_delay", 1.5)
        self.pages: int = r.get("pages", 2)
        self.flood_guard: int = r.get("flood_guard", 12)

    def normalize_municipality(self, municipality_slug: str) -> str:
        """Traduce barrios que los portales publican como municipio."""
        return self.aliases.get(municipality_slug, municipality_slug)

    def zone_of(self, municipality_slug: str) -> str | None:
        for zone, munis in self.zones.items():
            if municipality_slug in munis:
                return zone
        return None

    def is_allowed_municipality(self, municipality_slug: str) -> bool:
        """Sevilla capital llega con muchos alias ('Sevilla Capital', barrios)."""
        if not municipality_slug:
            return False
        municipality_slug = self.normalize_municipality(municipality_slug)
        if municipality_slug in self.allowed:
            return True
        # 'sevilla capital', 'sevilla ciudad'...
        return municipality_slug.split(" ")[0] == "sevilla"


def load(path: str | pathlib.Path | None = None) -> Config:
    p = pathlib.Path(path) if path else ROOT / "config.yaml"
    return Config(yaml.safe_load(p.read_text(encoding="utf-8")))
