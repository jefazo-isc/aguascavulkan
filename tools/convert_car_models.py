#!/usr/bin/env python3
"""
convert_car_models.py - TAREA 1
Convierte los GLB de Kenney (o genera procedurales) para el pipeline de StreetVulkan.
Genera models/cars/car_<type>.glb y models/cars/manifest.json.
"""
import os
import sys
import argparse
import json
import numpy as np
import trimesh
from PIL import Image

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from gltf_writer import export_glb_mesh

CAR_SPECS = {
    "sedan": {
        "source_file": "sedan.glb",
        "target_length": 4.5,
        "default_color": (0.8, 0.1, 0.1, 1.0)
    },
    "compacto": {
        "source_file": "hatchback-sports.glb",
        "target_length": 4.0,
        "default_color": (0.1, 0.5, 0.8, 1.0)
    },
    "pickup": {
        "source_file": "delivery-flat.glb",
        "target_length": 5.3,
        "default_color": (0.2, 0.2, 0.25, 1.0)
    },
    "van": {
        "source_file": "van.glb",
        "target_length": 5.5,
        "default_color": (0.9, 0.9, 0.9, 1.0)
    },
    "taxi": {
        "source_file": "taxi.glb",
        "target_length": 4.5,
        "default_color": (0.95, 0.75, 0.05, 1.0)
    },
    "bus": {
        "source_file": "garbage-truck.glb",
        "target_length": 11.0,
        "default_color": (0.1, 0.6, 0.3, 1.0)
    }
}

def create_procedural_car(car_type, spec):
    """Genera una malla procedural con cajas y cilindros en caso de fallback."""
    length = spec["target_length"]
    width = length * 0.4
    height = length * 0.35 if car_type in ["van", "bus"] else length * 0.3
    body_color = spec["default_color"]

    # Body box
    body = trimesh.creation.box(extents=[width, height * 0.6, length])
    body.apply_translation([0, height * 0.5, 0])
    
    # Cabin box
    cabin_len = length * 0.5
    cabin_h = height * 0.45
    cabin = trimesh.creation.box(extents=[width * 0.9, cabin_h, cabin_len])
    cabin.apply_translation([0, height * 0.6 + cabin_h * 0.5, -length * 0.05])
    
    # Combine body + cabin
    mesh = trimesh.util.concatenate([body, cabin])
    
    # Sample wheel radius and positions
    wheel_r = height * 0.25
    wheel_w = width * 0.15
    wheel_z_front = length * 0.3
    wheel_z_back = -length * 0.3
    wheel_x = width * 0.45
    
    wheel_positions = [
        [wheel_x, wheel_r, wheel_z_front],
        [-wheel_x, wheel_r, wheel_z_front],
        [wheel_x, wheel_r, wheel_z_back],
        [-wheel_x, wheel_r, wheel_z_back]
    ]
    
    wheels = []
    for pos in wheel_positions:
        w = trimesh.creation.cylinder(radius=wheel_r, height=wheel_w, sections=12)
        # rotate to align with X axis
        w.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
        w.apply_translation(pos)
        wheels.append(w)
        
    full_mesh = trimesh.util.concatenate([mesh] + wheels)
    
    # Vertices to gltf_writer format
    verts_out = []
    min_b, max_b = full_mesh.bounds
    z_min, z_max = min_b[2], max_b[2]
    y_min, y_max = min_b[1], max_b[1]
    x_min, x_max = min_b[0], max_b[0]
    
    # Vertices & Normals
    normals = full_mesh.vertex_normals
    positions = full_mesh.vertices
    faces = full_mesh.faces
    
    for tri in faces:
        for v_idx in tri:
            pos = positions[v_idx].tolist()
            norm = normals[v_idx].tolist()
            uv = [0.0, 0.0]
            
            x, y, z = pos
            is_front = (z > z_max - 0.15 * length) and (y > y_min + 0.2 * height) and (y < y_min + 0.7 * height) and (abs(x) > 0.2 * width)
            is_back = (z < z_min + 0.15 * length) and (y > y_min + 0.2 * height) and (y < y_min + 0.7 * height) and (abs(x) > 0.2 * width)
            
            if is_front:
                col = [1.0, 1.0, 1.0, 1.0]
                em = 0.9
            elif is_back:
                col = [1.0, 0.0, 0.0, 1.0]
                em = 0.9
            else:
                col = list(body_color)
                em = 0.0
                
            verts_out.append((pos, norm, uv, col, em))
            
    bbox = (max_b - min_b).tolist()
    return verts_out, bbox, wheel_positions, wheel_r

def convert_kenney_car(car_type, spec, kenney_dir):
    source_path = os.path.join(kenney_dir, spec["source_file"])
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"No se encontró {source_path}")
        
    scene = trimesh.load(source_path)
    
    # Texture colormap
    tex_path = os.path.join(kenney_dir, "Textures", "colormap.png")
    colormap_img = None
    if os.path.exists(tex_path):
        colormap_img = Image.open(tex_path).convert("RGBA")
        img_w, img_h = colormap_img.size
        img_data = np.array(colormap_img)
    
    # Find wheel positions and radius from scene graph
    wheel_positions = []
    wheel_radii = []
    
    # Collect meshes
    mesh_list = []
    for node in scene.graph.nodes_geometry:
        tf, gname = scene.graph[node]
        geom = scene.geometry[gname].copy()
        geom.apply_transform(tf)
        
        # Check if wheel
        if "wheel" in node.lower() or "wheel" in gname.lower():
            b = geom.bounds
            center = (b[0] + b[1]) / 2.0
            radius = (b[1][1] - b[0][1]) / 2.0
            wheel_positions.append(center)
            wheel_radii.append(radius)
            
        mesh_list.append(geom)
        
    combined = trimesh.util.concatenate(mesh_list)
    
    # Bounding box scaling
    bounds = combined.bounds
    orig_len = bounds[1][2] - bounds[0][2]
    scale = spec["target_length"] / orig_len
    
    # Scale combined mesh and wheel data
    combined.apply_scale(scale)
    
    scaled_wheels = []
    for pos in wheel_positions:
        scaled_wheels.append((pos * scale).tolist())
    scaled_wheel_radius = (float(np.mean(wheel_radii)) * scale) if wheel_radii else (spec["target_length"] * 0.08)
    
    # Align bottom Y to 0, center X and Z to 0
    min_b, max_b = combined.bounds
    center_x = (min_b[0] + max_b[0]) / 2.0
    min_y = min_b[1]
    center_z = (min_b[2] + max_b[2]) / 2.0
    
    shift = np.array([-center_x, -min_y, -center_z])
    combined.apply_translation(shift)
    
    final_wheel_positions = []
    for pos in scaled_wheels:
        final_wheel_positions.append([pos[0] + shift[0], pos[1] + shift[1], pos[2] + shift[2]])
        
    min_b, max_b = combined.bounds
    width = max_b[0] - min_b[0]
    height = max_b[1] - min_b[1]
    length = max_b[2] - min_b[2]
    
    # Extract vertices & bake lights
    verts_out = []
    positions = combined.vertices
    normals = combined.vertex_normals
    uvs = combined.visual.uv if hasattr(combined.visual, 'uv') and combined.visual.uv is not None else None
    
    for tri in combined.faces:
        for v_idx in tri:
            pos = positions[v_idx].tolist()
            norm = normals[v_idx].tolist()
            uv = uvs[v_idx].tolist() if uvs is not None else [0.0, 0.0]
            
            # Base color from texture
            col = [0.8, 0.8, 0.8, 1.0]
            if uvs is not None and colormap_img is not None:
                u, v = uv[0], uv[1]
                px = int(np.clip(u * img_w, 0, img_w - 1))
                py = int(np.clip((1.0 - v) * img_h, 0, img_h - 1))
                c = img_data[py, px] / 255.0
                col = c.tolist()
                
            x, y, z = pos
            is_front = (z > max_b[2] - 0.12 * length) and (y > min_b[1] + 0.15 * height) and (y < min_b[1] + 0.65 * height) and (abs(x) > 0.22 * width)
            is_back = (z < min_b[2] + 0.12 * length) and (y > min_b[1] + 0.15 * height) and (y < min_b[1] + 0.65 * height) and (abs(x) > 0.22 * width)
            
            if is_front:
                col = [1.0, 1.0, 1.0, 1.0]
                em = 0.9
            elif is_back:
                col = [1.0, 0.0, 0.0, 1.0]
                em = 0.9
            else:
                em = 0.0
                
            verts_out.append((pos, norm, uv, col, em))
            
    bbox = [round(float(width), 3), round(float(height), 3), round(float(length), 3)]
    return verts_out, bbox, final_wheel_positions, round(float(scaled_wheel_radius), 3)

def main():
    parser = argparse.ArgumentParser(description="Convert Kenney car models or fallback to procedural cars")
    parser.add_argument("--procedural", action="store_true", help="Force procedural car generation fallback")
    args = parser.parse_args()
    
    out_dir = "models/cars"
    os.makedirs(out_dir, exist_ok=True)
    
    kenney_dir = "assets/models/cars_src/Models/GLB format"
    use_procedural = args.procedural or not os.path.exists(kenney_dir)
    
    if use_procedural:
        print("[Convert] Usando MODO FALLBACK procedural")
    else:
        print(f"[Convert] Procesando modelos desde {kenney_dir}")
        
    manifest = {}
    
    for car_type, spec in CAR_SPECS.items():
        glb_path = os.path.join(out_dir, f"car_{car_type}.glb")
        
        try:
            if use_procedural:
                verts, bbox, wheel_pos, wheel_r = create_procedural_car(car_type, spec)
            else:
                verts, bbox, wheel_pos, wheel_r = convert_kenney_car(car_type, spec, kenney_dir)
        except Exception as e:
            print(f"[Convert] ADVERTENCIA: Falló conversión de {car_type} ({e}), recurriendo a procedural")
            verts, bbox, wheel_pos, wheel_r = create_procedural_car(car_type, spec)
            
        export_glb_mesh(glb_path, verts)
        
        # Verify with trimesh
        test_mesh = trimesh.load(glb_path)
        actual_bbox = test_mesh.extents.tolist()
        print(f"[Convert] Verificado {car_type}: bbox={actual_bbox}")
        
        manifest[car_type] = {
            "bbox": bbox,
            "ground_offset": 0.0,
            "wheel_positions": [[round(p[0], 3), round(p[1], 3), round(p[2], 3)] for p in wheel_pos],
            "wheel_radius": wheel_r
        }
        
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[Convert] Manifest guardado en {manifest_path}")

if __name__ == "__main__":
    main()
