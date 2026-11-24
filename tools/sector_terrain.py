#!/usr/bin/env python3
"""
sector_terrain.py - Terrain mesh generation, hydrological features, and spatial indices.

Extracts terrain, underpass trench cutout, riverbeds, and geometric spatial query structures
for the Aguascalientes 3D procedural engine.
"""

from collections import defaultdict
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from bridge_generator import make_underground_pass_3d
from geo_dem import MeshElevationGrid, geo_to_meters

VertexTuple = Tuple[
    Tuple[float, float, float],  # position: (x, y, z)
    Tuple[float, float, float],  # normal: (nx, ny, nz)
    Tuple[float, float],         # uv: (u, v)
    Tuple[float, float, float, float],  # color: (r, g, b, a)
    float                        # emission: em
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Geometric helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_point_in_quad(px: float, pz: float, quad: Sequence[Tuple[float, float]]) -> bool:
    """
    Ray-casting point-in-polygon test specifically optimized for 4-point quads or arbitrary planar polygons.
    """
    n = len(quad)
    if n < 3:
        return False
    inside = False
    p1x, p1z = quad[0]
    for i in range(1, n + 1):
        p2x, p2z = quad[i % n]
        if min(p1z, p2z) < pz <= max(p1z, p2z):
            if px <= max(p1x, p2x):
                x_inters = (pz - p1z) * (p2x - p1x) / (p2z - p1z) + p1x
                if p1x == p2x or px <= x_inters:
                    inside = not inside
        p1x, p1z = p2x, p2z
    return inside


def _point_to_segment_dist(px: float, pz: float, ax: float, az: float, bx: float, bz: float) -> float:
    """
    Calculates perpendicular Euclidean distance from point (px, pz) to 2D line segment (ax, az)-(bx, bz).
    """
    dx = bx - ax
    dz = bz - az
    len_sq = dx * dx + dz * dz
    if len_sq < 1e-6:
        return math.hypot(px - ax, pz - az)
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / len_sq))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def point_in_polygon(x: float, z: float, poly: Sequence[Tuple[float, float]]) -> bool:
    """
    Standard ray-casting point-in-polygon test.
    """
    n = len(poly)
    if n < 3:
        return False
    inside = False
    p1x, p1z = poly[0]
    for i in range(1, n + 1):
        p2x, p2z = poly[i % n]
        if min(p1z, p2z) < z <= max(p1z, p2z):
            if x <= max(p1x, p2x):
                if p1z != p2z:
                    xinters = (z - p1z) * (p2x - p1x) / (p2z - p1z) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1z = p2x, p2z
    return inside


def is_near_building(x: float, z: float, buildings: Sequence[Dict[str, Any]], threshold: float = 8.0) -> bool:
    """
    Simple centroid distance check against a building list.
    """
    for b in buildings:
        poly = b.get("polygon") or b.get("poly") or []
        if not poly:
            continue
        cx = sum(p[0] for p in poly) / len(poly)
        cz = sum(p[1] for p in poly) / len(poly)
        if math.hypot(x - cx, z - cz) < threshold:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Spatial indices
# ─────────────────────────────────────────────────────────────────────────────

class RoadSpatialIndex:
    """
    Spatial 2D hash grid for fast proximity testing against road segments.
    Used for vegetation / prop placement avoidance.
    """
    def __init__(self, highway_pts_m: Sequence[Sequence[Tuple[float, float]]], cell_size: float = 40.0):
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int], List[Tuple[float, float, float, float]]] = {}
        for pts in highway_pts_m:
            for i in range(len(pts) - 1):
                p0_x, p0_z = pts[i]
                p1_x, p1_z = pts[i + 1]
                min_x = min(p0_x, p1_x) - 7.0
                max_x = max(p0_x, p1_x) + 7.0
                min_z = min(p0_z, p1_z) - 7.0
                max_z = max(p0_z, p1_z) + 7.0
                c_x0 = int(min_x // cell_size)
                c_x1 = int(max_x // cell_size)
                c_z0 = int(min_z // cell_size)
                c_z1 = int(max_z // cell_size)
                seg = (p0_x, p0_z, p1_x, p1_z)
                for cx in range(c_x0, c_x1 + 1):
                    for cz in range(c_z0, c_z1 + 1):
                        key = (cx, cz)
                        if key not in self.grid:
                            self.grid[key] = []
                        self.grid[key].append(seg)

    def is_near(self, x: float, z: float, threshold: float = 6.0) -> bool:
        """
        Returns True if (x, z) is within threshold distance of any registered road segment.
        """
        cell = (int(x // self.cell_size), int(z // self.cell_size))
        candidates = self.grid.get(cell, [])
        for ax, az, bx, bz in candidates:
            if _point_to_segment_dist(x, z, ax, az, bx, bz) < threshold:
                return True
        return False


class BuildingSpatialIndex:
    """
    Spatial 2D hash grid for fast point-in-polygon and buffer distance testing against building footprints.
    """
    def __init__(self, buildings: Sequence[Dict[str, Any]], cell_size: float = 40.0):
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int], List[Tuple[Sequence[Tuple[float, float]], float, float, float, float]]] = {}
        for b in buildings:
            poly = b.get("polygon") or b.get("poly") or []
            if not poly:
                continue
            min_x = min(p[0] for p in poly) - 6.0
            max_x = max(p[0] for p in poly) + 6.0
            min_z = min(p[1] for p in poly) - 6.0
            max_z = max(p[1] for p in poly) + 6.0
            c_x0 = int(min_x // cell_size)
            c_x1 = int(max_x // cell_size)
            c_z0 = int(min_z // cell_size)
            c_z1 = int(max_z // cell_size)
            item = (poly, min_x, max_x, min_z, max_z)
            for cx in range(c_x0, c_x1 + 1):
                for cz in range(c_z0, c_z1 + 1):
                    key = (cx, cz)
                    if key not in self.grid:
                        self.grid[key] = []
                    self.grid[key].append(item)

    def is_inside_or_near(self, x: float, z: float, min_dist: float = 6.0) -> bool:
        """
        Returns True if (x, z) is inside any building polygon or closer than min_dist to its vertices.
        """
        cell = (int(x // self.cell_size), int(z // self.cell_size))
        candidates = self.grid.get(cell, [])
        for poly, min_x, max_x, min_z, max_z in candidates:
            if x < min_x or x > max_x or z < min_z or z > max_z:
                continue
            if point_in_polygon(x, z, poly):
                return True
            for px, pz in poly:
                if math.hypot(x - px, z - pz) < min_dist:
                    return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Trench underpass pre-generation and spatial index
# ─────────────────────────────────────────────────────────────────────────────

def build_trench_spatial_index(
    tunnels: Sequence[Tuple[Sequence[Tuple[float, float]], Dict[str, Any], Any]],
    origin_lat: float,
    origin_lon: float,
    mesh_grid: MeshElevationGrid,
    trench_cell_size: float = 100.0,
) -> Tuple[
    List[VertexTuple],
    List[List[Tuple[float, float]]],
    Dict[Tuple[int, int], List[Tuple[int, float, float, float, float, List[Tuple[float, float]]]]],
    List[List[Tuple[float, float]]],
    List[Tuple[List[Tuple[float, float]], float, Dict[str, Any]]],
]:
    """
    Pre-generates open-trench underpasses and builds a 2D spatial hash grid of trench clipping polygons.

    Returns:
        (tunnel_vertices, all_trench_polys, trench_spatial, tunnel_highway_pts, tunnel_highways)
    """
    print(f"[Malla Túneles] Pre-generando {len(tunnels)} pasos a desnivel subterráneos/túneles en trinchera abierta...")
    tunnel_vertices: List[VertexTuple] = []
    apron_vertices: List[VertexTuple] = []
    all_trench_polys: List[List[Tuple[float, float]]] = []
    tunnel_highway_pts: List[List[Tuple[float, float]]] = []
    tunnel_highways: List[Tuple[List[Tuple[float, float]], float, Dict[str, Any]]] = []

    # 1. Convertir a metros y fusionar segmentos contiguos de un mismo túnel divididos en nodos OSM
    raw_tunnels = []
    for coords, tags, refs in tunnels:
        if len(coords) < 2:
            continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        raw_tunnels.append({"pts": pts_m, "tags": tags})

    merged_tunnels = []
    used = [False] * len(raw_tunnels)
    for i in range(len(raw_tunnels)):
        if used[i]:
            continue
        used[i] = True
        cur_pts = list(raw_tunnels[i]["pts"])
        cur_tags = raw_tunnels[i]["tags"]
        cur_ow = (cur_tags.get("oneway") == "yes" or "link" in cur_tags.get("highway", ""))
        cur_name = cur_tags.get("name") or ""

        changed = True
        while changed:
            changed = False
            for j in range(len(raw_tunnels)):
                if used[j]:
                    continue
                cand_pts = raw_tunnels[j]["pts"]
                cand_tags = raw_tunnels[j]["tags"]
                cand_ow = (cand_tags.get("oneway") == "yes" or "link" in cand_tags.get("highway", ""))
                cand_name = cand_tags.get("name") or ""
                if cur_ow != cand_ow or (cur_name and cand_name and cur_name != cand_name):
                    continue
                if math.hypot(cur_pts[-1][0] - cand_pts[0][0], cur_pts[-1][1] - cand_pts[0][1]) < 1.0:
                    cur_pts.extend(cand_pts[1:])
                    used[j] = True
                    changed = True
                    break
                if math.hypot(cand_pts[-1][0] - cur_pts[0][0], cand_pts[-1][1] - cur_pts[0][1]) < 1.0:
                    cur_pts = list(cand_pts[:-1]) + cur_pts
                    used[j] = True
                    changed = True
                    break
        merged_tunnels.append((cur_pts, cur_tags))

    # 2. Detectar conectores/ramas cortas (< 55m) cuyo extremo conecta con el interior de otro túnel mayor
    def _poly_len(pts):
        return sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(len(pts) - 1))

    tunnel_lengths = [_poly_len(pts) for pts, _ in merged_tunnels]
    skipped_connectors = 0
    for idx_t, (pts_m, tags) in enumerate(merged_tunnels):
        t_len = tunnel_lengths[idx_t]
        tunnel_highway_pts.append(pts_m)
        is_oneway = (tags.get('oneway') == 'yes' or 'link' in tags.get('highway', ''))
        lanes_str = str(tags.get('lanes', ''))
        lanes_cnt = int(lanes_str) if lanes_str.isdigit() else (1 if 'link' in tags.get('highway', '') else 2)

        # Descartar ramas cortas (< 55m) que conectan con otro túnel para evitar muros/albardillas cruzando calzadas
        if t_len < 55.0:
            touches_longer = False
            for ep in (pts_m[0], pts_m[-1]):
                for other_idx, (o_pts, _) in enumerate(merged_tunnels):
                    if other_idx == idx_t or tunnel_lengths[other_idx] <= t_len:
                        continue
                    if any(math.hypot(ep[0] - op[0], ep[1] - op[1]) < 2.5 for op in o_pts):
                        touches_longer = True
                        break
                if touches_longer:
                    break
            if touches_longer or lanes_cnt <= 1 or 'link' in tags.get('highway', ''):
                skipped_connectors += 1
                continue

        if is_oneway:
            road_w = min(8.2, max(6.8, lanes_cnt * 3.4 + 0.6))
        else:
            road_w = 11.5 if tags.get('highway') in ('primary', 'trunk') else 9.5

        tun_verts, trench_polys = make_underground_pass_3d(
            pts_m, road_w=road_w, depth_m=5.4, mesh_grid=mesh_grid, is_oneway=is_oneway, apron_out=apron_vertices
        )
        tunnel_vertices.extend(tun_verts)
        all_trench_polys.extend(trench_polys)
        tunnel_highways.append((pts_m, road_w, tags))

    if skipped_connectors:
        print(f"[Malla Túneles] Conectores subterráneos cortos omitidos como trinchera aislada: {skipped_connectors}")

    print(f"[Malla Túneles] {len(all_trench_polys)} polígonos de trinchera a cielo abierto indexados para recorte de terreno.")

    trench_spatial: Dict[Tuple[int, int], List[Tuple[int, float, float, float, float, List[Tuple[float, float]]]]] = defaultdict(list)
    for poly_idx, poly in enumerate(all_trench_polys):
        poly_min_x = min(p[0] for p in poly)
        poly_max_x = max(p[0] for p in poly)
        poly_min_z = min(p[1] for p in poly)
        poly_max_z = max(p[1] for p in poly)
        cx0 = int(poly_min_x // trench_cell_size)
        cx1 = int(poly_max_x // trench_cell_size)
        cz0 = int(poly_min_z // trench_cell_size)
        cz1 = int(poly_max_z // trench_cell_size)
        item = (poly_idx, poly_min_x, poly_min_z, poly_max_x, poly_max_z, poly)
        for cx in range(cx0, cx1 + 1):
            for cz in range(cz0, cz1 + 1):
                trench_spatial[(cx, cz)].append(item)

    # Filtrar faldones satelitales que caigan dentro de trincheras paralelas o vecinas
    kept_aprons = 0
    dropped_aprons = 0
    for idx in range(0, len(apron_vertices), 3):
        v0, v1, v2 = apron_vertices[idx], apron_vertices[idx + 1], apron_vertices[idx + 2]
        cx_tri = (v0[0][0] + v1[0][0] + v2[0][0]) / 3.0
        cz_tri = (v0[0][2] + v1[0][2] + v2[0][2]) / 3.0
        tcx = int(cx_tri // trench_cell_size)
        tcz = int(cz_tri // trench_cell_size)
        inside_trench = False
        for cand in trench_spatial.get((tcx, tcz), []):
            if cand[1] <= cx_tri <= cand[3] and cand[2] <= cz_tri <= cand[4]:
                if is_point_in_quad(cx_tri, cz_tri, cand[5]):
                    inside_trench = True
                    break
        if inside_trench:
            dropped_aprons += 1
        else:
            tunnel_vertices.append(v0)
            tunnel_vertices.append(v1)
            tunnel_vertices.append(v2)
            kept_aprons += 1
    if dropped_aprons:
        print(f"[Malla Túneles] Faldones filtrados por solapamiento con trinchera: {dropped_aprons} descartados, {kept_aprons} conservados.")

    return tunnel_vertices, all_trench_polys, trench_spatial, tunnel_highway_pts, tunnel_highways


# ─────────────────────────────────────────────────────────────────────────────
# 4. Continuous terrain mesh grid generation
# ─────────────────────────────────────────────────────────────────────────────

def create_mesh_grid(
    x0: float,
    z0: float,
    x1: float,
    z1: float,
    get_real_topography_py: Callable[[float, float], float],
    cols: int = 256,
    rows: int = 256,
) -> MeshElevationGrid:
    """
    Creates and populates a MeshElevationGrid sampled from the topography elevation function.
    """
    dx = (x1 - x0) / cols
    dz = (z1 - z0) / rows
    grid_pts = []
    for r in range(rows + 1):
        pz = z0 + r * dz
        v = (pz - z0) / (z1 - z0)
        for c in range(cols + 1):
            px = x0 + c * dx
            py = get_real_topography_py(px, pz)
            u = (px - x0) / (x1 - x0)
            grid_pts.append((px, py, pz, u, v))
    return MeshElevationGrid(x0, z0, x1, z1, cols, rows, grid_pts)


def generate_terrain_mesh(
    x0: float,
    z0: float,
    x1: float,
    z1: float,
    mesh_grid: MeshElevationGrid,
    trench_spatial: Dict[Tuple[int, int], List[Any]],
    get_real_topography_py: Callable[[float, float], float],
    cols: int = 256,
    rows: int = 256,
    trench_cell_size: float = 100.0,
    uv_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> List[VertexTuple]:
    """
    Generates continuous high-definition terrain mesh with adaptive 16x16 subquad
    subdivision, cutout around open-trench underpasses, and perimeter antifissure skirt.
    """
    if hasattr(mesh_grid, "cols"):
        cols = mesh_grid.cols
    if hasattr(mesh_grid, "rows"):
        rows = mesh_grid.rows

    # Límites UV metropolitanos globales para coincidencia perfecta de ortofoto entre sectores
    if uv_bounds is not None:
        ux0, uz0, ux1, uz1 = uv_bounds
    else:
        ux0, uz0, ux1, uz1 = -7712.602, -7834.476, 5439.987, 9103.524

    u_range = max(1.0, ux1 - ux0)
    v_range = max(1.0, uz1 - uz0)

    dx = (x1 - x0) / cols
    dz = (z1 - z0) / rows

    grid_pts = []
    has_heights = hasattr(mesh_grid, "heights") and len(mesh_grid.heights) > rows
    for r in range(rows + 1):
        pz = z0 + r * dz
        v = (pz - uz0) / v_range
        row_h = mesh_grid.heights[r] if has_heights else None
        for c in range(cols + 1):
            px = x0 + c * dx
            py = row_h[c] if row_h is not None else get_real_topography_py(px, pz)
            u = (px - ux0) / u_range
            grid_pts.append((px, py, pz, u, v))

    norm_up = (0.0, 1.0, 0.0)
    terrain_col = (1.0, 1.0, 1.0, 0.0)
    skipped_subquads = 0
    N_SUB = 32
    vertices: List[VertexTuple] = []

    for r in range(rows):
        for c in range(cols):
            idx0 = r * (cols + 1) + c
            idx1 = idx0 + 1
            idx2 = (r + 1) * (cols + 1) + c
            idx3 = idx2 + 1
            p0, p1, p2, p3 = grid_pts[idx0], grid_pts[idx1], grid_pts[idx2], grid_pts[idx3]

            q_min_x = min(p0[0], p1[0], p2[0], p3[0])
            q_max_x = max(p0[0], p1[0], p2[0], p3[0])
            q_min_z = min(p0[2], p1[2], p2[2], p3[2])
            q_max_z = max(p0[2], p1[2], p2[2], p3[2])

            tc_x0 = int(q_min_x // trench_cell_size)
            tc_x1 = int(q_max_x // trench_cell_size)
            tc_z0 = int(q_min_z // trench_cell_size)
            tc_z1 = int(q_max_z // trench_cell_size)

            candidates = []
            seen_ids = set()
            for tcx in range(tc_x0, tc_x1 + 1):
                for tcz in range(tc_z0, tc_z1 + 1):
                    for item in trench_spatial.get((tcx, tcz), []):
                        if item[0] not in seen_ids:
                            seen_ids.add(item[0])
                            if not (q_max_x < item[1] or q_min_x > item[3] or q_max_z < item[2] or q_min_z > item[4]):
                                candidates.append(item)

            if not candidates:
                vertices.append(((p0[0], p0[1], p0[2]), norm_up, (p0[3], p0[4]), terrain_col, 0.0))
                vertices.append(((p1[0], p1[1], p1[2]), norm_up, (p1[3], p1[4]), terrain_col, 0.0))
                vertices.append(((p2[0], p2[1], p2[2]), norm_up, (p2[3], p2[4]), terrain_col, 0.0))
                vertices.append(((p1[0], p1[1], p1[2]), norm_up, (p1[3], p1[4]), terrain_col, 0.0))
                vertices.append(((p3[0], p3[1], p3[2]), norm_up, (p3[3], p3[4]), terrain_col, 0.0))
                vertices.append(((p2[0], p2[1], p2[2]), norm_up, (p2[3], p2[4]), terrain_col, 0.0))
            else:
                sub_dx = (p1[0] - p0[0]) / N_SUB
                sub_dz = (p2[2] - p0[2]) / N_SUB
                for sr in range(N_SUB):
                    for sc in range(N_SUB):
                        spx0 = p0[0] + sc * sub_dx
                        spz0 = p0[2] + sr * sub_dz
                        spx1 = spx0 + sub_dx
                        spz1 = spz0 + sub_dz
                        sub_cx = 0.5 * (spx0 + spx1)
                        sub_cz = 0.5 * (spz0 + spz1)

                        test_pts = (
                            (sub_cx, sub_cz),
                            (spx0, spz0), (spx1, spz0), (spx0, spz1), (spx1, spz1),
                            (sub_cx, spz0), (sub_cx, spz1), (spx0, sub_cz), (spx1, sub_cz),
                        )
                        in_trench = False
                        for cand in candidates:
                            # cand: (poly_idx, poly_min_x, poly_min_z, poly_max_x, poly_max_z, poly)
                            if not (spx1 < cand[1] or spx0 > cand[3] or spz1 < cand[2] or spz0 > cand[4]):
                                poly = cand[5]
                                if any(is_point_in_quad(px_t, pz_t, poly) for px_t, pz_t in test_pts):
                                    in_trench = True
                                    break

                        if in_trench:
                            skipped_subquads += 1
                            continue

                        spy0 = mesh_grid.get_mesh_height(spx0, spz0)
                        spy1 = mesh_grid.get_mesh_height(spx1, spz0)
                        spy2 = mesh_grid.get_mesh_height(spx0, spz1)
                        spy3 = mesh_grid.get_mesh_height(spx1, spz1)

                        su0 = (spx0 - ux0) / u_range
                        sv0 = (spz0 - uz0) / v_range
                        su1 = (spx1 - ux0) / u_range
                        sv1 = (spz1 - uz0) / v_range

                        vertices.append(((spx0, spy0, spz0), norm_up, (su0, sv0), terrain_col, 0.0))
                        vertices.append(((spx1, spy1, spz0), norm_up, (su1, sv0), terrain_col, 0.0))
                        vertices.append(((spx0, spy2, spz1), norm_up, (su0, sv1), terrain_col, 0.0))
                        vertices.append(((spx1, spy1, spz0), norm_up, (su1, sv0), terrain_col, 0.0))
                        vertices.append(((spx1, spy3, spz1), norm_up, (su1, sv1), terrain_col, 0.0))
                        vertices.append(((spx0, spy2, spz1), norm_up, (su0, sv1), terrain_col, 0.0))

    # ── Faldón Perimetral Antifisuras (Downward Perimeter Skirt) ──
    # Extiende paredes verticales hacia abajo (Y - 15m) en los 4 bordes para
    # garantizar cobertura total y sellar cualquier fisura visual entre macro-sectores,
    # omitiendo los tramos donde un paso a desnivel cruza el borde del sector.
    SKIRT_DEPTH = 15.0

    def _emit_skirt_edge(pA, pB, norm_edge):
        ax, ay, az, au, av = pA
        bx, by, bz, bu, bv = pB
        e_min_x, e_max_x = min(ax, bx), max(ax, bx)
        e_min_z, e_max_z = min(az, bz), max(az, bz)
        tc_x0 = int(e_min_x // trench_cell_size)
        tc_x1 = int(e_max_x // trench_cell_size)
        tc_z0 = int(e_min_z // trench_cell_size)
        tc_z1 = int(e_max_z // trench_cell_size)
        cands = []
        seen = set()
        for tcx in range(tc_x0, tc_x1 + 1):
            for tcz in range(tc_z0, tc_z1 + 1):
                for item in trench_spatial.get((tcx, tcz), []):
                    if item[0] not in seen:
                        seen.add(item[0])
                        if not (e_max_x < item[1] or e_min_x > item[3] or e_max_z < item[2] or e_min_z > item[4]):
                            cands.append(item)
        steps = N_SUB if cands else 1
        for k in range(steps):
            t0 = k / float(steps)
            t1 = (k + 1) / float(steps)
            sx0 = ax + t0 * (bx - ax); sy0 = ay + t0 * (by - ay); sz0 = az + t0 * (bz - az)
            su0 = au + t0 * (bu - au); sv0 = av + t0 * (bv - av)
            sx1 = ax + t1 * (bx - ax); sy1 = ay + t1 * (by - ay); sz1 = az + t1 * (bz - az)
            su1 = au + t1 * (bu - au); sv1 = av + t1 * (bv - av)
            if cands:
                mx = 0.5 * (sx0 + sx1)
                mz = 0.5 * (sz0 + sz1)
                if any(
                    c[1] <= px_t <= c[3] and c[2] <= pz_t <= c[4] and is_point_in_quad(px_t, pz_t, c[5])
                    for c in cands
                    for px_t, pz_t in ((mx, mz), (sx0, sz0), (sx1, sz1))
                ):
                    continue
            vertices.append(((sx0, sy0, sz0), norm_edge, (su0, sv0), terrain_col, 0.0))
            vertices.append(((sx1, sy1, sz1), norm_edge, (su1, sv1), terrain_col, 0.0))
            vertices.append(((sx0, sy0 - SKIRT_DEPTH, sz0), norm_edge, (su0, sv0), terrain_col, 0.0))
            vertices.append(((sx1, sy1, sz1), norm_edge, (su1, sv1), terrain_col, 0.0))
            vertices.append(((sx1, sy1 - SKIRT_DEPTH, sz1), norm_edge, (su1, sv1), terrain_col, 0.0))
            vertices.append(((sx0, sy0 - SKIRT_DEPTH, sz0), norm_edge, (su0, sv0), terrain_col, 0.0))

    # 1. Borde Norte (r = 0, z = z0)
    norm_north = (0.0, 0.0, -1.0)
    for c in range(cols):
        _emit_skirt_edge(grid_pts[0 * (cols + 1) + c], grid_pts[0 * (cols + 1) + c + 1], norm_north)

    # 2. Borde Sur (r = rows, z = z1)
    norm_south = (0.0, 0.0, 1.0)
    for c in range(cols):
        _emit_skirt_edge(grid_pts[rows * (cols + 1) + c + 1], grid_pts[rows * (cols + 1) + c], norm_south)

    # 3. Borde Oeste (c = 0, x = x0)
    norm_west = (-1.0, 0.0, 0.0)
    for r in range(rows):
        _emit_skirt_edge(grid_pts[(r + 1) * (cols + 1) + 0], grid_pts[r * (cols + 1) + 0], norm_west)

    # 4. Borde Este (c = cols, x = x1)
    norm_east = (1.0, 0.0, 0.0)
    for r in range(rows):
        _emit_skirt_edge(grid_pts[r * (cols + 1) + cols], grid_pts[(r + 1) * (cols + 1) + cols], norm_east)

    print(f"[Malla] Terreno continuo generado con faldón perimetral: {skipped_subquads} sub-cuadrantes recortados sobre pasos a desnivel.")
    return vertices


# ─────────────────────────────────────────────────────────────────────────────
# 5. Riverbeds modeling
# ─────────────────────────────────────────────────────────────────────────────

def generate_riverbeds_mesh(
    rivers_geo: Sequence[Dict[str, Any]],
    mesh_grid: MeshElevationGrid,
) -> List[VertexTuple]:
    """
    Generates textured riverbed geometry for natural rivers and arroyos (gravel / sediment beds).
    """
    print("[Malla Hidrología] Modelando lechos fluviales de arroyos (cantos rodados y sedimentos)...")
    vertices: List[VertexTuple] = []

    for r_info in rivers_geo:
        r_pts = r_info.get("pts", [])
        ch_w = r_info.get("channel_w", 10.0) * 0.5
        for s_idx in range(len(r_pts) - 1):
            rp0 = r_pts[s_idx]
            rp1 = r_pts[s_idx + 1]
            rdx = rp1[0] - rp0[0]
            rdz = rp1[1] - rp0[1]
            rlen = math.hypot(rdx, rdz)
            if rlen < 1.0:
                continue
            rnx = -rdz / rlen
            rnz = rdx / rlen
            n_rsub = max(1, int(rlen / 15.0))
            for rs in range(n_rsub):
                t0 = rs / float(n_rsub)
                t1 = (rs + 1) / float(n_rsub)
                sp0 = (rp0[0] + t0 * rdx, rp0[1] + t0 * rdz)
                sp1 = (rp0[0] + t1 * rdx, rp0[1] + t1 * rdz)
                y_c0 = mesh_grid.get_mesh_height(sp0[0], sp0[1]) + 0.05
                y_c1 = mesh_grid.get_mesh_height(sp1[0], sp1[1]) + 0.05

                rq0 = (sp0[0] - rnx * ch_w, y_c0, sp0[1] - rnz * ch_w)
                rq1 = (sp0[0] + rnx * ch_w, y_c0, sp0[1] + rnz * ch_w)
                rq2 = (sp1[0] + rnx * ch_w, y_c1, sp1[1] + rnz * ch_w)
                rq3 = (sp1[0] - rnx * ch_w, y_c1, sp1[1] - rnz * ch_w)

                u_b = 4.0 * 0.125
                u_sp = 0.125
                v_b = 2.0 * 0.125
                v_sp = 0.125
                uv_r0 = (u_b, v_b + v_sp)
                uv_r1 = (u_b + u_sp, v_b + v_sp)
                uv_r2 = (u_b + u_sp, v_b)
                uv_r3 = (u_b, v_b)
                bed_col = (1.0, 1.0, 1.0, 1.0)
                norm_r = (0.0, 1.0, 0.0)

                vertices.append((rq0, norm_r, uv_r0, bed_col, 0.0))
                vertices.append((rq1, norm_r, uv_r1, bed_col, 0.0))
                vertices.append((rq2, norm_r, uv_r2, bed_col, 0.0))
                vertices.append((rq0, norm_r, uv_r0, bed_col, 0.0))
                vertices.append((rq2, norm_r, uv_r2, bed_col, 0.0))
                vertices.append((rq3, norm_r, uv_r3, bed_col, 0.0))

    return vertices


__all__ = [
    "is_point_in_quad",
    "_point_to_segment_dist",
    "point_in_polygon",
    "is_near_building",
    "RoadSpatialIndex",
    "BuildingSpatialIndex",
    "build_trench_spatial_index",
    "create_mesh_grid",
    "generate_terrain_mesh",
    "generate_riverbeds_mesh",
]
