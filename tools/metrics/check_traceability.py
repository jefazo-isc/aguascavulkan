#!/usr/bin/env python3
"""Verificador de Trazabilidad Tecnica (ISO/IEC 29110-SI e ISO/IEC/IEEE 12207)."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def check_shader_spv_pairing():
    shader_dir = os.path.join(ROOT, "shaders")
    sources = [fn for fn in sorted(os.listdir(shader_dir)) if fn.endswith((".vert", ".frag"))]
    missing = []
    stale = []
    for src in sources:
        base = os.path.splitext(src)[0]
        spv_path = os.path.join(shader_dir, f"{base}.spv")
        src_path = os.path.join(shader_dir, src)
        if not os.path.isfile(spv_path):
            missing.append(src)
        elif os.path.getmtime(spv_path) < os.path.getmtime(src_path):
            stale.append(src)
    return {
        "total_shaders": len(sources),
        "missing_spv": missing,
        "stale_spv": stale,
        "ok": len(sources) > 0 and not missing and not stale,
    }


def check_c_header_and_tests():
    src_dir = os.path.join(ROOT, "src")
    inc_dir = os.path.join(ROOT, "include")
    test_c_path = os.path.join(ROOT, "tests", "test_c_modules.c")

    c_modules = sorted(os.path.splitext(fn)[0] for fn in os.listdir(src_dir) if fn.endswith(".c"))
    headers = {os.path.splitext(fn)[0] for fn in os.listdir(inc_dir) if fn.endswith(".h")}

    with open(test_c_path, "r", encoding="utf-8", errors="ignore") as f:
        test_src = f.read()

    # Modulos sin cabecera homonima (ej. main.c) se permiten si no exportan API
    paired = [m for m in c_modules if m in headers]
    tested = [m for m in c_modules if f'#include "{m}.h"' in test_src]

    return {
        "c_modules": len(c_modules),
        "paired_headers": len(paired),
        "tested_c_modules": len(tested),
        "tested_list": tested,
        "ok": len(c_modules) >= 8 and len(tested) >= 3,
    }


def main():
    sh = check_shader_spv_pairing()
    ch = check_c_header_and_tests()
    ok = sh["ok"] and ch["ok"]

    print("=== Trazabilidad Tecnica ISO/IEC 29110 (SI) & 12207 ===")
    print(f"[{'PASS' if sh['ok'] else 'FAIL'}] Shaders GLSL->SPIR-V: "
          f"{sh['total_shaders']} fuentes, missing={len(sh['missing_spv'])}, stale={len(sh['stale_spv'])}")
    print(f"[{'PASS' if ch['ok'] else 'FAIL'}] Modularidad y Cobertura C: "
          f"{ch['c_modules']} modulos, {ch['paired_headers']} con .h homonimo, "
          f"{ch['tested_c_modules']} con pruebas en test_c_modules.c ({', '.join(ch['tested_list'])})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
