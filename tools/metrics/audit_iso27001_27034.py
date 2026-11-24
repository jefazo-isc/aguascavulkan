#!/usr/bin/env python3
"""Auditor de Seguridad de la Informacion y Aplicaciones (ISO/IEC 27001 & 27034) para StreetVulkan."""

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THIRD_PARTY_HEADERS = {"cgltf.h", "stb_image.h", "stb_truetype.h"}

CRITICAL_UNSAFE_C = [("gets(", re.compile(r"\bgets\s*\("))]
ADVISORY_UNSAFE_C = [
    ("sprintf(", re.compile(r"\bsprintf\s*\(")),
    ("vsprintf(", re.compile(r"\bvsprintf\s*\(")),
    ("strcpy(", re.compile(r"\bstrcpy\s*\(")),
    ("strcat(", re.compile(r"\bstrcat\s*\(")),
]

SECRET_PATTERNS = [
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API Key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("GitHub Token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b")),
]


def iter_owned_c_files(root=ROOT):
    """Retorna rutas relativas de archivos .c/.h propios en src/ e include/."""
    files = []
    for folder in ("src", "include"):
        dirpath = os.path.join(root, folder)
        if not os.path.isdir(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith((".c", ".h")):
                continue
            if folder == "include" and fname in THIRD_PARTY_HEADERS:
                continue
            files.append(os.path.join(folder, fname))
    return files


def iter_code_files(root=ROOT):
    """Retorna rutas relativas de archivos de codigo propio (.c, .h, .py) para escaneo de secretos."""
    files = list(iter_owned_c_files(root))
    tools_dir = os.path.join(root, "tools")
    if os.path.isdir(tools_dir):
        for cur_root, _, fnames in os.walk(tools_dir):
            if "__pycache__" in cur_root:
                continue
            for fname in sorted(fnames):
                if fname.endswith(".py"):
                    full = os.path.join(cur_root, fname)
                    files.append(os.path.relpath(full, root))
    return sorted(files)


def check_security(root=ROOT):
    """Ejecuta controles ISO/IEC 27001 y 27034 sobre el repositorio."""
    c_files = iter_owned_c_files(root)
    all_code_files = iter_code_files(root)

    critical_findings = []
    advisory_counts = {label: 0 for label, _ in ADVISORY_UNSAFE_C}
    secret_findings = []

    for rel in c_files:
        full = os.path.join(root, rel)
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, 1):
                for label, rx in CRITICAL_UNSAFE_C:
                    if rx.search(line):
                        critical_findings.append((rel, lineno, label))
                for label, rx in ADVISORY_UNSAFE_C:
                    if rx.search(line):
                        advisory_counts[label] += 1

    for rel in all_code_files:
        full = os.path.join(root, rel)
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for label, regex in SECRET_PATTERNS:
            if regex.search(content):
                secret_findings.append((rel, label))

    makefile_path = os.path.join(root, "Makefile")
    has_wall_wextra = False
    if os.path.isfile(makefile_path):
        with open(makefile_path, "r", encoding="utf-8", errors="ignore") as f:
            mk = f.read()
        has_wall_wextra = ("-Wall" in mk and "-Wextra" in mk)

    has_gitignore = os.path.isfile(os.path.join(root, ".gitignore"))

    passed = (
        len(critical_findings) == 0
        and len(secret_findings) == 0
        and has_wall_wextra
    )

    return {
        "c_files_scanned": len(c_files),
        "all_files_scanned": len(all_code_files),
        "critical_findings": critical_findings,
        "advisory_counts": advisory_counts,
        "secret_findings": secret_findings,
        "has_wall_wextra": has_wall_wextra,
        "has_gitignore": has_gitignore,
        "passed": passed,
    }


def main():
    res = check_security(ROOT)
    print("=== Auditoria ISO/IEC 27001 & 27034 (Seguridad de Aplicaciones) ===")
    print(f"  Archivos C/H propios escaneados : {res['c_files_scanned']}")
    print(f"  Archivos totales (C/H/Py)       : {res['all_files_scanned']}")
    print(f"  Compilacion estricta (-Wall -Wextra): {'OK' if res['has_wall_wextra'] else 'FALTA'}")
    print(f"  Control .gitignore presente     : {'OK' if res['has_gitignore'] else 'NO'}")
    print(f"  Llamadas criticas inseguras     : {len(res['critical_findings'])}")
    print(f"  Secretos/llaves hardcodeadas    : {len(res['secret_findings'])}")
    adv_total = sum(res["advisory_counts"].values())
    if adv_total > 0:
        detail = ", ".join(f"{k}:{v}" for k, v in res["advisory_counts"].items() if v > 0)
        print(f"  [INFO] Llamadas C legadas bajo vigilancia ({adv_total}): {detail}")

    if res["critical_findings"]:
        for rel, ln, pat in res["critical_findings"]:
            print(f"  [FAIL] Llamada critica {pat} en {rel}:{ln}")
    if res["secret_findings"]:
        for rel, label in res["secret_findings"]:
            print(f"  [FAIL] Posible secreto ({label}) en {rel}")

    if res["passed"]:
        print("  [PASS] Controles ISO/IEC 27001 & 27034 verificados sin hallazgos criticos.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
