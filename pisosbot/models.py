"""Modelo comun al que se normalizan todos los portales."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


def slugify(text: str) -> str:
    """Minusculas sin acentos ni puntuacion, para comparar municipios."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("ñ", "n")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@dataclass
class Listing:
    """Un anuncio ya normalizado, venga del portal que venga."""

    portal: str
    portal_id: str
    url: str
    title: str = ""
    price: int | None = None
    surface: int | None = None
    rooms: int | None = None
    bathrooms: int | None = None
    municipality: str = ""
    neighborhood: str = ""
    lat: float | None = None
    lon: float | None = None
    published_ts: float | None = None
    is_agency: bool | None = None
    is_temporary: bool = False
    image: str = ""
    description: str = ""

    # Rellenado por las fases de enriquecimiento.
    transport: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    price_per_m2: float | None = None
    deal_ratio: float | None = None

    @property
    def uid(self) -> str:
        return f"{self.portal}:{self.portal_id}"

    @property
    def municipality_slug(self) -> str:
        return slugify(self.municipality)

    def fingerprint(self) -> str:
        """Huella para detectar el mismo piso publicado en varios portales.

        Precio exacto + superficie redondeada a 5 m2 + municipio identifica el
        mismo inmueble con muy pocos falsos positivos; las coordenadas se
        comparan aparte porque no todos los portales las dan.
        """
        surf = round(self.surface / 5) * 5 if self.surface else 0
        return hashlib.sha1(
            f"{self.price}|{surf}|{self.municipality_slug}|{self.rooms or 0}".encode()
        ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "portal": self.portal,
            "url": self.url,
            "title": self.title,
            "price": self.price,
            "surface": self.surface,
            "rooms": self.rooms,
            "municipality": self.municipality,
            "neighborhood": self.neighborhood,
            "lat": self.lat,
            "lon": self.lon,
            "published_ts": self.published_ts,
            "is_agency": self.is_agency,
            "score": round(self.score, 1),
            "transport": self.transport,
            "price_per_m2": self.price_per_m2,
            "deal_ratio": self.deal_ratio,
        }
