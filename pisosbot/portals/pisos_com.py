"""pisos.com: comarcas ordenadas por fecha.

La provincia entera no tiene pagina propia, pero si sus comarcas, y las tres
que usamos cubren exactamente la zona de busqueda. Cada tarjeta HTML tiene un
bloque ld+json hermano con coordenadas GPS, que emparejamos por id.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..models import Listing
from .base import Portal

BASE = "https://www.pisos.com/alquiler/pisos-{area}/hasta-{max_price}/fecharecientedesde-desc/"

# Sevilla capital, el Aljarafe y el area metropolitana este (Dos Hermanas,
# Alcala de Guadaira, Camas).
AREAS = ("sevilla_capital", "el_aljarafe", "area_de_sevilla")

_NUM = re.compile(r"[\d.]+")


def _int(text: str | None) -> int | None:
    if not text:
        return None
    m = _NUM.search(text.replace("\xa0", " "))
    if not m:
        return None
    try:
        return int(m.group(0).replace(".", ""))
    except ValueError:
        return None


class PisosCom(Portal):
    name = "pisos.com"

    def search_urls(self) -> list[str]:
        return [BASE.format(area=a, max_price=self.cfg.max_price) for a in AREAS]

    def parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")

        # ld+json indexado por id: aporta coordenadas y municipio limpio.
        meta: dict[str, dict] = {}
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                obj = json.loads(tag.string or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(obj, dict) and obj.get("@id"):
                meta[str(obj["@id"])] = obj

        out: list[Listing] = []
        for card in soup.select("div.ad-preview[id]"):
            ad_id = card.get("id")
            href = card.get("data-lnk-href") or ""
            if not ad_id or not href:
                continue

            info = meta.get(ad_id, {})
            geo = info.get("geo") or {}
            address = info.get("address") or {}

            price_el = card.select_one(".ad-preview__price")
            title_el = card.select_one(".ad-preview__title")
            desc_el = card.select_one(".ad-preview__description")

            surface = rooms = baths = None
            for char in card.select(".ad-preview__char"):
                text = char.get_text(" ", strip=True).lower()
                if "m²" in text or "m2" in text:
                    surface = _int(text)
                elif "hab" in text:
                    rooms = _int(text)
                elif "baño" in text or "bano" in text:
                    baths = _int(text)

            def _f(value):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None

            out.append(
                Listing(
                    portal=self.name,
                    portal_id=ad_id,
                    url=f"https://www.pisos.com{href}" if href.startswith("/") else href,
                    title=title_el.get_text(" ", strip=True) if title_el else "",
                    price=_int(price_el.get_text() if price_el else None),
                    surface=surface,
                    rooms=rooms,
                    bathrooms=baths,
                    municipality=address.get("addressLocality", ""),
                    neighborhood=(
                        card.select_one(".ad-preview__info").get_text(" ", strip=True)
                        if card.select_one(".ad-preview__info")
                        else ""
                    ),
                    lat=_f(geo.get("latitude")),
                    lon=_f(geo.get("longitude")),
                    image=info.get("image", ""),
                    description=desc_el.get_text(" ", strip=True) if desc_el else "",
                )
            )
        return out
