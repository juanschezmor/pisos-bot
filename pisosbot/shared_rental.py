"""Detecta anuncios que dicen ser un piso entero pero alquilan por habitaciones.

Es el falso positivo mas caro del bot: un anuncio de habitacion lleva el precio
de UNA habitacion y la superficie del piso ENTERO, asi que su €/m2 sale
ridiculamente bajo y el detector de chollos lo empuja a lo mas alto de la lista.

Dos capas. Aqui van solo patrones de alta precision, y se aplican antes de
calcular la mediana de €/m2 para que estos anuncios tampoco distorsionen el
baremo del resto. Lo ambiguo ("piso exclusivo para estudiantes", sin mas datos)
se deja al clasificador de llm.py, que juzga por contexto y no por cadenas.
"""
from __future__ import annotations

import re
import unicodedata

# No se usa slugify() a proposito: borra el simbolo de moneda y la barra, y
# entonces "300€/habitacion" y "consta de 1 habitacion" quedan identicos.
# Aqui se conservan € y / porque son justo la senal que distingue el caso.
_KEEP = re.compile(r"[^a-z0-9€/:\s]+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("ñ", "n").replace("eur", "€").replace("euros", "€")
    return re.sub(r"\s+", " ", _KEEP.sub(" ", text)).strip()


_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Precio referido explicitamente a la habitacion: "300€/habitacion",
    # "300 € por habitacion", "habitacion: 300€". Exige la moneda, que es lo
    # que separa esto de un inocente "consta de 1 habitacion".
    ("precio por habitación", re.compile(
        r"\d+\s*€\s*(?:al mes\s*)?(?:/|por|cada|la)\s*habitacion"
        r"|habitacion\s*[:/]\s*\d+\s*€"
        r"|precio\s+por\s+habitacion"
    )),
    ("precio por persona", re.compile(r"\d+\s*€\s*(?:al mes\s*)?(?:/|por)\s*persona\b")),
    # Singular y plural: "se alquilan habitaciones" y "se alquila habitacion".
    # El verbo tiene que ir pegado al sustantivo, para que "alquilo piso con
    # habitacion amplia" no salte.
    ("se alquila(n) habitación(es)", re.compile(
        r"\b(?:se\s+)?alquil\w+\s+(?:una?\s+|las?\s+)?habitacion(?:es)?\b"
    )),
    ("alquiler por habitaciones", re.compile(r"\balquiler\s+por\s+habitaciones\b")),
    ("busca compañero de piso", re.compile(r"\bbusc\w*\s+(?:\w+\s+){0,3}?compane\w+\s+de\s+piso\b")),
    ("compañeros de piso", re.compile(r"\bcompane\w+\s+de\s+piso\b")),
    ("piso compartido", re.compile(r"\bpiso\s+compartido\b|\bcompartir\s+(?:el\s+)?piso\b")),
    # "quedan 2 habitaciones disponibles" -> exige el cuantificador delante,
    # para no chocar con "3 habitaciones" a secas.
    # Las residencias de estudiantes y los coliving de Sevilla se anuncian a
    # menudo en ingles, para captar estudiantes internacionales. Alquilan por
    # plaza, no la vivienda entera, y ningun patron en espanol los coge.
    ("anuncio en inglés por habitación", re.compile(
        r"\bstudent (?:accommodation|housing|residence)\b"
        r"|\bshared (?:flat|apartment|room)\b"
        r"|\bflat ?mates?\b|\broom ?mates?\b"
        r"|\bper (?:room|person)\b"
        r"|\bprivate room\b|\bensuite room\b"
        r"|\bco ?living\b"
    )),
    ("quedan habitaciones libres", re.compile(
        r"\b(?:quedan?|hay|aun)\s+\d*\s*habitacion\w*\s+(?:libres?|disponibles?)\b"
    )),
]


def detect(*texts: str) -> str | None:
    """Devuelve el nombre del patron que salta, o None si ninguno lo hace."""
    haystack = normalize(" ".join(t for t in texts if t))
    if not haystack:
        return None
    for label, pattern in _PATTERNS:
        if pattern.search(haystack):
            return label
    return None
