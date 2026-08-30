"""Habitaclia: paginas por municipio.

Es del mismo grupo que Fotocasa (Scout24), asi que su inventario se solapa
bastante; el dedup se encarga. Aporta sobre todo anuncios de agencias locales
que a veces no estan en el resto.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Listing
from .base import Portal

BASE = "https://www.habitaclia.com/alquiler-{muni}.htm?pmax={max_price}"

# Municipios con suficiente oferta como para que compense una peticion.
MUNICIPIOS = (
    "sevilla",
    "dos_hermanas",
    "alcala_de_guadaira",
    "mairena_del_aljarafe",
    "tomares",
    "san_juan_de_aznalfarache",
)

_PRICE = re.compile(r"[\d.]+")


class Habitaclia(Portal):
    name = "habitaclia"

    def search_urls(self) -> list[str]:
        return [BASE.format(muni=m, max_price=self.cfg.max_price) for m in MUNICIPIOS]

    def parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []

        for card in soup.select("article.js-list-item[data-id]"):
            url = card.get("data-href") or ""
            if not url:
                continue

            price = None
            price_el = card.find(attrs={"itemprop": "price"})
            if price_el:
                m = _PRICE.search(price_el.get_text().replace("\xa0", " "))
                if m:
                    try:
                        price = int(m.group(0).replace(".", ""))
                    except ValueError:
                        price = None

            feat = card.select_one(".list-item-feature")
            feat_text = feat.get_text(" ", strip=True).lower() if feat else ""
            # "81m 2 - 2 habitaciones - 2 baños - 22,22€/m 2"  (el 2 es un <sup>)
            surface = _first_int(feat_text, r"(\d+)\s*m")
            rooms = _first_int(feat_text, r"(\d+)\s*habitacion")
            baths = _first_int(feat_text, r"(\d+)\s*ba[nñ]o")

            loc_el = card.select_one(".list-item-location")
            location = loc_el.get_text(" ", strip=True) if loc_el else ""
            # "Sevilla - Alfalfa - Santa Cruz" -> municipio, barrio
            parts = [p.strip() for p in location.split("-") if p.strip()]
            municipality = parts[0] if parts else ""
            neighborhood = " - ".join(parts[1:]) if len(parts) > 1 else ""

            title_el = card.select_one(".list-item-title")
            desc_el = card.find(attrs={"itemprop": "description"})
            img = card.find("img")

            out.append(
                Listing(
                    portal=self.name,
                    portal_id=str(card["data-id"]),
                    url=url.split("?")[0],
                    title=title_el.get_text(" ", strip=True) if title_el else "",
                    price=price,
                    surface=surface,
                    rooms=rooms,
                    bathrooms=baths,
                    municipality=municipality,
                    neighborhood=neighborhood,
                    is_agency=(card.get("data-esparticular") != "PARTICULAR"),
                    image=(img.get("src") or img.get("data-src") or "") if img else "",
                    description=desc_el.get_text(" ", strip=True) if desc_el else "",
                )
            )
        return out


def _first_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None
