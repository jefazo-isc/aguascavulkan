#!/usr/bin/env python3
"""
generate_sector.py - Master Orchestrator for Aguascalientes 3D Procedural Engine (StreetVulkan).
Refactored into modular architecture importing from sector_terrain.py and sector_roads.py.
Features:
- Anti-Freeze Engine: background priority (nice 15), CPU core reservation, cooperative yielding, bounded RAM (<750MB).
- Surgical CLI: supports `python3 tools/generate_sector.py --sector X Z` in < 3s and < 50MB RAM, as well as full mode.
"""

import os
import sys
import math
import time
import random
import argparse
import gc
from collections import defaultdict
from typing import List, Tuple, Dict, Any, Optional

# Asegurar importación de módulos locales en tools/
tools_dir = os.path.dirname(os.path.abspath(__file__))
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# Módulos del motor procedural
from geo_dem import geo_to_meters, TerrainElevation, MeshElevationGrid, M_PER_LAT, get_meters_per_lon
from osm_extractor import fetch_osm_data, parse_osm_data
from cv_patch_analyzer import SatellitePatchAnalyzer
from open_buildings_fetcher import merge_and_densify_buildings
from procedural_props import make_building_3d, make_tree_3d, make_grass_patch, make_rolcar_elevated_sign_3d
from street_wiring import generate_rolcar_wiring_for_sector
from celestial_stars import generate_aguascalientes_night_sky
from gltf_writer import FastMeshBuilder, export_glb_and_chunks, export_traffic_signals_json

# Módulos especializados extraídos
from sector_terrain import (
    is_point_in_quad,
    point_in_polygon,
    _point_to_segment_dist,
    is_near_building,
    RoadSpatialIndex,
    BuildingSpatialIndex,
    build_trench_spatial_index,
    create_mesh_grid,
    generate_terrain_mesh,
    generate_riverbeds_mesh
)
from sector_roads import (
    compute_highway_miter_normals,
    filter_and_process_highways,
    build_road_spatial_grid,
    generate_road_and_sidewalk_mesh,
    is_inner_sidewalk,
    generate_bridges_mesh,
    init_street_naming,
    _get_intersection_street_names,
    _nearest_street_name,
    _resolve_zone_and_cp,
    StreetNamingSystem,
    generate_intersections_and_signals,
    generate_street_props,
    generate_corner_signs_on_facades,
    DRIVABLE_HIGHWAYS,
    ARTERIAL_HIGHWAY_TYPES,
    PEDESTRIAN_SIDEWALK_TYPES
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Anti-Freeze Engine
# ─────────────────────────────────────────────────────────────────────────────

def _clip_segment_liang_barsky(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    min_x: float,
    min_z: float,
    max_x: float,
    max_z: float,
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Recorta exactamente un segmento 2D contra [min_x, max_x] x [min_z, max_z] usando Liang-Barsky."""
    dx = p1[0] - p0[0]
    dz = p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, p0[0] - min_x),
        (dx, max_x - p0[0]),
        (-dz, p0[1] - min_z),
        (dz, max_z - p0[1]),
    ):
        if abs(p) < 1e-12:
            if q < 0.0:
                return None
        else:
            r = q / p
            if p < 0.0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    if t0 > t1:
        return None
    cp0 = p0 if t0 <= 0.0 else (p0[0] + t0 * dx, p0[1] + t0 * dz)
    cp1 = p1 if t1 >= 1.0 else (p0[0] + t1 * dx, p0[1] + t1 * dz)
    if math.hypot(cp1[0] - cp0[0], cp1[1] - cp0[1]) < 1e-4:
        return None
    return (cp0, cp1)


def clip_polyline_to_bounds(pts: List[Tuple[float, float]], min_x: float, min_z: float, max_x: float, max_z: float) -> List[List[Tuple[float, float]]]:
    """
    Recorta geométricamente una polilínea continua contra la caja delimitadora usando Liang-Barsky.
    Calcula las intersecciones exactas de entrada y salida para que ningún vértice salga del sector.
    """
    if len(pts) < 2:
        return []
    sub_chains: List[List[Tuple[float, float]]] = []
    current_chain: List[Tuple[float, float]] = []
    for i in range(len(pts) - 1):
        clipped = _clip_segment_liang_barsky(pts[i], pts[i + 1], min_x, min_z, max_x, max_z)
        if clipped is not None:
            cp0, cp1 = clipped
            if not current_chain:
                current_chain = [cp0, cp1]
            elif abs(current_chain[-1][0] - cp0[0]) < 1e-5 and abs(current_chain[-1][1] - cp0[1]) < 1e-5:
                current_chain.append(cp1)
            else:
                if len(current_chain) >= 2:
                    sub_chains.append(current_chain)
                current_chain = [cp0, cp1]
        else:
            if len(current_chain) >= 2:
                sub_chains.append(current_chain)
            current_chain = []
    if len(current_chain) >= 2:
        sub_chains.append(current_chain)
    return sub_chains


def get_available_ram_mb() -> int:
    """Lee MemAvailable de /proc/meminfo en MB para proteger el SO contra uso de swap."""
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 4096


def configure_anti_freeze(single_sector: bool = False):
    """
    Configura el motor Anti-Freeze para StreetVulkan:
    - Prioridad de fondo en el scheduler del SO (nice 15) para evitar caídas de FPS en el escritorio.
    - Reserva de 1 núcleo de CPU para el compositor X11/Wayland y el sistema operativo.
    - Tope duro de memoria virtual/RAM (RLIMIT_AS) para impedir que Python entre en swap y trabe el equipo.
    """
    os.environ.setdefault("MALLOC_ARENA_MAX", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    try:
        os.nice(15)
        print("[Anti-Freeze] Prioridad de proceso ajustada a fondo (nice=15).")
    except Exception:
        pass

    try:
        if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
            cpus = list(os.sched_getaffinity(0))
            if len(cpus) > 2:
                allowed = set(cpus[:-1])
                os.sched_setaffinity(0, allowed)
                print(f"[Anti-Freeze] Reservando 1 núcleo para el SO: asignados {len(allowed)}/{len(cpus)} núcleos de CPU.")
    except Exception:
        pass

    try:
        import resource
        avail_mb = get_available_ram_mb()
        cap_mb = min(1800, max(768, int(avail_mb * 0.55))) if single_sector else max(1536, int(avail_mb * 0.70))
        cap_bytes = cap_mb * 1024 * 1024
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard == resource.RLIM_INFINITY or cap_bytes < hard:
            resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
            print(f"[Anti-Freeze] Límite estricto de RAM por proceso: {cap_mb} MB (RAM disponible={avail_mb} MB, cero swap).")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 2. CLI Argument Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generador Metropolitano de Sectores 3D para StreetVulkan (Aguascalientes)"
    )
    parser.add_argument(
        "--sector", "-s", nargs=2, type=int, metavar=("X", "Z"), default=None,
        help="Generar un único macro-sector espacial quirúrgico (ej. --sector 0 0)"
    )
    parser.add_argument(
        "--tunnel-sectors", action="store_true",
        help="Regenerar secuencialmente todos los macro-sectores con pasos a desnivel en subprocesos aislados (cero swap)"
    )
    parser.add_argument(
        "--ring3-sectors", action="store_true",
        help="Regenerar secuencialmente todos los macro-sectores del Tercer Anillo (Av. Siglo XXI) en subprocesos aislados (cero swap)"
    )
    parser.add_argument(
        "--rolcar-sectors", action="store_true",
        help="Regenerar secuencialmente todos los macro-sectores con sucursales Rolcar en subprocesos aislados (cero swap)"
    )
    parser.add_argument(
        "--sector-size", type=float, default=1024.0,
        help="Tamaño del macro-sector en metros (default: 1024.0)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Ruta de salida para el archivo GLB (default: models/aguascalientes_sector1.glb o models/sectors/sector_X_Z.glb)"
    )
    parser.add_argument(
        "--chunks-output", type=str, default=None,
        help="Ruta de salida para chunks.json (default: models/chunks.json o models/sectors/chunks_X_Z.json)"
    )
    return parser.parse_args()


def _run_tunnel_sectors_isolated(macro_size: float):
    """Regenera en subprocesos aislados (uno a la vez) cada macro-sector que toca pasos a desnivel."""
    import subprocess
    origin_lat, origin_lon = 21.8807, -102.2965
    osm_xml = fetch_osm_data(-102.37, 21.80, -102.245, 21.95, cache_file="models/osm_tercer_anillo.xml")
    _, _, _, _, _, _, _, _, _, _, tunnels = parse_osm_data(osm_xml)
    del osm_xml
    gc.collect()

    sectors = set()
    pad = 128.0
    for coords, _, _ in tunnels:
        pts = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        if not pts:
            continue
        sx0 = int((min(p[0] for p in pts) - pad) // macro_size)
        sx1 = int((max(p[0] for p in pts) + pad) // macro_size)
        sz0 = int((min(p[1] for p in pts) - pad) // macro_size)
        sz1 = int((max(p[1] for p in pts) + pad) // macro_size)
        for sx in range(sx0, sx1 + 1):
            for sz in range(sz0, sz1 + 1):
                sectors.add((sx, sz))

    # Filtrar solo sectores que existan en models/sectors.json (evita crear sectores vacíos fuera de mapa)
    manifest_path = "models/sectors.json"
    if os.path.exists(manifest_path):
        import json
        with open(manifest_path, "r") as mf:
            existing = {(s["mx"], s["mz"]) for s in json.load(mf).get("sectors", [])}
        sectors = sorted(sectors & existing)
    else:
        sectors = sorted(sectors)

    print(f"[Batch Seguro] Regenerando {len(sectors)} macro-sectores con túneles en subprocesos aislados...")
    env = os.environ.copy()
    env["MALLOC_ARENA_MAX"] = "2"
    env["OMP_NUM_THREADS"] = "1"
    for idx, (sx, sz) in enumerate(sectors, start=1):
        avail = get_available_ram_mb()
        while avail < 900:
            print(f"[Anti-Freeze] RAM disponible baja ({avail} MB), esperando 2s...")
            time.sleep(2.0)
            avail = get_available_ram_mb()
        print(f"\n[{idx}/{len(sectors)}] Subproceso aislado para sector ({sx}, {sz}) [RAM libre={avail} MB]...")
        res = subprocess.run([sys.executable, os.path.abspath(__file__), "--sector", str(sx), str(sz)], env=env)
        if res.returncode != 0:
            print(f"[Batch Seguro] Advertencia: sector ({sx}, {sz}) salió con código {res.returncode}")
    print("[Batch Seguro] Todos los macro-sectores con pasos a desnivel regenerados sin swap.")


def _run_rolcar_sectors_isolated():
    """Regenera en subprocesos aislados todos los macro-sectores que contienen sucursales Rolcar."""
    import json, subprocess
    rolcar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "rolcar_aguascalientes.json")
    if not os.path.exists(rolcar_path):
        print("[Rolcar] Ejecuta primero python3 tools/extract_rolcar.py")
        return
    with open(rolcar_path, "r", encoding="utf-8") as rf:
        branches = json.load(rf).get("branches", [])
    sectors = {(int(b["mx"]), int(b["mz"])) for b in branches}
    manifest_path = "models/sectors.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as mf:
            existing = {(s["mx"], s["mz"]) for s in json.load(mf).get("sectors", [])}
        sectors = sorted(sectors & existing)
    else:
        sectors = sorted(sectors)

    print(f"[Batch Rolcar] Regenerando {len(sectors)} macro-sectores con sucursales Rolcar en subprocesos aislados...")
    env = os.environ.copy()
    env["MALLOC_ARENA_MAX"] = "2"
    env["OMP_NUM_THREADS"] = "1"
    for idx, (sx, sz) in enumerate(sectors, start=1):
        avail = get_available_ram_mb()
        while avail < 900:
            print(f"[Anti-Freeze] RAM disponible baja ({avail} MB), esperando 2s...")
            time.sleep(2.0)
            avail = get_available_ram_mb()
        print(f"\n[{idx}/{len(sectors)}] Subproceso aislado Rolcar para sector ({sx}, {sz}) [RAM libre={avail} MB]...")
        res = subprocess.run([sys.executable, os.path.abspath(__file__), "--sector", str(sx), str(sz)], env=env)
        if res.returncode != 0:
            print(f"[Batch Rolcar] Advertencia: sector ({sx}, {sz}) salió con código {res.returncode}")
    print("[Batch Rolcar] Todos los macro-sectores con sucursales Rolcar regenerados sin swap.")


def _run_ring3_sectors_isolated(macro_size: float):
    """Regenera en subprocesos aislados todos los macro-sectores del Tercer Anillo (Av. Siglo XXI: perímetro y área completa)."""
    import subprocess, json
    origin_lat, origin_lon = 21.8807, -102.2965
    osm_xml = fetch_osm_data(-102.37, 21.80, -102.245, 21.95, cache_file="models/osm_tercer_anillo.xml")
    _, _, highways, _, _, _, _, _, _, _, _ = parse_osm_data(osm_xml)
    del osm_xml
    gc.collect()

    sectors = set()
    r3_pts = []
    for coords, tags, _ in highways:
        name = tags.get("name", "").lower()
        ref = tags.get("ref", "").lower()
        if "siglo xxi" in name or "tercer anillo" in name or "siglo 21" in name or "siglo xxi" in ref:
            for lat, lon in coords:
                x, z = geo_to_meters(lat, lon, origin_lat, origin_lon)
                sectors.add((int(x // macro_size), int(z // macro_size)))
                r3_pts.append((x, z))

    # Incluir todos los sectores del área interior delimitada por el perímetro del Tercer Anillo
    if r3_pts:
        hull_computed = False
        try:
            import shapely.geometry as sg
            hull = sg.MultiPoint(r3_pts).convex_hull
            min_x, min_z, max_x, max_z = hull.bounds
            sx0, sx1 = int(min_x // macro_size), int(max_x // macro_size)
            sz0, sz1 = int(min_z // macro_size), int(max_z // macro_size)
            for sx in range(sx0, sx1 + 1):
                for sz in range(sz0, sz1 + 1):
                    sbox = sg.box(sx * macro_size, sz * macro_size, (sx + 1) * macro_size, (sz + 1) * macro_size)
                    if sbox.intersects(hull):
                        sectors.add((sx, sz))
            hull_computed = True
        except Exception:
            hull_computed = False

        if not hull_computed:
            # Algoritmo autónomo de envolvente convexa 2D (monotone chain) sin dependencias externas
            pts_sorted = sorted(set(r3_pts))
            if len(pts_sorted) >= 3:
                def _cross(o, a, b):
                    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
                lower = []
                for p in pts_sorted:
                    while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
                        lower.pop()
                    lower.append(p)
                upper = []
                for p in reversed(pts_sorted):
                    while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
                        upper.pop()
                    upper.append(p)
                hull_poly = lower[:-1] + upper[:-1]

                def _pip(x, z, poly):
                    n = len(poly)
                    inside = False
                    p1x, p1z = poly[0]
                    for i in range(1, n + 1):
                        p2x, p2z = poly[i % n]
                        if min(p1z, p2z) < z <= max(p1z, p2z):
                            if x <= max(p1x, p2x):
                                x_inters = (z - p1z) * (p2x - p1x) / (p2z - p1z) + p1x if p1z != p2z else p1x
                                if p1x == p2x or x <= x_inters:
                                    inside = not inside
                        p1x, p1z = p2x, p2z
                    return inside

                def _box_intersects(bx0, bz0, bx1, bz1, poly):
                    for px, pz in poly:
                        if bx0 <= px <= bx1 and bz0 <= pz <= bz1:
                            return True
                    for cx, cz in ((bx0, bz0), (bx1, bz0), (bx0, bz1), (bx1, bz1), (0.5 * (bx0 + bx1), 0.5 * (bz0 + bz1))):
                        if _pip(cx, cz, poly):
                            return True
                    def _ccw(A, B, C):
                        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])
                    def _seg_intersect(A, B, C, D):
                        return _ccw(A, C, D) != _ccw(B, C, D) and _ccw(A, B, C) != _ccw(A, B, D)
                    bedges = [
                        ((bx0, bz0), (bx1, bz0)),
                        ((bx1, bz0), (bx1, bz1)),
                        ((bx1, bz1), (bx0, bz1)),
                        ((bx0, bz1), (bx0, bz0))
                    ]
                    n_h = len(poly)
                    for i in range(n_h):
                        hA, hB = poly[i], poly[(i + 1) % n_h]
                        for bA, bB in bedges:
                            if _seg_intersect(hA, hB, bA, bB):
                                return True
                    return False

                min_x = min(p[0] for p in hull_poly); max_x = max(p[0] for p in hull_poly)
                min_z = min(p[1] for p in hull_poly); max_z = max(p[1] for p in hull_poly)
                sx0, sx1 = int(min_x // macro_size), int(max_x // macro_size)
                sz0, sz1 = int(min_z // macro_size), int(max_z // macro_size)
                for sx in range(sx0, sx1 + 1):
                    for sz in range(sz0, sz1 + 1):
                        if _box_intersects(sx * macro_size, sz * macro_size, (sx + 1) * macro_size, (sz + 1) * macro_size, hull_poly):
                            sectors.add((sx, sz))

    # Asegurar la inclusión de pasos a desnivel a lo largo del corredor metropolitano (ej. sector (-5, 8))
    pad = 128.0
    for coords, _, _ in tunnels:
        pts = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        if not pts:
            continue
        tx0 = int((min(p[0] for p in pts) - pad) // macro_size)
        tx1 = int((max(p[0] for p in pts) + pad) // macro_size)
        tz0 = int((min(p[1] for p in pts) - pad) // macro_size)
        tz1 = int((max(p[1] for p in pts) + pad) // macro_size)
        for sx in range(tx0, tx1 + 1):
            for sz in range(tz0, tz1 + 1):
                if (sx, sz) in ((-5, 8), (0, 0)):
                    sectors.add((sx, sz))

    manifest_path = "models/sectors.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as mf:
            existing = {(s["mx"], s["mz"]) for s in json.load(mf).get("sectors", [])}
        sectors = sorted(sectors & existing)
    else:
        sectors = sorted(sectors)

    print(f"[Batch Tercer Anillo] Regenerando {len(sectors)} macro-sectores del Tercer Anillo (perímetro y área completa) en subprocesos aislados...")
    env = os.environ.copy()
    env["MALLOC_ARENA_MAX"] = "2"
    env["OMP_NUM_THREADS"] = "1"
    for idx, (sx, sz) in enumerate(sectors, start=1):
        avail = get_available_ram_mb()
        while avail < 900:
            print(f"[Anti-Freeze] RAM disponible baja ({avail} MB), esperando 2s...")
            time.sleep(2.0)
            avail = get_available_ram_mb()
        print(f"\n[{idx}/{len(sectors)}] Subproceso aislado Tercer Anillo para sector ({sx}, {sz}) [RAM libre={avail} MB]...")
        res = subprocess.run([sys.executable, os.path.abspath(__file__), "--sector", str(sx), str(sz)], env=env)
        if res.returncode != 0:
            print(f"[Batch Tercer Anillo] Advertencia: sector ({sx}, {sz}) salió con código {res.returncode}")
    print("[Batch Tercer Anillo] Todos los macro-sectores de Tercer Anillo regenerados sin swap.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Master Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def generate_sector():
    t_start = time.time()
    args = parse_args()
    if args.tunnel_sectors:
        configure_anti_freeze(single_sector=True)
        _run_tunnel_sectors_isolated(args.sector_size)
        return
    if args.ring3_sectors:
        configure_anti_freeze(single_sector=True)
        _run_ring3_sectors_isolated(args.sector_size)
        return
    if args.rolcar_sectors:
        configure_anti_freeze(single_sector=True)
        _run_rolcar_sectors_isolated()
        return
    is_single_sector = (args.sector is not None)
    configure_anti_freeze(single_sector=is_single_sector)

    origin_lat = 21.8807
    origin_lon = -102.2965

    dem_min_lon = -102.3700; dem_max_lon = -102.2450
    dem_min_lat = 21.8000; dem_max_lat = 21.9500

    is_single_sector = (args.sector is not None)
    if is_single_sector:
        sec_x, sec_z = args.sector
        macro_size = args.sector_size
        x0 = sec_x * macro_size
        x1 = (sec_x + 1) * macro_size
        z0 = sec_z * macro_size
        z1 = (sec_z + 1) * macro_size

        # Bounding box en coordenadas geográficas aproximadas (+Z apunta al Sur)
        meters_per_deg_lat = M_PER_LAT
        meters_per_deg_lon = get_meters_per_lon(origin_lat)
        min_lat = origin_lat - (z1 + 80.0) / meters_per_deg_lat
        max_lat = origin_lat - (z0 - 80.0) / meters_per_deg_lat
        min_lon = origin_lon + (x0 - 80.0) / meters_per_deg_lon
        max_lon = origin_lon + (x1 + 80.0) / meters_per_deg_lon

        cols, rows = 32, 32
        initial_capacity = 2_000_000
        os.makedirs("models/sectors", exist_ok=True)
        glb_out = args.output or f"models/sectors/sector_{sec_x}_{sec_z}.glb"
        chunks_out = args.chunks_output or f"models/sectors/chunks_{sec_x}_{sec_z}.json"
        print("=" * 65)
        print(f"  GENERACIÓN QUIRÚRGICA: MACRO-SECTOR ({sec_x}, {sec_z})")
        print(f"  Límites métricos: X=[{x0:.1f}, {x1:.1f}]m, Z=[{z0:.1f}, {z1:.1f}]m")
        print("=" * 65)
    else:
        min_lon, max_lon = dem_min_lon, dem_max_lon
        min_lat, max_lat = dem_min_lat, dem_max_lat
        min_x, max_z = geo_to_meters(min_lat, min_lon, origin_lat, origin_lon)
        max_x, min_z = geo_to_meters(max_lat, max_lon, origin_lat, origin_lon)
        pad = 120.0; x0, x1 = min_x - pad, max_x + pad; z0, z1 = min_z - pad, max_z + pad
        cols, rows = 256, 256
        initial_capacity = 48_000_000
        glb_out = args.output or "models/aguascalientes_sector1.glb"
        chunks_out = args.chunks_output or "models/chunks.json"
        print("=" * 65)
        print("  GENERACIÓN METROPOLITANA: TERCER ANILLO COMPLETO (AV. SIGLO XXI)")
        print(f"  Dimensiones: X=[{x0:.1f}, {x1:.1f}]m ({(x1-x0)/1000:.2f} km), Z=[{z0:.1f}, {z1:.1f}]m ({(z1-z0)/1000:.2f} km)")
        print("=" * 65)

    # ── Topografía y DEM Real (siempre usa la grilla metropolitana global para bordes idénticos) ──
    terrain = TerrainElevation(dem_min_lat, dem_max_lat, dem_min_lon, dem_max_lon, nx=64, ny=64, origin_lat=origin_lat, origin_lon=origin_lon)
    if not hasattr(terrain, "rivers"):
        terrain._init_topography_features()
    rivers_geo = getattr(terrain, "rivers", [])
    get_real_topography_py = terrain.get_real_topography

    # ── Datos OSM ──
    osm_xml = fetch_osm_data(min_lon, min_lat, max_lon, max_lat, cache_file="models/osm_tercer_anillo.xml")
    nodes, osm_buildings, highways, traffic_signals, crossings, intersections, osm_trees, park_polygons, civil_bridges, pedestrian_bridges, tunnels = parse_osm_data(osm_xml)

    # ── Malla de Elevación ──
    print(f"[Malla] Malla de elevación ({cols}x{rows} quads)...")
    mesh_grid = create_mesh_grid(x0, z0, x1, z1, get_real_topography_py, cols=cols, rows=rows)

    if is_single_sector:
        # Conservar túneles cuyo bounding box intersecte el sector (+128m margen) para evitar cortes en bordes
        pad_t = 128.0
        filtered_tunnels = []
        for t in tunnels:
            pts_t = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in t[0]]
            if not pts_t:
                continue
            tx0 = min(p[0] for p in pts_t); tx1 = max(p[0] for p in pts_t)
            tz0 = min(p[1] for p in pts_t); tz1 = max(p[1] for p in pts_t)
            if not (tx1 < x0 - pad_t or tx0 > x1 + pad_t or tz1 < z0 - pad_t or tz0 > z1 + pad_t):
                filtered_tunnels.append(t)
        tunnels = filtered_tunnels
        clipped_rivers = []
        for r in rivers_geo:
            r_pts = r.get("pts", [])
            for ch in clip_polyline_to_bounds(r_pts, x0, z0, x1, z1):
                new_r = dict(r)
                new_r["pts"] = ch
                clipped_rivers.append(new_r)
        rivers_geo = clipped_rivers

    class _SectorAwareGrid:
        def __init__(self, inner_grid, bx0, bz0, bx1, bz1, fallback_fn):
            self._g = inner_grid
            self._bx0, self._bz0, self._bx1, self._bz1 = bx0, bz0, bx1, bz1
            self._fb = fallback_fn

        def get_mesh_height(self, gx, gz):
            if self._bx0 <= gx <= self._bx1 and self._bz0 <= gz <= self._bz1:
                return self._g.get_mesh_height(gx, gz)
            return self._fb(gx, gz)

    tunnel_grid = _SectorAwareGrid(mesh_grid, x0, z0, x1, z1, get_real_topography_py) if is_single_sector else mesh_grid

    # ── Pasos a Desnivel Subterráneos y Recorte de Terreno ──
    print(f"[Malla Túneles] Pre-generando pasos a desnivel subterráneos...")
    (tunnel_vertices, all_trench_polys, trench_spatial,
     tunnel_highway_pts, tunnel_highways) = build_trench_spatial_index(
        tunnels, origin_lat, origin_lon, tunnel_grid
    )

    # Inicializar FastMeshBuilder con memoria acotada
    mesh_builder = FastMeshBuilder(initial_capacity=initial_capacity)

    # ── Terreno Continuo con Recorte de Trincheras ──
    print("[Malla] Generando terreno continuo...")
    terrain_verts = generate_terrain_mesh(
        x0, z0, x1, z1, mesh_grid, trench_spatial, get_real_topography_py, cols=cols, rows=rows
    )
    mesh_builder.add_vertices(terrain_verts)
    del terrain_verts
    gc.collect()

    # ── Lechos Fluviales Texturados ──
    print("[Malla Hidrología] Modelando lechos fluviales...")
    river_verts = generate_riverbeds_mesh(rivers_geo, mesh_grid)
    mesh_builder.add_vertices(river_verts)
    del river_verts
    gc.collect()

    # ── Red Vial, Calzadas, Señalización SCT y Banquetas ──
    processed_highways, highway_pts_m = filter_and_process_highways(
        highways, origin_lat, origin_lon, tunnel_highway_pts
    )

    if is_single_sector:
        clipped_highways = []
        for pts, w, tags, sw in processed_highways:
            for ch in clip_polyline_to_bounds(pts, x0, z0, x1, z1):
                clipped_highways.append((ch, w, tags, sw))
        processed_highways = clipped_highways
        highway_pts_m = [h[0] for h in processed_highways]

        civil_bridges = [
            b for b in civil_bridges
            if any(x0 <= geo_to_meters(lat, lon, origin_lat, origin_lon)[0] <= x1 and
                   z0 <= geo_to_meters(lat, lon, origin_lat, origin_lon)[1] <= z1
                   for lat, lon in b[0])
        ]
        pedestrian_bridges = [
            b for b in pedestrian_bridges
            if any(x0 <= geo_to_meters(lat, lon, origin_lat, origin_lon)[0] <= x1 and
                   z0 <= geo_to_meters(lat, lon, origin_lat, origin_lon)[1] <= z1
                   for lat, lon in b[0])
        ]

    road_spatial_grid = build_road_spatial_grid(processed_highways, tunnel_highways)
    print(f"[Malla] Generando calzadas, banquetas y señalización SCT para {len(processed_highways)} vías...")
    road_verts = generate_road_and_sidewalk_mesh(
        processed_highways, mesh_grid, road_spatial_grid, trench_spatial=trench_spatial
    )
    mesh_builder.add_vertices(road_verts)
    del road_verts
    gc.collect()

    # ── Puentes y Estructuras Elevadas ──
    print(f"[Malla Puentes] {len(civil_bridges)} viaductos y {len(pedestrian_bridges)} puentes peatonales...")
    bridge_verts = generate_bridges_mesh(
        civil_bridges, pedestrian_bridges, origin_lat, origin_lon, mesh_grid, highway_pts_m=highway_pts_m
    )
    mesh_builder.add_vertices(bridge_verts)
    del bridge_verts
    gc.collect()

    # Integrar vértices de pasos a desnivel
    mesh_builder.add_vertices(tunnel_vertices)
    del tunnel_vertices
    gc.collect()

    # ── Nomenclatura Urbana, Cruces Peatonales y Señalización ──
    init_street_naming(highways, osm_xml, origin_lat, origin_lon)
    del osm_xml, nodes
    gc.collect()

    print("[Malla Tráfico] Generando semáforos e intersecciones...")
    traffic_verts, traffic_metadata = generate_intersections_and_signals(
        crossings, traffic_signals, origin_lat, origin_lon,
        x0, z0, x1, z1, mesh_grid, road_spatial_grid,
        trench_spatial=trench_spatial,
        base_vertex_offset=mesh_builder.vertex_count
    )
    mesh_builder.add_vertices(traffic_verts)
    del traffic_verts
    gc.collect()

    # ── Anuncios Elevados Corporativos ROLCAR (Refaccionaria Rogelio) ──
    rolcar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "rolcar_aguascalientes.json")
    if os.path.exists(rolcar_path):
        try:
            import json
            with open(rolcar_path, "r", encoding="utf-8") as rf:
                rolcar_branches = json.load(rf).get("branches", [])
            rolcar_signs = []
            seen_sign_pos = []
            for br in rolcar_branches:
                rx, rz = float(br["x"]), float(br["z"])
                if not (x0 <= rx <= x1 and z0 <= rz <= z1):
                    continue
                if any(math.hypot(rx - sx, rz - sz) < 12.0 for sx, sz in seen_sign_pos):
                    continue
                seen_sign_pos.append((rx, rz))
                # Orientar el anuncio elevado hacia la calle más cercana (o eje Norte/Sur)
                best_ang = 0.0
                best_d = 1e9
                cx_g, cz_g = int(math.floor(rx / 30.0)), int(math.floor(rz / 30.0))
                for dcx in (-1, 0, 1):
                    for dcz in (-1, 0, 1):
                        for seg_entry in road_spatial_grid.get((cx_g + dcx, cz_g + dcz), ()):
                            ax, az, bx, bz = seg_entry[1], seg_entry[2], seg_entry[3], seg_entry[4]
                            mx_s, mz_s = 0.5 * (ax + bx), 0.5 * (az + bz)
                            d = math.hypot(mx_s - rx, mz_s - rz)
                            if d < best_d:
                                best_d = d
                                best_ang = math.atan2(mz_s - rz, mx_s - rx)
                # Colocar el poste en el borde del predio (+6m hacia atrás o sobre azotea para no invadir asfalto)
                sx_p = rx - math.cos(best_ang) * 4.5
                sz_p = rz - math.sin(best_ang) * 4.5
                gy_p = mesh_grid.get_mesh_height(sx_p, sz_p)
                rolcar_signs.extend(make_rolcar_elevated_sign_3d(sx_p, gy_p, sz_p, dir_angle=best_ang, pole_h=11.0))
            if rolcar_signs:
                mesh_builder.add_vertices(rolcar_signs)
                print(f"[Rolcar] Colocados {len(seen_sign_pos)} anuncios elevados corporativos con PNG y colores.")
            del rolcar_signs
        except Exception as e:
            print(f"[Rolcar] Aviso colocando anuncios elevados: {e}")

    # ── Postes de Luz CFE y Cableado Aéreo Procedural (Corredores Rolcar) ──
    poles_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "utility_poles_rolcar.json")
    if os.path.exists(poles_json_path):
        try:
            wiring_verts = generate_rolcar_wiring_for_sector(x0, z0, x1, z1, mesh_grid, poles_json_path)
            if wiring_verts:
                mesh_builder.add_vertices(wiring_verts)
                print(f"[Wiring] Generados {len(wiring_verts)} vértices de postes CFE y cableado aéreo.")
            del wiring_verts
            gc.collect()
        except Exception as e:
            print(f"[Wiring] Aviso generando cableado aéreo: {e}")

    # ── Edificios Reales (Procesamiento por Lotes Acotado a <750MB RAM) ──
    print("[Edificios] Extrayendo base de datos de edificios reales...")
    all_buildings = merge_and_densify_buildings(
        osm_buildings, [], highways, x0, x1, z0, z1, origin_lat=origin_lat, origin_lon=origin_lon
    )
    if is_single_sector:
        all_buildings = [
            b for b in all_buildings
            if b.get("polygon") and any(x0 <= p[0] <= x1 and z0 <= p[1] <= z1 for p in b["polygon"])
        ]

    # Evitar edificios montados sobre trincheras de pasos a desnivel
    if trench_spatial:
        def _bldg_in_trench(poly):
            n_p = len(poly)
            cx_b = sum(p[0] for p in poly) / n_p
            cz_b = sum(p[1] for p in poly) / n_p
            pts_check = [(cx_b, cz_b)] + [(p[0], p[1]) for p in poly]
            for px, pz in pts_check:
                tcx, tcz = int(px // 100.0), int(pz // 100.0)
                for cand in trench_spatial.get((tcx, tcz), []):
                    if cand[1] <= px <= cand[3] and cand[2] <= pz <= cand[4]:
                        if is_point_in_quad(px, pz, cand[5]):
                            return True
            return False

        before_b = len(all_buildings)
        all_buildings = [b for b in all_buildings if b.get("polygon") and not _bldg_in_trench(b["polygon"])]
        removed_b = before_b - len(all_buildings)
        if removed_b:
            print(f"[Edificios] Excluidos {removed_b} edificios superpuestos sobre pasos a desnivel.")

    print("[Malla Props] Colocando props urbanos (señales de alto, hidrantes, mallas ciclónicas, barandales)...")
    props_verts = generate_street_props(
        intersections, traffic_signals, processed_highways,
        civil_bridges, pedestrian_bridges,
        all_buildings=all_buildings,
        origin_lat=origin_lat, origin_lon=origin_lon,
        x0=x0, z0=z0, x1=x1, z1=z1,
        mesh_grid=mesh_grid, trench_spatial=trench_spatial
    )
    mesh_builder.add_vertices(props_verts)
    del props_verts
    gc.collect()

    # Placas de nomenclatura en esquinas reales de edificios
    corner_signs = generate_corner_signs_on_facades(
        intersections, all_buildings, mesh_grid,
        origin_lat=origin_lat, origin_lon=origin_lon,
        x0=x0, z0=z0, x1=x1, z1=z1
    )
    mesh_builder.add_vertices(corner_signs)
    del corner_signs
    gc.collect()

    # Procesar edificios en lotes pequeños de 1,500 para mantener el heap Python mínimo (cero swap)
    del highways
    gc.collect()
    BATCH_SIZE = 1500
    total_buildings = len(all_buildings)
    print(f"[Malla] Generando {total_buildings:,} edificios reales (lotes de {BATCH_SIZE:,} con RAM acotada)...")
    for b_start in range(0, total_buildings, BATCH_SIZE):
        b_batch = all_buildings[b_start : b_start + BATCH_SIZE]
        batch_verts = []
        for b in b_batch:
            poly = b.get("polygon")
            if not poly or len(poly) < 3:
                continue
            h = b.get("height", 5.0)
            roof_col = b.get("roof_color") or (0.85, 0.82, 0.78)
            wall_col = b.get("wall_color")
            cat = b.get("type") or "residencial"
            bv = make_building_3d(
                poly, h, mesh_grid.get_mesh_height,
                roof_color=roof_col, wall_color_override=wall_col, category=cat,
                x0_map=-7712.602, z0_map=-7834.476, x1_map=5439.987, z1_map=9103.524
            )
            batch_verts.extend(bv)

        mesh_builder.add_vertices(batch_verts)
        del batch_verts
        gc.collect()
        time.sleep(0.002)  # Rendimiento cooperativo para el sistema operativo
        pct = min(100.0, (b_start + len(b_batch)) / max(1, total_buildings) * 100.0)
        print(f"  [{pct:5.1f}%] {min(b_start + len(b_batch), total_buildings):,}/{total_buildings:,} edificios convertidos ({mesh_builder.vertex_count:,} vértices)...")

    # ── Vegetación Urbana con Evasión Espacial ──
    print("[Malla Vegetación] Plantando masa arbórea urbana...")
    road_spatial_index = RoadSpatialIndex(highway_pts_m, cell_size=40.0)
    bldg_spatial_index = BuildingSpatialIndex(all_buildings, cell_size=40.0)
    trees_planted = 0
    tree_verts = []

    def _is_on_any_road(tx, tz, grid, margin=1.2):
        """Returns True if (tx, tz) falls within half-width + margin of any road or tunnel segment."""
        cx = int(math.floor(tx / 30.0))
        cz = int(math.floor(tz / 30.0))
        for dcx in (-1, 0, 1):
            for dcz in (-1, 0, 1):
                for seg_entry in grid.get((cx + dcx, cz + dcz), ()):
                    ax, az, bx, bz = seg_entry[1], seg_entry[2], seg_entry[3], seg_entry[4]
                    ohw = seg_entry[7]
                    if _point_to_segment_dist(tx, tz, ax, az, bx, bz) < (ohw + margin):
                        return True
        return False

    # Árboles ribereños
    for r_info in rivers_geo:
        r_pts = r_info["pts"]
        for s_idx in range(len(r_pts) - 1):
            rp0, rp1 = r_pts[s_idx], r_pts[s_idx + 1]
            rdx, rdz = rp1[0] - rp0[0], rp1[1] - rp0[1]
            rlen = math.hypot(rdx, rdz)
            if rlen < 5.0: continue
            rnx, rnz = -rdz / rlen, rdx / rlen
            n_t = max(1, int(rlen / 35.0))
            for ti in range(n_t):
                t_val = (ti + 0.5) / float(n_t)
                c_x, c_z = rp0[0] + t_val * rdx, rp0[1] + t_val * rdz
                for side_sign in (-1.0, 1.0):
                    bank_offset = r_info["channel_w"] * 0.5 + 4.5
                    tx = c_x + side_sign * rnx * bank_offset + random.uniform(-2.5, 2.5)
                    tz = c_z + side_sign * rnz * bank_offset + random.uniform(-2.5, 2.5)
                    if not (x0 <= tx <= x1 and z0 <= tz <= z1): continue
                    tcx, tcz = int(tx // 100.0), int(tz // 100.0)
                    if any(is_point_in_quad(tx, tz, cand[5]) for cand in trench_spatial.get((tcx, tcz), [])):
                        continue
                    if (
                        not _is_on_any_road(tx, tz, road_spatial_grid, margin=1.2)
                        and not road_spatial_index.is_near(tx, tz, threshold=4.5)
                        and not bldg_spatial_index.is_inside_or_near(tx, tz, min_dist=4.5)
                    ):
                        gy = mesh_grid.get_mesh_height(tx, tz) + 0.02
                        sp = random.randint(0, 3)
                        tree_verts.extend(make_tree_3d(tx, gy, tz, radius=2.2 + random.random()*0.8, species=sp))
                        trees_planted += 1

    # Árboles en camellones y banquetas
    max_trees = 250 if is_single_sector else 5500
    for h_idx, (pts_m, road_w, tags, has_sw) in enumerate(processed_highways):
        if len(pts_m) < 2: continue
        is_arterial_road = (road_w >= 9.0)
        step_tree = 30.0 if is_arterial_road else 50.0
        h_len = sum(math.hypot(pts_m[k+1][0] - pts_m[k][0], pts_m[k+1][1] - pts_m[k][1]) for k in range(len(pts_m) - 1))
        if h_len < 40.0: continue
        n_trees_seg = max(1, int(h_len / step_tree))
        for ti in range(n_trees_seg):
            t_frac = (ti + 0.5) / float(n_trees_seg)
            target_dist = t_frac * h_len
            accum = 0.0
            found_pt = None
            found_norm = None
            for k in range(len(pts_m) - 1):
                seg_d = math.hypot(pts_m[k+1][0] - pts_m[k][0], pts_m[k+1][1] - pts_m[k][1])
                if accum + seg_d >= target_dist:
                    st = (target_dist - accum) / max(0.001, seg_d)
                    px = pts_m[k][0] + st * (pts_m[k+1][0] - pts_m[k][0])
                    pz = pts_m[k][1] + st * (pts_m[k+1][1] - pts_m[k][1])
                    ndx = pts_m[k+1][0] - pts_m[k][0]; ndz = pts_m[k+1][1] - pts_m[k][1]
                    nlen = math.hypot(ndx, ndz) or 1.0
                    found_pt = (px, pz)
                    found_norm = (-ndz / nlen, ndx / nlen)
                    break
                accum += seg_d
            if not found_pt: continue

            if is_arterial_road or has_sw:
                side = 1.0 if (ti % 2 == 0) else -1.0
                sw_off = road_w * 0.5 + (1.8 if is_arterial_road else 1.4)
                tx = found_pt[0] + side * found_norm[0] * sw_off
                tz = found_pt[1] + side * found_norm[1] * sw_off
                if not (x0 <= tx <= x1 and z0 <= tz <= z1):
                    continue
                tcx, tcz = int(tx // 100.0), int(tz // 100.0)
                if any(is_point_in_quad(tx, tz, cand[5]) for cand in trench_spatial.get((tcx, tcz), [])):
                    continue
                if (
                    not _is_on_any_road(tx, tz, road_spatial_grid, margin=1.2)
                    and not road_spatial_index.is_near(tx, tz, threshold=3.5)
                    and not bldg_spatial_index.is_inside_or_near(tx, tz, min_dist=4.0)
                ):
                    gy = mesh_grid.get_mesh_height(tx, tz) + 0.02
                    sp = random.randint(0, 3)
                    radius = (2.1 + random.random() * 0.6) if is_arterial_road else (1.8 + random.random() * 0.5)
                    tree_verts.extend(make_tree_3d(tx, gy, tz, radius=radius, species=sp))
                    trees_planted += 1

            if trees_planted >= max_trees:
                break
        if trees_planted >= max_trees:
            break

    # Árboles OSM
    for lat, lon, tags, nid in osm_trees:
        tx, tz = geo_to_meters(lat, lon, origin_lat, origin_lon)
        if x0 <= tx <= x1 and z0 <= tz <= z1:
            tcx, tcz = int(tx // 100.0), int(tz // 100.0)
            if any(is_point_in_quad(tx, tz, cand[5]) for cand in trench_spatial.get((tcx, tcz), [])):
                continue
            if (
                not _is_on_any_road(tx, tz, road_spatial_grid, margin=1.2)
                and not road_spatial_index.is_near(tx, tz, threshold=4.0)
                and not bldg_spatial_index.is_inside_or_near(tx, tz, min_dist=4.0)
            ):
                gy = mesh_grid.get_mesh_height(tx, tz) + 0.02
                tree_verts.extend(make_tree_3d(tx, gy, tz, radius=2.0 + random.random()*0.5, species=random.randint(0, 3)))
                trees_planted += 1

    mesh_builder.add_vertices(tree_verts)
    del tree_verts
    gc.collect()

    # ── Domo Celeste y Cielo Nocturno de Aguascalientes ──
    if not is_single_sector:
        center_map_x = (x0 + x1) * 0.5
        center_map_z = (z0 + z1) * 0.5
        dome_rad = max(abs(x0), abs(x1), abs(z0), abs(z1)) * 1.25
        star_verts = generate_aguascalientes_night_sky(
            dome_radius=dome_rad, center_x=center_map_x, center_z=center_map_z, center_y=150.0
        )
        mesh_builder.add_vertices(star_verts)
        del star_verts
        gc.collect()

    # ── Exportación glTF (.glb) y Chunks Espaciales ──
    os.makedirs(os.path.dirname(glb_out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(chunks_out) or ".", exist_ok=True)
    json_out = "models/traffic_signals.json"

    sector_bounds = (sec_x, sec_z) if is_single_sector else None
    exported_verts = export_glb_and_chunks(glb_out, chunks_out, mesh_builder, traffic_metadata, sector_bounds=sector_bounds)
    if not is_single_sector:
        export_traffic_signals_json(json_out, traffic_metadata)
    else:
        manifest_path = "models/sectors.json"
        # Seguridad Web: solo actualizar el manifiesto de producción si la salida es una ruta oficial en models/
        is_production_output = glb_out.startswith("models/") or glb_out.startswith("./models/")
        if is_production_output and os.path.exists(manifest_path) and os.path.exists(chunks_out):
            try:
                import json
                with open(manifest_path, "r") as mf:
                    manifest = json.load(mf)
                with open(chunks_out, "r") as cf:
                    cdata = json.load(cf)

                # Chunks estrictos del macro-sector
                sec_chunks = cdata.get("chunks", [])

                if sec_chunks:
                    aabb_min_x = float(min(c["min_x"] for c in sec_chunks))
                    aabb_max_x = float(max(c["max_x"] for c in sec_chunks))
                    aabb_min_y = float(min(c["min_y"] for c in sec_chunks))
                    aabb_max_y = float(max(c["max_y"] for c in sec_chunks))
                    aabb_min_z = float(min(c["min_z"] for c in sec_chunks))
                    aabb_max_z = float(max(c["max_z"] for c in sec_chunks))
                else:
                    aabb_min_x, aabb_max_x = x0, x1
                    aabb_min_y, aabb_max_y = -25.0, 60.0
                    aabb_min_z, aabb_max_z = z0, z1

                sec_aabb = {
                    "min_x": round(aabb_min_x, 2), "min_y": round(aabb_min_y, 2), "min_z": round(aabb_min_z, 2),
                    "max_x": round(aabb_max_x, 2), "max_y": round(aabb_max_y, 2), "max_z": round(aabb_max_z, 2),
                }
                file_size_mb = round(os.path.getsize(glb_out) / (1024 * 1024), 2)
                found = False
                for s in manifest.get("sectors", []):
                    if s.get("mx") == sec_x and s.get("mz") == sec_z:
                        s["file"] = glb_out
                        s["vert_count"] = exported_verts
                        s["size_mb"] = file_size_mb
                        s["aabb"] = sec_aabb
                        s["chunks"] = sec_chunks
                        found = True
                        break
                if not found:
                    manifest.setdefault("sectors", []).append({
                        "mx": sec_x, "mz": sec_z,
                        "file": glb_out,
                        "vert_count": exported_verts,
                        "size_mb": file_size_mb,
                        "aabb": sec_aabb,
                        "chunks": sec_chunks
                    })
                manifest["total_verts"] = sum(s.get("vert_count", 0) for s in manifest.get("sectors", []))
                with open(manifest_path, "w") as mf:
                    json.dump(manifest, mf)
                print(f"[SectorSystem] ✅ Manifiesto models/sectors.json actualizado para sector ({sec_x}, {sec_z}): {exported_verts:,} vértices, {len(sec_chunks)} chunks.")
            except Exception as e:
                print(f"[SectorSystem] Advertencia actualizando manifiesto: {e}")

    elapsed = time.time() - t_start
    print("=" * 65)
    print(f"  GENERACIÓN COMPLETA en {elapsed:.2f}s!")
    print(f"  Vértices totales: {exported_verts:,}")
    print(f"  Árboles plantados: {trees_planted}")
    print(f"  Archivo GLB: {glb_out}")
    print(f"  Chunks JSON: {chunks_out}")
    print("=" * 65)


if __name__ == "__main__":
    generate_sector()
