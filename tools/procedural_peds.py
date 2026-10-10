#!/usr/bin/env python3
"""
procedural_peds.py - TAREA 2
Genera peatones low-poly procedurales (sin esqueleto) en models/peds/ped.glb + manifest.json.
4 variantes de cuerpo con paletas de colores. Altura total 1.75m, pies en y=0.
"""
import os
import sys
import json
import trimesh
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from procedural_props import make_box, make_icosahedron
from gltf_writer import export_glb_mesh

COLOR_PALETTES = [
    {
        "skin": (0.92, 0.75, 0.65, 1.0),
        "hair": (0.2, 0.15, 0.1, 1.0),
        "shirt": (0.8, 0.2, 0.2, 1.0),
        "pants": (0.2, 0.3, 0.6, 1.0),
        "shoes": (0.1, 0.1, 0.1, 1.0)
    },
    {
        "skin": (0.80, 0.60, 0.45, 1.0),
        "hair": (0.1, 0.08, 0.05, 1.0),
        "shirt": (0.2, 0.6, 0.8, 1.0),
        "pants": (0.15, 0.15, 0.2, 1.0),
        "shoes": (0.8, 0.8, 0.8, 1.0)
    },
    {
        "skin": (0.95, 0.82, 0.72, 1.0),
        "hair": (0.8, 0.6, 0.2, 1.0),
        "shirt": (0.2, 0.7, 0.3, 1.0),
        "pants": (0.7, 0.65, 0.5, 1.0),
        "shoes": (0.3, 0.2, 0.1, 1.0)
    },
    {
        "skin": (0.55, 0.38, 0.25, 1.0),
        "hair": (0.05, 0.05, 0.05, 1.0),
        "shirt": (0.9, 0.8, 0.1, 1.0),
        "pants": (0.25, 0.25, 0.3, 1.0),
        "shoes": (0.2, 0.2, 0.25, 1.0)
    }
]

def build_pedestrian_vertices(palette, x_offset=0.0):
    """
    Construye la lista de vértices (pos, norm, uv, col, em) para un peatón.
    Altura total 1.75m, pies en Y=0.
    """
    verts = []
    
    # 1. Pies/Zapatos (Y: 0.0 a 0.05)
    # Pie izquierdo
    verts.extend(make_box(x_offset - 0.11, 0.025, 0.02, 0.14, 0.05, 0.24, color=palette["shoes"]))
    # Pie derecho
    verts.extend(make_box(x_offset + 0.11, 0.025, 0.02, 0.14, 0.05, 0.24, color=palette["shoes"]))
    
    # 2. Piernas/Pantalones (Y: 0.05 a 0.90)
    # Pierna izquierda
    verts.extend(make_box(x_offset - 0.11, 0.475, 0.0, 0.15, 0.85, 0.18, color=palette["pants"]))
    # Pierna derecha
    verts.extend(make_box(x_offset + 0.11, 0.475, 0.0, 0.15, 0.85, 0.18, color=palette["pants"]))
    
    # 3. Torso/Camisa (Y: 0.90 a 1.45)
    verts.extend(make_box(x_offset, 1.175, 0.0, 0.40, 0.55, 0.22, color=palette["shirt"]))
    
    # 4. Brazos (Y: 0.95 a 1.45)
    verts.extend(make_box(x_offset - 0.25, 1.175, 0.0, 0.10, 0.50, 0.10, color=palette["skin"]))
    verts.extend(make_box(x_offset + 0.25, 1.175, 0.0, 0.10, 0.50, 0.10, color=palette["skin"]))
    
    # 5. Cabeza (Y: 1.45 a 1.72) -> icosaedro r=0.13m, centro Y=1.58m
    verts.extend(make_icosahedron(x_offset, 1.58, 0.0, 0.13, color=palette["skin"]))
    
    # 6. Cabello (Y: 1.62 a 1.75) -> icosaedro r=0.11m, centro Y=1.65m
    verts.extend(make_icosahedron(x_offset, 1.65, -0.02, 0.11, color=palette["hair"]))
    
    return verts

def convert_verts_to_trimesh(verts_tuples):
    positions = []
    normals = []
    colors = []
    for pos, norm, uv, col, em in verts_tuples:
        positions.append(pos)
        normals.append(norm)
        colors.append(col)
        
    positions = np.array(positions, dtype=np.float32)
    normals = np.array(normals, dtype=np.float32)
    colors = np.array(colors, dtype=np.float32)
    
    faces = np.arange(len(positions), dtype=np.int32).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=positions, faces=faces, vertex_normals=normals, vertex_colors=colors, process=False)
    return mesh

def main():
    out_dir = "models/peds"
    os.makedirs(out_dir, exist_ok=True)
    glb_path = os.path.join(out_dir, "ped.glb")
    manifest_path = os.path.join(out_dir, "manifest.json")
    
    trimesh_meshes = []
    all_verts = []
    
    for i, palette in enumerate(COLOR_PALETTES):
        # 4 variantes separadas en X por 1.0m para exportación multi-mesh
        verts = build_pedestrian_vertices(palette, x_offset=float(i) * 1.0)
        tm = convert_verts_to_trimesh(verts)
        tm.metadata['name'] = f"ped_var{i}"
        trimesh_meshes.append(tm)
        all_verts.extend(verts)
        
    # Exportar GLB con trimesh.Scene para 4 meshes explícitos
    scene = trimesh.Scene(trimesh_meshes)
    glb_bytes = scene.export(file_type='glb')
    with open(glb_path, 'wb') as f:
        f.write(glb_bytes)
        
    print(f"[Pedestrians] Exportado GLB con 4 variantes de peatones → {glb_path}")
    
    # Verificación con trimesh
    loaded = trimesh.load(glb_path)
    print(f"[Pedestrians] Reabierto ped.glb sin error. Geometrías: {len(loaded.geometry)}")
    
    # Medir altura de la primera variante
    var0_mesh = build_pedestrian_vertices(COLOR_PALETTES[0], x_offset=0.0)
    tm0 = convert_verts_to_trimesh(var0_mesh)
    min_b, max_b = tm0.bounds
    height = max_b[1] - min_b[1]
    bbox = (max_b - min_b).tolist()
    
    print(f"[Pedestrians] Variante 0: min_y={min_b[1]:.3f}, max_y={max_b[1]:.3f}, altura={height:.3f}m")
    assert abs(height - 1.75) <= 0.05, f"La altura {height} se sale del rango 1.75m ± 0.05"
    assert abs(min_b[1]) < 0.001, f"Los pies deben estar en Y=0, encontrado {min_b[1]}"
    
    manifest = {
        "bbox": [round(b, 3) for b in bbox],
        "ground_offset": 0.0,
        "variants_count": len(COLOR_PALETTES)
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[Pedestrians] Manifest guardado → {manifest_path}")

if __name__ == "__main__":
    main()
