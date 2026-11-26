#!/usr/bin/env python3
"""
Genera models/city_buildings.bin: huellas de edificios de toda Aguascalientes
para el mapa base web (capa LOD extruida fuera de los macro-sectores GLB).

Entrada: GeoJSONSeq de edificios de Overture Maps (no se versiona), p. ej.:
    overturemaps download --bbox=-102.3700,21.8000,-102.2450,21.9500 \
        -f geojsonseq -t building -o models/overture_aguascalientes_buildings.geojsonseq

Cada huella se proyecta con geo_dem.geo_to_meters, se simplifica
(Douglas-Peucker, máx. 24 vértices, CCW en el plano XZ) y se agrupa por
macro-celda de 1024 m según su centroide. La altura sale de Overture
(height / num_floors * 3.2) y, si falta, de la misma heurística que
classify_buildings.py (4 m por vivienda, naves > 800 m²).

Formato CBB1 (little-endian):
    header 16 B: char[4] "CBB1", u32 cell_count, u32 building_count, u32 point_count
    celdas (16 B c/u): i16 mx, i16 mz, u32 first_building, u32 building_count, u32 first_point
    edificios (4 B c/u): u8 n_points, u8 clase, u16 altura_dm
    puntos (4 B c/u): u16 qx, u16 qz con x = mx*1024 - 512 + qx/32 (idem z)
Clases: 0 residencial, 1 comercial, 2 educación, 3 religioso, 4 salud,
        5 cívico/oficinas, 6 industrial.
"""

import argparse
import json
import math
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_dem import geo_to_meters  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MACRO_SIZE = 1024.0
QUANT = 32.0          # 1/32 m de resolución
CELL_MARGIN = 512.0   # los vértices pueden salir hasta 512 m de su celda
MAX_POINTS = 24
MIN_AREA = 8.0

CLASS_RESIDENTIAL, CLASS_COMMERCIAL, CLASS_EDUCATION, CLASS_RELIGIOUS, CLASS_MEDICAL, CLASS_CIVIC, CLASS_INDUSTRIAL = range(7)
SUBTYPE_CLASS = {
    "residential": CLASS_RESIDENTIAL,
    "outbuilding": CLASS_RESIDENTIAL,
    "commercial": CLASS_COMMERCIAL,
    "entertainment": CLASS_COMMERCIAL,
    "education": CLASS_EDUCATION,
    "religious": CLASS_RELIGIOUS,
    "medical": CLASS_MEDICAL,
    "civic": CLASS_CIVIC,
    "service": CLASS_CIVIC,
    "transportation": CLASS_CIVIC,
    "industrial": CLASS_INDUSTRIAL,
    "agricultural": CLASS_INDUSTRIAL,
}
CLASS_HINTS = {
    "retail": CLASS_COMMERCIAL, "commercial": CLASS_COMMERCIAL, "supermarket": CLASS_COMMERCIAL,
    "school": CLASS_EDUCATION, "university": CLASS_EDUCATION, "college": CLASS_EDUCATION,
    "church": CLASS_RELIGIOUS, "cathedral": CLASS_RELIGIOUS, "chapel": CLASS_RELIGIOUS,
    "hospital": CLASS_MEDICAL, "office": CLASS_CIVIC, "government": CLASS_CIVIC,
    "industrial": CLASS_INDUSTRIAL, "warehouse": CLASS_INDUSTRIAL,
}


def ring_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, z0 = pts[i]
        x1, z1 = pts[(i + 1) % len(pts)]
        a += x0 * z1 - x1 * z0
    return a * 0.5


def _seg_dist(p, a, b):
    ax, az = a
    dx, dz = b[0] - ax, b[1] - az
    l2 = dx * dx + dz * dz
    if l2 <= 1e-12:
        return math.hypot(p[0] - ax, p[1] - az)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / l2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (az + t * dz))


def douglas_peucker(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        best, idx = -1.0, -1
        for i in range(i0 + 1, i1):
            d = _seg_dist(pts[i], pts[i0], pts[i1])
            if d > best:
                best, idx = d, i
        if idx >= 0 and best > tol:
            keep[idx] = True
            stack.append((i0, idx))
            stack.append((idx, i1))
    return [p for p, k in zip(pts, keep) if k]


def simplify_ring(pts):
    # Quitar cierre duplicado y vértices casi repetidos
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    clean = []
    for p in pts:
        if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.3:
            clean.append(p)
    if len(clean) > 2 and math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) <= 0.3:
        clean.pop()
    tol = 0.35
    out = clean
    while True:
        closed = out + [out[0]]
        simp = douglas_peucker(closed, tol)[:-1]
        if len(simp) <= MAX_POINTS or tol > 50:
            out = simp
            break
        tol *= 1.6
    return out


def building_height(props, area, fid):
    h = props.get("height")
    if isinstance(h, (int, float)) and 2.0 <= h <= 200.0:
        return float(h)
    floors = props.get("num_floors")
    if isinstance(floors, (int, float)) and floors >= 1:
        return min(200.0, float(floors) * 3.2 + 0.8)
    jitter = (zlib.crc32(fid.encode("utf-8")) % 1000) / 1000.0
    if area > 3000.0:
        return 9.0 + jitter * 3.0
    if area > 800.0:
        return 7.0 + jitter * 2.0
    # Vivienda típica de 1 piso (classify_buildings.py usa 4.0 m), ~15% de 2 pisos
    return 7.2 if jitter > 0.85 else 3.6 + jitter * 0.8


def building_class(props, area):
    sub = props.get("subtype")
    if sub in SUBTYPE_CLASS:
        return SUBTYPE_CLASS[sub]
    cls = props.get("class")
    if cls in CLASS_HINTS:
        return CLASS_HINTS[cls]
    return CLASS_INDUSTRIAL if area > 800.0 else CLASS_RESIDENTIAL


def iter_rings(geometry):
    if geometry is None:
        return
    if geometry.get("type") == "Polygon":
        yield geometry["coordinates"][0]
    elif geometry.get("type") == "MultiPolygon":
        for poly in geometry["coordinates"]:
            yield poly[0]


def build(input_path, output_path):
    cells = {}
    skipped = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            feat = json.loads(line)
            props = feat.get("properties") or {}
            if props.get("is_underground"):
                continue
            fid = str(feat.get("id", ""))
            for ring in iter_rings(feat.get("geometry")):
                pts = [geo_to_meters(lat, lon) for lon, lat in ring]
                pts = simplify_ring(pts)
                if len(pts) < 3:
                    skipped += 1
                    continue
                area = ring_area(pts)
                if abs(area) < MIN_AREA:
                    skipped += 1
                    continue
                if area < 0:
                    pts.reverse()   # CCW en (x, z)
                area = abs(area)
                cx = sum(p[0] for p in pts) / len(pts)
                cz = sum(p[1] for p in pts) / len(pts)
                mx, mz = int(math.floor(cx / MACRO_SIZE)), int(math.floor(cz / MACRO_SIZE))
                ox, oz = mx * MACRO_SIZE - CELL_MARGIN, mz * MACRO_SIZE - CELL_MARGIN
                q = [(int(round((x - ox) * QUANT)), int(round((z - oz) * QUANT))) for x, z in pts]
                if any(not (0 <= a <= 65535 and 0 <= b <= 65535) for a, b in q):
                    skipped += 1
                    continue
                height_dm = int(round(building_height(props, area, fid) * 10.0))
                cells.setdefault((mx, mz), []).append((len(q), building_class(props, area), height_dm, q))

    keys = sorted(cells)
    n_buildings = sum(len(cells[k]) for k in keys)
    n_points = sum(b[0] for k in keys for b in cells[k])
    with open(output_path, "wb") as out:
        out.write(struct.pack("<4sIII", b"CBB1", len(keys), n_buildings, n_points))
        first_b = first_p = 0
        for k in keys:
            out.write(struct.pack("<hhIII", k[0], k[1], first_b, len(cells[k]), first_p))
            first_b += len(cells[k])
            first_p += sum(b[0] for b in cells[k])
        for k in keys:
            for n, cls, h_dm, _q in cells[k]:
                out.write(struct.pack("<BBH", n, cls, min(h_dm, 65535)))
        for k in keys:
            for _n, _cls, _h, q in cells[k]:
                out.write(b"".join(struct.pack("<HH", a, b) for a, b in q))

    print(f"[Buildings] {n_buildings} edificios ({n_points} vértices) en {len(keys)} celdas, "
          f"{skipped} descartados -> {output_path} ({os.path.getsize(output_path) / 1048576:.1f} MiB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", "-i",
                        default=os.path.join(ROOT, "models", "overture_aguascalientes_buildings.geojsonseq"))
    parser.add_argument("--output", "-o", default=os.path.join(ROOT, "models", "city_buildings.bin"))
    args = parser.parse_args()
    if not os.path.isfile(args.input):
        parser.error(f"No existe {args.input}; descárgalo con overturemaps (ver docstring)")
    build(args.input, args.output)


if __name__ == "__main__":
    main()
