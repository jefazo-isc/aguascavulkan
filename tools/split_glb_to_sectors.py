#!/usr/bin/env python3
"""
tools/split_glb_to_sectors.py
Divide models/aguascalientes_sector1.glb y models/chunks.json en macro-cuadrantes
modulares de 1024m x 1024m, garantizando que NINGÚN archivo supere 99 MB.
"""

import os
import sys
import json
import struct
import numpy as np

CHUNK_SIZE = 128.0
MACRO_SIZE = 1024.0
CHUNKS_PER_MACRO = int(MACRO_SIZE // CHUNK_SIZE) # 8 chunks per macro side
MAX_FILE_BYTES = 99 * 1024 * 1024 # 99 MB límite estricto solicitado por el usuario

def write_single_glb(output_path, sub_pos, sub_norm, sub_uv, sub_col, sub_em):
    vcount = len(sub_pos)
    if vcount == 0:
        return 0

    pos_bytes = sub_pos.tobytes()
    norm_bytes = sub_norm.tobytes()
    uv_bytes = sub_uv.tobytes()
    col_bytes = sub_col.tobytes()
    em_bytes = sub_em.tobytes()
    idx_bytes = np.arange(vcount, dtype=np.uint32).tobytes()

    min_pos = [float(sub_pos[:, 0].min()), float(sub_pos[:, 1].min()), float(sub_pos[:, 2].min())]
    max_pos = [float(sub_pos[:, 0].max()), float(sub_pos[:, 1].max()), float(sub_pos[:, 2].max())]

    pos_offset = 0
    norm_offset = pos_offset + len(pos_bytes)
    uv_offset = norm_offset + len(norm_bytes)
    col_offset = uv_offset + len(uv_bytes)
    em_offset = col_offset + len(col_bytes)
    idx_offset = em_offset + len(em_bytes)
    total_bin_len = idx_offset + len(idx_bytes)

    gltf_json = {
        "asset": {"version": "2.0", "generator": "StreetVulkan Modular Sector (<99MB)"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {
            "POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "COLOR_0": 3, "_EMISSION": 4
        }, "indices": 5, "mode": 4}]}],
        "accessors": [
            {"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": vcount, "type": "VEC3", "min": min_pos, "max": max_pos},
            {"bufferView": 1, "byteOffset": 0, "componentType": 5126, "count": vcount, "type": "VEC3"},
            {"bufferView": 2, "byteOffset": 0, "componentType": 5126, "count": vcount, "type": "VEC2"},
            {"bufferView": 3, "byteOffset": 0, "componentType": 5126, "count": vcount, "type": "VEC4"},
            {"bufferView": 4, "byteOffset": 0, "componentType": 5126, "count": vcount, "type": "SCALAR"},
            {"bufferView": 5, "byteOffset": 0, "componentType": 5125, "count": vcount, "type": "SCALAR"}
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

    json_str = json.dumps(gltf_json)
    json_bytes = json_str.encode('utf-8')
    while len(json_bytes) % 4 != 0:
        json_bytes += b' '

    magic = 0x46546C67
    version = 2
    total_length = 12 + 8 + len(json_bytes) + 8 + total_bin_len

    if total_length > MAX_FILE_BYTES:
        raise ValueError(f"CRÍTICO: Archivo {output_path} supera el límite de 99 MB ({total_length / 1024 / 1024:.2f} MB)")

    glb_header = struct.pack('<III', magic, version, total_length)
    chunk0_header = struct.pack('<II', len(json_bytes), 0x4E4F534A)
    chunk1_header = struct.pack('<II', total_bin_len, 0x004E4942)

    with open(output_path, "wb") as f:
        f.write(glb_header)
        f.write(chunk0_header)
        f.write(json_bytes)
        f.write(chunk1_header)
        f.write(pos_bytes)
        f.write(norm_bytes)
        f.write(uv_bytes)
        f.write(col_bytes)
        f.write(em_bytes)
        f.write(idx_bytes)

    return total_length

def main():
    glb_in = "models/aguascalientes_sector1.glb"
    chunks_in = "models/chunks.json"
    sectors_dir = "models/sectors"
    manifest_out = "models/sectors.json"

    if not os.path.exists(glb_in) or not os.path.exists(chunks_in):
        print(f"Error: {glb_in} o {chunks_in} no existen.")
        sys.exit(1)

    os.makedirs(sectors_dir, exist_ok=True)

    print(f"[División] Leyendo {chunks_in}...")
    with open(chunks_in, "r") as f:
        chunks_data = json.load(f)
    raw_chunks = chunks_data["chunks"]
    print(f"[División] {len(raw_chunks)} chunks cargados.")

    # Mapear chunks a macro-sectores (1024m)
    macro_groups = {}
    for c in raw_chunks:
        mx = int(c["cx"] // CHUNKS_PER_MACRO)
        mz = int(c["cz"] // CHUNKS_PER_MACRO)
        mkey = (mx, mz)
        if mkey not in macro_groups:
            macro_groups[mkey] = []
        macro_groups[mkey].append(c)

    print(f"[División] {len(macro_groups)} macro-sectores detectados.")

    # Mapear memoria binaria del archivo GLB monolítico
    print(f"[División] Mapeando buffers binarios de {glb_in}...")
    with open(glb_in, "rb") as f:
        magic, version, total_len = struct.unpack('<III', f.read(12))
        chunk0_len, _ = struct.unpack('<II', f.read(8))
        json_bytes = f.read(chunk0_len)
        gltf_json = json.loads(json_bytes.decode('utf-8'))
        chunk1_len, _ = struct.unpack('<II', f.read(8))
        bin_offset = f.tell()

    # bufferViews
    bvs = gltf_json["bufferViews"]
    bv_pos = bvs[0]
    bv_norm = bvs[1]
    bv_uv = bvs[2]
    bv_col = bvs[3]
    bv_em = bvs[4]

    total_verts = gltf_json["accessors"][0]["count"]
    print(f"[División] Total vértices en GLB: {total_verts:,}")

    # Cargar buffers con np.memmap para no duplicar 2.4 GB en RAM
    with open(glb_in, "rb") as f:
        pos_mmap = np.memmap(f, dtype='<f4', mode='r', offset=bin_offset + bv_pos["byteOffset"], shape=(total_verts, 3))
        norm_mmap = np.memmap(f, dtype='<f4', mode='r', offset=bin_offset + bv_norm["byteOffset"], shape=(total_verts, 3))
        uv_mmap = np.memmap(f, dtype='<f4', mode='r', offset=bin_offset + bv_uv["byteOffset"], shape=(total_verts, 2))
        col_mmap = np.memmap(f, dtype='<f4', mode='r', offset=bin_offset + bv_col["byteOffset"], shape=(total_verts, 4))
        em_mmap = np.memmap(f, dtype='<f4', mode='r', offset=bin_offset + bv_em["byteOffset"], shape=(total_verts,))

        sector_manifest_list = []
        total_sectors = len(macro_groups)
        files_written = 0
        total_bytes_written = 0

        # Ordenar macro-sectores por coordenadas para reproducibilidad
        sorted_keys = sorted(macro_groups.keys(), key=lambda k: (k[0], k[1]))

        for idx, (mx, mz) in enumerate(sorted_keys):
            chunk_list = macro_groups[(mx, mz)]
            sector_verts = sum(c["count"] for c in chunk_list)
            if sector_verts == 0:
                continue

            sec_filename = f"sector_{mx}_{mz}.glb"
            sec_rel_path = f"models/sectors/{sec_filename}"

            # Construir buffers locales para este macro-sector
            local_pos = np.empty((sector_verts, 3), dtype='<f4')
            local_norm = np.empty((sector_verts, 3), dtype='<f4')
            local_uv = np.empty((sector_verts, 2), dtype='<f4')
            local_col = np.empty((sector_verts, 4), dtype='<f4')
            local_em = np.empty((sector_verts,), dtype='<f4')

            local_chunks = []
            curr_local_v = 0

            sec_min_x, sec_min_y, sec_min_z = 1e9, 1e9, 1e9
            sec_max_x, sec_max_y, sec_max_z = -1e9, -1e9, -1e9

            for c in chunk_list:
                c_start = c["start"]
                c_count = c["count"]
                c_end = c_start + c_count

                local_pos[curr_local_v : curr_local_v + c_count] = pos_mmap[c_start : c_end]
                local_norm[curr_local_v : curr_local_v + c_count] = norm_mmap[c_start : c_end]
                local_uv[curr_local_v : curr_local_v + c_count] = uv_mmap[c_start : c_end]
                local_col[curr_local_v : curr_local_v + c_count] = col_mmap[c_start : c_end]
                local_em[curr_local_v : curr_local_v + c_count] = em_mmap[c_start : c_end]

                local_chunks.append({
                    "cx": c["cx"], "cz": c["cz"],
                    "start": curr_local_v,
                    "count": c_count,
                    "min_x": c["min_x"], "min_y": c["min_y"], "min_z": c["min_z"],
                    "max_x": c["max_x"], "max_y": c["max_y"], "max_z": c["max_z"]
                })

                sec_min_x = min(sec_min_x, c["min_x"])
                sec_min_y = min(sec_min_y, c["min_y"])
                sec_min_z = min(sec_min_z, c["min_z"])
                sec_max_x = max(sec_max_x, c["max_x"])
                sec_max_y = max(sec_max_y, c["max_y"])
                sec_max_z = max(sec_max_z, c["max_z"])

                curr_local_v += c_count

            written_bytes = write_single_glb(sec_rel_path, local_pos, local_norm, local_uv, local_col, local_em)
            mb = written_bytes / (1024 * 1024)
            total_bytes_written += written_bytes
            files_written += 1

            if mb > 99.0:
                print(f"❌ ERROR: {sec_filename} es de {mb:.2f} MB (>99 MB!)")
                sys.exit(1)

            sector_manifest_list.append({
                "mx": mx, "mz": mz,
                "file": sec_rel_path,
                "vert_count": sector_verts,
                "size_mb": round(mb, 2),
                "aabb": {
                    "min_x": round(sec_min_x, 2), "min_y": round(sec_min_y, 2), "min_z": round(sec_min_z, 2),
                    "max_x": round(sec_max_x, 2), "max_y": round(sec_max_y, 2), "max_z": round(sec_max_z, 2)
                },
                "chunks": local_chunks
            })

            if (idx + 1) % 50 == 0 or idx == total_sectors - 1:
                print(f"[Progreso] {idx + 1}/{total_sectors} macro-sectores procesados. Último: {sec_filename} ({mb:.1f} MB)")

    # Escribir manifiesto maestro
    manifest_data = {
        "macro_size": MACRO_SIZE,
        "chunk_size": CHUNK_SIZE,
        "sector_count": len(sector_manifest_list),
        "total_verts": total_verts,
        "max_allowed_file_mb": 99.0,
        "sectors": sector_manifest_list
    }

    with open(manifest_out, "w") as f:
        json.dump(manifest_data, f, indent=2)

    max_actual_mb = max(s["size_mb"] for s in sector_manifest_list)
    print("="*65)
    print(f"✅ PARTICIÓN MODULAR COMPLETADA CON ÉXITO")
    print(f"• Archivos generados: {files_written} en {sectors_dir}/")
    print(f"• Manifiesto maestro: {manifest_out}")
    print(f"• Archivo más pesado: {max_actual_mb:.2f} MB (LÍMITE ESTRICTO: < 99.0 MB)")
    print(f"• Total datos particionados: {total_bytes_written / 1024 / 1024:.2f} MB")
    print("="*65)

if __name__ == "__main__":
    main()
