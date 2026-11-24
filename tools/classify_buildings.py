#!/usr/bin/env python3
"""
classify_buildings.py
======================
Clasifica los 32,305 edificios de overture_buildings.geojson relacionando:
 1. OSM POIs y tags de way (ej: Templo, Hospital, Escuela, OXXO)
 2. 9,249 registros reales del DENUE INEGI Aguascalientes (Spatial Join R-tree / cKDTree)
 3. Reglas heurísticas de geometría (Área, Pisos/Altura)

Genera: models/classified_buildings.json
"""

import os
import sys
import json
import math
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
# Simple spatial grid index (sin dependencia de scipy)
class SpatialGrid2D:
    def __init__(self, cell_size=25.0):
        self.cell_size = cell_size
        self.grid = {}

    def insert(self, x, z, item):
        cx = int(math.floor(x / self.cell_size))
        cz = int(math.floor(z / self.cell_size))
        key = (cx, cz)
        if key not in self.grid:
            self.grid[key] = []
        self.grid[key].append(item)

    def query_radius(self, x, z, radius=18.0):
        results = []
        min_cx = int(math.floor((x - radius) / self.cell_size))
        max_cx = int(math.floor((x + radius) / self.cell_size))
        min_cz = int(math.floor((z - radius) / self.cell_size))
        max_cz = int(math.floor((z + radius) / self.cell_size))
        r_sq = radius * radius
        for cx in range(min_cx, max_cx + 1):
            for cz in range(min_cz, max_cz + 1):
                items = self.grid.get((cx, cz), [])
                for it in items:
                    dx = it['x'] - x
                    dz = it['z'] - z
                    if dx*dx + dz*dz <= r_sq:
                        results.append(it)
        return results

# Origen local de proyección topográfica
ORIGIN_LAT = 21.8807
ORIGIN_LON = -102.2965

def geo_to_meters(lat, lon, ref_lat=ORIGIN_LAT, ref_lon=ORIGIN_LON):
    r_earth = 6371000.0
    phi1 = math.radians(ref_lat)
    phi2 = math.radians(lat)
    d_phi = math.radians(lat - ref_lat)
    d_lam = math.radians(lon - ref_lon)
    x = r_earth * d_lam * math.cos((phi1 + phi2) / 2.0)
    z = -r_earth * d_phi
    return x, z

def load_osm_data(osm_path=None):
    if osm_path is None:
        osm_path = BASE_DIR / "models" / "osm_cache.xml"
    else:
        osm_path = Path(osm_path)

    print(f"[Classify] Cargando datos OSM de {osm_path}...")
    if not osm_path.exists():
        return {}, []

    with open(osm_path, "rb") as f:
        root = ET.fromstring(f.read())

    nodes = {}
    node_pois = []
    for n in root.findall('node'):
        nid = n.attrib['id']
        lat = float(n.attrib['lat'])
        lon = float(n.attrib['lon'])
        x, z = geo_to_meters(lat, lon)
        nodes[nid] = (x, z)
        tags = {t.attrib['k']: t.attrib.get('v', '') for t in n.findall('tag')}
        if any(k in tags for k in ('amenity', 'shop', 'office', 'tourism', 'healthcare', 'name')):
            node_pois.append({
                'x': x, 'z': z,
                'name': tags.get('name', ''),
                'amenity': tags.get('amenity', ''),
                'shop': tags.get('shop', ''),
                'office': tags.get('office', ''),
                'brand': tags.get('brand', '')
            })

    way_buildings = []
    for w in root.findall('way'):
        tags = {t.attrib['k']: t.attrib.get('v', '') for t in w.findall('tag')}
        refs = [nd.attrib['ref'] for nd in w.findall('nd') if nd.attrib['ref'] in nodes]
        if 'building' in tags and len(refs) >= 3:
            poly = [nodes[r] for r in refs]
            cx = sum(p[0] for p in poly) / len(poly)
            cz = sum(p[1] for p in poly) / len(poly)
            way_buildings.append({
                'poly': poly, 'cx': cx, 'cz': cz, 'tags': tags
            })

    print(f"[Classify] OSM: {len(node_pois)} POIs en nodos, {len(way_buildings)} edificios etiquetados.")
    return node_pois, way_buildings

def load_denue_data(csv_path=None,
                    min_lat=21.8690, max_lat=21.8940, min_lon=-102.3110, max_lon=-102.2815):
    if csv_path is None:
        csv_path = BASE_DIR / "models" / "conjunto_de_datos" / "denue_inegi_01_.csv"
    else:
        csv_path = Path(csv_path)

    print(f"[Classify] Cargando INEGI DENUE desde {csv_path}...")
    denue_records = []
    if not csv_path.exists():
        print(f"[Classify] ERROR: Archivo DENUE no encontrado en {csv_path}")
        return denue_records

    with open(csv_path, encoding='latin-1') as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                lat = float(r['latitud'])
                lon = float(r['longitud'])
                if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                    x, z = geo_to_meters(lat, lon)
                    denue_records.append({
                        'x': x, 'z': z,
                        'name': r['nom_estab'].strip(),
                        'activity': r['nombre_act'].strip(),
                        'code': r['codigo_act'].strip()
                    })
            except (ValueError, KeyError):
                pass
    print(f"[Classify] DENUE: {len(denue_records)} establecimientos en el sector.")
    return denue_records

def categorize_building(building_props, poly_area, height, osm_matches, denue_matches):
    """
    Asigna una categoría semántica y paleta cromática a un edificio.
    """
    # 1. Reglas directas por marcas / POIs de renombre
    all_names = " ".join([m['name'].lower() for m in osm_matches + denue_matches])
    all_acts = " ".join([m.get('activity', '').lower() + " " + m.get('amenity', '').lower() + " " + m.get('shop', '').lower() for m in osm_matches + denue_matches])

    if any(k in all_names for k in ['rolcar', 'refaccionaria rogelio', 'refacionaria rogelio']):
        return {
            'type': 'rolcar',
            'label': 'Rolcar / Refaccionaria Rogelio',
            'color': (0.04, 0.48, 0.20), # Verde Rolcar corporativo
            'matID': 1.0,
            'has_sign': True
        }

    if any(k in all_names for k in ['oxxo', '7-eleven', '7 eleven', 'extra', 'circle k']):
        return {
            'type': 'oxxo',
            'label': 'OXXO / Tienda de Conveniencia',
            'color': (0.85, 0.15, 0.12), # Rojo OXXO corporativo
            'matID': 1.0,
            'has_sign': True
        }

    if any(k in all_names or k in all_acts for k in ['farmacia', 'guadalajara', 'similares', 'benavides']):
        return {
            'type': 'pharmacy',
            'label': 'Farmacia / Salud',
            'color': (0.15, 0.45, 0.85), # Azul farmacia
            'matID': 1.0,
            'has_sign': True
        }

    if any(k in all_names or k in all_acts for k in ['templo', 'parroquia', 'iglesia', 'catedral', 'san marcos', 'merced', 'guadalupe', 'place_of_worship']):
        return {
            'type': 'church',
            'label': 'Templo / Parroquia Religiosa',
            'color': (0.88, 0.82, 0.72), # Cantera clara
            'matID': 1.0,
            'has_sign': False
        }

    if any(k in all_names or k in all_acts for k in ['escuela', 'colegio', 'kínder', 'kinder', 'universidad', 'instituto', 'primaria', 'secundaria', 'preparatoria', 'school', 'university']):
        return {
            'type': 'school',
            'label': 'Institución Educativa',
            'color': (0.82, 0.75, 0.45), # Amarillo/beige educativo
            'matID': 1.0,
            'has_sign': True
        }

    if any(k in all_names or k in all_acts for k in ['supermercado', 'bodega aurrera', 'walmart', 'soriana', 'chedraui', 'superissste', 'supermarket']):
        return {
            'type': 'supermarket',
            'label': 'Supermercado / Gran Tienda',
            'color': (0.22, 0.65, 0.32), # Verde supermercado
            'matID': 1.0,
            'has_sign': True
        }

    if any(k in all_names or k in all_acts for k in ['palacio', 'presidencia', 'dirección de', 'secretaría', 'televisa', 'gobierno', 'townhall', 'police']):
        return {
            'type': 'government',
            'label': 'Edificio Gubernamental / Cívico',
            'color': (0.78, 0.68, 0.58), # Cantera rosa/gris
            'matID': 1.0,
            'has_sign': False
        }

    # 2. Si hay negocios DENUE en general (Comercios de barrio, talleres, restaurantes)
    if denue_matches or osm_matches:
        first_match = (denue_matches + osm_matches)[0]
        name = first_match.get('name') or first_match.get('activity') or 'Comercio Local'
        return {
            'type': 'commercial_local',
            'label': f"Comercio: {name[:30]}",
            'color': (0.75, 0.72, 0.68),
            'matID': 1.0,
            'has_sign': True
        }

    # 3. Heurística Geométrica para residencias / bodegas
    if poly_area > 800 and height < 7.0:
        return {
            'type': 'industrial',
            'label': 'Nave Industrial / Bodega',
            'color': (0.70, 0.72, 0.75), # Gris lámina/metal
            'matID': 1.0,
            'has_sign': False
        }

    if height >= 8.5:
        return {
            'type': 'residence_2f',
            'label': 'Vivienda Residencial (2-3 Pisos)',
            'color': (0.84, 0.78, 0.68), # Tinte cálido
            'matID': 1.0,
            'has_sign': False
        }

    # Por defecto: Vivienda residencial 1 piso
    return {
        'type': 'residence_1f',
        'label': 'Vivienda Residencial (1 Piso)',
        'color': (0.80, 0.76, 0.70), # Tinte residencial estándar
        'matID': 1.0,
        'has_sign': False
    }

def classify_all_buildings():
    print("="*65)
    print("  CLASIFICADOR REAL DE EDIFICIOS (DENUE INEGI + OSM + OVERTURE)")
    print("="*65)

    osm_pois, way_buildings = load_osm_data()
    denue_records = load_denue_data()

    # Construir SpatialGrid2D para búsquedas espaciales ultrarrápidas
    poi_grid = SpatialGrid2D(cell_size=30.0)
    for p in osm_pois:
        poi_grid.insert(p['x'], p['z'], {'x': p['x'], 'z': p['z'], 'name': p['name'], 'activity': p['amenity'] or p['shop'], 'source': 'OSM'})
    for wb in way_buildings:
        tags = wb.get('tags', {})
        activity = tags.get('amenity') or tags.get('shop') or tags.get('office') or (
            tags.get('building') if tags.get('building') not in (None, '', 'yes') else ''
        )
        name = tags.get('name', '')
        if name or activity:
            poi_grid.insert(wb['cx'], wb['cz'], {
                'x': wb['cx'], 'z': wb['cz'],
                'name': name, 'activity': activity, 'source': 'OSM'
            })
    for d in denue_records:
        poi_grid.insert(d['x'], d['z'], {'x': d['x'], 'z': d['z'], 'name': d['name'], 'activity': d['activity'], 'source': 'DENUE'})

    # Cargar los edificios modulares por anillos (evita sobrecarga de RAM en Python)
    ring_paths = [
        BASE_DIR / "models" / "overture_primer_anillo.geojson",
        BASE_DIR / "models" / "overture_segundo_anillo.geojson",
        BASE_DIR / "models" / "overture_tercer_anillo.geojson"
    ]
    existing_paths = [p for p in ring_paths if p.exists()]
    if not existing_paths:
        fallback = BASE_DIR / "models" / "overture_buildings.geojson"
        if fallback.exists():
            existing_paths = [fallback]
        else:
            print("[ERROR] No se encontraron archivos de edificios Overture")
            return

    classified_results = []
    category_counts = {}

    for geojson_path in existing_paths:
        print(f"[Classify] Leyendo {geojson_path.name}...")
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        print(f"[Classify] Procesando {len(features):,} edificios de {geojson_path.name}...")

        for idx, feat in enumerate(features):
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if not coords or geom.get("type") != "Polygon":
                continue

            poly_geo = coords[0]
            poly_m = [geo_to_meters(lat, lon) for lon, lat in poly_geo]
            if not poly_m:
                continue

            cx = sum(p[0] for p in poly_m) / len(poly_m)
            cz = sum(p[1] for p in poly_m) / len(poly_m)

            # Área del polígono
            n = len(poly_m)
            area = 0.5 * abs(sum(poly_m[i][0] * poly_m[(i+1)%n][1] - poly_m[(i+1)%n][0] * poly_m[i][1] for i in range(n)))

            # Estimación de altura
            height = 4.0
            props = feat.get("properties") or {}
            if props.get("height") is not None:
                try:
                    height = float(props["height"])
                except (ValueError, TypeError):
                    pass
            elif props.get("building:levels") is not None:
                try:
                    height = float(props["building:levels"]) * 3.2
                except (ValueError, TypeError):
                    pass

            # Búsqueda espacial de POIs en radio de 18 metros
            osm_matches = []
            denue_matches = []
            nearby_pois = poi_grid.query_radius(cx, cz, radius=18.0)
            for poi in nearby_pois:
                if poi['source'] == 'OSM':
                    osm_matches.append(poi)
                else:
                    denue_matches.append(poi)

            cat_info = categorize_building(props, area, height, osm_matches, denue_matches)

            t = cat_info['type']
            category_counts[t] = category_counts.get(t, 0) + 1

            classified_results.append({
                'id': idx,
                'type': cat_info['type'],
                'label': cat_info['label'],
                'color': cat_info['color']
            })

    out_json = BASE_DIR / "models" / "classified_buildings.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n[Classify] Resumen de Clasificación ({len(classified_results)} edificios):")
    if classified_results:
        for k, v in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (v / len(classified_results)) * 100.0
            print(f"  - {k:18s}: {v:5d} ({pct:5.1f}%)")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(classified_results, f, indent=2, ensure_ascii=False)

    print(f"\n[Classify] ✅ Guardado exitoso en {out_json}")

if __name__ == "__main__":
    classify_all_buildings()
