"""Fotocasa: la mejor fuente del lote.

Incrusta en el HTML un JSON completo (<script id="__initial_props__">) con
precio, superficie, coordenadas GPS y fecha exacta de publicacion, y admite
busqueda a nivel de provincia con filtro de precio y orden por fecha. Con eso,
dos peticiones cubren toda el area metropolitana.
"""
from __future__ import annotations

import json
import re

from ..models import Listing
from .base import Portal

_INITIAL = re.compile(
    r'<script[^>]*id="__initial_props__"[^>]*>(.*?)</script>', re.S
)

BASE = "https://www.fotocasa.es/es/alquiler/viviendas/sevilla-provincia/todas-las-zonas/l"


def _find_listings(node, depth: int = 0):
    """Localiza el array 'realEstates' sin depender de la ruta exacta del JSON."""
    if depth > 10:
        return None
    if isinstance(node, dict):
        val = node.get("realEstates")
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
        for child in node.values():
            found = _find_listings(child, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node[:60]:
            found = _find_listings(child, depth + 1)
            if found is not None:
                return found
    return None


def _localized(value) -> str:
    """Fotocasa devuelve algunos campos como {"es-ES": "..."}."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("es-ES") or next(iter(value.values()), "") or ""
    return ""


def _feature(raw: dict, key: str) -> int | None:
    for f in raw.get("features") or []:
        if f.get("key") == key:
            try:
                return int(f["value"])
            except (TypeError, ValueError):
                return None
    return None


class Fotocasa(Portal):
    name = "fotocasa"

    def search_urls(self) -> list[str]:
        q = f"?maxPrice={self.cfg.max_price}&sortType=publicationDate"
        urls = [f"{BASE}{q}"]
        for page in range(2, self.cfg.pages + 1):
            urls.append(f"{BASE}/{page}{q}")
        return urls

    def parse(self, html: str) -> list[Listing]:
        m = _INITIAL.search(html)
        if not m:
            return []
        rows = _find_listings(json.loads(m.group(1))) or []

        out: list[Listing] = []
        for raw in rows:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            addr = raw.get("address") or {}
            coords = raw.get("coordinates") or {}
            date = raw.get("date") or {}

            # 'detail' viene como {"es-ES": "/ruta/al/anuncio"}.
            path = _localized(raw.get("detail")) or _localized(raw.get("detailWithParams"))
            if not path:
                continue
            url = path if path.startswith("http") else f"https://www.fotocasa.es{path}"

            image = ""
            multimedia = raw.get("multimedia") or []
            if multimedia and isinstance(multimedia[0], dict):
                image = multimedia[0].get("src") or multimedia[0].get("url") or ""

            ts = date.get("timestamp")

            out.append(
                Listing(
                    portal=self.name,
                    portal_id=str(raw["id"]),
                    url=url,
                    title=_localized(raw.get("description")) or addr.get("neighborhood") or "Piso",
                    price=raw.get("rawPrice"),
                    surface=_feature(raw, "surface"),
                    rooms=_feature(raw, "rooms"),
                    bathrooms=_feature(raw, "bathrooms"),
                    municipality=addr.get("municipality") or addr.get("city") or "",
                    neighborhood=addr.get("neighborhood") or addr.get("district") or "",
                    lat=coords.get("latitude"),
                    lon=coords.get("longitude"),
                    published_ts=ts / 1000 if ts else None,
                    is_agency=(raw.get("clientType") != "particular"),
                    is_temporary=bool(raw.get("isTemporaryRental")),
                    image=image,
                    description=_localized(raw.get("description")),
                )
            )
        return out
