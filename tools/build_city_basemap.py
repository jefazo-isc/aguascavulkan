#!/usr/bin/env python3
"""
Genera models/city_basemap.bin: heightfield de toda Aguascalientes para el
cliente web (mapa base de baja resolución fuera de los macro-sectores GLB).

Muestrea TerrainElevation.get_real_topography (DEM + ríos + fallas), la misma
función que usan generate_sector.py y generate_road_graph.py, sobre una rejilla
regular alineada a los macro-sectores de 1024 m que cubre toda la red vial.

Formato CBM1 (little-endian):
    header 32 B: char[4] "CBM1", u32 cols, u32 rows, f32 x0, f32 z0,
                 f32 spacing, f32 min_h, f32 max_h
    heights:     f32[rows][cols] (fila = eje Z, columna = eje X), metros
                 relativos a TERRAIN_DEM_BASE_ELEVATION (1871 m)
"""

import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_dem import TerrainElevation  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEM_BOUNDS = (21.8000, 21.9500, -102.3700, -102.2450)
MACRO_SIZE = 1024.0


def road_graph_extent(path):
    """Devuelve (min_x, min_z, max_x, max_z) de los nodos de road_network.bin (RGP1)."""
    with open(path, "rb") as f:
        magic, n_nodes, _n_edges, _n_points = struct.unpack("<4sIII", f.read(16))
        if magic != b"RGP1":
            raise ValueError(f"{path}: magic inválido {magic!r}")
        min_x = min_z = math.inf
        max_x = max_z = -math.inf
        for _ in range(n_nodes):
            x, _y, z, _sig, _deg, _p0, _p1, _p2 = struct.unpack("<fffiBBBB", f.read(20))
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_z, max_z = min(min_z, z), max(max_z, z)
    return min_x, min_z, max_x, max_z


def build_basemap(road_path, out_path, spacing):
    min_x, min_z, max_x, max_z = road_graph_extent(road_path)
    x0 = math.floor(min_x / MACRO_SIZE) * MACRO_SIZE
    z0 = math.floor(min_z / MACRO_SIZE) * MACRO_SIZE
    x1 = math.ceil(max_x / MACRO_SIZE) * MACRO_SIZE
    z1 = math.ceil(max_z / MACRO_SIZE) * MACRO_SIZE
    cols = int(round((x1 - x0) / spacing)) + 1
    rows = int(round((z1 - z0) / spacing)) + 1

    terrain = TerrainElevation(*DEM_BOUNDS, nx=64, ny=64)
    heights = []
    for r in range(rows):
        z = z0 + r * spacing
        heights.extend(terrain.get_real_topography(x0 + c * spacing, z) for c in range(cols))

    min_h, max_h = min(heights), max(heights)
    with open(out_path, "wb") as f:
        f.write(struct.pack("<4sIIfffff", b"CBM1", cols, rows, x0, z0, spacing, min_h, max_h))
        f.write(struct.pack(f"<{len(heights)}f", *heights))

    print(f"[Basemap] {cols}x{rows} muestras cada {spacing:.0f} m "
          f"({x0:.0f},{z0:.0f}) -> ({x1:.0f},{z1:.0f}), alturas {min_h:.1f}..{max_h:.1f} m "
          f"-> {out_path} ({os.path.getsize(out_path) / 1024:.0f} KiB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roads", default=os.path.join(ROOT, "models", "road_network.bin"))
    parser.add_argument("--output", "-o", default=os.path.join(ROOT, "models", "city_basemap.bin"))
    parser.add_argument("--spacing", type=float, default=64.0, help="Separación de la rejilla en metros (divisor de 1024)")
    args = parser.parse_args()
    if MACRO_SIZE % args.spacing != 0:
        parser.error("--spacing debe dividir exactamente 1024")
    build_basemap(args.roads, args.output, args.spacing)


if __name__ == "__main__":
    main()
