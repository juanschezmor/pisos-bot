"""Nota 0-100 de cada anuncio y deteccion de chollos.

La mediana de precio/m2 se calcula con TODOS los anuncios vistos en la ronda
(no solo los nuevos), asi el baremo es el mercado real de esta semana.
"""
from __future__ import annotations

import statistics
import time

from .config import Config
from .models import Listing
from . import transport

MIN_SAMPLES = 8


def _median_table(listings: list[Listing]) -> tuple[dict[str, float], float | None]:
    """Mediana de €/m2 por municipio, mas la global como respaldo."""
    by_muni: dict[str, list[float]] = {}
    every: list[float] = []
    for x in listings:
        if x.price and x.surface and x.surface >= 15:
            ppm = x.price / x.surface
            by_muni.setdefault(x.municipality_slug, []).append(ppm)
            every.append(ppm)
    table = {
        muni: statistics.median(vals)
        for muni, vals in by_muni.items()
        if len(vals) >= MIN_SAMPLES
    }
    return table, (statistics.median(every) if len(every) >= MIN_SAMPLES else None)


def _deal_score(ratio: float | None) -> float:
    """ratio = €/m2 del piso / mediana de su zona. Menos es mejor."""
    if ratio is None:
        return 50.0  # sin datos, nota neutra
    for limit, score in ((0.70, 100), (0.80, 88), (0.90, 74), (1.00, 58),
                         (1.10, 42), (1.25, 25)):
        if ratio <= limit:
            return float(score)
    return 10.0


def _freshness_score(ts: float | None) -> float:
    if ts is None:
        return 55.0
    hours = max(0.0, (time.time() - ts) / 3600)
    for limit, score in ((1, 100), (3, 92), (6, 82), (12, 70), (24, 58), (72, 40)):
        if hours <= limit:
            return float(score)
    return 20.0


def enrich(listings: list[Listing], cfg: Config) -> list[Listing]:
    """Anade transporte, precio/m2, nota y motivos legibles."""
    table, global_median = _median_table(listings)

    for x in listings:
        x.transport = transport.evaluate(x.lat, x.lon, x.municipality)

        if x.price and x.surface and x.surface >= 15:
            x.price_per_m2 = round(x.price / x.surface, 1)
            baseline = table.get(x.municipality_slug) or global_median
            if baseline:
                x.deal_ratio = round(x.price_per_m2 / baseline, 3)

        w = cfg.weights
        deal = _deal_score(x.deal_ratio)
        fresh = _freshness_score(x.published_ts)
        private = 100.0 if x.is_agency is False else (35.0 if x.is_agency else 55.0)

        x.score = (
            w["transport"] * x.transport["score"]
            + w["deal"] * deal
            + w["freshness"] * fresh
            + w["private_seller"] * private
        )

        # Motivos: solo lo que de verdad distingue a este piso.
        if x.transport.get("mode") == "metro" and (x.transport.get("walk_m") or 9999) <= 700:
            x.reasons.insert(0, "metro a menos de 10 min andando")
        if x.deal_ratio and x.deal_ratio <= 0.80:
            pct = round((1 - x.deal_ratio) * 100)
            x.reasons.insert(0, f"{pct}% por debajo del €/m² de la zona")
        if x.is_agency is False:
            x.reasons.append("particular (sin honorarios)")
        if x.published_ts and (time.time() - x.published_ts) <= 3600:
            x.reasons.append("publicado hace menos de 1 h")

    listings.sort(key=lambda x: x.score, reverse=True)
    return listings
