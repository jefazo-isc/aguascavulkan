#!/usr/bin/env python3
"""Evaluador Maestro ISO/IEC 25040 & 25041: Genera build/quality_scorecard.json."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def classify_exit_code(exit_code):
    """Mapea el codigo de salida de un verificador a PASS (0), WARN (2) o FAIL (otro)."""
    if exit_code == 0:
        return "PASS"
    if exit_code == 2:
        return "WARN"
    return "FAIL"


def run_step(name, standard, cmd):
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    status = classify_exit_code(res.returncode)
    return {
        "name": name,
        "standard": standard,
        "status": status,
        "passed": status == "PASS",
        "warned": status == "WARN",
        "exit_code": res.returncode,
        "output": res.stdout.strip(),
        "errors": res.stderr.strip(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluador Maestro ISO/IEC 25040 & 25041")
    parser.add_argument("--strict", action="store_true", help="Falla con exit code 1 si existen checks en WARN")
    args = parser.parse_args(argv)

    steps = [
        ("Tamanio y Estimacion (KLOC/IFPUG/COSMIC/COCOMO-II)", "ISO/IEC 19761", [sys.executable, "tools/metrics/estimate_cocomo_fp.py"]),
        ("Calidad de Datos", "ISO/IEC 25012 & 25024", [sys.executable, "tools/metrics/validate_data_quality.py"]),
        ("Calidad de Producto", "ISO/IEC 25010 & 25023", [sys.executable, "tools/metrics/measure_iso25023.py"]),
        ("Mantenibilidad y Complejidad", "ISO/IEC 25023 & 14764", [sys.executable, "tools/metrics/measure_maintainability.py"]),
        ("Trazabilidad Tecnica", "ISO/IEC 29110-SI & 12207", [sys.executable, "tools/metrics/check_traceability.py"]),
        ("Seguridad de Aplicaciones", "ISO/IEC 27001 & 27034", [sys.executable, "tools/metrics/audit_iso27001_27034.py"]),
        ("Pruebas de Software", "ISO/IEC/IEEE 29119", [sys.executable, "tools/metrics/audit_iso29119.py"]),
        ("Gestion de Calidad y Riesgos", "ISO 9001 & 31000", [sys.executable, "tools/metrics/audit_iso9001_31000.py"]),
    ]

    results = [run_step(n, s, c) for n, s, c in steps]
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    score_pct = (passed / total * 100.0) if total else 0.0

    scorecard = {
        "project": "StreetVulkan",
        "evaluator": "ISO/IEC 25040 & 25041",
        "strict_mode": args.strict,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_checks": total,
        "passed_checks": passed,
        "warned_checks": warned,
        "failed_checks": failed,
        "compliance_pct": round(score_pct, 2),
        "results": results,
    }

    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    out_path = os.path.join(ROOT, "build", "quality_scorecard.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scorecard, f, indent=2, ensure_ascii=False)

    print("=== Evaluacion Consolidada ISO/IEC 25040 & 25041 ===")
    for r in results:
        print(f"  [{r['status']}] {r['standard']:24s} -> {r['name']}")
    print(
        f"Scorecard guardado en build/quality_scorecard.json "
        f"(PASS={passed}, WARN={warned}, FAIL={failed}, Total={total}, Cumplimiento={score_pct:.1f}%)"
    )

    if failed > 0 or (args.strict and warned > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
