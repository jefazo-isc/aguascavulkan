#!/usr/bin/env python3
"""Verificador automatizado de metricas ISO/IEC 25023 para StreetVulkan."""

from concurrent.futures import ThreadPoolExecutor
import contextlib
import glob
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOOLS_DIR = os.path.join(ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)


def run_cmd(cmd, cwd=ROOT):
    t0 = time.monotonic()
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    dt = time.monotonic() - t0
    return res.returncode, res.stdout + res.stderr, dt


def check_shader_compilation():
    if not shutil.which("glslangValidator"):
        return {
            "id": "Q-CMP-02",
            "name": "Compilacion SPIR-V",
            "ok": False,
            "detail": "glslangValidator no encontrado",
        }
    shader_dir = os.path.join(ROOT, "shaders")
    shaders = [
        os.path.join(shader_dir, fn)
        for fn in sorted(os.listdir(shader_dir))
        if fn.endswith((".vert", ".frag"))
    ]
    errors = 0
    with tempfile.TemporaryDirectory(prefix="sv_spv_") as tmpdir:
        for idx, sh in enumerate(shaders):
            out_spv = os.path.join(tmpdir, f"shader_{idx}.spv")
            rc, _, _ = run_cmd(["glslangValidator", "-V", sh, "-o", out_spv])
            if rc != 0:
                errors += 1
    return {
        "id": "Q-CMP-02",
        "name": "Compilacion SPIR-V",
        "ok": errors == 0 and len(shaders) > 0,
        "detail": f"{len(shaders)} shaders, {errors} errores",
    }


def _compile_single_c(args):
    cf, obj_path = args
    rc, out, dt = run_cmd(["gcc", "-Wall", "-Wextra", "-O2", "-Iinclude", "-c", cf, "-o", obj_path])
    warn_count = len(re.findall(r":\d+:\d+:\s+warning:", out))
    return rc, warn_count, dt


def check_compiler_warnings():
    src_dir = os.path.join(ROOT, "src")
    c_files = [os.path.join("src", fn) for fn in sorted(os.listdir(src_dir)) if fn.endswith(".c")]
    warnings = 0
    errors = 0
    t_seq = 0.0

    with tempfile.TemporaryDirectory(prefix="sv_objs_") as tmpdir:
        jobs = [
            (cf, os.path.join(tmpdir, f"{os.path.splitext(os.path.basename(cf))[0]}.o"))
            for cf in c_files
        ]
        workers = max(1, min(len(jobs), os.cpu_count() or 4))
        t_wall_0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_compile_single_c, jobs))
        t_wall = time.monotonic() - t_wall_0

    for rc, warn_count, dt in results:
        t_seq += dt
        if rc != 0:
            errors += 1
        warnings += warn_count

    return [
        {
            "id": "Q-MNT-01",
            "name": "Limpieza de Compilador (-Wall -Wextra)",
            "ok": errors == 0 and warnings == 0,
            "detail": f"{len(c_files)} archivos, {warnings} warnings, {errors} errores",
        },
        {
            "id": "Q-PRT-02",
            "name": "Tiempo de Compilacion C",
            "ok": errors == 0 and t_wall <= 10.0,
            "detail": f"paralelo={t_wall:.2f}s (umbral <= 10.0s), suma_secuencial={t_seq:.2f}s",
        },
    ]


def check_secret_leakage():
    rc, out, _ = run_cmd(["git", "ls-files"])
    if rc != 0:
        return {
            "id": "Q-SEC-01",
            "name": "Aislamiento de Claves API",
            "ok": False,
            "detail": "git ls-files fallo",
        }
    patterns = [
        re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
        re.compile(r"sk-[0-9A-Za-z]{32,}"),
    ]
    hits = 0
    for rel in out.splitlines():
        if not rel.endswith((".c", ".h", ".py", ".sh", ".vert", ".frag")):
            continue
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        for pat in patterns:
            if pat.search(txt):
                hits += 1
    return {
        "id": "Q-SEC-01",
        "name": "Aislamiento de Claves API",
        "ok": hits == 0,
        "detail": f"{hits} llaves expuestas",
    }


def check_glb_size():
    sectors_dir = os.path.join(ROOT, "models", "sectors")
    if os.path.isdir(sectors_dir):
        glbs = [
            os.path.join(sectors_dir, fn)
            for fn in os.listdir(sectors_dir)
            if fn.endswith(".glb")
        ]
        if glbs:
            max_mb = max(os.path.getsize(p) for p in glbs) / (1024 * 1024)
            return {
                "id": "Q-PRF-03",
                "name": "Tamano max sector GLB",
                "ok": max_mb <= 120.0,
                "detail": f"{len(glbs)} sectores, max={max_mb:.2f} MB (umbral <= 120.0 MB)",
            }
    glb = os.path.join(ROOT, "models", "aguascalientes_sector1.glb")
    if not os.path.isfile(glb):
        return {"id": "Q-PRF-03", "name": "Tamano GLB", "ok": True, "detail": "sin GLB en disco"}
    mb = os.path.getsize(glb) / (1024 * 1024)
    return {
        "id": "Q-PRF-03",
        "name": "Tamano GLB principal",
        "ok": mb <= 120.0,
        "detail": f"{mb:.2f} MB (umbral <= 120.0 MB)",
    }


def check_dem_topography_precision():
    """Verifica Q-FNC-02 comparando terrain_dem_get_elevation() en C contra geo_dem.py."""
    try:
        import geo_dem
    except Exception as exc:
        return {
            "id": "Q-FNC-02",
            "name": "Correccion de Cota Topografica DEM",
            "ok": False,
            "detail": f"Error importando geo_dem: {exc}",
        }

    with contextlib.redirect_stdout(io.StringIO()):
        te = geo_dem.TerrainElevation(21.800, 21.950, -102.370, -102.245, nx=64, ny=64)

    geo_samples = [
        ("Centro Plaza de la Patria", 21.8807, -102.2965, 0.0),
        ("Rio San Pedro Centro", 21.8900, -102.3320, 0.0),
        ("Rio San Pedro Sur", 21.8500, -102.3280, 0.0),
        ("Arroyo El Cedazo", 21.8700, -102.2800, 0.0),
        ("Arroyo Don Pascual", 21.9050, -102.2850, 0.0),
        ("Arroyo El Molino", 21.9320, -102.3000, 0.0),
        ("Falla Oriente Oeste", 21.8800, -102.2790, -25.0),
        ("Falla Oriente Este", 21.8800, -102.2790, 25.0),
        ("Falla Poniente Oeste", 21.8850, -102.3180, -25.0),
        ("Falla Poniente Este", 21.8850, -102.3180, 25.0),
        ("Tercer Anillo Norte", 21.9350, -102.2965, 0.0),
        ("Tercer Anillo Sur", 21.8200, -102.2965, 0.0),
        ("Tercer Anillo Este", 21.8807, -102.2550, 0.0),
        ("Tercer Anillo Oeste", 21.8807, -102.3550, 0.0),
    ]

    points = []
    for label, lat, lon, dx in geo_samples:
        x, z = geo_dem.geo_to_meters(lat, lon)
        x += dx
        py_y = float(te.get_real_topography(x, z))
        points.append((label, x, z, py_y))

    c_lines = [
        '#include <stdio.h>',
        '#include "terrain_dem_data.h"',
        'int main(void) {',
        '    static const float pts[][2] = {',
    ]
    for _, x, z, _ in points:
        c_lines.append(f"        {{{x:.6f}f, {z:.6f}f}},")
    c_lines.extend([
        '    };',
        '    size_t n = sizeof(pts) / sizeof(pts[0]);',
        '    for (size_t i = 0; i < n; i++) {',
        '        printf("%.6f\\n", terrain_dem_get_elevation(pts[i][0], pts[i][1]));',
        '    }',
        '    return 0;',
        '}',
    ])

    probe_c = "/tmp/sv_dem_probe.c"
    probe_bin = "/tmp/sv_dem_probe"
    try:
        with open(probe_c, "w", encoding="utf-8") as f:
            f.write("\n".join(c_lines) + "\n")

        rc, out, _ = run_cmd(["gcc", "-Wall", "-Wextra", "-O2", "-Iinclude", probe_c, "-lm", "-o", probe_bin])
        if rc != 0:
            first_err = out.strip().splitlines()[0] if out.strip() else "error desconocido"
            return {
                "id": "Q-FNC-02",
                "name": "Correccion de Cota Topografica DEM",
                "ok": False,
                "detail": f"Error compilando probe DEM: {first_err}",
            }

        rc, out, _ = run_cmd([probe_bin])
        if rc != 0:
            return {
                "id": "Q-FNC-02",
                "name": "Correccion de Cota Topografica DEM",
                "ok": False,
                "detail": f"Probe DEM retorno codigo {rc}",
            }

        c_vals = [float(line.strip()) for line in out.strip().splitlines() if line.strip()]
        if len(c_vals) != len(points):
            return {
                "id": "Q-FNC-02",
                "name": "Correccion de Cota Topografica DEM",
                "ok": False,
                "detail": f"Esperados {len(points)} valores, recibidos {len(c_vals)}",
            }

        diffs = [abs(c_y - py_y) for c_y, (_, _, _, py_y) in zip(c_vals, points)]
        max_diff = max(diffs)
        worst_idx = diffs.index(max_diff)
        worst_label = points[worst_idx][0]
        return {
            "id": "Q-FNC-02",
            "name": "Correccion de Cota Topografica DEM",
            "ok": max_diff < 0.05,
            "detail": (
                f"{len(points)} puntos Aguascalientes, max_diff={max_diff:.6f} m "
                f"en '{worst_label}' (umbral < 0.05 m)"
            ),
        }
    finally:
        for tmp_path in (probe_c, probe_bin):
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


def check_modular_architecture():
    """Verifica Q-MNT-02: >= 8 modulos C con cabecera .h propia."""
    src_dir = os.path.join(ROOT, "src")
    inc_dir = os.path.join(ROOT, "include")
    third_party = {"cgltf.h", "stb_image.h"}
    c_mods = sorted(os.path.splitext(fn)[0] for fn in os.listdir(src_dir) if fn.endswith(".c"))
    headers = {
        os.path.splitext(fn)[0]
        for fn in os.listdir(inc_dir)
        if fn.endswith(".h") and fn not in third_party
    }
    paired = [m for m in c_mods if m in headers]
    return {
        "id": "Q-MNT-02",
        "name": "Modularidad Arquitectural (.c + .h)",
        "ok": len(paired) >= 8,
        "detail": f"{len(paired)} modulos C con .h propio de {len(c_mods)} fuentes (umbral >= 8)",
    }


def check_makefile_targets():
    """Verifica Q-MNT-03: Makefile con targets all, clean, test y metrics."""
    makefile = os.path.join(ROOT, "Makefile")
    if not os.path.isfile(makefile):
        return {
            "id": "Q-MNT-03",
            "name": "Automatizacion de Build (Makefile)",
            "ok": False,
            "detail": "Makefile no encontrado",
        }
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    required = ("all", "clean", "test", "metrics")
    present = [t for t in required if re.search(rf"^\s*{t}\s*:", content, re.MULTILINE)]
    missing = [t for t in required if t not in present]
    return {
        "id": "Q-MNT-03",
        "name": "Automatizacion de Build (Makefile)",
        "ok": not missing,
        "detail": (
            f"targets {', '.join(present)} presentes"
            if not missing
            else f"faltan targets: {', '.join(missing)}"
        ),
    }


def check_vulkan_device_extensions():
    """Verifica Q-PRT-01: solo VK_KHR_swapchain como extension de dispositivo."""
    dev_c = os.path.join(ROOT, "src", "vulkan_device.c")
    if not os.path.isfile(dev_c):
        return {
            "id": "Q-PRT-01",
            "name": "Extensiones Vulkan de Dispositivo",
            "ok": False,
            "detail": "src/vulkan_device.c no encontrado",
        }
    with open(dev_c, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    match = re.search(r"deviceExtensions\s*\[\s*\]\s*=\s*\{([^}]*)\}", text)
    if not match:
        return {
            "id": "Q-PRT-01",
            "name": "Extensiones Vulkan de Dispositivo",
            "ok": False,
            "detail": "Arreglo deviceExtensions[] no encontrado en vulkan_device.c",
        }
    items = [tok.strip() for tok in match.group(1).split(",") if tok.strip()]
    allowed = {"VK_KHR_SWAPCHAIN_EXTENSION_NAME", '"VK_KHR_swapchain"'}
    only_swapchain = len(items) == 1 and items[0] in allowed
    return {
        "id": "Q-PRT-01",
        "name": "Extensiones Vulkan de Dispositivo",
        "ok": only_swapchain,
        "detail": f"deviceExtensions={items}",
    }


def _validate_single_glb(path):
    size = os.path.getsize(path)
    if size < 20:
        return False, "archivo < 20 bytes"
    with open(path, "rb") as f:
        magic, version, total_len = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF" or version != 2 or total_len != size:
            return False, f"cabecera GLB invalida (magic={magic}, ver={version}, len={total_len}/{size})"
        c0_len, c0_type = struct.unpack("<I4s", f.read(8))
        if c0_type != b"JSON" or 20 + c0_len > total_len:
            return False, f"chunk 0 invalido (type={c0_type}, len={c0_len})"
        raw_json = f.read(c0_len)
    try:
        doc = json.loads(raw_json.decode("utf-8"))
    except Exception as exc:
        return False, f"JSON invalido: {exc}"
    asset = doc.get("asset")
    if not isinstance(asset, dict) or not str(asset.get("version", "")).startswith("2."):
        return False, f"asset.version invalido: {asset}"
    return True, "ok"


def check_glb_conformance():
    """Verifica Q-CMP-01: cabecera glTF 2.0 y JSON valido en models/cars/*.glb y models/peds/*.glb."""
    glb_files = sorted(
        glob.glob(os.path.join(ROOT, "models", "cars", "*.glb"))
        + glob.glob(os.path.join(ROOT, "models", "peds", "*.glb"))
    )
    if not glb_files:
        return {
            "id": "Q-CMP-01",
            "name": "Conformidad glTF 2.0 (cars/peds)",
            "ok": False,
            "detail": "No se encontraron archivos .glb en models/cars ni models/peds",
        }
    failures = []
    for path in glb_files:
        ok, reason = _validate_single_glb(path)
        if not ok:
            failures.append(f"{os.path.relpath(path, ROOT)}: {reason}")
    return {
        "id": "Q-CMP-01",
        "name": "Conformidad glTF 2.0 (cars/peds)",
        "ok": len(failures) == 0,
        "detail": (
            f"{len(glb_files)}/{len(glb_files)} GLB validos (cabecera glTF 2.0 + JSON)"
            if not failures
            else f"{len(failures)} fallos: {'; '.join(failures)}"
        ),
    }


def main():
    checks = [
        check_dem_topography_precision(),
        check_glb_size(),
        check_glb_conformance(),
        check_shader_compilation(),
        check_secret_leakage(),
    ]
    checks.extend(check_compiler_warnings())
    checks.extend([
        check_modular_architecture(),
        check_makefile_targets(),
        check_vulkan_device_extensions(),
    ])

    print("=== Verificacion Automatizada ISO/IEC 25023 ===")
    all_ok = True
    for c in checks:
        status = "PASS" if c["ok"] else "FAIL"
        all_ok = all_ok and c["ok"]
        print(f"[{status}] {c['id']} ({c.get('name', '')}): {c['detail']}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
