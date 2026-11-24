#!/usr/bin/env python3
"""
tools/split_satellite_texture.py
Divide la ortofoto satelital monolítica (assets/satellite.png de 161 MB)
en 4 cuadrantes modulares (4096 x 4096 cada uno, < 45 MB).
"""
import os
import sys
from PIL import Image

def split_satellite(src_path="assets/satellite.png", out_dir="assets"):
    if not os.path.exists(src_path):
        print(f"Error: No se encontró {src_path}")
        return False

    print(f"[División] Abriendo ortofoto {src_path}...")
    img = Image.open(src_path)
    w, h = img.size
    print(f"[División] Dimensiones originales: {w}x{h} ({img.mode}), tamaño en disco: {os.path.getsize(src_path)/(1024*1024):.2f} MB")

    half_w = w // 2
    half_h = h // 2

    quadrants = [
        ("satellite_0_0.png", (0, 0, half_w, half_h), "Noroeste (Top-Left)"),
        ("satellite_1_0.png", (half_w, 0, w, half_h), "Noreste (Top-Right)"),
        ("satellite_0_1.png", (0, half_h, half_w, h), "Suroeste (Bottom-Left)"),
        ("satellite_1_1.png", (half_w, half_h, w, h), "Sureste (Bottom-Right)")
    ]

    os.makedirs(out_dir, exist_ok=True)
    generated = []

    for fname, box, desc in quadrants:
        out_path = os.path.join(out_dir, fname)
        print(f"[División] Procesando cuadrante {desc}: {fname} (box: {box})...")
        crop = img.crop(box)
        crop.save(out_path, format="PNG", optimize=True)
        fsize_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"  ✅ Guardado: {out_path} ({crop.size[0]}x{crop.size[1]}, {fsize_mb:.2f} MB) < 99 MB")
        generated.append(out_path)

    print("=" * 60)
    print("✅ DIVISIÓN DE ORTOFOTO SATELITAL COMPLETADA")
    for p in generated:
        print(f"  • {p}: {os.path.getsize(p)/(1024*1024):.2f} MB")
    print("=" * 60)
    return True

if __name__ == "__main__":
    split_satellite()
