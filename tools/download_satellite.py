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
import argparse
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # Permitir ensamblaje de imágenes gigantes en alta resolución

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

def latlon_to_global_pixels(lat_deg, lon_deg, z):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** z
    x = (lon_deg + 180.0) / 360.0 * n * 256.0
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * 256.0
    return x, y

def download_tile(base_url, headers, tile_cache_dir, zoom, tx, ty):
    cache_path = os.path.join(tile_cache_dir, f"tile_{zoom}_{tx}_{ty}.png")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 500:
        return tx, ty, cache_path

    url = base_url.format(z=zoom, x=tx, y=ty)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
                if len(data) > 500:
                    with open(cache_path, "wb") as f:
                        f.write(data)
                    return tx, ty, cache_path
        except Exception:
            time.sleep(0.3 * (attempt + 1))
    return tx, ty, None

def download_satellite_texture(min_lon=-102.3700, min_lat=21.8000, max_lon=-102.2450, max_lat=21.9500,
                               zoom=17, target_res=8192, out_path="assets/satellite.png", max_workers=32):
    origin_lat = 21.8807
    origin_lon = -102.2965

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

    print("=" * 68)
    print(f"  DESCARGADOR SATELITAL HD - TERCER ANILLO AGUASCALIENTES")
    print(f"  Nivel de Zoom: {zoom} (Resolución sub-métrica) | Target: {target_res}x{target_res}")
    print("=" * 68)

    x_min_tile, y_min_tile = deg2num(target_lat_max, target_lon_min, zoom)
    x_max_tile, y_max_tile = deg2num(target_lat_min, target_lon_max, zoom)

    tiles_x = x_max_tile - x_min_tile + 1
    tiles_y = y_max_tile - y_min_tile + 1
    total_tiles = tiles_x * tiles_y
    raw_w = tiles_x * 256
    raw_h = tiles_y * 256
    print(f"[Satélite] Cuadrícula: {tiles_x} x {tiles_y} = {total_tiles} teselas ({raw_w} x {raw_h} px crudos)")

    base_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    headers = {'User-Agent': 'StreetVulkanSatellite/2.0'}

    tile_cache_dir = "models/tile_cache"
    os.makedirs(tile_cache_dir, exist_ok=True)

    # Lista de todas las coordenadas de tesela requeridas
    tile_coords = []
    for ty in range(y_min_tile, y_max_tile + 1):
        for tx in range(x_min_tile, x_max_tile + 1):
            tile_coords.append((tx, ty))

    print(f"[Satélite] Descargando/Verificando teselas con {max_workers} hilos...")
    tile_paths = {}
    downloaded_count = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_tile, base_url, headers, tile_cache_dir, zoom, tx, ty): (tx, ty)
                   for tx, ty in tile_coords}
        for fut in as_completed(futures):
            tx, ty, path = fut.result()
            if path:
                tile_paths[(tx, ty)] = path
            downloaded_count += 1
            if downloaded_count % 250 == 0 or downloaded_count == total_tiles:
                pct = (downloaded_count / total_tiles) * 100.0
                elapsed = time.time() - t0
                speed = downloaded_count / max(0.1, elapsed)
                print(f"  [{pct:5.1f}%] {downloaded_count}/{total_tiles} teselas procesadas ({speed:.1f} teselas/s)...")

    print(f"[Satélite] Ensamblando lienzo de alta definición ({raw_w} x {raw_h} px)...")
    canvas = Image.new("RGBA", (raw_w, raw_h))

    for ty_idx, ty in enumerate(range(y_min_tile, y_max_tile + 1)):
        for tx_idx, tx in enumerate(range(x_min_tile, x_max_tile + 1)):
            cpath = tile_paths.get((tx, ty))
            if cpath and os.path.exists(cpath):
                try:
                    tile_img = Image.open(cpath).convert("RGBA")
                    canvas.paste(tile_img, (tx_idx * 256, ty_idx * 256))
                except Exception as e:
                    print(f"Error pegando tesela ({tx}, {ty}): {e}")

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

    print(f"[Satélite] Recortando coordenadas geográficas: ({crop_left}, {crop_top}) a ({crop_right}, {crop_bottom}) = {crop_right-crop_left}x{crop_bottom-crop_top} px...")
    cropped_img = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))

    # Redimensionar con filtro Lanczos para máxima nitidez y anti-aliasing
    print(f"[Satélite] Redimensionando a {target_res}x{target_res} con filtro Lanczos...")
    final_texture = cropped_img.resize((target_res, target_res), Image.Resampling.LANCZOS)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    print(f"[Satélite] Guardando en {out_path}...")
    final_texture.save(out_path, format="PNG", compress_level=1)
    file_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"¡Textura satelital generada y guardada con éxito en: {out_path} ({target_res}x{target_res}, {file_mb:.1f} MB)!")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Descargador de textura satelital en alta definición para Tercer Anillo")
    parser.add_argument("--zoom", type=int, default=16, help="Nivel de zoom de teselas satelitales (16 o 17)")
    parser.add_argument("--res", type=int, default=8192, help="Resolución cuadrada de salida (ej. 8192 o 16384)")
    parser.add_argument("--workers", type=int, default=32, help="Hilos concurrentes para descarga")
    args = parser.parse_args()

    download_satellite_texture(zoom=args.zoom, target_res=args.res, max_workers=args.workers)
