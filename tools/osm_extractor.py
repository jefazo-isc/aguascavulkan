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

    url = f"https://api.openstreetmap.org/api/0.6/map?bbox={min_lon},{min_lat},{max_lon},{max_lat}"
    print(f"[OSM] Descargando infraestructura urbana desde OpenStreetMap...")
    req = urllib.request.Request(url, headers={'User-Agent': 'StreetVulkan/2.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(cache_file, "wb") as f:
                f.write(data)
            print(f"[OSM] Descarga completa ({len(data)} bytes) y guardada en {cache_file}")
            return data
    except Exception as e:
        print(f"[OSM] Error descargando: {e}")
        return None

def parse_osm_data(xml_data):
    if not xml_data:
        return {}, [], [], [], [], []

    root = ET.fromstring(xml_data)

    nodes = {}
    traffic_signals = []
    crossings = []
    bus_stops = []
    trees = []

    for n in root.findall('node'):
        nid = n.attrib['id']
        lat = float(n.attrib['lat'])
        lon = float(n.attrib['lon'])
        nodes[nid] = (lat, lon)

        tags = {t.attrib['k']: t.attrib.get('v', '') for t in n.findall('tag')}
        if tags.get('highway') == 'traffic_signals':
            traffic_signals.append((lat, lon, tags, nid))
        elif tags.get('highway') == 'crossing':
            crossings.append((lat, lon, tags, nid))
        elif tags.get('highway') in ('bus_stop', 'platform') or tags.get('amenity') == 'bus_station':
            bus_stops.append((lat, lon, tags, nid))
        elif tags.get('natural') == 'tree':
            trees.append((lat, lon, tags, nid))

    buildings = []
    highways = []
    civil_bridges = []
    pedestrian_bridges = []
    tunnels = []
    park_polygons = []
    node_highway_count = {}

    for w in root.findall('way'):
        tags = {t.attrib['k']: t.attrib.get('v', '') for t in w.findall('tag')}
        refs = [nd.attrib['ref'] for nd in w.findall('nd') if nd.attrib['ref'] in nodes]

        if 'building' in tags and len(refs) >= 3:
            coords = [nodes[r] for r in refs]
            buildings.append((coords, tags))
        elif (tags.get('leisure') == 'park' or tags.get('landuse') in ('grass', 'village_green', 'park', 'recreation_ground', 'meadow') or tags.get('natural') in ('wood', 'scrub')) and len(refs) >= 3:
            coords = [nodes[r] for r in refs]
            park_polygons.append((coords, tags))
        elif 'highway' in tags and len(refs) >= 2:
            coords = [nodes[r] for r in refs]
            h_type = tags.get('highway', '')
            
            # Extracción segura del atributo layer (OSM puede devolver valores anómalos)
            layer_val = 0
            try:
                layer_val = int(tags.get('layer', '0') or 0)
            except (ValueError, TypeError):
                pass
                
            is_bridge = (tags.get('bridge') in ('yes', 'viaduct', 'cantilever', 'movable')) or (layer_val > 0)
            is_tunnel = (tags.get('tunnel') in ('yes', 'building_passage', 'covered')) or (layer_val < 0)
            
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
