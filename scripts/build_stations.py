"""Descarga las estaciones de transporte del area metropolitana de Sevilla desde
OpenStreetMap (Overpass) y las guarda en data/stations.json.

Se ejecuta a mano cuando la red de transporte cambia; el bot solo lee el JSON.
    python3 scripts/build_stations.py
"""
import json
import pathlib
import sys
import urllib.request

OVERPASS = "https://overpass-api.de/api/interpreter"

# Area metropolitana de Sevilla: del Aljarafe a Alcala, de Santiponce a Utrera.
BBOX = (37.15, -6.30, 37.50, -5.75)

QUERY = f"""
[out:json][timeout:90];
(
  node["railway"="station"]{BBOX};
  node["railway"="halt"]{BBOX};
  way["railway"="station"]{BBOX};
);
out center tags;
"""


def fetch():
    req = urllib.request.Request(
        OVERPASS,
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "pisos-bot/1.0 (uso personal)"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def classify(tags):
    """Devuelve (modo, peso) o None si la estacion no nos interesa."""
    if tags.get("station") == "subway" or tags.get("subway") == "yes":
        return "metro"
    if tags.get("light_rail") == "yes" or tags.get("station") == "light_rail":
        return "metro"
    operator = (tags.get("operator") or "").lower()
    network = (tags.get("network") or "").lower()
    if "metro de sevilla" in operator or "metro de sevilla" in network:
        return "metro"
    if tags.get("railway") in ("station", "halt"):
        if "cercanias" in network or "cercanías" in network:
            return "cercanias"
        if tags.get("train") == "yes" or tags.get("railway") == "halt":
            return "cercanias"
        return "cercanias"
    return None


def main():
    import urllib.parse  # noqa: F401  (usado arriba)

    data = fetch()
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        mode = classify(tags)
        if not mode:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        out.append(
            {
                "name": name,
                "mode": mode,
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "line": tags.get("ref") or tags.get("line") or "",
            }
        )

    # Deduplica por (nombre, modo) quedandonos con la primera aparicion.
    seen = set()
    uniq = []
    for s in sorted(out, key=lambda s: (s["mode"], s["name"])):
        key = (s["name"].lower(), s["mode"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)

    dest = pathlib.Path(__file__).resolve().parent.parent / "data" / "stations.json"
    dest.write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")
    metro = sum(1 for s in uniq if s["mode"] == "metro")
    print(f"{len(uniq)} estaciones -> {dest}  (metro: {metro}, cercanias: {len(uniq)-metro})")
    return 0


if __name__ == "__main__":
    import urllib.parse

    sys.exit(main())
