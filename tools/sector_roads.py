#!/usr/bin/env python3
"""
sector_roads.py - Modular Road, Bridge, Traffic & Prop Generation for Aguascalientes Sector Engine.
Extracted from tools/generate_sector.py.
"""

import math
import random
from collections import defaultdict
import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Any, Optional

from geo_dem import geo_to_meters
from procedural_props import (
    make_sidewalk_3d,
    make_zebra_crossing_3d,
    make_traffic_signal_3d,
    make_stop_sign_3d,
    make_fire_hydrant_3d,
    make_chainlink_fence_3d,
    make_railing_3d,
    make_corner_street_signs_on_facade
)
from bridge_generator import make_civil_bridge_3d, make_pedestrian_bridge_3d


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE RED VIAL
# ─────────────────────────────────────────────────────────────────────────────

DRIVABLE_HIGHWAYS = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary',
    'residential', 'unclassified', 'living_street',
    'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'
}

ARTERIAL_HIGHWAY_TYPES = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary',
    'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'
}

PEDESTRIAN_SIDEWALK_TYPES = {
    'primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'living_street'
}

CP_INFO = {
    '20000': ('DEL. CENTRO', 'COL. CENTRO'),
    '20002': ('DEL. CENTRO', 'COL. CENTRO'),
    '20010': ('DEL. CENTRO', 'B. LA PURISIMA'),
    '20020': ('DEL. CENTRO', 'B. DE LA SALUD'),
    '20030': ('DEL. CENTRO', 'B. SAN MARCOS'),
    '20040': ('DEL. CENTRO', 'B. DEL ENCINO'),
    '20050': ('DEL. CENTRO', 'B. GUADALUPE'),
    '20059': ('DEL. CENTRO', 'COL. CURTIDORES'),
    '20060': ('DEL. POCITOS', 'COL. GREMIAL'),
    '20070': ('DEL. SANTA ANITA', 'COL. PRIMAVERA'),
    '20080': ('DEL. POCITOS', 'COL. BUENOS AIRES'),
    '20160': ('DEL. SANTA ANITA', 'COL. HEROES'),
    '20174': ('DEL. SANTA ANITA', 'FRACC. CONSTITUCION'),
    '20180': ('DEL. POCITOS', 'COL. INDEPENDENCIA'),
    '20190': ('DEL. POCITOS', 'FRACC. FATIMA'),
    '20210': ('DEL. MORELOS', 'COL. LAS AMERICAS'),
    '20220': ('DEL. MORELOS', 'COL. SAN LUIS'),
    '20230': ('DEL. INSURGENTES', 'COL. DEL CARMEN'),
    '20239': ('DEL. INSURGENTES', 'FRACC. ESPANA'),
    '20240': ('DEL. INSURGENTES', 'COL. INSURGENTES'),
    '20259': ('DEL. MORELOS', 'COL. OJOCALIENTE'),
    '20270': ('DEL. MORELOS', 'FRACC. MORELOS'),
    '20320': ('DEL. SANTA ANITA', 'COL. LA ESTRELLA')
}


# ─────────────────────────────────────────────────────────────────────────────
# GEOMETRÍA BÁSICA
# ─────────────────────────────────────────────────────────────────────────────

def is_point_in_quad(px: float, pz: float, quad: List[Tuple[float, float]]) -> bool:
    """Ray casting point-in-polygon test for 4-vertex quads."""
    inside = False
    n = len(quad)
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
    dx, dz = bx - ax, bz - az
    len_sq = dx * dx + dz * dz
    if len_sq < 1e-6:
        return math.hypot(px - ax, pz - az)
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / len_sq))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


# ─────────────────────────────────────────────────────────────────────────────
# 1. CÁLCULO DE NORMALES MITER PARA CARRETERAS
# ─────────────────────────────────────────────────────────────────────────────

def compute_highway_miter_normals(pts_m: List[Tuple[float, float]]) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]], List[Tuple[float, float]]]:
    """
    Computes segment normals, vertex miter normals, and forward tangent vectors for a polyline.
    Returns:
        seg_normals: List of unit perpendicular vectors per segment
        vtx_normals: List of miter-scaled perpendicular vectors per vertex
        seg_fwd: List of unit forward tangent vectors per segment
    """
    K = len(pts_m) - 1
    if K < 1:
        return [(0.0, 1.0)], [(0.0, 1.0)], [(1.0, 0.0)]
    seg_normals = []
    seg_fwd = []
    for i in range(K):
        dx = pts_m[i+1][0] - pts_m[i][0]
        dz = pts_m[i+1][1] - pts_m[i][1]
        L = math.hypot(dx, dz)
        if L < 1e-4:
            seg_normals.append((0.0, 1.0))
            seg_fwd.append((1.0, 0.0))
        else:
            seg_normals.append((-dz / L, dx / L))
            seg_fwd.append((dx / L, dz / L))

    vtx_normals = [seg_normals[0]]
    for i in range(1, K):
        n_prev = seg_normals[i-1]
        n_curr = seg_normals[i]
        sx = n_prev[0] + n_curr[0]
        sz = n_prev[1] + n_curr[1]
        s_len = math.hypot(sx, sz)
        if s_len < 1e-4:
            vtx_normals.append(n_curr)
        else:
            ux = sx / s_len
            uz = sz / s_len
            dot = ux * n_curr[0] + uz * n_curr[1]
            if dot < 0.25:
                m = 1.5
            else:
                m = min(1.5, 1.0 / dot)
            vtx_normals.append((ux * m, uz * m))
    vtx_normals.append(seg_normals[-1])
    return seg_normals, vtx_normals, seg_fwd


# ─────────────────────────────────────────────────────────────────────────────
# 2. FILTRADO DE CARRETERAS Y GRID ESPACIAL
# ─────────────────────────────────────────────────────────────────────────────

def filter_and_process_highways(
    highways: List[Any],
    origin_lat: float,
    origin_lon: float,
    tunnel_highway_pts: Optional[List[List[Tuple[float, float]]]] = None
) -> Tuple[List[Tuple[List[Tuple[float, float]], float, Dict[str, Any], bool]], List[List[Tuple[float, float]]]]:
    """
    Filter highways down to drivable arterial network and urban core.
    Returns:
        processed_highways: List of (pts_m, road_w, tags, has_sw)
        highway_pts_m: List of polyline points (including tunnel_highway_pts if provided)
    """
    highway_pts_m = list(tunnel_highway_pts or [])
    processed_highways = []
    for coords, tags, refs in highways:
        if len(coords) < 2:
            continue
        htype = tags.get('highway', '')
        if htype not in DRIVABLE_HIGHWAYS:
            continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]

        is_arterial = (htype in ARTERIAL_HIGHWAY_TYPES)
        in_core = any(-1800.0 <= p[0] <= 1800.0 and -1800.0 <= p[1] <= 1800.0 for p in pts_m)
        if not (is_arterial or in_core):
            continue

        highway_pts_m.append(pts_m)
        road_w = 7.0
        if htype in ('primary', 'trunk', 'motorway'):
            road_w = 12.0
        elif htype == 'secondary':
            road_w = 9.5
        elif htype == 'tertiary':
            road_w = 8.0
        elif 'link' in htype:
            road_w = 6.5
        has_sw = (htype in PEDESTRIAN_SIDEWALK_TYPES)
        processed_highways.append((pts_m, road_w, tags, has_sw))

    return processed_highways, highway_pts_m


def build_road_spatial_grid(
    processed_highways: List[Any],
    tunnel_highways: Optional[List[Any]] = None,
    cell_size: float = 30.0
) -> Dict[Tuple[int, int], List[Any]]:
    """
    Constructs a spatial hash grid of surface road and tunnel ramp segments.
    Used for median sidewalk suppression, zebra crossing alignment, and prop clearance.
    """
    road_spatial_grid = defaultdict(list)

    def _add_road_to_grid(h_idx: int, pts_m: List[Tuple[float, float]], road_w: float, tags: Dict[str, Any], is_tun: bool = False):
        hw = road_w * 0.5
        is_ow = (tags.get('oneway') == 'yes' or tags.get('junction') == 'roundabout' or 'link' in tags.get('highway', ''))
        for s_idx in range(len(pts_m) - 1):
            p0 = pts_m[s_idx]; p1 = pts_m[s_idx + 1]
            dx_ab = p1[0] - p0[0]; dz_ab = p1[1] - p0[1]
            seg_len = math.hypot(dx_ab, dz_ab)
            if seg_len < 1e-4:
                continue
            fwd = (dx_ab / seg_len, dz_ab / seg_len)
            min_gx = min(p0[0], p1[0]) - hw - 3.0
            max_gx = max(p0[0], p1[0]) + hw + 3.0
            min_gz = min(p0[1], p1[1]) - hw - 3.0
            max_gz = max(p0[1], p1[1]) + hw + 3.0
            c_x0 = int(math.floor(min_gx / cell_size))
            c_x1 = int(math.floor(max_gx / cell_size))
            c_z0 = int(math.floor(min_gz / cell_size))
            c_z1 = int(math.floor(max_gz / cell_size))
            seg_entry = (h_idx, p0[0], p0[1], p1[0], p1[1], fwd, seg_len, hw, is_ow, is_tun)
            for cx in range(c_x0, c_x1 + 1):
                for cz in range(c_z0, c_z1 + 1):
                    road_spatial_grid[(cx, cz)].append(seg_entry)

    for h_idx, item in enumerate(processed_highways):
        pts_m = item[0]
        road_w = item[1]
        tags = item[2]
        _add_road_to_grid(h_idx, pts_m, road_w, tags, is_tun=False)

    if tunnel_highways:
        for t_idx, item in enumerate(tunnel_highways):
            pts_m = item[0]
            road_w = item[1]
            tags = item[2]
            _add_road_to_grid(1000000 + t_idx, pts_m, road_w, tags, is_tun=True)

    return road_spatial_grid


class RoadSpatialIndex:
    """Fast spatial index for querying proximity to road segments."""
    def __init__(self, highway_pts_m: List[List[Tuple[float, float]]], cell_size: float = 40.0):
        self.cell_size = cell_size
        self.grid = {}
        for pts in highway_pts_m:
            for i in range(len(pts) - 1):
                p0_x, p0_z = pts[i]
                p1_x, p1_z = pts[i+1]
                min_x = min(p0_x, p1_x) - 7.0
                max_x = max(p0_x, p1_x) + 7.0
                min_z = min(p0_z, p1_z) - 7.0
                max_z = max(p0_z, p1_z) + 7.0
                c_x0, c_x1 = int(min_x // cell_size), int(max_x // cell_size)
                c_z0, c_z1 = int(min_z // cell_size), int(max_z // cell_size)
                seg = (p0_x, p0_z, p1_x, p1_z)
                for cx in range(c_x0, c_x1 + 1):
                    for cz in range(c_z0, c_z1 + 1):
                        key = (cx, cz)
                        if key not in self.grid:
                            self.grid[key] = []
                        self.grid[key].append(seg)

    def is_near(self, x: float, z: float, threshold: float = 6.0) -> bool:
        cell = (int(x // self.cell_size), int(z // self.cell_size))
        candidates = self.grid.get(cell, [])
        for ax, az, bx, bz in candidates:
            if _point_to_segment_dist(x, z, ax, az, bx, bz) < threshold:
                return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. GENERACIÓN DE ASFALTO, SEÑALIZACIÓN MULTICARRIL Y BANQUETAS
# ─────────────────────────────────────────────────────────────────────────────

def is_inner_sidewalk(
    sw_x: float,
    sw_z: float,
    cur_h_idx: int,
    cur_mid_x: float,
    cur_mid_z: float,
    cur_fwd: Tuple[float, float],
    cur_is_oneway: bool,
    road_spatial_grid: Dict[Tuple[int, int], List[Any]],
    trench_spatial: Optional[Dict[Tuple[int, int], List[Any]]] = None,
    trench_cell_size: float = 100.0,
    road_grid_cell: float = 30.0
) -> bool:
    """
    Checks if a candidate sidewalk point lies in an internal median (camellón)
    or within an open underpass trench / retaining wall.
    """
    if trench_spatial:
        tcx = int(sw_x // trench_cell_size)
        tcz = int(sw_z // trench_cell_size)
        for cand in trench_spatial.get((tcx, tcz), []):
            poly = cand[5]
            if is_point_in_quad(sw_x, sw_z, poly):
                return True
            for vi in range(4):
                v0 = poly[vi]; v1 = poly[(vi + 1) % 4]
                edx = v1[0] - v0[0]; edz = v1[1] - v0[1]
                el2 = edx * edx + edz * edz
                if el2 > 1e-6:
                    et = max(0.0, min(1.0, ((sw_x - v0[0]) * edx + (sw_z - v0[1]) * edz) / el2))
                    if math.hypot(sw_x - (v0[0] + et * edx), sw_z - (v0[1] + et * edz)) < 2.5:
                        return True

    to_sw_x = sw_x - cur_mid_x
    to_sw_z = sw_z - cur_mid_z
    to_sw_len = math.hypot(to_sw_x, to_sw_z)
    if to_sw_len > 1e-4:
        sw_dir_x = to_sw_x / to_sw_len
        sw_dir_z = to_sw_z / to_sw_len
    else:
        sw_dir_x, sw_dir_z = 0.0, 0.0

    cx = int(math.floor(sw_x / road_grid_cell))
    cz = int(math.floor(sw_z / road_grid_cell))
    seen_segs = set()

    for dcx in (-1, 0, 1):
        for dcz in (-1, 0, 1):
            items = road_spatial_grid.get((cx + dcx, cz + dcz), [])
            for seg_entry in items:
                s_id = id(seg_entry)
                if s_id in seen_segs:
                    continue
                seen_segs.add(s_id)

                oh_idx, ax, az, bx, bz, o_fwd, o_len, ohw, o_is_ow, o_is_tun = seg_entry
                if oh_idx == cur_h_idx:
                    continue

                dx_ab = bx - ax; dz_ab = bz - az
                l2 = o_len * o_len
                if l2 < 1e-6:
                    continue

                # Proyección del punto de banqueta sobre la otra calzada
                t_sw = max(0.0, min(1.0, ((sw_x - ax) * dx_ab + (sw_z - az) * dz_ab) / l2))
                d_sw = math.hypot(sw_x - (ax + t_sw * dx_ab), sw_z - (az + t_sw * dz_ab))
                if d_sw < (ohw + 0.20):
                    return True

                # Proyección del centro de la calzada actual sobre la otra calzada
                t_mid = max(0.0, min(1.0, ((cur_mid_x - ax) * dx_ab + (cur_mid_z - az) * dz_ab) / l2))
                proj_mid_x = ax + t_mid * dx_ab
                proj_mid_z = az + t_mid * dz_ab
                d_mid = math.hypot(cur_mid_x - proj_mid_x, cur_mid_z - proj_mid_z)

                to_other_x = proj_mid_x - cur_mid_x
                to_other_z = proj_mid_z - cur_mid_z
                dot_side = sw_dir_x * to_other_x + sw_dir_z * to_other_z

                # Si está junto a un paso a desnivel/túnel (< 22m) y la banqueta mira hacia el túnel: suprimir
                if o_is_tun and d_mid < 22.0 and dot_side > 0.3:
                    return True

                # Si es una avenida dividida (carriles paralelos/antiparalelos con camellón < 18m)
                dot_fwd = cur_fwd[0] * o_fwd[0] + cur_fwd[1] * o_fwd[1]
                if abs(dot_fwd) > 0.65 and d_mid < 18.0:
                    if cur_is_oneway or o_is_ow or (d_mid < 14.0):
                        if dot_side > 0.4:
                            return True

    return False

# Backward-compatibility alias
_is_inner_sidewalk = is_inner_sidewalk


def generate_road_and_sidewalk_mesh(
    processed_highways: List[Tuple[List[Tuple[float, float]], float, Dict[str, Any], bool]],
    mesh_grid: Any,
    road_spatial_grid: Dict[Tuple[int, int], List[Any]],
    trench_spatial: Optional[Dict[Tuple[int, int], List[Any]]] = None,
    road_clearance: float = 0.12,
    trench_cell_size: float = 100.0,
    road_grid_cell: float = 30.0
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float], Tuple[float, float, float, float], float]]:
    """
    Generates 3D mesh vertices for asphalt pavement, horizontal SCT lane markings
    (dashed white for one-ways, solid yellow for two-ways), curb sidewalls,
    and continuous sidewalks with end caps and median suppression.
    Returns:
        List of vertex tuples: ((x, y, z), norm, uv, col, em)
    """
    norm_up = (0.0, 1.0, 0.0)
    asphalt_col = (0.22, 0.22, 0.24, 0.95)
    curb_col = (0.45, 0.45, 0.46, 0.95)
    all_vertices = []

    for h_idx, (pts_m, road_w, tags, has_sw) in enumerate(processed_highways):
        half_w = road_w * 0.5
        is_oneway = (tags.get('oneway') == 'yes' or tags.get('junction') == 'roundabout' or 'link' in tags.get('highway', ''))
        K = len(pts_m) - 1
        if K < 1:
            continue

        seg_normals, vtx_normals, seg_fwd = compute_highway_miter_normals(pts_m)
        target_step = 5.5 if has_sw else 12.0

        road_subsegments = []
        for i in range(K):
            p0 = pts_m[i]; p1 = pts_m[i+1]
            dx_r = p1[0] - p0[0]; dz_r = p1[1] - p0[1]
            rlen = math.hypot(dx_r, dz_r)
            if rlen < 0.1:
                continue

            sub_steps = max(1, int(math.ceil(rlen / target_step)))
            step_len = rlen / sub_steps
            nv0 = vtx_normals[i]; nv1 = vtx_normals[i+1]
            fwd = seg_fwd[i]

            for s in range(sub_steps):
                t_start = s / float(sub_steps); t_end = (s + 1) / float(sub_steps)
                sp0_x = p0[0] + t_start * dx_r; sp0_z = p0[1] + t_start * dz_r
                sp1_x = p0[0] + t_end * dx_r; sp1_z = p0[1] + t_end * dz_r

                mid_x = (sp0_x + sp1_x) * 0.5
                mid_z = (sp0_z + sp1_z) * 0.5
                if trench_spatial:
                    in_trench = False
                    sample_pts = (
                        (0.75 * sp0_x + 0.25 * sp1_x, 0.75 * sp0_z + 0.25 * sp1_z),
                        (mid_x, mid_z),
                        (0.25 * sp0_x + 0.75 * sp1_x, 0.25 * sp0_z + 0.75 * sp1_z),
                    )
                    for pt_x, pt_z in sample_pts:
                        tcx = int(pt_x // trench_cell_size)
                        tcz = int(pt_z // trench_cell_size)
                        for cand in trench_spatial.get((tcx, tcz), []):
                            if cand[1] <= pt_x <= cand[3] and cand[2] <= pt_z <= cand[4]:
                                if is_point_in_quad(pt_x, pt_z, cand[5]):
                                    in_trench = True
                                    break
                        if in_trench:
                            break
                    if in_trench:
                        continue

                nx0 = (1.0 - t_start) * nv0[0] + t_start * nv1[0]
                nz0 = (1.0 - t_start) * nv0[1] + t_start * nv1[1]
                nx1 = (1.0 - t_end) * nv0[0] + t_end * nv1[0]
                nz1 = (1.0 - t_end) * nv0[1] + t_end * nv1[1]

                y0 = mesh_grid.get_mesh_height(sp0_x, sp0_z) + road_clearance
                y1 = mesh_grid.get_mesh_height(sp1_x, sp1_z) + road_clearance

                gen_r = False
                gen_l = False
                if has_sw:
                    mid_nx = (nx0 + nx1) * 0.5
                    mid_nz = (nz0 + nz1) * 0.5
                    sw_offset = half_w + 0.80
                    r_mid_x = mid_x + sw_offset * mid_nx
                    r_mid_z = mid_z + sw_offset * mid_nz
                    gen_r = not is_inner_sidewalk(
                        r_mid_x, r_mid_z, h_idx, mid_x, mid_z, fwd, is_oneway,
                        road_spatial_grid, trench_spatial, trench_cell_size, road_grid_cell
                    )

                    l_mid_x = mid_x - sw_offset * mid_nx
                    l_mid_z = mid_z - sw_offset * mid_nz
                    gen_l = not is_inner_sidewalk(
                        l_mid_x, l_mid_z, h_idx, mid_x, mid_z, fwd, is_oneway,
                        road_spatial_grid, trench_spatial, trench_cell_size, road_grid_cell
                    )

                road_subsegments.append({
                    'sp0': (sp0_x, sp0_z), 'sp1': (sp1_x, sp1_z),
                    'y0': y0, 'y1': y1,
                    'n0': (nx0, nz0), 'n1': (nx1, nz1),
                    'fwd': fwd, 'step_len': step_len,
                    'gen_r': gen_r, 'gen_l': gen_l
                })

        num_sub = len(road_subsegments)
        if num_sub == 0:
            continue

        # Filtrar stubs aislados de banqueta (< 2 subsegmentos consecutivos, aprox < 8m)
        for side_key in ('gen_r', 'gen_l'):
            runs = []
            cur_run = []
            for s_idx, seg in enumerate(road_subsegments):
                if seg[side_key]:
                    cur_run.append(s_idx)
                else:
                    if cur_run:
                        runs.append(cur_run)
                        cur_run = []
            if cur_run:
                runs.append(cur_run)
            for run in runs:
                if len(run) < 2:
                    for s_idx in run:
                        road_subsegments[s_idx][side_key] = False

        # Generar geometría de asfalto y señalización
        htype = tags.get('highway', '')
        is_arterial_marking = (htype in ('motorway', 'trunk', 'primary', 'secondary') and half_w >= 3.8)
        accum_dist = 0.0

        for s_idx, seg in enumerate(road_subsegments):
            sp0_x, sp0_z = seg['sp0']
            sp1_x, sp1_z = seg['sp1']
            y0, y1 = seg['y0'], seg['y1']
            nx0, nz0 = seg['n0']
            nx1, nz1 = seg['n1']
            step_len = seg['step_len']

            # Asfalto de la calzada
            q0 = (sp0_x - half_w * nx0, y0, sp0_z - half_w * nz0)
            q1 = (sp0_x + half_w * nx0, y0, sp0_z + half_w * nz0)
            q2 = (sp1_x + half_w * nx1, y1, sp1_z + half_w * nz1)
            q3 = (sp1_x - half_w * nx1, y1, sp1_z - half_w * nz1)

            all_vertices.append((q0, norm_up, (0, 0), asphalt_col, 0.0))
            all_vertices.append((q1, norm_up, (0, 0), asphalt_col, 0.0))
            all_vertices.append((q2, norm_up, (0, 0), asphalt_col, 0.0))
            all_vertices.append((q0, norm_up, (0, 0), asphalt_col, 0.0))
            all_vertices.append((q2, norm_up, (0, 0), asphalt_col, 0.0))
            all_vertices.append((q3, norm_up, (0, 0), asphalt_col, 0.0))

            # Señalización horizontal en vías primarias/arteriales
            if is_arterial_marking:
                stripe_y0 = y0 + 0.025
                stripe_y1 = y1 + 0.025
                col_yellow = (0.92, 0.82, 0.12, 0.95)
                col_white  = (0.95, 0.95, 0.95, 0.95)
                mid_d = accum_dist + 0.5 * step_len

                if is_oneway:
                    # Línea discontinua blanca entre carriles (3m pintura / 3m espacio)
                    num_lanes = 3 if road_w >= 10.5 else (2 if road_w >= 7.0 else 1)
                    if (mid_d % 6.0) < 3.0:
                        hw_dash = 0.06
                        for lane_idx in range(1, num_lanes):
                            frac = lane_idx / float(num_lanes)
                            lane_off = -half_w + frac * road_w
                            d0 = (sp0_x + (lane_off - hw_dash) * nx0, stripe_y0, sp0_z + (lane_off - hw_dash) * nz0)
                            d1 = (sp0_x + (lane_off + hw_dash) * nx0, stripe_y0, sp0_z + (lane_off + hw_dash) * nz0)
                            d2 = (sp1_x + (lane_off + hw_dash) * nx1, stripe_y1, sp1_z + (lane_off + hw_dash) * nz1)
                            d3 = (sp1_x + (lane_off - hw_dash) * nx1, stripe_y1, sp1_z + (lane_off - hw_dash) * nz1)
                            all_vertices.append((d0, norm_up, (0.0, 0.0), col_white, 0.0))
                            all_vertices.append((d1, norm_up, (1.0, 0.0), col_white, 0.0))
                            all_vertices.append((d2, norm_up, (1.0, 1.0), col_white, 0.0))
                            all_vertices.append((d0, norm_up, (0.0, 0.0), col_white, 0.0))
                            all_vertices.append((d2, norm_up, (1.0, 1.0), col_white, 0.0))
                            all_vertices.append((d3, norm_up, (0.0, 1.0), col_white, 0.0))
                else:
                    # Doble sentido: Línea continua amarilla central
                    hw_yellow = 0.08
                    y0_line = (sp0_x - hw_yellow * nx0, stripe_y0, sp0_z - hw_yellow * nz0)
                    y1_line = (sp0_x + hw_yellow * nx0, stripe_y0, sp0_z + hw_yellow * nz0)
                    y2_line = (sp1_x + hw_yellow * nx1, stripe_y1, sp1_z + hw_yellow * nz1)
                    y3_line = (sp1_x - hw_yellow * nx1, stripe_y1, sp1_z - hw_yellow * nz1)
                    all_vertices.append((y0_line, norm_up, (0.0, 0.0), col_yellow, 0.0))
                    all_vertices.append((y1_line, norm_up, (1.0, 0.0), col_yellow, 0.0))
                    all_vertices.append((y2_line, norm_up, (1.0, 1.0), col_yellow, 0.0))
                    all_vertices.append((y0_line, norm_up, (0.0, 0.0), col_yellow, 0.0))
                    all_vertices.append((y2_line, norm_up, (1.0, 1.0), col_yellow, 0.0))
                    all_vertices.append((y3_line, norm_up, (0.0, 1.0), col_yellow, 0.0))

            accum_dist += step_len

            # Guarnición / Borde lateral
            base_y0 = y0 - road_clearance; base_y1 = y1 - road_clearance
            b_r0 = (q1[0], base_y0, q1[2]); b_r1 = (q2[0], base_y1, q2[2])
            avg_nx = 0.5 * (nx0 + nx1); avg_nz = 0.5 * (nz0 + nz1)
            norm_r_side = (avg_nx, 0.0, avg_nz)
            norm_l_side = (-avg_nx, 0.0, -avg_nz)

            all_vertices.append((q1, norm_r_side, (0, 0), curb_col, 0.0))
            all_vertices.append((b_r0, norm_r_side, (0, 0), curb_col, 0.0))
            all_vertices.append((b_r1, norm_r_side, (0, 0), curb_col, 0.0))
            all_vertices.append((q1, norm_r_side, (0, 0), curb_col, 0.0))
            all_vertices.append((b_r1, norm_r_side, (0, 0), curb_col, 0.0))
            all_vertices.append((q2, norm_r_side, (0, 0), curb_col, 0.0))

            b_l0 = (q0[0], base_y0, q0[2]); b_l1 = (q3[0], base_y1, q3[2])
            all_vertices.append((q3, norm_l_side, (0, 0), curb_col, 0.0))
            all_vertices.append((b_l1, norm_l_side, (0, 0), curb_col, 0.0))
            all_vertices.append((b_l0, norm_l_side, (0, 0), curb_col, 0.0))
            all_vertices.append((q3, norm_l_side, (0, 0), curb_col, 0.0))
            all_vertices.append((b_l0, norm_l_side, (0, 0), curb_col, 0.0))
            all_vertices.append((q0, norm_l_side, (0, 0), curb_col, 0.0))

            gen_r = seg['gen_r']
            gen_l = seg['gen_l']

            if gen_r or gen_l:
                cap_start_r = gen_r and (s_idx == 0 or not road_subsegments[s_idx - 1]['gen_r'])
                cap_end_r   = gen_r and (s_idx == num_sub - 1 or not road_subsegments[s_idx + 1]['gen_r'])
                cap_start_l = gen_l and (s_idx == 0 or not road_subsegments[s_idx - 1]['gen_l'])
                cap_end_l   = gen_l and (s_idx == num_sub - 1 or not road_subsegments[s_idx + 1]['gen_l'])

                is_corner_r = cap_start_r or cap_end_r or (s_idx <= 1) or (s_idx >= num_sub - 2)
                is_corner_l = cap_start_l or cap_end_l or (s_idx <= 1) or (s_idx >= num_sub - 2)

                sw_verts = make_sidewalk_3d(
                    sp0_x, sp0_z, sp1_x, sp1_z, y0, y1, half_w,
                    norm0=(nx0, nz0), norm1=(nx1, nz1),
                    sidewalk_w=1.60, curb_h=0.15,
                    gen_right=gen_r, gen_left=gen_l,
                    cap_start_r=cap_start_r, cap_end_r=cap_end_r,
                    cap_start_l=cap_start_l, cap_end_l=cap_end_l,
                    fwd_dir=seg['fwd'],
                    is_corner_r=is_corner_r, is_corner_l=is_corner_l
                )
                all_vertices.extend(sw_verts)

    return all_vertices


# ─────────────────────────────────────────────────────────────────────────────
# 4. ESTRUCTURAS ELEVADAS (PUENTES VEHICULARES Y PEATONALES)
# ─────────────────────────────────────────────────────────────────────────────

def generate_bridges_mesh(
    civil_bridges: List[Any],
    pedestrian_bridges: List[Any],
    origin_lat: float,
    origin_lon: float,
    mesh_grid: Any,
    highway_pts_m: Optional[List[List[Tuple[float, float]]]] = None
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float], Tuple[float, float, float, float], float]]:
    """
    Generate 3D meshes for civil vehicular bridges/viaducts and pedestrian overpasses.
    Optionally registers bridge road paths into highway_pts_m for spatial queries.
    Returns:
        List of vertex tuples: ((x, y, z), norm, uv, col, em)
    """
    bridge_vertices = []
    print(f"[Malla Puentes] {len(civil_bridges)} viaductos/puentes vehiculares...")
    for coords, tags, refs in civil_bridges:
        if len(coords) < 2:
            continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        if highway_pts_m is not None:
            highway_pts_m.append(pts_m)
        road_w = 9.0
        if tags.get('highway') in ('primary', 'trunk') or tags.get('bridge') == 'viaduct':
            road_w = 11.5
        layer_lvl = int(tags.get('layer', '1') or 1)
        clearance = 5.5 * max(1, layer_lvl)
        b_verts = make_civil_bridge_3d(pts_m, road_w=road_w, clearance_h=clearance, mesh_grid=mesh_grid)
        bridge_vertices.extend(b_verts)

    print(f"[Malla Puentes] {len(pedestrian_bridges)} puentes peatonales elevados...")
    for coords, tags, refs in pedestrian_bridges:
        if len(coords) < 2:
            continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        p_verts = make_pedestrian_bridge_3d(pts_m, width=2.4, clearance_h=5.4, mesh_grid=mesh_grid)
        bridge_vertices.extend(p_verts)

    return bridge_vertices


# ─────────────────────────────────────────────────────────────────────────────
# 5. ÍNDICES DE NOMENCLATURA VIAL Y CÓDIGOS POSTALES
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_NAMED_GRID: Dict[Tuple[int, int], List[Tuple[float, float, str]]] = {}
_DEFAULT_PC_GRID: Dict[Tuple[int, int], List[Tuple[float, float, str]]] = {}


def build_street_name_index(
    highways: List[Any],
    origin_lat: float,
    origin_lon: float,
    named_cell: float = 60.0
) -> Dict[Tuple[int, int], List[Tuple[float, float, str]]]:
    """Builds spatial grid index of named roads for O(1) street name lookups."""
    named_grid = {}
    for coords, tags, refs in highways:
        if len(coords) < 2:
            continue
        name = tags.get('name')
        if name:
            pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
            for p in pts_m:
                gx, gz = int(p[0] // named_cell), int(p[1] // named_cell)
                k = (gx, gz)
                if k not in named_grid:
                    named_grid[k] = []
                named_grid[k].append((p[0], p[1], name))
    return named_grid


def build_postal_code_index(
    osm_xml: Optional[str],
    origin_lat: float,
    origin_lon: float,
    pc_cell_size: float = 100.0
) -> Dict[Tuple[int, int], List[Tuple[float, float, str]]]:
    """Builds spatial grid index of postal codes parsed from OSM XML (streaming iterparse)."""
    import io
    pc_spatial_grid: Dict[Tuple[int, int], List[Tuple[float, float, str]]] = {}
    if not osm_xml:
        return pc_spatial_grid
    try:
        raw_bytes = osm_xml.encode('utf-8') if isinstance(osm_xml, str) else osm_xml
        for _, elem in ET.iterparse(io.BytesIO(raw_bytes), events=('end',)):
            if elem.tag == 'node':
                pc = None
                for tag in elem.findall('tag'):
                    k = tag.get('k', ''); v = tag.get('v', '')
                    if 'postcode' in k and len(v) == 5 and v.isdigit():
                        pc = v
                        break
                if pc:
                    nlat = float(elem.get('lat')); nlon = float(elem.get('lon'))
                    nx_m, nz_m = geo_to_meters(nlat, nlon, origin_lat, origin_lon)
                    cx_c, cz_c = int(nx_m // pc_cell_size), int(nz_m // pc_cell_size)
                    pc_spatial_grid.setdefault((cx_c, cz_c), []).append((nx_m, nz_m, pc))
            if elem.tag in ('node', 'way', 'relation'):
                elem.clear()
    except Exception as e:
        print(f"[OSM] Error parseando xml para CP: {e}")
    return pc_spatial_grid


def init_street_naming(
    highways: List[Any],
    osm_xml: Optional[str],
    origin_lat: float,
    origin_lon: float,
    named_cell: float = 60.0,
    pc_cell_size: float = 100.0
) -> Tuple[Dict[Tuple[int, int], List[Tuple[float, float, str]]], Dict[Tuple[int, int], List[Tuple[float, float, str]]]]:
    """Initialize global module-level defaults for street naming and postal codes."""
    global _DEFAULT_NAMED_GRID, _DEFAULT_PC_GRID
    _DEFAULT_NAMED_GRID = build_street_name_index(highways, origin_lat, origin_lon, named_cell)
    _DEFAULT_PC_GRID = build_postal_code_index(osm_xml, origin_lat, origin_lon, pc_cell_size)
    return _DEFAULT_NAMED_GRID, _DEFAULT_PC_GRID


def _get_intersection_street_names(
    ix_m: float,
    iz_m: float,
    named_grid: Optional[Dict[Tuple[int, int], List[Tuple[float, float, str]]]] = None,
    max_dist: float = 45.0,
    named_cell: float = 60.0
) -> Tuple[str, str]:
    """Finds up to 2 intersecting or nearest street names at a coordinate."""
    grid = named_grid if named_grid is not None else _DEFAULT_NAMED_GRID
    found = []
    dists = []
    gx, gz = int(ix_m // named_cell), int(iz_m // named_cell)
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for mx, mz, nm in grid.get((gx + dx, gz + dz), []):
                d = math.hypot(ix_m - mx, iz_m - mz)
                if d <= max_dist and nm not in found:
                    found.append(nm)
                    dists.append(d)
    sorted_names = [n for _, n in sorted(zip(dists, found))]
    st1 = sorted_names[0] if len(sorted_names) > 0 else "AVENIDA"
    st2 = sorted_names[1] if len(sorted_names) > 1 else ""
    return st1, st2


def _nearest_street_name(
    ix_m: float,
    iz_m: float,
    named_grid: Optional[Dict[Tuple[int, int], List[Tuple[float, float, str]]]] = None,
    max_dist: float = 45.0,
    named_cell: float = 60.0
) -> str:
    """Finds the nearest street name at a coordinate."""
    st1, _ = _get_intersection_street_names(ix_m, iz_m, named_grid=named_grid, max_dist=max_dist, named_cell=named_cell)
    return st1


def _resolve_zone_and_cp(
    x_m: float,
    z_m: float,
    pc_spatial_grid: Optional[Dict[Tuple[int, int], List[Tuple[float, float, str]]]] = None,
    pc_cell_size: float = 100.0
) -> Tuple[str, str, str]:
    """Resolves postal code, delegación, and colonia for given meter coordinates."""
    grid = pc_spatial_grid if pc_spatial_grid is not None else _DEFAULT_PC_GRID
    cx_c, cz_c = int(x_m // pc_cell_size), int(z_m // pc_cell_size)
    best_d = 1e9
    best_cp = '20000'
    for dx in range(-4, 5):
        for dz in range(-4, 5):
            for px, pz, pc in grid.get((cx_c + dx, cz_c + dz), []):
                d = math.hypot(x_m - px, z_m - pz)
                if d < best_d:
                    best_d = d
                    best_cp = pc
    if best_cp in CP_INFO:
        del_name, col_name = CP_INFO[best_cp]
    elif z_m > 400:
        del_name, col_name = ('DEL. POCITOS', 'ZONA NORTE')
    elif z_m < -500 and x_m < 0:
        del_name, col_name = ('DEL. INSURGENTES', 'ZONA SUR')
    elif z_m < -500 and x_m >= 0:
        del_name, col_name = ('DEL. MORELOS', 'ZONA SURESTE')
    elif x_m > 600:
        del_name, col_name = ('DEL. SANTA ANITA', 'ZONA ORIENTE')
    else:
        del_name, col_name = ('DEL. CENTRO', 'COL. CENTRO')
    return best_cp, del_name, col_name


class StreetNamingSystem:
    """Encapsulated class for managing street naming and postal code lookups."""
    def __init__(self, highways: List[Any], osm_xml: Optional[str], origin_lat: float, origin_lon: float,
                 named_cell: float = 60.0, pc_cell_size: float = 100.0):
        self.named_cell = named_cell
        self.pc_cell_size = pc_cell_size
        self.named_grid = build_street_name_index(highways, origin_lat, origin_lon, named_cell)
        self.pc_spatial_grid = build_postal_code_index(osm_xml, origin_lat, origin_lon, pc_cell_size)

    def get_intersection_street_names(self, ix_m: float, iz_m: float, max_dist: float = 45.0) -> Tuple[str, str]:
        return _get_intersection_street_names(ix_m, iz_m, named_grid=self.named_grid, max_dist=max_dist, named_cell=self.named_cell)

    def nearest_street_name(self, ix_m: float, iz_m: float, max_dist: float = 45.0) -> str:
        return _nearest_street_name(ix_m, iz_m, named_grid=self.named_grid, max_dist=max_dist, named_cell=self.named_cell)

    def resolve_zone_and_cp(self, x_m: float, z_m: float) -> Tuple[str, str, str]:
        return _resolve_zone_and_cp(x_m, z_m, pc_spatial_grid=self.pc_spatial_grid, pc_cell_size=self.pc_cell_size)


# ─────────────────────────────────────────────────────────────────────────────
# 6. ELEMENTOS DE TRÁFICO, SEMÁFOROS Y PROPS URBANOS
# ─────────────────────────────────────────────────────────────────────────────

def _find_nearest_road_segment(
    px: float,
    pz: float,
    road_spatial_grid: Optional[Dict[Tuple[int, int], List[Any]]],
    road_grid_cell: float = 30.0,
    max_dist: float = 20.0
) -> Tuple[Optional[Tuple[float, float]], float]:
    """Finds the unit forward vector and half-width of the closest surface road segment."""
    if not road_spatial_grid:
        return None, 4.0
    rcx = int(math.floor(px / road_grid_cell))
    rcz = int(math.floor(pz / road_grid_cell))
    cell_rad = max(1, int(math.ceil(max_dist / max(1.0, road_grid_cell))))
    best_road_d = max_dist
    best_fwd = None
    best_hw = 4.0
    for dcx in range(-cell_rad, cell_rad + 1):
        for dcz in range(-cell_rad, cell_rad + 1):
            for seg_item in road_spatial_grid.get((rcx + dcx, rcz + dcz), []):
                _, ax, az, bx, bz, fwd, seg_len, hw, _, is_tun = seg_item
                if is_tun or seg_len < 1e-4:
                    continue
                dx_ab = bx - ax
                dz_ab = bz - az
                t = max(0.0, min(1.0, ((px - ax) * dx_ab + (pz - az) * dz_ab) / (seg_len * seg_len)))
                proj_x = ax + t * dx_ab
                proj_z = az + t * dz_ab
                d = math.hypot(px - proj_x, pz - proj_z)
                if d < best_road_d:
                    best_road_d = d
                    best_fwd = fwd
                    best_hw = hw
    return best_fwd, best_hw


def _assign_spatial_intersection(
    sx: float,
    sz: float,
    clusters: List[Dict[str, Any]],
    radius: float = 35.0
) -> Tuple[int, int]:
    """Assigns a signal at (sx, sz) to the closest intersection centroid < radius, or creates a new one."""
    best_cluster = None
    best_dist = radius
    for cluster in clusters:
        d = math.hypot(sx - cluster["cx"], sz - cluster["cz"])
        if d < best_dist:
            best_dist = d
            best_cluster = cluster
    if best_cluster is not None:
        best_cluster["sum_x"] += sx
        best_cluster["sum_z"] += sz
        best_cluster["count"] += 1
        n = best_cluster["count"]
        best_cluster["cx"] = best_cluster["sum_x"] / n
        best_cluster["cz"] = best_cluster["sum_z"] / n
        return best_cluster["id"], n - 1
    new_id = len(clusters)
    clusters.append({
        "id": new_id,
        "cx": sx,
        "cz": sz,
        "sum_x": sx,
        "sum_z": sz,
        "count": 1,
    })
    return new_id, 0


def generate_intersections_and_signals(
    crossings: List[Any],
    traffic_signals: List[Any],
    origin_lat: float,
    origin_lon: float,
    x0: float,
    z0: float,
    x1: float,
    z1: float,
    mesh_grid: Any,
    road_spatial_grid: Dict[Tuple[int, int], List[Any]],
    trench_spatial: Optional[Dict[Tuple[int, int], List[Any]]] = None,
    named_grid: Optional[Dict[Tuple[int, int], List[Tuple[float, float, str]]]] = None,
    base_vertex_offset: int = 0,
    road_clearance: float = 0.12,
    trench_cell_size: float = 100.0,
    road_grid_cell: float = 30.0
) -> Tuple[List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float], Tuple[float, float, float, float], float]], List[Dict[str, Any]]]:
    """
    Generate pedestrian zebra crossings (aligned perpendicularly to roads)
    and traffic signals with green overhead street name signs and dynamic lens metadata.
    Returns:
        vertices: List of 3D vertex tuples
        traffic_metadata: List of signal metadata dicts for traffic cycle animation
    """
    vertices = []
    traffic_metadata = []

    print("[Malla] Cebras...")
    zebra_count = 0
    for lat, lon, tags, nid in crossings:
        cx, cz = geo_to_meters(lat, lon, origin_lat, origin_lon)
        if not (x0 <= cx <= x1 and z0 <= cz <= z1):
            continue

        # Evitar cebras dentro de trincheras de pasos a desnivel
        tcx = int(cx // trench_cell_size)
        tcz = int(cz // trench_cell_size)
        in_trench = False
        if trench_spatial:
            for cand in trench_spatial.get((tcx, tcz), []):
                if is_point_in_quad(cx, cz, cand[5]):
                    in_trench = True
                    break
        if in_trench:
            continue

        # Buscar vía vehicular más cercana para alinear la cebra transversalmente a la calle
        best_fwd, best_hw = _find_nearest_road_segment(
            cx, cz, road_spatial_grid, road_grid_cell=road_grid_cell, max_dist=20.0
        )

        if best_fwd is not None:
            road_dir_angle = math.atan2(best_fwd[1], best_fwd[0])
            r_width = max(6.0, min(16.0, best_hw * 2.0))
        else:
            continue

        gy = mesh_grid.get_mesh_height(cx, cz) + road_clearance
        zebra_verts = make_zebra_crossing_3d(cx, gy, cz, road_dir_angle=road_dir_angle, road_width=r_width)
        vertices.extend(zebra_verts)
        zebra_count += 1
    print(f"[Malla] {zebra_count} pasos de cebra alineados perpendicularmente a las calzadas.")

    print(f"[Malla] {len(traffic_signals)} semáforos con letreros verdes superiores...")
    sig_counter = 0
    inter_clusters = []
    for lat, lon, tags, nid in traffic_signals:
        sx, sz = geo_to_meters(lat, lon, origin_lat, origin_lon)
        if x0 <= sx <= x1 and z0 <= sz <= z1:
            gy = mesh_grid.get_mesh_height(sx, sz) + road_clearance
            inter_id, slot_in_cluster = _assign_spatial_intersection(sx, sz, inter_clusters, radius=35.0)
            best_fwd, _ = _find_nearest_road_segment(
                sx, sz, road_spatial_grid, road_grid_cell=road_grid_cell, max_dist=35.0
            )
            if best_fwd is not None:
                dir_angle = math.atan2(best_fwd[1], best_fwd[0]) % (2.0 * math.pi)
            else:
                dir_angle = (slot_in_cluster % 4) * (math.pi * 0.5)
            phase = 0 if abs(math.cos(dir_angle)) >= abs(math.sin(dir_angle)) else 1
            st_name = _nearest_street_name(sx, sz, named_grid=named_grid)
            global_offset = base_vertex_offset + len(vertices)
            sig_verts, meta = make_traffic_signal_3d(sig_counter, inter_id, phase, sx, gy, sz, dir_angle, street_name=st_name)
            if "lenses" in meta:
                for lens_name in meta["lenses"]:
                    meta["lenses"][lens_name]["start"] += global_offset
            vertices.extend(sig_verts)
            traffic_metadata.append(meta)
            sig_counter += 1

    return vertices, traffic_metadata


def generate_street_props(
    intersections: List[Any],
    traffic_signals: List[Any],
    processed_highways: List[Any],
    civil_bridges: Optional[List[Any]] = None,
    pedestrian_bridges: Optional[List[Any]] = None,
    all_buildings: Optional[List[Dict[str, Any]]] = None,
    origin_lat: float = 21.8807,
    origin_lon: float = -102.2965,
    x0: float = -5000.0,
    z0: float = -5000.0,
    x1: float = 5000.0,
    z1: float = 5000.0,
    mesh_grid: Any = None,
    trench_spatial: Optional[Dict[Tuple[int, int], List[Any]]] = None,
    road_clearance: float = 0.12,
    trench_cell_size: float = 100.0
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float], Tuple[float, float, float, float], float]]:
    """
    Generate NOM SCT octagonal stop signs, municipal fire hydrants,
    perimeter chainlink fences on schools/industrial sites, and bridge safety railings.
    Returns:
        vertices: List of 3D vertex tuples
    """
    vertices = []

    # 1. Señales de ALTO (Stop Signs NOM SCT) en intersecciones
    print("[Malla Señalización] Colocando señales de ALTO (Stop Signs NOM SCT)...")
    stop_sign_count = 0
    signal_positions = [(sx, sz) for sx, sz in [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon, tags, nid in traffic_signals]]
    used_stop_locs = set()
    for in_coord in intersections:
        ix, iz = geo_to_meters(in_coord[0], in_coord[1], origin_lat, origin_lon)
        if not (x0 <= ix <= x1 and z0 <= iz <= z1):
            continue
        if any(math.hypot(ix - sx, iz - sz) < 28.0 for sx, sz in signal_positions):
            continue
        loc_key = (round(ix, -1), round(iz, -1))
        if loc_key in used_stop_locs:
            continue
        used_stop_locs.add(loc_key)

        ss_x = ix + 4.5; ss_z = iz + 4.5
        gy_ss = mesh_grid.get_mesh_height(ss_x, ss_z) + road_clearance
        stop_verts = make_stop_sign_3d(ss_x, gy_ss, ss_z, dir_angle=0.0)
        vertices.extend(stop_verts)
        stop_sign_count += 1
        if stop_sign_count >= 350:
            break
    print(f"[Malla Señalización] {stop_sign_count} señales de ALTO colocadas.")

    # 2. Hidrantes urbanos en banquetas
    print("[Malla Props] Colocando hidrantes urbanos en esquinas de banquetas...")
    hydrant_count = 0
    for h_idx, item in enumerate(processed_highways):
        pts_m = item[0]
        road_w = item[1]
        has_sw = item[3] if len(item) > 3 else True
        if not has_sw or len(pts_m) < 2:
            continue
        if h_idx % 4 != 0:
            continue
        p_start = pts_m[0]
        if not (x0 <= p_start[0] <= x1 and z0 <= p_start[1] <= z1):
            continue
        hx = p_start[0] + (road_w * 0.5 + 0.75)
        hz = p_start[1]
        tcx = int(hx // trench_cell_size)
        tcz = int(hz // trench_cell_size)
        if trench_spatial and any(is_point_in_quad(hx, hz, cand[5]) for cand in trench_spatial.get((tcx, tcz), [])):
            continue
        hy = mesh_grid.get_mesh_height(hx, hz) + road_clearance
        hydrant_verts = make_fire_hydrant_3d(hx, hy, hz)
        vertices.extend(hydrant_verts)
        hydrant_count += 1
        if hydrant_count >= 300:
            break
    print(f"[Malla Props] {hydrant_count} hidrantes urbanos colocados.")

    # 3. Mallas ciclónicas perimetrales en escuelas e industrias
    print("[Malla Herrería] Colocando mallas ciclónicas y barandales...")
    fence_count = 0
    if all_buildings:
        for b in all_buildings:
            cat_str = str(b.get("category") or b.get("type") or "").lower()
            if any(w in cat_str for w in ("school", "escuela", "industrial", "bodega")):
                poly = b.get("polygon", [])
                if len(poly) < 3:
                    continue
                for pi in range(min(2, len(poly) - 1)):
                    pf0 = poly[pi]; pf1 = poly[pi + 1]
                    if not (x0 <= pf0[0] <= x1 and z0 <= pf0[1] <= z1):
                        continue
                    flen = math.hypot(pf1[0] - pf0[0], pf1[1] - pf0[1])
                    if 8.0 <= flen <= 60.0:
                        y_f0 = mesh_grid.get_mesh_height(pf0[0], pf0[1]) + 0.05
                        y_f1 = mesh_grid.get_mesh_height(pf1[0], pf1[1]) + 0.05
                        f_verts = make_chainlink_fence_3d(pf0, pf1, y_f0, y_f1, height=1.80)
                        vertices.extend(f_verts)
                        fence_count += 1
                        if fence_count >= 250:
                            break
                if fence_count >= 250:
                    break

    # 4. Barandales en puentes peatonales
    railing_count = 0
    for coords, tags, refs in (pedestrian_bridges or []):
        if len(coords) < 2:
            continue
        pts_b = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        for bi in range(len(pts_b) - 1):
            bp0 = pts_b[bi]; bp1 = pts_b[bi + 1]
            y_r0 = mesh_grid.get_mesh_height(bp0[0], bp0[1]) + 5.4
            y_r1 = mesh_grid.get_mesh_height(bp1[0], bp1[1]) + 5.4
            r_verts = make_railing_3d(bp0, bp1, y_r0, y_r1, height=1.05)
            vertices.extend(r_verts)
            railing_count += 1

    # 5. Barandales en puentes vehiculares sobre arroyos y desniveles
    for coords, tags, refs in (civil_bridges or [])[:80]:
        if len(coords) < 2:
            continue
        pts_b = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        for bi in range(len(pts_b) - 1):
            bp0 = pts_b[bi]; bp1 = pts_b[bi + 1]
            dx_b = bp1[0] - bp0[0]; dz_b = bp1[1] - bp0[1]
            blen = math.hypot(dx_b, dz_b)
            if blen < 1.0 or blen > 150.0:
                continue
            bnx = -dz_b / blen; bnz = dx_b / blen
            rw = 5.5
            y_r0 = mesh_grid.get_mesh_height(bp0[0], bp0[1]) + road_clearance + 5.5
            y_r1 = mesh_grid.get_mesh_height(bp1[0], bp1[1]) + road_clearance + 5.5
            vertices.extend(make_railing_3d((bp0[0] - bnx*rw, bp0[1] - bnz*rw), (bp1[0] - bnx*rw, bp1[1] - bnz*rw), y_r0, y_r1, height=1.05))
            vertices.extend(make_railing_3d((bp0[0] + bnx*rw, bp0[1] + bnz*rw), (bp1[0] + bnx*rw, bp1[1] + bnz*rw), y_r0, y_r1, height=1.05))
            railing_count += 2

    print(f"[Malla Herrería] {fence_count} tramos de malla ciclónica y {railing_count} barandales colocados.")
    return vertices


def generate_corner_signs_on_facades(
    intersections: List[Any],
    all_buildings: List[Dict[str, Any]],
    mesh_grid: Any,
    origin_lat: float = 21.8807,
    origin_lon: float = -102.2965,
    x0: float = -5000.0,
    z0: float = -5000.0,
    x1: float = 5000.0,
    z1: float = 5000.0,
    named_grid: Optional[Dict[Tuple[int, int], List[Tuple[float, float, str]]]] = None,
    pc_spatial_grid: Optional[Dict[Tuple[int, int], List[Tuple[float, float, str]]]] = None,
    road_clearance: float = 0.12,
    corner_cell_size: float = 30.0,
    max_signs: int = 1500
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float], Tuple[float, float, float, float], float]]:
    """
    Finds real building corners facing street intersections and mounts dual nomenclature
    corner street signs on building facades with real Aguascalientes names, CP and Delegación.
    Returns:
        vertices: List of 3D vertex tuples
    """
    bldg_corner_grid = {}
    for b in all_buildings:
        poly = b.get("polygon") or []
        n = len(poly)
        if n < 3:
            continue
        bh = b.get("height", 5.0)
        if bh < 2.4:
            continue
        cx_b = sum(p[0] for p in poly) / n
        cz_b = sum(p[1] for p in poly) / n
        for i in range(n):
            p0 = poly[(i - 1) % n]
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            dx1, dz1 = p0[0] - p1[0], p0[1] - p1[1]
            l1 = math.hypot(dx1, dz1)
            dx2, dz2 = p2[0] - p1[0], p2[1] - p1[1]
            l2 = math.hypot(dx2, dz2)
            if l1 < 1.2 or l2 < 1.2:
                continue
            w1 = (dx1 / l1, dz1 / l1)
            n1 = (-w1[1], w1[0])
            if n1[0] * (p1[0] - cx_b) + n1[1] * (p1[1] - cz_b) < 0:
                n1 = (-n1[0], -n1[1])
            w2 = (dx2 / l2, dz2 / l2)
            n2 = (w2[1], -w2[0])
            if n2[0] * (p1[0] - cx_b) + n2[1] * (p1[1] - cz_b) < 0:
                n2 = (-n2[0], -n2[1])
            gx, gz = int(p1[0] // corner_cell_size), int(p1[1] // corner_cell_size)
            key = (gx, gz)
            if key not in bldg_corner_grid:
                bldg_corner_grid[key] = []
            bldg_corner_grid[key].append((p1, w1, n1, w2, n2, bh, (cx_b, cz_b)))

    used_corners = set()
    corner_sign_count = 0
    all_vertices = []

    for ix, (ilat, ilon) in enumerate(intersections):
        if corner_sign_count >= max_signs:
            break
        ix_m, iz_m = geo_to_meters(ilat, ilon, origin_lat, origin_lon)
        if not (x0 <= ix_m <= x1 and z0 <= iz_m <= z1):
            continue
        gx, gz = int(ix_m // corner_cell_size), int(iz_m // corner_cell_size)
        best = None
        best_d = 1e9
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for item in bldg_corner_grid.get((gx + dx, gz + dz), []):
                    p1, w1, n1, w2, n2, bh, centroid = item
                    c_id = (round(p1[0], 1), round(p1[1], 1))
                    if c_id in used_corners:
                        continue
                    d = math.hypot(p1[0] - ix_m, p1[1] - iz_m)
                    if 5.0 <= d <= 18.0 and d < best_d:
                        to_int = (ix_m - p1[0], iz_m - p1[1])
                        if (to_int[0] * n1[0] + to_int[1] * n1[1] > 0) or (to_int[0] * n2[0] + to_int[1] * n2[1] > 0):
                            best_d = d
                            best = item
        if best:
            p1, w1, n1, w2, n2, bh, centroid = best
            c_id = (round(p1[0], 1), round(p1[1], 1))
            used_corners.add(c_id)
            igy = mesh_grid.get_mesh_height(p1[0], p1[1]) + road_clearance
            st_name1, st_name2 = _get_intersection_street_names(ix_m, iz_m, named_grid=named_grid)
            cp, delegacion, colonia = _resolve_zone_and_cp(ix_m, iz_m, pc_spatial_grid=pc_spatial_grid)
            corner_verts = make_corner_street_signs_on_facade(
                p1[0], p1[1], igy, w1, n1, w2, n2,
                name1=st_name1, name2=st_name2, bldg_height=bh,
                cp=cp, delegacion=delegacion, colonia=colonia
            )
            all_vertices.extend(corner_verts)
            corner_sign_count += 1

    print(f"[Malla] {corner_sign_count} placas de nomenclatura montadas en esquinas de casas con Nombres, CP y Delegación reales.")
    return all_vertices
