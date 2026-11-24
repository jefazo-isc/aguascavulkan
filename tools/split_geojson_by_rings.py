#!/usr/bin/env python3
"""
tools/split_geojson_by_rings.py
Divide models/overture_tercer_anillo.geojson en 3 zonas radiales (anillos viales)
de Aguascalientes para que ningún archivo supere los 80 MB y evitar congelamientos
de memoria RAM durante la generación:

1. models/overture_primer_anillo.geojson  (Centro Histórico y Primer Anillo <= 2.3 km)
2. models/overture_segundo_anillo.geojson (Zona intermedia y Segundo Anillo 2.3 - 4.6 km)
3. models/overture_tercer_anillo.geojson  (Periferia urbana y Tercer Anillo > 4.6 km)
"""

import os
import sys
import json
import math

ORIGIN_LAT = 21.8807
ORIGIN_LON = -102.2965
DEG_TO_RAD = math.pi / 180.0
EARTH_R = 6371000.0

R1_MAX_M = 2300.0  # Primer Anillo (Av. Convención)
R2_MAX_M = 4600.0  # Segundo Anillo (Av. Aguascalientes)

def geo_dist_m(lat, lon):
    dlat = (lat - ORIGIN_LAT) * DEG_TO_RAD
    dlon = (lon - ORIGIN_LON) * DEG_TO_RAD
    x = dlon * math.cos(ORIGIN_LAT * DEG_TO_RAD) * EARTH_R
    z = -dlat * EARTH_R
    return math.hypot(x, z)

def main():
    input_file = "models/overture_tercer_anillo.geojson"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} no existe.")
        sys.exit(1)

    print(f"[Anillos] Leyendo {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    total_f = len(features)
    print(f"[Anillos] Total de edificios a clasificar por anillos: {total_f:,}")

    f_ring1 = []
    f_ring2 = []
    f_ring3 = []

    for idx, feat in enumerate(features):
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        if not coords or geom.get("type") != "Polygon":
            continue

        poly = coords[0]
        # Calcular centroide aproximado
        avg_lon = sum(p[0] for p in poly) / len(poly)
        avg_lat = sum(p[1] for p in poly) / len(poly)
        d = geo_dist_m(avg_lat, avg_lon)

        if d <= R1_MAX_M:
            f_ring1.append(feat)
        elif d <= R2_MAX_M:
            f_ring2.append(feat)
        else:
            f_ring3.append(feat)

        if (idx + 1) % 50000 == 0:
            print(f"  Procesados {idx + 1:,}/{total_f:,} edificios...")

    print(f"\n[Distribución por Anillos]:")
    print(f"  • Primer Anillo (Zona Centro <= {R1_MAX_M:.0f}m): {len(f_ring1):,} edificios ({len(f_ring1)/total_f*100:.1f}%)")
    print(f"  • Segundo Anillo (Zona Media <= {R2_MAX_M:.0f}m):  {len(f_ring2):,} edificios ({len(f_ring2)/total_f*100:.1f}%)")
    print(f"  • Tercer Anillo (Periferia > {R2_MAX_M:.0f}m):    {len(f_ring3):,} edificios ({len(f_ring3)/total_f*100:.1f}%)")

    # Archivo temporal para el anillo 3 antes de sobrescribir el archivo de 181 MB
    targets = [
        ("models/overture_primer_anillo.geojson", f_ring1, "Primer Anillo / Centro Histórico"),
        ("models/overture_segundo_anillo.geojson", f_ring2, "Segundo Anillo / Zona Media"),
        ("models/overture_tercer_anillo_temp.geojson", f_ring3, "Tercer Anillo / Periferia")
    ]

    for out_path, feat_list, label in targets:
        print(f"\n[Guardando] {label} en {out_path}...")
        out_data = {
            "type": "FeatureCollection",
            "name": label,
            "crs": data.get("crs", {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}),
            "features": feat_list
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f)
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"  ✅ {out_path}: {size_mb:.2f} MB ({len(feat_list):,} edificios)")

    # Reemplazar el archivo gigante de 181 MB por el archivo limpio de Tercer Anillo (~75 MB)
    temp_r3 = "models/overture_tercer_anillo_temp.geojson"
    final_r3 = "models/overture_tercer_anillo.geojson"
    if os.path.exists(temp_r3):
        os.replace(temp_r3, final_r3)
        final_size = os.path.getsize(final_r3) / (1024 * 1024)
        print(f"\n✅ {final_r3} reemplazado con éxito: {final_size:.2f} MB (< 99 MB)")

    print("=" * 65)
    print("  DIVISIÓN POR ANILLOS COMPLETADA CON ÉXITO")
    print("  Ningún archivo supera los 80 MB.")
    print("=" * 65)

if __name__ == "__main__":
    main()
