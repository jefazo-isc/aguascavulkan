#!/usr/bin/env python3
"""
Extracts real-position street utility poles and pole-to-pole cable spans
around all 27 Rolcar branches in Aguascalientes.

1. Scans local OSM XML files (models/osm_tercer_anillo.xml, etc.) for real
   pole/power nodes (power=pole/tower/portal/transformer, man_made=utility_pole,
   highway=street_lamp, and nodes along power=line/minor_line/cable ways) within
   300m of any Rolcar branch (source='osm_real').
2. Where adjacent street corridors have no OSM pole nodes, derives curb-side
   pole positions along the nearest real OSM street ways (offset to sidewalk
   edge, ~35m spacing, within 180m of any Rolcar branch) with
   source='osm_street_curb'.
3. Builds pole-to-pole cable spans connecting consecutive poles along the same
   power line or street curb (max span 55m).
4. Writes models/utility_poles_rolcar.json.
"""

import glob
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from geo_dem import geo_to_meters, meters_to_geo

ORIGIN_LAT = 21.8807
ORIGIN_LON = -102.2965
MACRO_SIZE = 1024.0

OSM_REAL_RADIUS = 300.0
STREET_CURB_RADIUS = 180.0
POLE_SPACING = 35.0
MIN_POLE_SEPARATION = 18.0
MIN_SPAN_LEN = 8.0
MAX_SPAN_LEN = 55.0

ALLOWED_HIGHWAYS = {
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "residential",
    "unclassified",
    "living_street",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}


def road_half_width(hw_type):
    if hw_type in ("primary", "trunk"):
        return 5.5
    if hw_type == "secondary":
        return 4.5
    if hw_type == "tertiary":
        return 4.0
    if hw_type in ("primary_link", "secondary_link", "tertiary_link"):
        return 3.5
    return 3.75


def cable_count_for_highway(hw_type):
    if hw_type in ("trunk", "primary", "secondary"):
        return 4
    return 3


def min_dist_to_branches(x, z, branch_pts):
    best = 1e18
    for bx, bz in branch_pts:
        d = math.hypot(x - bx, z - bz)
        if d < best:
            best = d
    return best


class SpatialGrid:
    def __init__(self, cell_size=25.0):
        self.cell_size = cell_size
        self.cells = {}

    def _key(self, x, z):
        return (int(math.floor(x / self.cell_size)), int(math.floor(z / self.cell_size)))

    def add(self, pid, x, z):
        k = self._key(x, z)
        self.cells.setdefault(k, []).append((pid, x, z))

    def find_nearest(self, x, z, max_dist):
        cx, cz = self._key(x, z)
        r = int(math.ceil(max_dist / self.cell_size))
        best_id = None
        best_d = max_dist
        for dx in range(-r, r + 1):
            for dz in range(-r, r + 1):
                for pid, px, pz in self.cells.get((cx + dx, cz + dz), ()):
                    d = math.hypot(x - px, z - pz)
                    if d < best_d:
                        best_d = d
                        best_id = pid
        return best_id, best_d


def sample_polyline(pts, spacing=POLE_SPACING):
    """Sample points along a 2D polyline at ~spacing meters, returning (x, z, tx, tz)."""
    if len(pts) < 2:
        return []

    # Compute cumulative arc lengths
    cum = [0.0]
    for i in range(1, len(pts)):
        seg_len = math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        cum.append(cum[-1] + seg_len)

    total_len = cum[-1]
    if total_len < 6.0:
        return []

    # Choose sample distances: start slightly inset from intersections (6m)
    inset = min(6.0, total_len * 0.25)
    usable = total_len - 2.0 * inset
    if usable <= 0.0:
        sample_ds = [total_len * 0.5]
    else:
        n_segs = max(1, int(round(usable / spacing)))
        step = usable / n_segs
        sample_ds = [inset + i * step for i in range(n_segs + 1)]

    samples = []
    seg_idx = 0
    for s in sample_ds:
        while seg_idx < len(cum) - 2 and cum[seg_idx + 1] < s:
            seg_idx += 1
        d0 = cum[seg_idx]
        d1 = cum[seg_idx + 1]
        seg_len = d1 - d0
        if seg_len < 1e-6:
            continue
        t = (s - d0) / seg_len
        x0, z0 = pts[seg_idx]
        x1, z1 = pts[seg_idx + 1]
        px = x0 + t * (x1 - x0)
        pz = z0 + t * (z1 - z0)
        tx = (x1 - x0) / seg_len
        tz = (z1 - z0) / seg_len
        samples.append((px, pz, tx, tz))

    return samples


def extract_utility_poles():
    rolcar_path = os.path.join(ROOT, "models", "rolcar_aguascalientes.json")
    out_path = os.path.join(ROOT, "models", "utility_poles_rolcar.json")

    with open(rolcar_path, "r", encoding="utf-8") as f:
        rolcar_data = json.load(f)
    branches = rolcar_data.get("branches", [])

    # Deduplicate branch coordinates (some branches share exact lat/lon)
    branch_pts = []
    for br in branches:
        bx, bz = float(br["x"]), float(br["z"])
        if not any(math.hypot(bx - ox, bz - oz) < 1.0 for ox, oz in branch_pts):
            branch_pts.append((bx, bz))

    # Find all local OSM XML files in models/
    osm_files = sorted(
        set(
            glob.glob(os.path.join(ROOT, "models", "*.xml"))
            + glob.glob(os.path.join(ROOT, "models", "*.osm"))
        )
    )
    if not osm_files:
        raise FileNotFoundError("No local OSM XML files found in models/")

    poles = []
    spans = []
    seen_spans = set()
    grid = SpatialGrid(cell_size=25.0)

    def add_pole(lat, lon, x, z, angle, source, has_transformer):
        pid = len(poles)
        mx = int(math.floor(x / MACRO_SIZE))
        mz = int(math.floor(z / MACRO_SIZE))
        poles.append({
            "id": pid,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "x": round(x, 2),
            "z": round(z, 2),
            "mx": mx,
            "mz": mz,
            "angle": round(angle, 4),
            "source": source,
            "has_transformer": bool(has_transformer),
        })
        grid.add(pid, x, z)
        return pid

    def add_span(a, b, cables):
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        if key in seen_spans:
            return
        pa, pb = poles[a], poles[b]
        dist = math.hypot(pb["x"] - pa["x"], pb["z"] - pa["z"])
        if dist < MIN_SPAN_LEN or dist > MAX_SPAN_LEN:
            return
        seen_spans.add(key)
        mid_x = 0.5 * (pa["x"] + pb["x"])
        mid_z = 0.5 * (pa["z"] + pb["z"])
        spans.append({
            "a": a,
            "b": b,
            "mx": int(math.floor(mid_x / MACRO_SIZE)),
            "mz": int(math.floor(mid_z / MACRO_SIZE)),
            "cables": int(cables),
        })

    osm_node_to_pid = {}
    highway_ways = []

    for osm_file in osm_files:
        tree = ET.parse(osm_file)
        root = tree.getroot()

        nodes = {}
        power_ways = []

        for el in root:
            if el.tag == "node":
                nid = el.attrib["id"]
                lat = float(el.attrib["lat"])
                lon = float(el.attrib["lon"])
                nodes[nid] = (lat, lon)

                tags = {t.attrib["k"]: t.attrib["v"] for t in el.findall("tag")}
                if not tags:
                    continue
                p_tag = tags.get("power")
                mm_tag = tags.get("man_made")
                hw_tag = tags.get("highway")
                if (
                    p_tag in ("pole", "tower", "portal", "transformer")
                    or mm_tag == "utility_pole"
                    or hw_tag == "street_lamp"
                ):
                    x, z = geo_to_meters(lat, lon, ORIGIN_LAT, ORIGIN_LON)
                    if min_dist_to_branches(x, z, branch_pts) <= OSM_REAL_RADIUS:
                        has_xfmr = (p_tag == "transformer") or ("transformer" in tags)
                        pid = add_pole(lat, lon, x, z, 0.0, "osm_real", has_xfmr)
                        osm_node_to_pid[nid] = pid

            elif el.tag == "way":
                tags = {t.attrib["k"]: t.attrib["v"] for t in el.findall("tag")}
                nds = [nd.attrib["ref"] for nd in el.findall("nd")]
                if len(nds) < 2:
                    continue
                if tags.get("power") in ("line", "minor_line", "cable"):
                    power_ways.append((nds, tags))
                hw = tags.get("highway")
                if hw in ALLOWED_HIGHWAYS:
                    highway_ways.append((nds, tags, nodes))

        # Process real OSM power ways
        for nds, tags in power_ways:
            way_pids = []
            cables = 4 if tags.get("power") == "line" else 3
            for i, ref in enumerate(nds):
                if ref not in nodes:
                    continue
                lat, lon = nodes[ref]
                x, z = geo_to_meters(lat, lon, ORIGIN_LAT, ORIGIN_LON)
                if min_dist_to_branches(x, z, branch_pts) > OSM_REAL_RADIUS:
                    way_pids.append(None)
                    continue
                if ref in osm_node_to_pid:
                    pid = osm_node_to_pid[ref]
                else:
                    # Compute tangent angle from neighbor
                    angle = 0.0
                    if i + 1 < len(nds) and nds[i + 1] in nodes:
                        nx, nz = geo_to_meters(*nodes[nds[i + 1]], ORIGIN_LAT, ORIGIN_LON)
                        angle = math.atan2(nz - z, nx - x)
                    elif i > 0 and nds[i - 1] in nodes:
                        px, pz = geo_to_meters(*nodes[nds[i - 1]], ORIGIN_LAT, ORIGIN_LON)
                        angle = math.atan2(z - pz, x - px)
                    pid = add_pole(lat, lon, x, z, angle, "osm_real", False)
                    osm_node_to_pid[ref] = pid
                way_pids.append(pid)

            for i in range(len(way_pids) - 1):
                if way_pids[i] is not None and way_pids[i + 1] is not None:
                    add_span(way_pids[i], way_pids[i + 1], cables)

    # Derive curb-side poles along real OSM street ways near Rolcar branches
    curb_counter = 0
    for nds, tags, nodes in highway_ways:
        pts = []
        near_any = False
        for ref in nds:
            if ref not in nodes:
                continue
            lat, lon = nodes[ref]
            x, z = geo_to_meters(lat, lon, ORIGIN_LAT, ORIGIN_LON)
            pts.append((x, z))
            if not near_any and min_dist_to_branches(x, z, branch_pts) <= STREET_CURB_RADIUS + 40.0:
                near_any = True

        if not near_any or len(pts) < 2:
            continue

        hw_type = tags.get("highway", "residential")
        curb_offset = road_half_width(hw_type) + 1.4
        cables = cable_count_for_highway(hw_type)

        samples = sample_polyline(pts, spacing=POLE_SPACING)
        way_pole_ids = []
        for sx, sz, tx, tz in samples:
            # Right-hand curb normal
            nx, nz = -tz, tx
            px = sx + nx * curb_offset
            pz = sz + nz * curb_offset

            if min_dist_to_branches(px, pz, branch_pts) > STREET_CURB_RADIUS:
                way_pole_ids.append(None)
                continue

            nearest_id, nearest_d = grid.find_nearest(px, pz, MIN_POLE_SEPARATION)
            if nearest_id is not None:
                way_pole_ids.append(nearest_id)
                continue

            lat, lon = meters_to_geo(px, pz, ORIGIN_LAT, ORIGIN_LON)
            angle = math.atan2(tz, tx)
            has_xfmr = (curb_counter % 5 == 2)
            curb_counter += 1
            pid = add_pole(lat, lon, px, pz, angle, "osm_street_curb", has_xfmr)
            way_pole_ids.append(pid)

        for i in range(len(way_pole_ids) - 1):
            a = way_pole_ids[i]
            b = way_pole_ids[i + 1]
            if a is not None and b is not None:
                add_span(a, b, cables)

    payload = {
        "poles": poles,
        "spans": spans,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    n_real = sum(1 for p in poles if p["source"] == "osm_real")
    n_curb = sum(1 for p in poles if p["source"] == "osm_street_curb")
    n_xfmr = sum(1 for p in poles if p["has_transformer"])
    sectors = sorted({(p["mx"], p["mz"]) for p in poles})

    print(f"[UtilityPoles] Wrote {out_path}")
    print(f"[UtilityPoles] Poles: {len(poles)} total (osm_real={n_real}, osm_street_curb={n_curb}, transformers={n_xfmr})")
    print(f"[UtilityPoles] Spans: {len(spans)} total across {len(sectors)} macro-sectors")

    # Verify Paseo de la Cruz (x=971.23, z=776.97, sector 0,0)
    paseo_poles = [
        p for p in poles
        if p["mx"] == 0 and p["mz"] == 0 and math.hypot(p["x"] - 971.23, p["z"] - 776.97) <= 180.0
    ]
    paseo_ids = {p["id"] for p in paseo_poles}
    paseo_spans = [s for s in spans if s["a"] in paseo_ids or s["b"] in paseo_ids]
    print(f"[UtilityPoles] Paseo de la Cruz (sector 0,0 within 180m): {len(paseo_poles)} poles, {len(paseo_spans)} spans")
    for p in sorted(paseo_poles, key=lambda q: math.hypot(q["x"] - 971.23, q["z"] - 776.97))[:5]:
        print(f"  sample pole: {p}")

    return payload


if __name__ == "__main__":
    extract_utility_poles()
