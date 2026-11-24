#!/usr/bin/env python3
"""
Módulo de Extracción y Análisis de OpenStreetMap (OSM)
- Descarga y parseo con caché de redes viales, nodos de semáforos, pasos peatonales y edificios.
- Detección topológica de intersecciones viales.
"""

import os
import urllib.request
import xml.etree.ElementTree as ET

def fetch_osm_data(min_lon, min_lat, max_lon, max_lat, cache_file="models/osm_cache.xml"):
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "rb") as f:
                data = f.read()
                if len(data) > 1000:
                    print(f"[OSM] Cargado desde caché local: {cache_file} ({len(data)} bytes)")
                    return data
        except Exception as e:
            print(f"[OSM] Error leyendo caché: {e}")

    area_sq_deg = (max_lat - min_lat) * (max_lon - min_lon)
    # Si el área es pequeña (<0.003 grados²), usar endpoint directo de OSM
    if area_sq_deg <= 0.003:
        url = f"https://api.openstreetmap.org/api/0.6/map?bbox={min_lon},{min_lat},{max_lon},{max_lat}"
        print(f"[OSM] Descargando infraestructura urbana desde OpenStreetMap...")
        req = urllib.request.Request(url, headers={'User-Agent': 'StreetVulkan/2.0'})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = resp.read()
                os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
                with open(cache_file, "wb") as f:
                    f.write(data)
                print(f"[OSM] Descarga completa ({len(data)} bytes) y guardada en {cache_file}")
                return data
        except Exception as e:
            print(f"[OSM] Error descargando directo de OSM: {e}")

    # Para áreas metropolitanas completas (como todo Tercer Anillo ~220 km²):
    # Usar Overpass API para descargar toda la red vial, semáforos y puentes sin sobrecargar memoria
    print(f"[OSM] Descargando red metropolitana completa (Tercer Anillo) vía Overpass API...")
    overpass_urls = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]
    query = f"""[out:xml][timeout:180];
(
  way["highway"]({min_lat},{min_lon},{max_lat},{max_lon});
  node(w);
  node["highway"="traffic_signals"]({min_lat},{min_lon},{max_lat},{max_lon});
  node["highway"="crossing"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out body;
"""
    query_bytes = query.encode('utf-8')
    for op_url in overpass_urls:
        print(f"[OSM] Intentando con servidor {op_url}...")
        try:
            req = urllib.request.Request(
                op_url,
                data=query_bytes,
                headers={'User-Agent': 'StreetVulkan/2.0', 'Content-Type': 'application/x-www-form-urlencoded'}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                if len(data) > 5000 and b"<osm" in data:
                    os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
                    with open(cache_file, "wb") as f:
                        f.write(data)
                    print(f"[OSM] ¡Red metropolitana descargada con éxito ({len(data)} bytes) en {cache_file}!")
                    return data
        except Exception as e:
            print(f"[OSM] Falló servidor {op_url}: {e}")

    # Fallback por cuadrícula de teselas OSM
    print(f"[OSM] Iniciando descarga subdividida en cuadrícula de teselas...")
    nx_tiles = 4
    ny_tiles = 5
    d_lon = (max_lon - min_lon) / nx_tiles
    d_lat = (max_lat - min_lat) / ny_tiles
    tile_dir = "models/osm_tiles"
    os.makedirs(tile_dir, exist_ok=True)
    all_nodes = {}
    all_ways = {}

    for iy in range(ny_tiles):
        t_min_lat = min_lat + iy * d_lat
        t_max_lat = t_min_lat + d_lat
        for ix in range(nx_tiles):
            t_min_lon = min_lon + ix * d_lon
            t_max_lon = t_min_lon + d_lon
            t_cache = os.path.join(tile_dir, f"tile_{iy}_{ix}.xml")
            t_data = None
            if os.path.exists(t_cache):
                try:
                    with open(t_cache, "rb") as tf:
                        t_data = tf.read()
                except Exception:
                    pass
            if not t_data or len(t_data) < 500:
                t_url = f"https://api.openstreetmap.org/api/0.6/map?bbox={t_min_lon:.5f},{t_min_lat:.5f},{t_max_lon:.5f},{t_max_lat:.5f}"
                try:
                    treq = urllib.request.Request(t_url, headers={'User-Agent': 'StreetVulkan/2.0'})
                    with urllib.request.urlopen(treq, timeout=30) as tresp:
                        t_data = tresp.read()
                        with open(t_cache, "wb") as tf:
                            tf.write(t_data)
                except Exception as te:
                    print(f"[OSM] Aviso en tesela ({ix},{iy}): {te}")

            if t_data and b"<osm" in t_data:
                try:
                    t_root = ET.fromstring(t_data)
                    for n in t_root.findall('node'):
                        all_nodes[n.attrib['id']] = n
                    for w in t_root.findall('way'):
                        all_ways[w.attrib['id']] = w
                except Exception as pe:
                    print(f"[OSM] Error parseando tesela ({ix},{iy}): {pe}")

    if all_nodes and all_ways:
        combined_root = ET.Element('osm', {'version': '0.6', 'generator': 'StreetVulkan Grid Merger'})
        for n in all_nodes.values():
            combined_root.append(n)
        for w in all_ways.values():
            combined_root.append(w)
        combined_data = ET.tostring(combined_root, encoding='utf-8')
        with open(cache_file, "wb") as f:
            f.write(combined_data)
        print(f"[OSM] Cuadrícula combinada exitosamente ({len(combined_data)} bytes) en {cache_file}")
        return combined_data

    print(f"[OSM] No se pudo obtener datos para el área solicitada.")
    return None

def parse_osm_data(xml_data):
    if not xml_data:
        return {}, [], [], [], [], [], [], [], [], [], []

    import io
    raw_bytes = xml_data.encode('utf-8') if isinstance(xml_data, str) else xml_data

    nodes = {}
    traffic_signals = []
    crossings = []
    bus_stops = []
    trees = []
    buildings = []
    highways = []
    civil_bridges = []
    pedestrian_bridges = []
    tunnels = []
    park_polygons = []
    node_highway_count = {}

    for event, elem in ET.iterparse(io.BytesIO(raw_bytes), events=('end',)):
        tag_name = elem.tag
        if tag_name == 'node':
            nid = elem.attrib['id']
            lat = float(elem.attrib['lat'])
            lon = float(elem.attrib['lon'])
            nodes[nid] = (lat, lon)

            tags = {t.attrib['k']: t.attrib.get('v', '') for t in elem.findall('tag')}
            if tags.get('highway') == 'traffic_signals':
                traffic_signals.append((lat, lon, tags, nid))
            elif tags.get('highway') == 'crossing':
                crossings.append((lat, lon, tags, nid))
            elif tags.get('highway') in ('bus_stop', 'platform') or tags.get('amenity') == 'bus_station':
                bus_stops.append((lat, lon, tags, nid))
            elif tags.get('natural') == 'tree':
                trees.append((lat, lon, tags, nid))
            elem.clear()
        elif tag_name == 'way':
            tags = {t.attrib['k']: t.attrib.get('v', '') for t in elem.findall('tag')}
            refs = [nd.attrib['ref'] for nd in elem.findall('nd') if nd.attrib['ref'] in nodes]

            if 'building' in tags and len(refs) >= 3:
                coords = [nodes[r] for r in refs]
                buildings.append((coords, tags))
            elif (tags.get('leisure') == 'park' or tags.get('landuse') in ('grass', 'village_green', 'park', 'recreation_ground', 'meadow') or tags.get('natural') in ('wood', 'scrub')) and len(refs) >= 3:
                coords = [nodes[r] for r in refs]
                park_polygons.append((coords, tags))
            elif 'highway' in tags and len(refs) >= 2:
                coords = [nodes[r] for r in refs]
                h_type = tags.get('highway', '')

                layer_val = 0
                try:
                    layer_val = int(tags.get('layer', '0') or 0)
                except (ValueError, TypeError):
                    pass

                is_bridge = (tags.get('bridge') in ('yes', 'viaduct', 'cantilever', 'movable')) or (layer_val > 0)
                is_tunnel = (
                    h_type in (
                        'motorway', 'motorway_link',
                        'trunk', 'trunk_link',
                        'primary', 'primary_link',
                        'secondary', 'secondary_link',
                        'tertiary', 'tertiary_link',
                        'residential', 'unclassified',
                    )
                    and tags.get('tunnel') == 'yes'
                )

                if is_bridge:
                    if h_type in ('footway', 'path', 'pedestrian', 'steps', 'cycleway'):
                        pedestrian_bridges.append((coords, tags, refs))
                    else:
                        civil_bridges.append((coords, tags, refs))
                elif is_tunnel:
                    tunnels.append((coords, tags, refs))
                else:
                    highways.append((coords, tags, refs))

                for r in refs:
                    node_highway_count[r] = node_highway_count.get(r, 0) + 1
            elem.clear()

    # Intersecciones: Nodos que conectan múltiples vías
    intersections = []
    for nid, count in node_highway_count.items():
        if count >= 2 and nid in nodes:
            intersections.append(nodes[nid])

    print(f"[OSM] Geometrías procesadas: {len(buildings)} edificios, {len(highways)} calles a nivel,")
    print(f"      {len(civil_bridges)} puentes civiles/viaductos, {len(pedestrian_bridges)} puentes peatonales,")
    print(f"      {len(tunnels)} pasos a desnivel subterráneos/túneles,")
    print(f"      {len(trees)} árboles OSM, {len(park_polygons)} parques/zonas verdes,")
    print(f"      {len(traffic_signals)} semáforos, {len(crossings)} pasos de cebra, {len(intersections)} intersecciones.")

    return nodes, buildings, highways, traffic_signals, crossings, intersections, trees, park_polygons, civil_bridges, pedestrian_bridges, tunnels
