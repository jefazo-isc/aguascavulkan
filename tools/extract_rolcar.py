#!/usr/bin/env python3
"""Extrae todas las sucursales de Rolcar (Refaccionaria Rogelio) en Aguascalientes desde INEGI DENUE."""

import csv
import json
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from geo_dem import geo_to_meters

ORIGIN_LAT = 21.8807
ORIGIN_LON = -102.2965
MACRO_SIZE = 1024.0


def extract_rolcar_branches(csv_path=None, out_path=None):
    csv_path = csv_path or os.path.join(ROOT, "models", "conjunto_de_datos", "denue_inegi_01_.csv")
    out_path = out_path or os.path.join(ROOT, "models", "rolcar_aguascalientes.json")

    branches = []
    seen = set()
    with open(csv_path, "r", encoding="latin-1", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nom = (row.get("nom_estab", "") or "").strip()
            raz = (row.get("raz_social", "") or "").strip()
            blob = f"{nom} {raz}".upper()
            if not (
                "REFACCIONARIA ROGELIO" in blob
                or "REFACIONARIA ROGELIO" in blob
                or "ROLCAR" in blob
            ):
                continue
            try:
                lat = float(row["latitud"])
                lon = float(row["longitud"])
            except (KeyError, ValueError, TypeError):
                continue

            key = (round(lat, 5), round(lon, 5), nom)
            if key in seen:
                continue
            seen.add(key)

            x, z = geo_to_meters(lat, lon, ORIGIN_LAT, ORIGIN_LON)
            mx = int(math.floor(x / MACRO_SIZE))
            mz = int(math.floor(z / MACRO_SIZE))

            addr = " ".join(
                p for p in [
                    (row.get("tipo_vial") or "").strip(),
                    (row.get("nom_vial") or "").strip(),
                    ("#" + row["numero_ext"].strip()) if (row.get("numero_ext") or "").strip() else "",
                    (row.get("nomb_asent") or "").strip(),
                ] if p
            )

            branches.append({
                "name": nom,
                "raz_social": raz,
                "address": addr,
                "cp": (row.get("cod_postal") or "").strip(),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "x": round(x, 2),
                "z": round(z, 2),
                "mx": mx,
                "mz": mz,
            })

    branches.sort(key=lambda b: b["name"])
    payload = {
        "brand": "ROLCAR (Refaccionaria Rogelio)",
        "colors": {
            "primary_green": [0.04, 0.48, 0.20],
            "accent_yellow": [0.96, 0.77, 0.04],
            "white": [0.96, 0.96, 0.96],
        },
        "count": len(branches),
        "branches": branches,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    sectors = sorted({(b["mx"], b["mz"]) for b in branches})
    print(f"[Rolcar] Extraidas {len(branches)} sucursales en {len(sectors)} macro-sectores -> {out_path}")
    print(f"[Rolcar] Sectores: {sectors}")
    return payload


if __name__ == "__main__":
    extract_rolcar_branches()
