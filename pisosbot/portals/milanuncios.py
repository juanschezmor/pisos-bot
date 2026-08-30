"""Milanuncios: la mejor fuente de particulares.

Solo renderiza en servidor las primeras tarjetas de cada pagina, pero como
pedimos el listado ordenado por fecha, esas son precisamente las mas recientes,
que es justo lo que necesita una alerta.

El municipio se saca de la URL del anuncio (.../alquiler-de-pisos-en-<muni>-sevilla/...)
porque el texto visible da el barrio ("Montequinto (Sevilla)"), no el municipio.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Listing
from .base import Portal

BASE = "https://www.milanuncios.com/alquiler-de-pisos-en-sevilla/"

_MUNI_FROM_URL = re.compile(r"/alquiler-de-pisos-en-([a-z0-9\-]+?)-sevilla/")
_ID_FROM_URL = re.compile(r"-(\d+)\.htm")
_NUM = re.compile(r"[\d.]+")


class Milanuncios(Portal):
    name = "milanuncios"

    def search_urls(self) -> list[str]:
        q = f"?orden=date&hasta={self.cfg.max_price}"
        urls = [f"{BASE}{q}"]
        for page in range(2, self.cfg.pages + 1):
            urls.append(f"{BASE}{q}&pagina={page}")
        return urls

    def parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []

        for card in soup.select("article.ma-AdCardV2"):
            link = next((a for a in card.find_all("a") if a.get("href")), None)
            if not link:
                continue  # tarjeta sin enlace utilizable
            href = link["href"]

            muni_match = _MUNI_FROM_URL.search(href)
            id_match = _ID_FROM_URL.search(href)
            if not muni_match or not id_match:
                continue
            municipality = muni_match.group(1).replace("-", " ")

            price_el = card.select_one(".ma-AdPrice-value")
            price = None
            if price_el:
                m = _NUM.search(price_el.get_text().replace("\xa0", " "))
                if m:
                    try:
                        price = int(m.group(0).replace(".", ""))
                    except ValueError:
                        price = None

            surface = rooms = baths = None
            for tag in card.select(".ma-AdTag-label"):
                text = tag.get_text(" ", strip=True).lower()
                num = _NUM.search(text)
                value = int(num.group(0).replace(".", "")) if num else None
                if value is None:
                    continue
                if "m²" in text or "m2" in text:
                    surface = value
                elif "dorm" in text or "hab" in text:
                    rooms = value
                elif "baño" in text or "bano" in text:
                    baths = value

            loc_el = card.select_one(".ma-AdLocation")
            title_el = card.select_one(".ma-AdCardListingV2-TitleLink") or card.find(["h2", "h3"])
            desc_el = card.select_one(".ma-AdCardV2-detail, .ma-SharedText")
            img = card.find("img")

            out.append(
                Listing(
                    portal=self.name,
                    portal_id=id_match.group(1),
                    url=f"https://www.milanuncios.com{href}" if href.startswith("/") else href,
                    title=title_el.get_text(" ", strip=True) if title_el else "",
                    price=price,
                    surface=surface,
                    rooms=rooms,
                    bathrooms=baths,
                    municipality=municipality,
                    neighborhood=(
                        loc_el.get_text(" ", strip=True).split("(")[0].strip() if loc_el else ""
                    ),
                    # Milanuncios es mayoritariamente particulares, pero no lo
                    # declara en el listado: lo dejamos sin determinar.
                    is_agency=None,
                    image=(img.get("src") or "") if img else "",
                    description=desc_el.get_text(" ", strip=True) if desc_el else "",
                )
            )
        return out
