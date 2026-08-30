"""Pruebas de precision del detector de alquiler por habitaciones.

Sin dependencias: python3 tests/test_shared_rental.py

Esta logica es delicada en las dos direcciones. Si es demasiado laxa se cuelan
habitaciones disfrazadas de piso (y ademas encabezan la lista, porque su €/m2
falso las marca como chollo). Si es demasiado agresiva tira pisos enteros
legitimos. Cada caso de aqui viene de un anuncio real.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pisosbot.shared_rental import detect  # noqa: E402

DEBE_SALTAR = [
    "Se alquila piso de estudiantes, 3 habitaciones, quedan 2 disponibles 300€/habitación",
    "Hola! Mi nombre es carmen, busco dos compañeras de piso de septiembre hasta junio",
    "Se alquilan habitaciones en piso luminoso y tranquilo en sevilla",
    "Alquiler por habitaciones, 280 € por habitación",
    "Habitación: 350€ gastos incluidos",
    "Piso compartido con dos chicas",
    "Quedan 2 habitaciones libres",
    "250 € por persona al mes",
    "Se alquila habitación en piso céntrico",
    # Anuncio real: residencia de estudiantes en La Cartuja, anunciada en
    # inglés, que ningún patrón en español detectaba.
    "Sevilla Lago is a student accommodation located in La Cartuja, close to the university",
    "Bright private room in a shared flat, all bills included",
    "Looking for a flatmate from September, 350 per person",
    "Modern coliving space in the city centre",
]

# El motivo por el que cada uno NO debe saltar, para que quede claro al leerlo.
NO_DEBE_SALTAR = [
    ("Estupendo piso en La Motilla de 50 m2. Consta de 1 habitación, salón comedor",
     "'1 habitación' no es un precio por habitación"),
    ("Piso muy luminoso, dispone de 3 habitaciones, salón amplio, cocina independiente",
     "enumerar habitaciones es lo normal en un piso entero"),
    ("Alquilo piso de 69 metros cuadrados, con salón-comedor, 3 dormitorios, un baño",
     "'alquilo piso' no es 'alquilo habitaciones'"),
    ("Cada habitación tiene armario empotrado y aire acondicionado",
     "describe el equipamiento, no un precio por habitación"),
    ("Amplio loft, ideal para 1 persona o 1 pareja",
     "'1 persona' sin precio no implica compartir"),
    ("Vivienda de dos habitaciones con plaza de garaje incluida por 700 €",
     "'plaza' aquí es de garaje"),
    ("Piso de 3 habitaciones disponibles desde septiembre",
     "'disponibles' se refiere a la fecha, no a plazas libres"),
    ("Piso exclusivo para estudiantes curso 2026-2027 en calle peatonal",
     "ambiguo a proposito: lo resuelve el clasificador, no las reglas"),
    ("Bright apartment in the city centre, fully furnished, two bedrooms",
     "en ingles pero es la vivienda entera"),
    ("Spacious flat with living room and private terrace",
     "'private terrace' no es 'private room'"),
]


def main() -> int:
    fallos = []

    for texto in DEBE_SALTAR:
        if not detect(texto):
            fallos.append(f"NO detectado (debería): {texto[:70]}")

    for texto, razon in NO_DEBE_SALTAR:
        hit = detect(texto)
        if hit:
            fallos.append(f"falso positivo [{hit}]: {texto[:60]} — {razon}")

    total = len(DEBE_SALTAR) + len(NO_DEBE_SALTAR)
    if fallos:
        print(f"{len(fallos)}/{total} FALLOS:")
        for f in fallos:
            print(f"  - {f}")
        return 1

    print(f"{total}/{total} pruebas OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
