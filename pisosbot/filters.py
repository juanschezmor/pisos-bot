"""Descartes duros: lo que ni siquiera merece puntuarse."""
from __future__ import annotations

from .config import Config
from .models import Listing, slugify


def reject_reason(listing: Listing, cfg: Config) -> tuple[str, str] | None:
    """Devuelve (categoría, detalle) del descarte, o None si el anuncio vale."""
    if listing.price is None:
        return ("sin precio", "")
    if listing.price > cfg.max_price:
        return ("fuera de presupuesto", f"{listing.price}€ > {cfg.max_price}€")
    if listing.price < cfg.min_price:
        return ("precio sospechosamente bajo", f"{listing.price}€ (¿habitación?)")

    if not cfg.is_allowed_municipality(listing.municipality_slug):
        return ("municipio fuera de zona", listing.municipality or "?")

    # La superficie ausente no descarta: muchos anuncios buenos no la ponen.
    if listing.surface is not None:
        if listing.surface < cfg.min_surface:
            return ("demasiado pequeño", f"{listing.surface} m²")
        # Cota de cordura: un piso de mas de 300 m2 por menos de 700 € es un
        # error de parseo o una finca rustica, no un chollo.
        if listing.surface > cfg.max_surface:
            return ("superficie implausible", f"{listing.surface} m²")

    if listing.rooms is not None and listing.rooms > cfg.max_rooms:
        return ("demasiadas habitaciones", str(listing.rooms))

    if cfg.exclude_temporary and listing.is_temporary:
        return ("alquiler de temporada", "")

    haystack = slugify(f"{listing.title} {listing.description}")
    for kw in cfg.exclude_keywords:
        if kw in haystack:
            return ("palabra excluida", kw)

    return None


def apply(listings: list[Listing], cfg: Config) -> tuple[list[Listing], dict[str, int]]:
    kept: list[Listing] = []
    rejected: dict[str, int] = {}
    for item in listings:
        reason = reject_reason(item, cfg)
        if reason is None:
            kept.append(item)
        else:
            rejected[reason[0]] = rejected.get(reason[0], 0) + 1
    return kept, rejected
