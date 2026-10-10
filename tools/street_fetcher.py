#!/usr/bin/env python3
"""
street_fetcher.py
Extractor multifuente de fotos a nivel de calle (Street View / KartaView).
No requiere API Keys de pago ni tarjetas de crédito.
"""

import sys
import os
import json
import re
import io
import argparse
import requests
from PIL import Image

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.google.com/maps/'
}

def find_gsv_panorama(lat: float, lon: float, radius: int = 50):
    """
    Localiza el panorama de Google Street View más cercano a (lat, lon) usando
    el endpoint público de metadatos GeoPhotoService.
    """
    url = (
        f"https://maps.googleapis.com/maps/api/js/GeoPhotoService.SingleImageSearch"
        f"?pb=!1m5!1sapiv3!5sUS!11m2!1m1!1b0!2m4!1m2!3d{lat}!4d{lon}!2d{radius}"
        f"!3m10!2m2!1sen!2sUS!9m1!1e2!11m4!1m3!1e2!2b1!3e2!4m10!1e1!1e2!1e3!1e4!1e8!1e6!5m1!1e2!6m1!1e2"
        f"&callback=_xdc_._0"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        
        raw = resp.text
        start = raw.find('(') + 1
        end = raw.rfind(')')
        if start <= 0 or end <= 0:
            return None
        
        data = json.loads(raw[start:end].strip())
        pano_id = data[1][1][1]
        res_lat = data[1][5][0][1][0][2]
        res_lon = data[1][5][0][1][0][3]
        
        # Heading / orientación original de la cámara
        heading = 0.0
        try:
            heading = float(data[1][5][0][2][2][0])
        except Exception:
            pass

        return {
            "service": "GoogleStreetView",
            "pano_id": pano_id,
            "lat": res_lat,
            "lon": res_lon,
            "heading": heading
        }
    except Exception as e:
        print(f"[Aviso] Error consultando GSV: {e}", file=sys.stderr)
        return None

def download_gsv_panorama(pano_id: str, zoom: int = 1, output_path: str = None) -> Image.Image:
    """
    Descarga y ensambla las teselas (tiles) de 512x512 del panorama equirrectangular.
    zoom=1 -> 1024x512 (2x1 tiles)
    zoom=2 -> 2048x1024 (4x2 tiles)
    zoom=3 -> 4096x2048 (8x4 tiles)
    """
    zoom_dims = {
        1: (2, 1),
        2: (4, 2),
        3: (8, 4)
    }
    cols, rows = zoom_dims.get(zoom, (2, 1))
    tile_w, tile_h = 512, 512

    full_img = Image.new('RGB', (cols * tile_w, rows * tile_h))

    for y in range(rows):
        for x in range(cols):
            url = f"https://streetviewpixels-pa.googleapis.com/v1/tile?cb_client=maps_sv.tactile&panoid={pano_id}&x={x}&y={y}&zoom={zoom}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                tile = Image.open(io.BytesIO(resp.content))
                full_img.paste(tile, (x * tile_w, y * tile_h))
            else:
                print(f"[Aviso] No se pudo descargar tile ({x}, {y})", file=sys.stderr)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        full_img.save(output_path, quality=95)
        print(f"[StreetFetcher] Panorama guardado en: {output_path} ({full_img.size[0]}x{full_img.size[1]})")

    return full_img

def find_kartaview_photo(lat: float, lon: float, radius: int = 200):
    """
    Servicio secundario open-source (KartaView / OpenStreetCam).
    """
    url = f"https://api.kartaview.org/2.0/photo/?lat={lat}&lng={lon}&radius={radius}"
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get('result', {}).get('data', [])
            if data:
                photo = data[0]
                img_url = photo.get('fileurl_l') or photo.get('fileurl_m') or photo.get('fileurl_s')
                return {
                    "service": "KartaView",
                    "id": photo.get('id'),
                    "lat": float(photo.get('lat', lat)),
                    "lon": float(photo.get('lng', lon)),
                    "heading": float(photo.get('heading', 0.0)),
                    "image_url": img_url
                }
    except Exception as e:
        print(f"[Aviso] Error consultando KartaView: {e}", file=sys.stderr)
    return None

def fetch_street_image(lat: float, lon: float, zoom: int = 1, output_dir: str = "assets/streetview"):
    """
    Función principal que intenta GSV y hace fallback a KartaView si es necesario.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Intentar Google Street View (Tiles públicos)
    meta = find_gsv_panorama(lat, lon)
    if meta:
        out_name = f"gsv_{meta['pano_id']}_z{zoom}.jpg"
        out_path = os.path.join(output_dir, out_name)
        img = download_gsv_panorama(meta['pano_id'], zoom=zoom, output_path=out_path)
        meta['file_path'] = out_path
        meta['width'] = img.size[0]
        meta['height'] = img.size[1]
        
        meta_path = out_path.replace('.jpg', '.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)
        return meta

    # 2. Fallback: KartaView
    print("[StreetFetcher] No se encontró GSV cercano, intentando KartaView...", file=sys.stderr)
    kv_meta = find_kartaview_photo(lat, lon)
    if kv_meta and kv_meta.get('image_url'):
        out_name = f"kartaview_{kv_meta['id']}.jpg"
        out_path = os.path.join(output_dir, out_name)
        resp = requests.get(kv_meta['image_url'], timeout=15)
        if resp.status_code == 200:
            with open(out_path, 'wb') as f:
                f.write(resp.content)
            kv_meta['file_path'] = out_path
            return kv_meta

    print("[StreetFetcher] No se encontraron fotos a nivel de calle en esta ubicación.", file=sys.stderr)
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Street Photo Fetcher (Open Access)")
    parser.add_argument("--lat", type=float, default=21.8807, help="Latitud")
    parser.add_argument("--lon", type=float, default=-102.2965, help="Longitud")
    parser.add_argument("--zoom", type=int, default=1, choices=[1, 2, 3], help="Nivel de resolución/zoom")
    parser.add_argument("--output-dir", type=str, default="assets/streetview", help="Directorio destino")

    args = parser.parse_args()
    print(f"[StreetFetcher] Buscando fotos callejeras en ({args.lat}, {args.lon})...")
    res = fetch_street_image(args.lat, args.lon, zoom=args.zoom, output_dir=args.output_dir)
    if res:
        print("[StreetFetcher] ✓ Adquisición completada:")
        print(json.dumps(res, indent=2))
    else:
        sys.exit(1)
