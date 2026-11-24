#!/usr/bin/env python3
"""
generate_road_graph.py - TAREA 3
Genera grafo vial navegable desde models/osm_cache.xml.
Muestra elevación Y desde geo_dem.TerrainElevation.
Exporta road_network.bin en formato RGP1 y guarda PNG top-down de verificación sobre assets/satellite.png.
"""
import os
import sys
import struct
import math
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from geo_dem import geo_to_meters, TerrainElevation, DEFAULT_ORIGIN_LAT, DEFAULT_ORIGIN_LON

SPEED_MAP = {
    'motorway': 25.0,
    'trunk': 19.4,
    'primary': 16.7,
    'secondary': 13.9,
    'tertiary': 11.1,
    'residential': 8.3,
    'unclassified': 8.3,
    'living_street': 5.6,
    'service': 4.2,
    'motorway_link': 16.7,
    'trunk_link': 13.9,
    'primary_link': 11.1,
    'secondary_link': 8.3,
    'tertiary_link': 8.3
}

DRIVEABLE_TYPES = set(SPEED_MAP.keys())

def parse_maxspeed(speed_str):
    if not speed_str:
        return None
    try:
        val = float(speed_str.split()[0])
        return val / 3.6  # km/h to m/s
    except Exception:
        return None

def main():
    osm_file = "models/osm_tercer_anillo.xml"
    if not os.path.exists(osm_file):
        osm_file = "models/osm_cache.xml"
    if not os.path.exists(osm_file):
        print(f"Error: archivo OSM no encontrado")
        sys.exit(1)

    print(f"[RoadGraph] Leyendo {osm_file}...")
    tree = ET.parse(osm_file)
    root = tree.getroot()

    nodes_geo = {}
    signal_nodes = set()
    
    for n in root.findall('node'):
        nid = n.attrib['id']
        lat = float(n.attrib['lat'])
        lon = float(n.attrib['lon'])
        nodes_geo[nid] = (lat, lon)

        tags = {t.attrib['k']: t.attrib.get('v', '') for t in n.findall('tag')}
        if tags.get('highway') == 'traffic_signals':
            signal_nodes.add(nid)

    # Colectar vías manejables
    driveable_ways = []
    node_use_count = {}

    for w in root.findall('way'):
        tags = {t.attrib['k']: t.attrib.get('v', '') for t in w.findall('tag')}
        h_type = tags.get('highway', '')
        
        if h_type not in DRIVEABLE_TYPES:
            continue
            
        refs = [nd.attrib['ref'] for nd in w.findall('nd') if nd.attrib['ref'] in nodes_geo]
        if len(refs) < 2:
            continue

        driveable_ways.append((refs, tags))
        for r in refs:
            node_use_count[r] = node_use_count.get(r, 0) + 1

    # Identificar nodos del grafo (intersecciones >= 2 vías, semáforos, extremos)
    graph_nodes_set = set()
    for refs, tags in driveable_ways:
        graph_nodes_set.add(refs[0])
        graph_nodes_set.add(refs[-1])
        for r in refs:
            if node_use_count.get(r, 0) >= 2 or r in signal_nodes:
                graph_nodes_set.add(r)

    print(f"[RoadGraph] Nodos totales OSM: {len(nodes_geo)}, Nodos del grafo: {len(graph_nodes_set)}")

    # Asignar índices de nodos
    node_id_to_idx = {nid: i for i, nid in enumerate(sorted(graph_nodes_set))}
    idx_to_node_id = {i: nid for nid, i in node_id_to_idx.items()}

    # Inicializar terreno DEM con las mismas cotas que el sector metropolitano y el shader Vulkan
    # Bounding box metropolitano completo (Tercer Anillo):
    min_lat = 21.8000
    max_lat = 21.9500
    min_lon = -102.3700
    max_lon = -102.2450

    terrain = TerrainElevation(min_lat, max_lat, min_lon, max_lon, nx=64, ny=64)
    ROAD_SURFACE_OFFSET = 0.12  # Cota exacta del asfalto (road_clearance = 0.12m) para apoyo perfecto de neumáticos

    # Cargar traffic_signals.json si existe para mapear signal_groups
    signals_json = "models/traffic_signals.json"
    signal_groups_by_pos = []
    if os.path.exists(signals_json):
        import json
        with open(signals_json, "r") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    signal_groups_by_pos.append((data["x"], data["z"], data.get("phase", 0)))
                except Exception:
                    pass

    def find_signal_group(x, z):
        for sx, sz, ph in signal_groups_by_pos:
            if math.hypot(x - sx, z - sz) < 15.0:
                return ph
        return 0

    # Construir lista de nodos
    nodes_data = [] # list of (x, y, z, signal_group, degree)
    node_coords_3d = {}

    for i in range(len(graph_nodes_set)):
        nid = idx_to_node_id[i]
        lat, lon = nodes_geo[nid]
        x, z = geo_to_meters(lat, lon)
        y = terrain.get_real_topography(x, z) + ROAD_SURFACE_OFFSET
        
        has_signal = nid in signal_nodes
        sg = find_signal_group(x, z) if has_signal else -1
        
        node_coords_3d[i] = (x, y, z)
        nodes_data.append([x, y, z, sg, 0]) # degree will be updated

    # Fragmentar vías en aristas entre nodos del grafo
    raw_edges = []
    all_points = []
    
    for refs, tags in driveable_ways:
        h_type = tags.get('highway', 'residential')
        speed_ms = parse_maxspeed(tags.get('maxspeed')) or SPEED_MAP.get(h_type, 8.3)
        
        is_oneway = tags.get('oneway') in ('yes', '1', 'true') or h_type in ('motorway', 'motorway_link')
        lanes_tag = tags.get('lanes')
        if lanes_tag and lanes_tag.isdigit():
            l_num = max(1, int(lanes_tag))
            if is_oneway:
                lanes_fwd, lanes_rev = l_num, 0
            else:
                lanes_fwd = max(1, l_num // 2)
                lanes_rev = max(1, l_num - lanes_fwd)
        else:
            lanes_fwd = 1
            lanes_rev = 0 if is_oneway else 1

        width = float(tags.get('width', 0.0))
        if width <= 0.0:
            width = (lanes_fwd + lanes_rev) * 3.5

        # Detección de puentes elevados y túneles para sincronizar cotas con la malla 3D
        layer_val = 0
        try:
            layer_val = int(tags.get('layer', '0'))
        except (ValueError, TypeError):
            pass
        is_bridge = (tags.get('bridge') in ('yes', 'viaduct', 'cantilever', 'movable')) or (layer_val > 0)
        is_tunnel = (tags.get('tunnel') in ('yes', 'building_passage', 'covered')) or (layer_val < 0)
        bridge_elev = (5.5 * max(1, layer_val)) if is_bridge else 0.0

        if is_tunnel:
            way_meters = [geo_to_meters(nodes_geo[r][0], nodes_geo[r][1]) for r in refs]
            way_dists = [0.0]
            for wi in range(len(way_meters) - 1):
                way_dists.append(way_dists[-1] + math.hypot(way_meters[wi+1][0] - way_meters[wi][0], way_meters[wi+1][1] - way_meters[wi][1]))
            way_total_len = max(1.0, way_dists[-1])
            way_ramp_len = min(70.0, way_total_len * 0.30)

        # Recorrer puntos y dividir en aristas
        curr_start_node = refs[0]
        curr_pts = [nodes_geo[refs[0]]]
        curr_ref_indices = [0]

        for ref_idx, r in enumerate(refs[1:], start=1):
            curr_pts.append(nodes_geo[r])
            curr_ref_indices.append(ref_idx)
            if r in node_id_to_idx:
                # Terminar arista
                u = node_id_to_idx[curr_start_node]
                v = node_id_to_idx[r]

                if u != v and len(curr_pts) >= 2:
                    # Convertir polilínea a 3D con DEM y rasante exacta
                    pts_3d = []
                    if is_tunnel:
                        for pi in range(len(curr_pts) - 1):
                            p0_ll = curr_pts[pi]
                            p1_ll = curr_pts[pi + 1]
                            p0_m = geo_to_meters(p0_ll[0], p0_ll[1])
                            p1_m = geo_to_meters(p1_ll[0], p1_ll[1])
                            seg_len = math.hypot(p1_m[0] - p0_m[0], p1_m[1] - p0_m[1])
                            n_sub = max(1, int(math.ceil(seg_len / 6.0)))
                            d0 = way_dists[curr_ref_indices[pi]]
                            d1 = way_dists[curr_ref_indices[pi + 1]]
                            for s in range(n_sub):
                                t = s / float(n_sub)
                                px = p0_m[0] + t * (p1_m[0] - p0_m[0])
                                pz = p0_m[1] + t * (p1_m[1] - p0_m[1])
                                sd = d0 + t * (d1 - d0)
                                if sd < way_ramp_len:
                                    tr = sd / max(1.0, way_ramp_len)
                                    dip = 0.5 * (1.0 - math.cos(tr * math.pi))
                                elif sd > (way_total_len - way_ramp_len):
                                    tr = (way_total_len - sd) / max(1.0, way_ramp_len)
                                    dip = 0.5 * (1.0 - math.cos(tr * math.pi))
                                else:
                                    dip = 1.0
                                py = terrain.get_real_topography(px, pz) + ROAD_SURFACE_OFFSET - 5.4 * dip
                                pts_3d.append((px, py, pz))
                        # Último punto del tramo
                        p_last_ll = curr_pts[-1]
                        p_last_m = geo_to_meters(p_last_ll[0], p_last_ll[1])
                        d_last = way_dists[curr_ref_indices[-1]]
                        if d_last < way_ramp_len:
                            tr = d_last / max(1.0, way_ramp_len)
                            dip = 0.5 * (1.0 - math.cos(tr * math.pi))
                        elif d_last > (way_total_len - way_ramp_len):
                            tr = (way_total_len - d_last) / max(1.0, way_ramp_len)
                            dip = 0.5 * (1.0 - math.cos(tr * math.pi))
                        else:
                            dip = 1.0
                        py = terrain.get_real_topography(p_last_m[0], p_last_m[1]) + ROAD_SURFACE_OFFSET - 5.4 * dip
                        pts_3d.append((p_last_m[0], py, p_last_m[1]))
                    else:
                        for lat, lon in curr_pts:
                            px, pz = geo_to_meters(lat, lon)
                            py = terrain.get_real_topography(px, pz) + ROAD_SURFACE_OFFSET + bridge_elev
                            pts_3d.append((px, py, pz))

                    raw_edges.append({
                        "a": u, "b": v,
                        "pts": pts_3d,
                        "speed_ms": speed_ms,
                        "width": width,
                        "lanes_fwd": lanes_fwd,
                        "lanes_rev": lanes_rev,
                        "oneway": 1 if is_oneway else 0
                    })
                    nodes_data[u][4] += 1
                    nodes_data[v][4] += 1

                # Reiniciar para siguiente tramo
                curr_start_node = r
                curr_pts = [nodes_geo[r]]
                curr_ref_indices = [ref_idx]

    # Filtrar aristas de < 2 puntos
    valid_edges = [e for e in raw_edges if len(e["pts"]) >= 2]
    print(f"[RoadGraph] Aristas generadas: {len(valid_edges)}")

    # Análisis de componente conexa mayor
    from collections import defaultdict, deque
    adj = defaultdict(list)
    for idx, e in enumerate(valid_edges):
        adj[e["a"]].append((e["b"], idx))
        adj[e["b"]].append((e["a"], idx))

    visited_edges = set()
    components = []

    for idx, e in enumerate(valid_edges):
        if idx in visited_edges:
            continue
        comp_edges = []
        queue = deque([e["a"]])
        visited_nodes_local = {e["a"]}
        
        while queue:
            curr = queue.popleft()
            for nxt, e_idx in adj[curr]:
                if e_idx not in visited_edges:
                    visited_edges.add(e_idx)
                    comp_edges.append(e_idx)
                if nxt not in visited_nodes_local:
                    visited_nodes_local.add(nxt)
                    queue.append(nxt)
        components.append(comp_edges)

    components.sort(key=lambda c: len(c), reverse=True)
    largest_comp = components[0] if components else []
    cov_ratio = len(largest_comp) / len(valid_edges) if valid_edges else 0.0

    print(f"[RoadGraph] Componentes conexas: {len(components)}. La mayor cubre {len(largest_comp)}/{len(valid_edges)} aristas ({cov_ratio*100:.1f}%)")

    # Si hay aristas fuera de la componente principal, conservamos la mayor o mantenemos todas si cov_ratio >= 0.95
    if cov_ratio < 0.95 and largest_comp:
        print("[RoadGraph] ADVERTENCIA: La componente principal es menor al 95%; conservando únicamente la componente conexa mayor.")
        keep = set(largest_comp)
        valid_edges = [e for idx, e in enumerate(valid_edges) if idx in keep]
        for nd in nodes_data:
            nd[4] = 0
        for e in valid_edges:
            nodes_data[e["a"]][4] += 1
            nodes_data[e["b"]][4] += 1

    # Preparar datos finales para binario
    pt_offset = 0
    final_edges = []
    final_points = []

    for e in valid_edges:
        pts = e["pts"]
        e_pt_off = len(final_points)
        e_pt_cnt = len(pts)
        final_points.extend(pts)
        
        final_edges.append({
            "a": e["a"], "b": e["b"],
            "pt_off": e_pt_off, "pt_count": e_pt_cnt,
            "speed_ms": e["speed_ms"], "width": e["width"],
            "lanes_fwd": e["lanes_fwd"], "lanes_rev": e["lanes_rev"],
            "oneway": e["oneway"]
        })

    total_km = sum(
        sum(math.hypot(p2[0]-p1[0], math.hypot(p2[1]-p1[1], p2[2]-p1[2])) 
            for p1, p2 in zip(e["pts"][:-1], e["pts"][1:]))
        for e in valid_edges
    ) / 1000.0

    print(f"[RoadGraph] STATS FINAL:")
    print(f"  - Nodos: {len(nodes_data)}")
    print(f"  - Aristas: {len(final_edges)}")
    print(f"  - Puntos de polilínea: {len(final_points)}")
    print(f"  - Longitud total de vías: {total_km:.2f} km")

    # Escribir binario road_network.bin
    bin_path = "models/road_network.bin"
    with open(bin_path, "wb") as f:
        # Header (16B): char[4]="RGP1", u32 n_nodes, n_edges, n_points
        header = struct.pack("<4sIII", b"RGP1", len(nodes_data), len(final_edges), len(final_points))
        f.write(header)

        # Nodes (20B cada uno): f32 x,y,z; i32 signal_group; u8 degree, pad[3]
        for nd in nodes_data:
            deg = min(255, nd[4])
            node_bytes = struct.pack("<fffiBBBB", nd[0], nd[1], nd[2], nd[3], deg, 0, 0, 0)
            f.write(node_bytes)

        # Edges (28B cada uno): u32 a,b, pt_off, pt_count; f32 speed_ms, width; u8 lanes_fwd, lanes_rev, oneway, pad
        for ed in final_edges:
            edge_bytes = struct.pack("<IIIIffBBBB",
                                     ed["a"], ed["b"], ed["pt_off"], ed["pt_count"],
                                     ed["speed_ms"], ed["width"],
                                     ed["lanes_fwd"], ed["lanes_rev"], ed["oneway"], 0)
            f.write(edge_bytes)

        # Points (12B cada uno): f32 x,y,z
        for pt in final_points:
            pt_bytes = struct.pack("<fff", pt[0], pt[1], pt[2])
            f.write(pt_bytes)

    print(f"[RoadGraph] Binario exportado exitosamente → {bin_path} ({os.path.getsize(bin_path)} bytes)")

    # Visualización top-down PNG sobre assets/satellite.png
    sat_path = "assets/satellite.png"
    img = None
    if os.path.exists(sat_path):
        print(f"[RoadGraph] Generando verificación visual PNG sobre {sat_path}...")
        img = Image.open(sat_path).convert("RGB")
    elif os.path.exists("assets/satellite_0_0.png") and os.path.exists("assets/satellite_1_0.png") and os.path.exists("assets/satellite_0_1.png") and os.path.exists("assets/satellite_1_1.png"):
        print(f"[RoadGraph] Ensamblando ortofoto satelital desde 4 cuadrantes modulares...")
        q00 = Image.open("assets/satellite_0_0.png").convert("RGB")
        q10 = Image.open("assets/satellite_1_0.png").convert("RGB")
        q01 = Image.open("assets/satellite_0_1.png").convert("RGB")
        q11 = Image.open("assets/satellite_1_1.png").convert("RGB")
        qw, qh = q00.size
        img = Image.new("RGB", (qw * 2, qh * 2))
        img.paste(q00, (0, 0))
        img.paste(q10, (qw, 0))
        img.paste(q01, (0, qh))
        img.paste(q11, (qw, qh))

    if img is not None:
        img_w, img_h = img.size
        
        # Rango de coordenadas de satellite.png (usado en generate_sector.py)
        origin_lat = 21.8807; origin_lon = -102.2965
        min_lon = -102.3700; max_lon = -102.2450; min_lat = 21.8000; max_lat = 21.9500
        min_x, max_z = geo_to_meters(min_lat, min_lon, origin_lat, origin_lon)
        max_x, min_z = geo_to_meters(max_lat, max_lon, origin_lat, origin_lon)

        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        def world_to_pixel(wx, wz):
            px = int((wx - min_x) / (max_x - min_x) * img_w)
            py = int((wz - min_z) / (max_z - min_z) * img_h)
            return px, py

        # Dibujar aristas
        for e in valid_edges:
            pts = e["pts"]
            pix_pts = [world_to_pixel(p[0], p[2]) for p in pts]
            color = (0, 100, 255) if e["oneway"] else (0, 230, 80)
            if len(pix_pts) >= 2:
                draw.line(pix_pts, fill=color, width=2)

        # Dibujar nodos de semáforo
        for nd in nodes_data:
            if nd[3] >= 0:
                px, py = world_to_pixel(nd[0], nd[2])
                draw.ellipse([px-4, py-4, px+4, py+4], fill=(255, 0, 0), outline=(255, 255, 255))

        out_png = "models/road_graph_verification.png"
        img.save(out_png)
        print(f"[RoadGraph] Imagen de verificación guardada → {out_png}")

if __name__ == "__main__":
    main()
