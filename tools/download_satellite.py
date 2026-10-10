#!/usr/bin/env python3
"""
Descargador y ensamblador de textura satelital / mapa para Aguascalientes.
Descarga teselas (tiles) de alta resolución georreferenciadas que cubren
con precisión sub-métrica el área del modelo topográfico 3D y las ensambla en
`assets/satellite.png`.
"""

import os
import sys
import math
import urllib.request
from PIL import Image

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

def download_satellite_texture():
    # Mismas coordenadas del generador 3D (con el padding de 120m incluido)
    origin_lat = 21.8807
    origin_lon = -102.2965

    min_lon = -102.3110
    max_lon = -102.2815
    min_lat = 21.8690
    max_lat = 21.8940

    m_per_lat = 111320.0
    m_per_lon = 111320.0 * math.cos(math.radians(origin_lat))

    pad = 120.0
    min_x = (min_lon - origin_lon) * m_per_lon
    max_x = (max_lon - origin_lon) * m_per_lon
    max_z = -(min_lat - origin_lat) * m_per_lat
    min_z = -(max_lat - origin_lat) * m_per_lat

    x0, x1 = min_x - pad, max_x + pad
    z0, z1 = min_z - pad, max_z + pad

    # Coordenadas geográficas exactas de las esquinas del terreno
    target_lon_min = origin_lon + x0 / m_per_lon
    target_lon_max = origin_lon + x1 / m_per_lon
    target_lat_max = origin_lat - z0 / m_per_lat
    target_lat_min = origin_lat - z1 / m_per_lat

    zoom = 17  # Ultra alta resolución (~1.1 metros por pixel)
    print(f"Descargando teselas satelitales en Alta Definición a nivel de zoom {zoom}...")

    x_min_tile, y_min_tile = deg2num(target_lat_max, target_lon_min, zoom)
    x_max_tile, y_max_tile = deg2num(target_lat_min, target_lon_max, zoom)

    tiles_x = x_max_tile - x_min_tile + 1
    tiles_y = y_max_tile - y_min_tile + 1
    print(f"Cuadrícula de teselas: {tiles_x} x {tiles_y} ({tiles_x * tiles_y} teselas en total)")

    canvas = Image.new("RGBA", (tiles_x * 256, tiles_y * 256))

    # Servidor de tiles OSM / CartoDB / Esri Satellite
    # Usamos Esri World Imagery (satelital de alta resolución mundial y libre para visualización)
    base_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

    headers = {'User-Agent': 'StreetVulkanSatellite/1.0'}

    tile_cache_dir = "models/tile_cache"
    os.makedirs(tile_cache_dir, exist_ok=True)

    for ty_idx, ty in enumerate(range(y_min_tile, y_max_tile + 1)):
        for tx_idx, tx in enumerate(range(x_min_tile, x_max_tile + 1)):
            cache_path = os.path.join(tile_cache_dir, f"tile_{zoom}_{tx}_{ty}.png")
            if not os.path.exists(cache_path):
                url = base_url.format(z=zoom, x=tx, y=ty)
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        with open(cache_path, "wb") as f:
                            f.write(resp.read())
                except Exception as e:
                    print(f"Aviso al descargar tesela ({tx}, {ty}): {e}")

            if os.path.exists(cache_path):
                try:
                    tile_img = Image.open(cache_path).convert("RGBA")
                    canvas.paste(tile_img, (tx_idx * 256, ty_idx * 256))
                except Exception as e:
                    print(f"Error procesando tesela local: {e}")

    # Coordenadas exactas en píxeles Web Mercator
    def latlon_to_global_pixels(lat_deg, lon_deg, z):
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** z
        x = (lon_deg + 180.0) / 360.0 * n * 256.0
        y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * 256.0
        return x, y

    # Esquina superior izquierda de la cuadrícula de teselas en píxeles globales
    origin_px_x = x_min_tile * 256.0
    origin_px_y = y_min_tile * 256.0

    # Píxeles exactos del bounding box dentro del canvas
    crop_px_left, crop_px_top = latlon_to_global_pixels(target_lat_max, target_lon_min, zoom)
    crop_px_right, crop_px_bottom = latlon_to_global_pixels(target_lat_min, target_lon_max, zoom)

    crop_left = int(round(crop_px_left - origin_px_x))
    crop_top = int(round(crop_px_top - origin_px_y))
    crop_right = int(round(crop_px_right - origin_px_x))
    crop_bottom = int(round(crop_px_bottom - origin_px_y))

    total_w, total_h = canvas.size
    crop_left = max(0, min(total_w - 1, crop_left))
    crop_right = max(crop_left + 1, min(total_w, crop_right))
    crop_top = max(0, min(total_h - 1, crop_top))
    crop_bottom = max(crop_top + 1, min(total_h, crop_bottom))

    cropped_img = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))

    # Redimensionar a resolución de Alta Definición 4096x4096
    final_texture = cropped_img.resize((4096, 4096), Image.Resampling.LANCZOS)
    
    os.makedirs("assets", exist_ok=True)
    out_path = "assets/satellite.png"
    final_texture.save(out_path, format="PNG")
    print(f"¡Textura satelital generada y guardada con éxito en: {out_path} (4096x4096)!")

if __name__ == '__main__':
    download_satellite_texture()
