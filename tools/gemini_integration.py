#!/usr/bin/env python3
"""
Integración entre gemini_obj_generator y el pipeline de generate_sector.py
==========================================================================
Permite usar Gemini como fuente complementaria para generar edificios 3D
más detallados que la extrusión procedural simple.

Uso desde generate_sector.py:
    from gemini_integration import enhance_buildings_with_gemini

    # Después de merge_and_densify_buildings:
    enhanced = enhance_buildings_with_gemini(
        all_buildings, "assets/satellite.png",
        map_bounds={"x0": x0, "z0": z0, "x1": x1, "z1": z1},
        max_buildings=20,        # Límite de llamadas a Gemini
        min_area_m2=200,         # Solo edificios grandes
        api_key=os.environ.get("GEMINI_API_KEY")
    )
"""

import os
import sys
import json
import time

# Importar el generador
from gemini_obj_generator import generate_from_patch, GeneratedObject3D


def buildings_to_patches(buildings, padding_m=5.0):
    """
    Convierte la lista de edificios del pipeline (con 'polygon', 'height', 'area_m2')
    a una lista de definiciones de parches para el generador de Gemini.
    """
    patches = []
    for b in buildings:
        poly = b["polygon"]
        if len(poly) < 3:
            continue

        # Calcular bounding box del polígono
        xs = [p[0] for p in poly]
        zs = [p[1] for p in poly]
        x0 = min(xs) - padding_m
        x1 = max(xs) + padding_m
        z0 = min(zs) - padding_m
        z1 = max(zs) + padding_m

        patches.append({
            "bbox": {"x0": x0, "z0": z0, "x1": x1, "z1": z1},
            "metadata": {
                "type": "building",
                "area_m2": b.get("area_m2", abs((x1 - x0) * (z1 - z0))),
                "stories_hint": max(1, int(b.get("height", 4.0) / 3.2)),
                "roof_color": list(b.get("roof_color", (0.85, 0.82, 0.78))),
            },
            "original_building": b  # Referencia al edificio original
        })

    return patches


def enhance_buildings_with_gemini(buildings, sat_image_path, map_bounds,
                                   max_buildings=10, min_area_m2=200.0,
                                   output_dir="models/gemini_enhanced",
                                   api_key=None):
    """
    Selecciona los edificios más grandes/importantes y genera modelos 3D
    detallados con Gemini, exportándolos como OBJ individuales.

    Los edificios pequeños se dejan con la extrusión procedural normal.

    Returns:
        Lista de rutas a los archivos OBJ generados.
    """
    # Filtrar y ordenar por área (los más grandes primero)
    candidates = [b for b in buildings if b.get("area_m2", 0) >= min_area_m2]
    candidates.sort(key=lambda b: b.get("area_m2", 0), reverse=True)
    candidates = candidates[:max_buildings]

    if not candidates:
        print("[Gemini Integration] No hay edificios que cumplan el criterio mínimo de área.")
        return []

    print(f"[Gemini Integration] Seleccionados {len(candidates)} edificios para mejora con Gemini")
    os.makedirs(output_dir, exist_ok=True)

    patches = buildings_to_patches(candidates)
    results = []

    for i, patch in enumerate(patches):
        print(f"\n[Gemini Integration] Procesando edificio {i+1}/{len(patches)} "
              f"(área: {patch['metadata']['area_m2']:.0f} m²)")

        out_path = os.path.join(output_dir, f"building_{i:04d}.obj")

        try:
            generated = generate_from_patch(
                sat_image_path,
                patch["bbox"],
                patch["metadata"],
                map_bounds=map_bounds,
                output_path=out_path,
                api_key=api_key
            )
            results.append({
                "path": out_path,
                "type": generated.object_type,
                "confidence": generated.confidence,
                "bbox": patch["bbox"],
                "ok": True
            })
        except Exception as e:
            print(f"[Gemini Integration] Error: {e}")
            results.append({
                "path": out_path,
                "error": str(e),
                "bbox": patch["bbox"],
                "ok": False
            })

        # Rate limiting
        if i < len(patches) - 1:
            time.sleep(1.5)

    # Guardar índice de resultados
    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[Gemini Integration] Índice guardado: {index_path}")

    ok_count = sum(1 for r in results if r["ok"])
    print(f"[Gemini Integration] Completado: {ok_count}/{len(patches)} edificios mejorados")

    return results
