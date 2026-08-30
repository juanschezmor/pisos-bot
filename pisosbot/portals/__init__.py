"""Registro de portales. Anadir uno nuevo es crear el modulo e importarlo aqui."""
from __future__ import annotations

from .base import Portal
from .fotocasa import Fotocasa
from .habitaclia import Habitaclia
from .milanuncios import Milanuncios
from .pisos_com import PisosCom

ALL: dict[str, type[Portal]] = {
    "fotocasa": Fotocasa,
    "pisos_com": PisosCom,
    "habitaclia": Habitaclia,
    "milanuncios": Milanuncios,
}

__all__ = ["ALL", "Portal", "Fotocasa", "PisosCom", "Habitaclia", "Milanuncios"]
