#!/usr/bin/env python3
"""Auditor de Gestion de Calidad (ISO 9001) y Gestion de Riesgos (ISO 31000) para StreetVulkan."""

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

REQUIRED_DOCS = [
    "docs/ISO_IEC_25010.md",
    "docs/ISO_IEC_25012_25024.md",
    "docs/ISO_IEC_25023.md",
    "docs/ISO_IEC_27001_27034.md",
    "docs/ISO_IEC_29119.md",
    "docs/ISO_9001_31000.md",
    "docs/OPENUP_TSP.md",
    "docs/SCRUM_XP.md",
    "docs/ESTIMACION_Y_TRAZABILIDAD.md",
]


def evaluate_qms_and_risk(root=ROOT, min_doc_bytes=1024):
    """Verifica evidencia documental SGC ISO 9001, registro de riesgos ISO 31000 y gates en Makefile."""
    doc_status = []
    for rel in REQUIRED_DOCS:
        full = os.path.join(root, rel)
        exists = os.path.isfile(full)
        size = os.path.getsize(full) if exists else 0
        ok = exists and size > min_doc_bytes
        doc_status.append({"path": rel, "exists": exists, "bytes": size, "ok": ok})

    makefile_path = os.path.join(root, "Makefile")
    has_metrics_gate = False
    has_quality_gate = False
    if os.path.isfile(makefile_path):
        with open(makefile_path, "r", encoding="utf-8", errors="ignore") as f:
            mk = f.read()
        has_metrics_gate = bool(re.search(r"^metrics\s*:", mk, re.MULTILINE))
        has_quality_gate = bool(re.search(r"^quality\s*:", mk, re.MULTILINE))

    passed = all(d["ok"] for d in doc_status) and has_metrics_gate and has_quality_gate
    return {
        "docs": doc_status,
        "has_metrics_gate": has_metrics_gate,
        "has_quality_gate": has_quality_gate,
        "passed": passed,
    }


def main():
    res = evaluate_qms_and_risk(ROOT)
    print("=== Auditoria ISO 9001 (SGC) & ISO 31000 (Gestion de Riesgos) ===")
    for d in res["docs"]:
        tag = "OK" if d["ok"] else "FALTA/CORTO"
        print(f"  [{tag:11s}] {d['path']} ({d['bytes']} bytes)")
    print(f"  Gate Makefile 'metrics:' : {'OK' if res['has_metrics_gate'] else 'FALTA'}")
    print(f"  Gate Makefile 'quality:' : {'OK' if res['has_quality_gate'] else 'FALTA'}")
    if res["passed"]:
        print("  [PASS] Sistema de Gestion de Calidad ISO 9001 y Riesgos ISO 31000 conforme.")
        return 0
    print("  [FAIL] Documentacion SGC o gates de calidad incompletos.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
