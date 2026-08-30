"""Colapsa el mismo piso publicado en varios portales.

Fotocasa, Habitaclia y Milanuncios son del mismo grupo (Scout24) y comparten
mucho inventario, asi que sin esto llegarian avisos triplicados.
"""
from __future__ import annotations

from .models import Listing
from .transport import haversine_m

# Prioridad cuando dos anuncios son el mismo piso: nos quedamos con el portal
# que mejores datos da (Fotocasa trae coordenadas y fecha exacta).
PORTAL_RANK = {"fotocasa": 0, "pisos.com": 1, "habitaclia": 2, "milanuncios": 3}


def _same_flat(a: Listing, b: Listing) -> bool:
    if a.price != b.price:
        return False
    if a.municipality_slug != b.municipality_slug:
        return False
    # Si ambos tienen superficie, tiene que cuadrar (+/- 4 m2).
    if a.surface and b.surface and abs(a.surface - b.surface) > 4:
        return False
    # Si ambos tienen coordenadas, tienen que estar practicamente encima.
    if None not in (a.lat, a.lon, b.lat, b.lon):
        return haversine_m(a.lat, a.lon, b.lat, b.lon) <= 150
    return True


def collapse(listings: list[Listing]) -> list[Listing]:
    """Agrupa duplicados y devuelve un representante por piso.

    El representante conserva en `reasons` en que otros portales aparece.
    """
    # Un mismo anuncio puede venir dos veces del mismo portal (por ejemplo,
    # Sevilla capital aparece en dos comarcas de pisos.com).
    by_uid: dict[str, Listing] = {}
    for item in listings:
        by_uid.setdefault(item.uid, item)

    groups: list[list[Listing]] = []
    for item in by_uid.values():
        for group in groups:
            if _same_flat(group[0], item):
                group.append(item)
                break
        else:
            groups.append([item])

    out: list[Listing] = []
    for group in groups:
        group.sort(key=lambda x: PORTAL_RANK.get(x.portal, 99))
        best = group[0]
        # Completa huecos del representante con datos de sus duplicados.
        for other in group[1:]:
            for attr in ("surface", "rooms", "bathrooms", "lat", "lon", "image", "published_ts"):
                if getattr(best, attr) in (None, "") and getattr(other, attr) not in (None, ""):
                    setattr(best, attr, getattr(other, attr))
        others = sorted({x.portal for x in group[1:]} - {best.portal})
        if others:
            best.reasons.append(f"también en {', '.join(others)}")
        out.append(best)
    return out
