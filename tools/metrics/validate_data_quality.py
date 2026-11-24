#!/usr/bin/env python3
"""Auditor de Calidad de Datos (ISO/IEC 25012 y 25024) para StreetVulkan."""

import csv
import glob
import json
import math
import os
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def check_traffic_signals(path):
    required = {"id", "intersection", "phase", "x", "y", "z"}
    total = 0
    valid = 0
    invalid_coords = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            obj = json.loads(line)
            if not required.issubset(obj.keys()):
                continue
            coords = [obj["x"], obj["y"], obj["z"]]
            if any(c is None or not isinstance(c, (int, float)) or not math.isfinite(c) for c in coords):
                invalid_coords += 1
                continue
            valid += 1
    completeness = (valid / total) if total else 0.0
    return {
        "dataset": "models/traffic_signals.json",
        "records": total,
        "valid": valid,
        "invalid_coords": invalid_coords,
        "completeness": completeness,
        "ok": total > 0 and completeness >= 0.99,
    }


def check_classified_buildings(path):
    required = {"id", "type", "label", "color"}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    total = len(data)
    valid = 0
    for item in data:
        if (
            isinstance(item, dict)
            and required.issubset(item.keys())
            and isinstance(item["color"], list)
            and len(item["color"]) == 3
            and all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0 for c in item["color"])
        ):
            valid += 1
    completeness = (valid / total) if total else 0.0
    return {
        "dataset": "models/classified_buildings.json",
        "records": total,
        "valid": valid,
        "completeness": completeness,
        "ok": total > 0 and completeness >= 0.99,
    }


def check_sectors_consistency(sectors_json_path):
    with open(sectors_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    sectors = data.get("sectors", [])
    total = len(sectors)
    existing = 0
    missing_files = []
    for sec in sectors:
        rel = sec.get("file", "")
        full = os.path.join(ROOT, rel)
        if rel and os.path.isfile(full):
            existing += 1
        else:
            missing_files.append(rel)
    consistency = (existing / total) if total else 0.0
    return {
        "dataset": "models/sectors.json -> models/sectors/*.glb",
        "records": total,
        "existing_glb": existing,
        "missing": len(missing_files),
        "consistency": consistency,
        "ok": total > 0 and consistency == 1.0,
    }


def check_road_network_bin(bin_path):
    size = os.path.getsize(bin_path)
    with open(bin_path, "rb") as f:
        magic = f.read(4)
        n_nodes, n_edges, n_points = struct.unpack("<III", f.read(12))
    # RoadNode = 20 bytes, RoadEdge = 28 bytes, RoadPoint = 12 bytes
    expected_size = 16 + n_nodes * 20 + n_edges * 28 + n_points * 12
    return {
        "dataset": "models/road_network.bin",
        "magic": magic.decode("ascii", errors="replace"),
        "nodes": n_nodes,
        "edges": n_edges,
        "points": n_points,
        "actual_bytes": size,
        "expected_bytes": expected_size,
        "ok": magic == b"RGP1" and size == expected_size and n_nodes > 0 and n_edges > 0,
    }


def check_chunks_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    chunks = data.get("chunks", [])
    chunk_size = data.get("chunk_size", 0)
    valid = 0
    for ch in chunks:
        if (
            ch.get("count", 0) > 0
            and ch.get("min_x", 1) <= ch.get("max_x", 0)
            and ch.get("min_y", 1) <= ch.get("max_y", 0)
            and ch.get("min_z", 1) <= ch.get("max_z", 0)
        ):
            valid += 1
    consistency = (valid / len(chunks)) if chunks else 0.0
    return {
        "dataset": "models/chunks.json",
        "chunk_size": chunk_size,
        "records": len(chunks),
        "valid_aabbs": valid,
        "consistency": consistency,
        "ok": chunk_size > 0 and len(chunks) > 0 and consistency == 1.0,
    }


def check_dem_caches(pattern):
    files = sorted(glob.glob(pattern))
    total_pts = 0
    valid_pts = 0
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            grid = json.load(f)
        rows = grid if isinstance(grid, list) else []
        for row in rows:
            vals = row if isinstance(row, list) else [row]
            for v in vals:
                total_pts += 1
                if isinstance(v, (int, float)) and math.isfinite(v) and 1000.0 <= v <= 3000.0:
                    valid_pts += 1
    accuracy = (valid_pts / total_pts) if total_pts else 0.0
    return {
        "dataset": "models/dem_*.json",
        "files": len(files),
        "samples": total_pts,
        "valid_samples": valid_pts,
        "accuracy": round(accuracy, 4),
        "ok": len(files) > 0 and accuracy >= 0.99,
    }


def check_manifests():
    cars_manifest = os.path.join(ROOT, "models/cars/manifest.json")
    peds_manifest = os.path.join(ROOT, "models/peds/manifest.json")
    with open(cars_manifest, "r", encoding="utf-8") as f:
        cars = json.load(f)
    with open(peds_manifest, "r", encoding="utf-8") as f:
        peds = json.load(f)
    missing = 0
    for car_name in cars.keys():
        glb = os.path.join(ROOT, f"models/cars/car_{car_name}.glb")
        if not os.path.isfile(glb):
            missing += 1
    if not os.path.isfile(os.path.join(ROOT, "models/peds/ped.glb")):
        missing += 1
    return {
        "dataset": "models/{cars,peds}/manifest.json",
        "car_types": len(cars),
        "ped_variants": peds.get("variants_count", 0),
        "missing_glb": missing,
        "ok": len(cars) > 0 and missing == 0,
    }


def check_denue_csv(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    non_empty = [r for r in rows if any(c.strip() for c in r)]
    return {
        "dataset": "models/diccionario_de_datos/denue_diccionario_de_datos.csv",
        "rows": len(non_empty),
        "ok": len(non_empty) > 1,
    }


def main():
    results = [
        check_traffic_signals(os.path.join(ROOT, "models/traffic_signals.json")),
        check_classified_buildings(os.path.join(ROOT, "models/classified_buildings.json")),
        check_sectors_consistency(os.path.join(ROOT, "models/sectors.json")),
        check_road_network_bin(os.path.join(ROOT, "models/road_network.bin")),
        check_chunks_json(os.path.join(ROOT, "models/chunks.json")),
        check_dem_caches(os.path.join(ROOT, "models/dem_*.json")),
        check_manifests(),
        check_denue_csv(os.path.join(ROOT, "models/diccionario_de_datos/denue_diccionario_de_datos.csv")),
    ]

    print("=== Auditoria ISO/IEC 25012 & 25024 (Calidad de Datos) ===")
    all_ok = True
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        all_ok = all_ok and r["ok"]
        summary = ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("dataset", "ok"))
        print(f"[{status}] {r['dataset']} -> {summary}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
