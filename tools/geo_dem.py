#!/usr/bin/env python3
"""
Módulo de Geodesia y Topografía Satelital (DEM)
- Proyecciones entre coordenadas geográficas (lat/lon) y métricas cartesianas (X, Z).
- Descarga, almacenamiento en caché e interpolación bilineal de elevaciones satelitales reales.
- Modelado de fallas geológicas (Falla San Marcos y Falla Oriente).
"""

import os
import json
import math
import time
import urllib.request

DEFAULT_ORIGIN_LAT = 21.8807
DEFAULT_ORIGIN_LON = -102.2965
M_PER_LAT = 111320.0

def get_meters_per_lon(origin_lat=DEFAULT_ORIGIN_LAT):
    return M_PER_LAT * math.cos(math.radians(origin_lat))

def geo_to_meters(lat, lon, origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON):
    m_per_lon = get_meters_per_lon(origin_lat)
    x = (lon - origin_lon) * m_per_lon
    z = -(lat - origin_lat) * M_PER_LAT
    return x, z

def meters_to_geo(x, z, origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON):
    m_per_lon = get_meters_per_lon(origin_lat)
    lon = origin_lon + x / m_per_lon
    lat = origin_lat - z / M_PER_LAT
    return lat, lon

def fetch_dem_grid(min_lat, max_lat, min_lon, max_lon, nx=40, ny=40):
    cache_file = os.path.join(os.path.dirname(__file__), "..", "models", f"dem_cache_{nx}x{ny}.json")
    if not os.path.exists(cache_file):
        cache_file = f"models/dem_cache_{nx}x{ny}.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                grid = json.load(f)
                all_vals = [h for row in grid for h in row]
                print(f"[DEM] Cargado desde caché ({cache_file}): Min {min(all_vals)}m, Max {max(all_vals)}m")
                return grid
        except Exception as e:
            print(f"[DEM] Error leyendo caché: {e}")

    pts = []
    for j in range(ny):
        lat = min_lat + j * (max_lat - min_lat) / (ny - 1)
        for i in range(nx):
            lon = min_lon + i * (max_lon - min_lon) / (nx - 1)
            pts.append((lat, lon))

    print(f"[DEM] Descargando {len(pts)} puntos de elevación satelital...")
    elevs = []
    chunk_size = 100
    for k in range(0, len(pts), chunk_size):
        chunk = pts[k:k+chunk_size]
        lats = ','.join(f"{p[0]:.5f}" for p in chunk)
        lons = ','.join(f"{p[1]:.5f}" for p in chunk)
        url = f"https://api.open-meteo.com/v1/elevation?latitude={lats}&longitude={lons}"
        req = urllib.request.Request(url, headers={'User-Agent': 'StreetVulkan/2.0'})

        success = False
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    vals = data.get('elevation', [])
                    if len(vals) == len(chunk):
                        elevs.extend(vals)
                        success = True
                        break
            except Exception:
                time.sleep(1.0 + attempt * 1.5)

        if not success:
            elevs.extend([1865.0] * len(chunk))
        time.sleep(0.2)

    grid = [[1865.0 for _ in range(nx)] for _ in range(ny)]
    for idx, elev in enumerate(elevs):
        j = idx // nx
        i = idx % nx
        if j < ny and i < nx:
            grid[j][i] = elev

    try:
        os.makedirs("models", exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(grid, f)
        print(f"[DEM] Guardado en caché: {cache_file}")
    except Exception:
        pass

    return grid

class TerrainElevation:
    def __init__(self, min_lat, max_lat, min_lon, max_lon, nx=40, ny=40,
                 origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON, base_elevation=1865.0):
        self.min_lat = min_lat
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.max_lon = max_lon
        self.nx = nx
        self.ny = ny
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon
        self.base_elevation = base_elevation
        self.grid = fetch_dem_grid(min_lat, max_lat, min_lon, max_lon, nx, ny)

        m_per_lon = get_meters_per_lon(origin_lat)
        self.fault_sm_x = (-102.3012 - origin_lon) * m_per_lon
        self.fault_or_x = (-102.2865 - origin_lon) * m_per_lon

    def get_dem_elevation(self, lat, lon):
        u = (lon - self.min_lon) / (self.max_lon - self.min_lon) * (self.nx - 1)
        v = (lat - self.min_lat) / (self.max_lat - self.min_lat) * (self.ny - 1)
        u = max(0.0, min(float(self.nx - 1), float(u)))
        v = max(0.0, min(float(self.ny - 1), float(v)))

        i = min(int(u), self.nx - 2)
        j = min(int(v), self.ny - 2)
        du = u - i
        dv = v - j

        h00 = self.grid[j][i]
        h10 = self.grid[j][i + 1]
        h01 = self.grid[j + 1][i]
        h11 = self.grid[j + 1][i + 1]

        h0 = h00 * (1.0 - du) + h10 * du
        h1 = h01 * (1.0 - du) + h11 * du
        return h0 * (1.0 - dv) + h1 * dv

    def get_ground_elevation(self, x, z):
        lat, lon = meters_to_geo(x, z, self.origin_lat, self.origin_lon)
        dem_h = self.get_dem_elevation(lat, lon)
        y = dem_h - self.base_elevation

        # Escarpes de fallas geológicas reales de Aguascalientes
        d_sm = (x - self.fault_sm_x) / 12.0
        scarp_sm = -2.2 * (0.5 - 0.5 * math.tanh(d_sm))

        d_or = (x - self.fault_or_x) / 12.0
        scarp_or = -1.8 * (0.5 + 0.5 * math.tanh(d_or))

        return y + scarp_sm + scarp_or

class MeshElevationGrid:
    """
    Interpolador de elevación EXACTO sobre los triángulos de la malla que dibuja la GPU.
    Elimina por completo el z-fighting calculando la altura baricéntrica exacta de la superficie rasterizada.
    """
    def __init__(self, x0, z0, x1, z1, cols, rows, grid_pts):
        self.x0 = x0
        self.z0 = z0
        self.x1 = x1
        self.z1 = z1
        self.cols = cols
        self.rows = rows
        self.dx = (x1 - x0) / cols
        self.dz = (z1 - z0) / rows
        # Matriz 2D de alturas (py) indexada por [r][c]
        self.heights = [[0.0 for _ in range(cols + 1)] for _ in range(rows + 1)]
        for r in range(rows + 1):
            for c in range(cols + 1):
                idx = r * (cols + 1) + c
                self.heights[r][c] = grid_pts[idx][1]

    def get_mesh_height(self, px, pz):
        # Localizar celda
        c = int((px - self.x0) / self.dx)
        r = int((pz - self.z0) / self.dz)

        c = max(0, min(self.cols - 1, c))
        r = max(0, min(self.rows - 1, r))

        # Coordenadas relativas normalizadas dentro de la celda [0, 1]
        u = (px - (self.x0 + c * self.dx)) / self.dx
        v = (pz - (self.z0 + r * self.dz)) / self.dz
        u = max(0.0, min(1.0, u))
        v = max(0.0, min(1.0, v))

        y00 = self.heights[r][c]
        y10 = self.heights[r][c + 1]
        y01 = self.heights[r + 1][c]
        y11 = self.heights[r + 1][c + 1]

        # Interpolar sobre el plano del triángulo correspondiente
        # Triángulo 1: (0,0), (1,0), (0,1) donde u + v <= 1
        # Triángulo 2: (1,0), (1,1), (0,1) donde u + v > 1
        if u + v <= 1.0:
            return y00 + u * (y10 - y00) + v * (y01 - y00)
        else:
            return y11 + (1.0 - u) * (y01 - y11) + (1.0 - v) * (y10 - y11)
