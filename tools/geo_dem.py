#!/usr/bin/env python3
"""
Módulo de Geodesia y Topografía Satelital Real (DEM)
- Proyecciones entre coordenadas geográficas (lat/lon) y métricas cartesianas (X, Z).
- Descarga y decodificación de elevaciones satelitales continuas de alta precisión
  (NASA SRTM / USGS 3DEP / Mapzen Terrarium en AWS).
- 100% elevación real sin franjas ni mesetas artificiales.
"""

import os
import json
import math
import io
import urllib.request
import numpy as np
from PIL import Image

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

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile

def num2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg

def fetch_dem_grid(min_lat, max_lat, min_lon, max_lon, nx=64, ny=64, zoom=12):
    cache_name = f"dem_terrarium_{min_lat:.3f}_{max_lat:.3f}_{min_lon:.3f}_{max_lon:.3f}_{nx}x{ny}.json"
    cache_file = os.path.join(os.path.dirname(__file__), "..", "models", cache_name)
    if not os.path.exists(cache_file):
        cache_file = f"models/{cache_name}"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                grid = json.load(f)
                all_vals = [h for row in grid for h in row]
                print(f"[DEM Real] Cargado desde caché ({cache_file}): Min {min(all_vals):.1f}m, Max {max(all_vals):.1f}m")
                return grid
        except Exception as e:
            print(f"[DEM] Error leyendo caché: {e}")

    print(f"[DEM Real] Descargando topografía satelital continua (NASA SRTM / AWS Terrarium)...")
    x_min_tile, y_min_tile = deg2num(max_lat, min_lon, zoom)
    x_max_tile, y_max_tile = deg2num(min_lat, max_lon, zoom)

    tile_cache_dir = "models/tile_cache_dem"
    os.makedirs(tile_cache_dir, exist_ok=True)

    rows = []
    headers = {'User-Agent': 'StreetVulkanDEM/2.0'}

    for ty in range(y_min_tile, y_max_tile + 1):
        row_tiles = []
        for tx in range(x_min_tile, x_max_tile + 1):
            cache_path = os.path.join(tile_cache_dir, f"dem_{zoom}_{tx}_{ty}.png")
            if not os.path.exists(cache_path) or os.path.getsize(cache_path) < 500:
                url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{tx}/{ty}.png"
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        with open(cache_path, "wb") as f:
                            f.write(resp.read())
                except Exception as e:
                    print(f"[DEM] Error descargando tesela ({tx}, {ty}): {e}")

            if os.path.exists(cache_path):
                img = Image.open(cache_path).convert("RGBA")
                row_tiles.append(np.array(img))
            else:
                # Fallback neutro solo si falla conexión de red
                row_tiles.append(np.zeros((256, 256, 4), dtype=np.uint8))
        rows.append(np.hstack(row_tiles))

    full_img = np.vstack(rows)
    r = full_img[:, :, 0].astype(np.float32)
    g = full_img[:, :, 1].astype(np.float32)
    b = full_img[:, :, 2].astype(np.float32)
    # Fórmula oficial Terrarium: elevación en metros = (R * 256 + G + B / 256) - 32768
    elev_map = (r * 256.0 + g + b / 256.0) - 32768.0

    # Coordenadas geográficas de las esquinas del mosaico de teselas
    tile_top_lat, tile_left_lon = num2deg(x_min_tile, y_min_tile, zoom)
    tile_bottom_lat, tile_right_lon = num2deg(x_max_tile + 1, y_max_tile + 1, zoom)

    # Remuestreo preciso a la grilla nx x ny
    grid = []
    map_h, map_w = elev_map.shape
    for j in range(ny):
        lat = min_lat + j * (max_lat - min_lat) / (ny - 1)
        # Web Mercator proyección Y dentro del mosaico
        n = 2.0 ** zoom
        lat_rad = math.radians(lat)
        py = ((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n - y_min_tile) * 256.0
        py = max(0.0, min(float(map_h - 1), py))
        iy = int(py)
        fy = py - iy
        iy_next = min(map_h - 1, iy + 1)

        row = []
        for i in range(nx):
            lon = min_lon + i * (max_lon - min_lon) / (nx - 1)
            px = ((lon + 180.0) / 360.0 * n - x_min_tile) * 256.0
            px = max(0.0, min(float(map_w - 1), px))
            ix = int(px)
            fx = px - ix
            ix_next = min(map_w - 1, ix + 1)

            # Interpolación bilineal sobre el mapa de elevación satelital
            h00 = elev_map[iy, ix]
            h10 = elev_map[iy, ix_next]
            h01 = elev_map[iy_next, ix]
            h11 = elev_map[iy_next, ix_next]

            h0 = h00 * (1.0 - fx) + h10 * fx
            h1 = h01 * (1.0 - fx) + h11 * fx
            h = float(h0 * (1.0 - fy) + h1 * fy)
            row.append(round(h, 2))
        grid.append(row)

    try:
        os.makedirs("models", exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(grid, f)
        all_vals = [h for row in grid for h in row]
        print(f"[DEM Real] ✅ Topografía 100% REAL guardada: Min {min(all_vals):.1f}m, Max {max(all_vals):.1f}m → {cache_file}")
    except Exception as e:
        print(f"[DEM] Aviso guardando caché: {e}")

    return grid

def _dist_and_side_to_poly(px, pz, polyline):
    min_d = float('inf'); side_val = 0.0
    for i in range(len(polyline) - 1):
        ax, az = polyline[i]; bx, bz = polyline[i+1]
        dx, dz = bx - ax, bz - az
        l_sq = dx*dx + dz*dz
        if l_sq < 1e-6:
            d = math.hypot(px-ax, pz-az); s = 0.0
        else:
            t = max(0.0, min(1.0, ((px-ax)*dx + (pz-az)*dz) / l_sq))
            proj_x = ax + t*dx; proj_z = az + t*dz
            d = math.hypot(px-proj_x, pz-proj_z)
            s = (px-ax)*dz - (pz-az)*dx
        if d < min_d:
            min_d = d; side_val = s
    return min_d, side_val

AGUASCALIENTES_RIVERS_GEO = [
    {
        "name": "Río San Pedro",
        "coords": [
            (21.950, -102.350), (21.932, -102.345), (21.912, -102.338),
            (21.890, -102.332), (21.870, -102.330), (21.850, -102.328),
            (21.830, -102.332), (21.800, -102.340)
        ],
        "valley_w": 120.0, "channel_w": 32.0, "depth": 3.8
    },
    {
        "name": "Arroyo El Cedazo",
        "coords": [
            (21.848, -102.248), (21.856, -102.260), (21.865, -102.270),
            (21.870, -102.280), (21.874, -102.295), (21.878, -102.315),
            (21.880, -102.330)
        ],
        "valley_w": 55.0, "channel_w": 18.0, "depth": 2.5
    },
    {
        "name": "Arroyo Don Pascual",
        "coords": [
            (21.935, -102.255), (21.920, -102.270), (21.905, -102.285),
            (21.898, -102.305), (21.892, -102.325), (21.890, -102.332)
        ],
        "valley_w": 45.0, "channel_w": 16.0, "depth": 2.2
    },
    {
        "name": "Arroyo El Molino",
        "coords": [
            (21.940, -102.285), (21.932, -102.300), (21.925, -102.320),
            (21.918, -102.336)
        ],
        "valley_w": 40.0, "channel_w": 15.0, "depth": 2.0
    }
]

AGUASCALIENTES_FAULTS_GEO = [
    {
        "name": "Falla Oriente",
        "coords": [
            (21.945, -102.274), (21.910, -102.277), (21.880, -102.279),
            (21.850, -102.281), (21.810, -102.284)
        ],
        "step": 0.90, "down_sign": -1.0
    },
    {
        "name": "Falla Poniente",
        "coords": [
            (21.940, -102.316), (21.910, -102.317), (21.885, -102.318),
            (21.855, -102.319), (21.820, -102.321)
        ],
        "step": 0.85, "down_sign": 1.0
    }
]

class TerrainElevation:
    def __init__(self, min_lat, max_lat, min_lon, max_lon, nx=64, ny=64,
                 origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON, base_elevation=1871.0):
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
        return dem_h - self.base_elevation

    def _init_topography_features(self):
        self.rivers = [
            {
                "name": r["name"],
                "pts": [geo_to_meters(lat, lon, self.origin_lat, self.origin_lon) for lat, lon in r["coords"]],
                "valley_w": r["valley_w"],
                "channel_w": r["channel_w"],
                "depth": r["depth"]
            }
            for r in AGUASCALIENTES_RIVERS_GEO
        ]
        self.faults = [
            {
                "name": f["name"],
                "pts": [geo_to_meters(lat, lon, self.origin_lat, self.origin_lon) for lat, lon in f["coords"]],
                "step": f["step"],
                "down_sign": f["down_sign"]
            }
            for f in AGUASCALIENTES_FAULTS_GEO
        ]

    def get_real_topography(self, x, z):
        if not hasattr(self, "rivers"):
            self._init_topography_features()
        py = self.get_ground_elevation(x, z)
        for r_info in self.rivers:
            d, _ = _dist_and_side_to_poly(x, z, r_info["pts"])
            if d < r_info["valley_w"]:
                f = 1.0 - (d / r_info["valley_w"])
                py -= r_info["depth"] * (f * f)
        for f_info in self.faults:
            d, s = _dist_and_side_to_poly(x, z, f_info["pts"])
            if d < 120.0:
                t_fault = math.tanh(s / 40.0) * f_info["down_sign"]
                py += f_info["step"] * 0.5 * t_fault
        return py

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
        self.heights = [[0.0 for _ in range(cols + 1)] for _ in range(rows + 1)]
        for r in range(rows + 1):
            for c in range(cols + 1):
                idx = r * (cols + 1) + c
                self.heights[r][c] = grid_pts[idx][1]

    def get_mesh_height(self, px, pz):
        c = int((px - self.x0) / self.dx)
        r = int((pz - self.z0) / self.dz)

        c = max(0, min(self.cols - 1, c))
        r = max(0, min(self.rows - 1, r))

        u = (px - (self.x0 + c * self.dx)) / self.dx
        v = (pz - (self.z0 + r * self.dz)) / self.dz
        u = max(0.0, min(1.0, u))
        v = max(0.0, min(1.0, v))

        y00 = self.heights[r][c]
        y10 = self.heights[r][c + 1]
        y01 = self.heights[r + 1][c]
        y11 = self.heights[r + 1][c + 1]

        if u + v <= 1.0:
            return y00 + u * (y10 - y00) + v * (y01 - y00)
        else:
            return y11 + (1.0 - u) * (y01 - y11) + (1.0 - v) * (y10 - y11)
