#!/usr/bin/env python3
"""Auditor de Pruebas de Software (ISO/IEC/IEEE 29119) para StreetVulkan."""

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def evaluate_testing(root=ROOT, min_c_tests=10, min_py_tests=8):
    """Verifica infraestructura, automatizacion y conteo de pruebas ISO/IEC/IEEE 29119."""
    c_test_path = os.path.join(root, "tests", "test_c_modules.c")
    py_test_path = os.path.join(root, "tests", "test_python_tools.py")
    makefile_path = os.path.join(root, "Makefile")
    ci_path = os.path.join(root, ".github", "workflows", "ci.yml")

    c_test_count = 0
    if os.path.isfile(c_test_path):
        with open(c_test_path, "r", encoding="utf-8", errors="ignore") as f:
            c_src = f.read()
        # Contar funciones static void test_... o llamadas ASSERT_
        c_funcs = re.findall(r"\bvoid\s+test_[A-Za-z0-9_]+\s*\(", c_src)
        c_asserts = re.findall(r"\b(?:TEST_ASSERT|ASSERT_TRUE|ASSERT_EQ|assert)\b", c_src)
        c_test_count = len(c_funcs) if c_funcs else len(c_asserts)

    py_test_count = 0
    if os.path.isfile(py_test_path):
        with open(py_test_path, "r", encoding="utf-8", errors="ignore") as f:
            py_src = f.read()
        py_test_count = len(re.findall(r"^\s*def\s+test_[A-Za-z0-9_]+\s*\(", py_src, re.MULTILINE))

    mk_targets = {"test": False, "asan-test": False, "quality": False}
    if os.path.isfile(makefile_path):
        with open(makefile_path, "r", encoding="utf-8", errors="ignore") as f:
            mk = f.read()
        for t in mk_targets:
            mk_targets[t] = bool(re.search(rf"^{re.escape(t)}\s*:", mk, re.MULTILINE))

    has_ci = os.path.isfile(ci_path)

    passed = (
        os.path.isfile(c_test_path)
        and os.path.isfile(py_test_path)
        and c_test_count >= min_c_tests
        and py_test_count >= min_py_tests
        and all(mk_targets.values())
        and has_ci
    )

    return {
        "c_test_exists": os.path.isfile(c_test_path),
        "py_test_exists": os.path.isfile(py_test_path),
        "c_test_count": c_test_count,
        "py_test_count": py_test_count,
        "mk_targets": mk_targets,
        "has_ci": has_ci,
        "passed": passed,
    }


def main():
    res = evaluate_testing(ROOT)
    print("=== Auditoria ISO/IEC/IEEE 29119 (Pruebas de Software) ===")
    print(f"  Suite C  (tests/test_c_modules.c)   : {res['c_test_count']} pruebas/funciones")
    print(f"  Suite Py (tests/test_python_tools.py): {res['py_test_count']} metodos test_*")
    targets_str = ", ".join(f"{k}={'OK' if v else 'FALTA'}" for k, v in res["mk_targets"].items())
    print(f"  Targets Makefile                    : {targets_str}")
    print(f"  Pipeline CI (.github/workflows/ci.yml): {'OK' if res['has_ci'] else 'FALTA'}")
    if res["passed"]:
        print("  [PASS] Infraestructura y cobertura de pruebas ISO/IEC/IEEE 29119 conforme.")
        return 0
    print("  [FAIL] Faltan artefactos o umbrales minimos de pruebas ISO/IEC/IEEE 29119.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
