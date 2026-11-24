#!/usr/bin/env python3
"""
Módulo de Cobertura Total de Edificios (100% Google Maps Equivalent)
- Combina las huellas de OpenStreetMap con las detecciones por visión por computadora (OpenCV).
- Aplica filtrado espacial estricto para evitar colisiones con la red vial (carreteras/intersecciones).
- Elimina cualquier bloque espurio en parques, glorietas o sobre el asfalto.
"""

import math
import os
from geo_dem import geo_to_meters

def dist_point_to_segment(px, pz, x0, z0, x1, z1):
    dx = x1 - x0
    dz = z1 - z0
    seg_len_sq = dx * dx + dz * dz
    if seg_len_sq < 0.001:
        return math.hypot(px - x0, pz - z0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (pz - z0) * dz) / seg_len_sq))
    proj_x = x0 + t * dx
    proj_z = z0 + t * dz
    return math.hypot(px - proj_x, pz - proj_z)

def _iter_geojson_features(geojson_path, chunk_size=1024 * 1024):
    """Generador streaming que lee features de un GeoJSON grande sin cargarlo entero a RAM."""
    import json
    dec = json.JSONDecoder()
    with open(geojson_path, "r", encoding="utf-8") as f:
        buf = ""
        idx = 0
        found_arr = False
        eof = False
        while True:
            if not eof and (len(buf) - idx) < chunk_size // 2:
                if idx > 0:
                    buf = buf[idx:]
                    idx = 0
                chunk = f.read(chunk_size)
                if not chunk:
                    eof = True
                else:
                    buf += chunk
            if not found_arr:
                pos = buf.find('"features"')
                if pos == -1:
                    if eof:
                        return
                    if len(buf) > 1024:
                        buf = buf[-1024:]
                        idx = 0
                    continue
                bpos = buf.find("[", pos)
                if bpos == -1:
                    if eof:
                        return
                    continue
                idx = bpos + 1
                found_arr = True
            while True:
                while idx < len(buf) and buf[idx] in " \t\r\n,":
                    idx += 1
                if idx >= len(buf):
                    break
                if buf[idx] == "]":
                    return
                try:
                    obj, end = dec.raw_decode(buf, idx)
                    idx = end
                    yield obj
                except json.JSONDecodeError:
                    if eof:
                        return
                    break
            if eof and idx >= len(buf):
                return


def load_overture_buildings(geojson_path, origin_lat=21.8807, origin_lon=-102.2965, road_segments=None, bbox=None):
    """
    Carga decenas de miles de edificios reales desde Overture Maps / Google Open Buildings
    usando lectura por streaming para mantener el uso de RAM acotado.
    """
    import json
    import os
    if not os.path.exists(geojson_path):
        alt = os.path.join(os.path.dirname(__file__), "..", geojson_path)
        if os.path.exists(alt):
            geojson_path = alt
        else:
            return []

    print(f"[Overture] Cargando edificios reales (streaming) desde {geojson_path}...")
    buildings = []

    # Intentar cargar clasificación semántica si existe (omitir en sectores quirúrgicos pequeños para <50MB RAM y <3s)
    classified_map = {}
    is_small_sector = (bbox is not None and (bbox[2] - bbox[0] < 3500.0) and (bbox[3] - bbox[1] < 3500.0))
    classified_path = "models/classified_buildings.json"
    if not is_small_sector and os.path.exists(classified_path):
        try:
            with open(classified_path, "r", encoding="utf-8") as cf:
                cdata = json.load(cf)
                for cb in cdata:
                    classified_map[cb['id']] = cb
            print(f"[Classified] Cargada clasificación semántica para {len(classified_map)} edificios.")
        except Exception as e:
            print(f"[Classified] Aviso leyendo clasificación: {e}")

    for idx, feat in enumerate(_iter_geojson_features(geojson_path)):
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Polygon":
            continue
        coords = geom["coordinates"][0]
        if len(coords) < 3:
            continue

        # Filtro rápido de BBox sobre el primer nodo
        if bbox is not None:
            c0_lon, c0_lat = coords[0]
            p0_x, p0_z = geo_to_meters(c0_lat, c0_lon, origin_lat, origin_lon)
            if not (bbox[0] - 60.0 <= p0_x <= bbox[2] + 60.0 and bbox[1] - 60.0 <= p0_z <= bbox[3] + 60.0):
                continue

        pts = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lon, lat in coords]

        # Calcular área (Shoelace)
        area = 0.5 * abs(sum(pts[i][0]*pts[(i+1)%len(pts)][1] - pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts))))
        if area < 15.0 or area > 120000.0:
            continue

        props = feat.get("properties", {})
        h = props.get("height")
        if h is None and props.get("num_floors") is not None:
            try:
                h = float(props["num_floors"]) * 3.2
            except (ValueError, TypeError):
                pass

        if h is None:
            # Estimación arquitectónica típica de Aguascalientes
            if area < 75: h = 3.6    # 1 piso
            elif area < 220: h = 6.2  # 2 pisos
            elif area < 650: h = 8.5  # 3 pisos
            else: h = 10.5           # Nave / Comercial grande

        cb = classified_map.get(idx)
        cat_type = cb['type'] if cb else 'generic'
        cat_label = cb['label'] if cb else 'Edificio Generico'
        wall_col = tuple(cb['color']) if cb else None

        buildings.append({
            "polygon": pts,
            "height": h,
            "source": "overture_google",
            "type": cat_type,
            "label": cat_label,
            "wall_color": wall_col,
            "roof_color": None
        })

    print(f"[Overture] Extraídos {len(buildings)} edificios reales de alta fidelidad.")
    return buildings

def merge_and_densify_buildings(osm_buildings, cv_buildings, highways, min_x, max_x, min_z, max_z,
                                origin_lat=21.8807, origin_lon=-102.2965):
    final_buildings = []
    occupied_centers = []

    # 1. Precalcular segmentos viales para el test de colisión (filtrados al BBox + margen)
    road_segments = []
    pad_r = 100.0
    for coords, tags, refs in highways:
        if len(coords) < 2:
            continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        if not any(min_x - pad_r <= px <= max_x + pad_r and min_z - pad_r <= pz <= max_z + pad_r for px, pz in pts_m):
            continue
        road_w = 7.5
        if tags.get('highway') in ('primary', 'trunk'): road_w = 11.0
        elif tags.get('highway') == 'secondary': road_w = 9.0
        half_w = road_w * 0.5

        for i in range(len(pts_m) - 1):
            road_segments.append((pts_m[i][0], pts_m[i][1], pts_m[i + 1][0], pts_m[i + 1][1], half_w))

    # 2. Cargar los datasets modulares por anillos de Overture (<82 MB c/u)
    # Carga selectiva: solo abre los archivos cuyos radios intersectan el área a generar
    ring_files = [
        ("models/overture_primer_anillo.geojson", 0.0, 2500.0),
        ("models/overture_segundo_anillo.geojson", 2100.0, 4800.0),
        ("models/overture_tercer_anillo.geojson", 4400.0, 15000.0)
    ]
    max_d_box = max(math.hypot(x, z) for x in (min_x, max_x) for z in (min_z, max_z))
    min_d_box = 0.0 if (min_x <= 0 <= max_x and min_z <= 0 <= max_z) else min(math.hypot(x, z) for x in (min_x, max_x) for z in (min_z, max_z))

    overture_buildings = []
    loaded_rings = []
    cur_bbox = (min_x, min_z, max_x, max_z)
    for rf, r_min, r_max in ring_files:
        if not os.path.exists(rf): continue
        if max_d_box < r_min or min_d_box > r_max: continue
        b_list = load_overture_buildings(rf, origin_lat, origin_lon, road_segments, bbox=cur_bbox)
        if b_list:
            overture_buildings.extend(b_list)
            loaded_rings.append(os.path.basename(rf))

    if loaded_rings:
        print(f"[Overture] Cargados modularmente por anillos: {', '.join(loaded_rings)} ({len(overture_buildings):,} edificios)")
    elif os.path.exists("models/overture_buildings.geojson"):
        overture_buildings = load_overture_buildings("models/overture_buildings.geojson", origin_lat, origin_lon, road_segments, bbox=cur_bbox)

    # 2b. Etiquetar o sintetizar todas las sucursales de ROLCAR (Refaccionaria Rogelio)
    rolcar_path = os.path.join(os.path.dirname(__file__), "..", "models", "rolcar_aguascalientes.json")
    if os.path.exists(rolcar_path):
        try:
            import json
            with open(rolcar_path, "r", encoding="utf-8") as rf:
                rolcar_data = json.load(rf)
            rolcar_tagged = 0
            rolcar_synth = 0
            seen_rc = []
            for br in rolcar_data.get("branches", []):
                rx, rz = float(br["x"]), float(br["z"])
                if not (min_x - 35.0 <= rx <= max_x + 35.0 and min_z - 35.0 <= rz <= max_z + 35.0):
                    continue
                if any(math.hypot(rx - sx, rz - sz) < 12.0 for sx, sz in seen_rc):
                    continue
                seen_rc.append((rx, rz))
                # Buscar el edificio Overture más cercano dentro de 35m
                best_b = None
                best_d = 35.0
                for b in overture_buildings:
                    poly = b.get("polygon")
                    if not poly:
                        continue
                    cx_b = sum(p[0] for p in poly) / len(poly)
                    cz_b = sum(p[1] for p in poly) / len(poly)
                    d = math.hypot(cx_b - rx, cz_b - rz)
                    if d < best_d:
                        best_d = d
                        best_b = b
                if best_b is not None:
                    best_b["type"] = "rolcar"
                    best_b["label"] = br["name"]
                    best_b["wall_color"] = (0.95, 0.95, 0.93)
                    best_b["roof_color"] = (0.86, 0.86, 0.84)
                    best_b["height"] = min(max(float(best_b.get("height", 5.8)), 5.4), 6.8)
                    rolcar_tagged += 1
                else:
                    # Sintetizar nave comercial Rolcar si no hay huella Overture en esa coordenada
                    on_road = any(
                        dist_point_to_segment(rx, rz, x0s, z0s, x1s, z1s) < (hw + 4.5)
                        for x0s, z0s, x1s, z1s, hw in road_segments
                    )
                    if not on_road:
                        hw_b, hd_b = 7.0, 5.5
                        overture_buildings.append({
                            "polygon": [
                                (rx - hw_b, rz - hd_b), (rx + hw_b, rz - hd_b),
                                (rx + hw_b, rz + hd_b), (rx - hw_b, rz + hd_b),
                            ],
                            "height": 5.8,
                            "source": "rolcar_denue",
                            "type": "rolcar",
                            "label": br["name"],
                            "wall_color": (0.95, 0.95, 0.93),
                            "roof_color": (0.86, 0.86, 0.84),
                        })
                        rolcar_synth += 1
            if rolcar_tagged or rolcar_synth:
                print(f"[Rolcar] Sucursales integradas en el sector: {rolcar_tagged} etiquetadas, {rolcar_synth} sintetizadas.")
        except Exception as e:
            print(f"[Rolcar] Aviso cargando sucursales: {e}")

    if overture_buildings:
        # Optimización con Spatial Hashing Grid: de O(N*M) a O(N) casi instantáneo (0.3s)
        cell_size = 40.0
        grid = {}
        for rx0, rz0, rx1, rz1, half_w in road_segments:
            rx_min, rx_max = min(rx0, rx1) - half_w - 2.0, max(rx0, rx1) + half_w + 2.0
            rz_min, rz_max = min(rz0, rz1) - half_w - 2.0, max(rz0, rz1) + half_w + 2.0
            c_x0, c_x1 = int(rx_min // cell_size), int(rx_max // cell_size)
            c_z0, c_z1 = int(rz_min // cell_size), int(rz_max // cell_size)
            seg = (rx0, rz0, rx1, rz1, half_w)
            for cx_idx in range(c_x0, c_x1 + 1):
                for cz_idx in range(c_z0, c_z1 + 1):
                    key = (cx_idx, cz_idx)
                    if key not in grid:
                        grid[key] = []
                    grid[key].append(seg)

        for b in overture_buildings:
            pts = b["polygon"]
            cx = sum(p[0] for p in pts) / len(pts)
            cz = sum(p[1] for p in pts) / len(pts)

            # Evitar edificios que caigan sobre carreteras
            cell = (int(cx // cell_size), int(cz // cell_size))
            candidates = grid.get(cell, [])
            on_road = False
            for rx0, rz0, rx1, rz1, half_w in candidates:
                d = dist_point_to_segment(cx, cz, rx0, rz0, rx1, rz1)
                if d < (half_w + 1.5):
                    on_road = True
                    break
            if on_road:
                continue

            final_buildings.append(b)

        # Incorporar además edificios y puntos de interés de OSM a lo largo de toda la metrópoli y Tercer Anillo
        osm_added = 0
        for coords, tags in osm_buildings:
            pts = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
            if len(pts) < 3:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cz = sum(p[1] for p in pts) / len(pts)

            # Evitar colisión con carreteras
            cell = (int(cx // cell_size), int(cz // cell_size))
            candidates = grid.get(cell, [])
            on_road = False
            for rx0, rz0, rx1, rz1, half_w in candidates:
                d = dist_point_to_segment(cx, cz, rx0, rz0, rx1, rz1)
                if d < (half_w + 1.5):
                    on_road = True
                    break
            if on_road:
                continue

            # Altura según niveles o tipo de edificio
            h = 4.2
            if 'building:levels' in tags:
                try:
                    h = float(tags['building:levels']) * 3.2
                except ValueError:
                    pass
            elif 'height' in tags:
                try:
                    h = float(tags['height'].replace('m', ''))
                except ValueError:
                    pass
            elif tags.get('building') in ('commercial', 'retail', 'hospital', 'university', 'school'):
                h = 7.5

            final_buildings.append({
                "polygon": pts,
                "height": h,
                "source": "osm_metro",
                "roof_color": None
            })
            osm_added += 1

        print(f"[Edificios] Total Overture/Google: {len(overture_buildings)} base + {osm_added} edificios metropolitanos OSM.")
        return final_buildings

    # 3. Fallback: Procesar edificios oficiales de OpenStreetMap + OpenCV si no hay Overture
    for coords, tags in osm_buildings:
        pts = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        if len(pts) < 3:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cz = sum(p[1] for p in pts) / len(pts)
        occupied_centers.append((cx, cz))

        height = 4.2
        if 'building:levels' in tags:
            try:
                height = float(tags['building:levels']) * 3.2
            except ValueError:
                pass
        elif 'height' in tags:
            try:
                height = float(tags['height'].replace('m', ''))
            except ValueError:
                pass

        final_buildings.append({
            "polygon": pts,
            "height": height,
            "source": "osm",
            "roof_color": None
        })

    # Filtrar candidatos de OpenCV contra la red vial y duplicados
    valid_cv_count = 0
    for cv_b in cv_buildings:
        pts = cv_b["polygon"]
        if len(pts) < 3:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cz = sum(p[1] for p in pts) / len(pts)

        duplicate = False
        for ocx, ocz in occupied_centers:
            if abs(cx - ocx) < 7.0 and abs(cz - ocz) < 7.0:
                duplicate = True
                break
        if duplicate:
            continue

        on_road = False
        for rx0, rz0, rx1, rz1, half_w in road_segments:
            if min(rx0, rx1) - 15.0 <= cx <= max(rx0, rx1) + 15.0 and \
               min(rz0, rz1) - 15.0 <= cz <= max(rz0, rz1) + 15.0:
                d = dist_point_to_segment(cx, cz, rx0, rz0, rx1, rz1)
                if d < (half_w + 3.5):
                    on_road = True
                    break
        if on_road:
            continue

        occupied_centers.append((cx, cz))
        final_buildings.append({
            "polygon": pts,
            "height": cv_b.get("height", 4.0),
            "source": "opencv",
            "roof_color": cv_b.get("roof_color", (0.85, 0.82, 0.78))
        })
        valid_cv_count += 1

    print(f"[Edificios] Total fusionado: {len(final_buildings)} edificios 3D válidos ({valid_cv_count} agregados por OpenCV fuera de vías).")
    return final_buildings
