#!/usr/bin/env python3
"""
gltf_writer.py - FASE 3
- Incluye _EMISSION por vértice
- Exporta traffic_signals.json con lenses anidados (start/count globales)
- Exporta chunks.json con metadatos de chunks para frustum culling
"""
import json
import struct

# Tamaño de cada chunk en metros (cuadrado en X/Z)
CHUNK_SIZE = 128.0

def export_chunks_json(output_path, vertex_list):
    """
    Agrupa triángulos (grupos de 3 vértices consecutivos) en chunks espaciales.
    El chunk de un triángulo se determina por el centroide de sus 3 vértices.
    Preserva integridad de triángulos — nunca separa los 3 vértices de un tri.
    Reordena vertex_list in-place y devuelve dict {old_tri_start: new_tri_start}.
    """
    if not vertex_list:
        return {}

    n = len(vertex_list)
    # Asegurar múltiplo de 3
    if n % 3 != 0:
        print(f"[Chunks] ADVERTENCIA: {n} vértices no es múltiplo de 3, truncando")
        n = (n // 3) * 3

    from collections import defaultdict
    chunk_tris = defaultdict(list)  # (cx, cz) → [tri_index, ...]  (tri_index = i//3)

    for i in range(0, n, 3):
        # Centroide del triángulo en X/Z
        x = (vertex_list[i][0][0] + vertex_list[i+1][0][0] + vertex_list[i+2][0][0]) / 3.0
        z = (vertex_list[i][0][2] + vertex_list[i+1][0][2] + vertex_list[i+2][0][2]) / 3.0
        cx = int(x // CHUNK_SIZE)
        cz = int(z // CHUNK_SIZE)
        chunk_tris[(cx, cz)].append(i // 3)

    new_order = []
    chunk_meta = []
    old_to_new = {}  # old_vert_start → new_vert_start (para lentes de semáforos)

    for (cx, cz), tri_indices in sorted(chunk_tris.items()):
        start_vert = len(new_order)
        min_x = min_y = min_z =  1e18
        max_x = max_y = max_z = -1e18

        for ti in tri_indices:
            old_v = ti * 3
            new_v = len(new_order)
            old_to_new[old_v] = new_v
            for k in range(3):
                v = vertex_list[old_v + k]
                new_order.append(v)
                px, py, pz = v[0][0], v[0][1], v[0][2]
                if px < min_x: min_x = px
                if py < min_y: min_y = py
                if pz < min_z: min_z = pz
                if px > max_x: max_x = px
                if py > max_y: max_y = py
                if pz > max_z: max_z = pz

        count_verts = len(new_order) - start_vert
        min_y -= 1.0
        max_y += 15.0
        chunk_meta.append({
            "cx": cx, "cz": cz,
            "start": start_vert, "count": count_verts,
            "min_x": round(min_x, 2), "min_y": round(min_y, 2), "min_z": round(min_z, 2),
            "max_x": round(max_x, 2), "max_y": round(max_y, 2), "max_z": round(max_z, 2),
        })

    vertex_list[:] = new_order

    data = {"chunk_size": CHUNK_SIZE, "chunks": chunk_meta}
    with open(output_path, "w") as f:
        json.dump(data, f)
    total_verts = sum(c["count"] for c in chunk_meta)
    print(f"[Chunks] Exportados {len(chunk_meta)} chunks ({CHUNK_SIZE:.0f}m) "
          f"con {total_verts} vértices → {output_path}")
    return old_to_new

def export_glb_mesh(output_path, vertex_list):
    vertex_count = len(vertex_list)
    if vertex_count == 0:
        print("[glTF] No hay vértices")
        return
    pos_bytes = bytearray(); norm_bytes = bytearray(); uv_bytes = bytearray()
    col_bytes = bytearray(); em_bytes = bytearray(); idx_bytes = bytearray()
    min_pos = [float('inf')]*3; max_pos = [float('-inf')]*3
    for i, (pos, norm, uv, col, em) in enumerate(vertex_list):
        for k in range(3):
            if pos[k] < min_pos[k]: min_pos[k] = pos[k]
            if pos[k] > max_pos[k]: max_pos[k] = pos[k]
        pos_bytes.extend(struct.pack('<fff', float(pos[0]), float(pos[1]), float(pos[2])))
        norm_bytes.extend(struct.pack('<fff', float(norm[0]), float(norm[1]), float(norm[2])))
        uv_bytes.extend(struct.pack('<ff', float(uv[0]), float(uv[1])))
        col_bytes.extend(struct.pack('<ffff', float(col[0]), float(col[1]), float(col[2]), float(col[3])))
        em_bytes.extend(struct.pack('<f', float(em)))
        idx_bytes.extend(struct.pack('<I', i))
    bin_data = bytearray()
    def align4(b):
        while len(b) % 4 != 0: b.append(0)
    pos_offset = len(bin_data); bin_data.extend(pos_bytes); align4(bin_data)
    norm_offset = len(bin_data); bin_data.extend(norm_bytes); align4(bin_data)
    uv_offset = len(bin_data); bin_data.extend(uv_bytes); align4(bin_data)
    col_offset = len(bin_data); bin_data.extend(col_bytes); align4(bin_data)
    em_offset = len(bin_data); bin_data.extend(em_bytes); align4(bin_data)
    idx_offset = len(bin_data); bin_data.extend(idx_bytes); align4(bin_data)
    total_bin_len = len(bin_data)
    gltf_json = {
        "asset": {"version": "2.0", "generator": "StreetVulkan + emission"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "COLOR_0": 3, "_EMISSION": 4}, "indices": 5, "mode": 4}]}],
        "accessors": [
            {"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": vertex_count, "type": "VEC3", "min": min_pos, "max": max_pos},
            {"bufferView": 1, "byteOffset": 0, "componentType": 5126, "count": vertex_count, "type": "VEC3"},
            {"bufferView": 2, "byteOffset": 0, "componentType": 5126, "count": vertex_count, "type": "VEC2"},
            {"bufferView": 3, "byteOffset": 0, "componentType": 5126, "count": vertex_count, "type": "VEC4"},
            {"bufferView": 4, "byteOffset": 0, "componentType": 5126, "count": vertex_count, "type": "SCALAR"},
            {"bufferView": 5, "byteOffset": 0, "componentType": 5125, "count": vertex_count, "type": "SCALAR"}
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset, "byteLength": len(pos_bytes)},
            {"buffer": 0, "byteOffset": norm_offset, "byteLength": len(norm_bytes)},
            {"buffer": 0, "byteOffset": uv_offset, "byteLength": len(uv_bytes)},
            {"buffer": 0, "byteOffset": col_offset, "byteLength": len(col_bytes)},
            {"buffer": 0, "byteOffset": em_offset, "byteLength": len(em_bytes)},
            {"buffer": 0, "byteOffset": idx_offset, "byteLength": len(idx_bytes)}
        ],
        "buffers": [{"byteLength": total_bin_len}]
    }
    json_str = json.dumps(gltf_json); json_bytes = json_str.encode('utf-8')
    while len(json_bytes) % 4 != 0: json_bytes += b' '
    magic = 0x46546C67; version = 2; total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    glb_header = struct.pack('<III', magic, version, total_length)
    chunk0_header = struct.pack('<II', len(json_bytes), 0x4E4F534A)
    chunk1_header = struct.pack('<II', len(bin_data), 0x004E4942)
    with open(output_path, "wb") as f:
        f.write(glb_header); f.write(chunk0_header); f.write(json_bytes); f.write(chunk1_header); f.write(bin_data)
    print(f"[glTF] Guardado: {output_path} ({total_length/1024/1024:.2f} MB, {vertex_count} verts)")

def export_traffic_signals_json(output_path, signal_metadata_list):
    """
    FIXED: Exporta lenses con start global y count.
    Formato por línea:
    {"id":0, "intersection":0, "phase":0, "x":.., "y":.., "z":.., "lenses":{"red":{"start":123,"count":6},"amber":{"start":129,"count":6},"green":{"start":135,"count":6}}}
    """
    with open(output_path, "w") as f:
        for sig in signal_metadata_list:
            # Asegurar que lenses existe
            if "lenses" not in sig:
                sig["lenses"] = {}
            # Escribir como JSON de una línea (JSONL)
            f.write(json.dumps(sig) + "\n")
    print(f"[Tráfico] Exportados {len(signal_metadata_list)} semáforos con lenses globales a {output_path}")
