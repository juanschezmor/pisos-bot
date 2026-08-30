"""Puntuacion de conectividad con Sevilla por transporte publico.

El criterio: metro > cercanias > autobus. La distancia se mide en linea recta a
la estacion mas cercana y se penaliza suponiendo un recorrido a pie ~1.3x.
"""
from __future__ import annotations

import json
import math
import pathlib

from .models import slugify

_STATIONS: list[dict] | None = None

# Municipios sin ferrocarril: solo autobus interurbano. La nota base refleja
# lo bien conectados que estan por bus con Sevilla.
BUS_BASELINE = {
    "alcala de guadaira": 45,   # M-12x muy frecuentes, pero sin tren
    "coria del rio": 30,        # limite sur del Aljarafe, bus M-14x
    "palomares del rio": 33,
    "almensilla": 28,
    "bormujos": 42,             # bus M-16x frecuente + cercania a metro Cavaleri
    "gines": 40,
    "castilleja de la cuesta": 45,
    "espartinas": 33,
    "tomares": 48,              # pegado a San Juan Alto
    "gelves": 35,
    "bollullos de la mitacion": 25,
    "valencina de la concepcion": 30,
    "santiponce": 32,
}

DEFAULT_BASELINE = 25
SEVILLA_URBAN_BASELINE = 55  # Tussam cubre bien toda la capital


def _load() -> list[dict]:
    global _STATIONS
    if _STATIONS is None:
        path = pathlib.Path(__file__).resolve().parent.parent / "data" / "stations.json"
        _STATIONS = json.loads(path.read_text(encoding="utf-8"))
    return _STATIONS


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos coordenadas."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _distance_score(walk_m: float, mode: str) -> int:
    """Nota 0-100 segun metros a pie hasta la estacion."""
    if mode == "metro":
        tiers = [(400, 100), (700, 92), (1100, 80), (1600, 66), (2200, 52)]
    else:  # cercanias: menos frecuencia, penaliza algo mas
        tiers = [(400, 85), (700, 77), (1100, 66), (1600, 54), (2200, 42)]
    for limit, score in tiers:
        if walk_m <= limit:
            return score
    return 0


def evaluate(lat: float | None, lon: float | None, municipality: str) -> dict:
    """Devuelve {'score', 'label', 'station', 'mode', 'walk_m'} para un anuncio."""
    muni = slugify(municipality)

    if muni.startswith("sevilla"):
        baseline = SEVILLA_URBAN_BASELINE
    else:
        baseline = BUS_BASELINE.get(muni, DEFAULT_BASELINE)

    best = None
    if lat is not None and lon is not None:
        for st in _load():
            straight = haversine_m(lat, lon, st["lat"], st["lon"])
            if straight > 3000:
                continue
            walk = straight * 1.3  # las calles no van en linea recta
            score = _distance_score(walk, st["mode"])
            if score and (best is None or score > best["score"]):
                best = {
                    "score": score,
                    "station": st["name"],
                    "mode": st["mode"],
                    "walk_m": int(walk),
                }

    if best is None:
        label = "sin estación cerca" if lat else "ubicación aproximada"
        return {"score": baseline, "label": label, "station": None, "mode": None, "walk_m": None}

    # La nota final nunca baja del suelo del municipio: tener metro cerca suma,
    # no tenerlo no debe hundir a un piso en pleno centro de Sevilla.
    final = max(best["score"], baseline)
    icon = "🚇" if best["mode"] == "metro" else "🚆"
    label = f"{icon} {best['station']} · {best['walk_m']} m"
    return {
        "score": final,
        "label": label,
        "station": best["station"],
        "mode": best["mode"],
        "walk_m": best["walk_m"],
    }
