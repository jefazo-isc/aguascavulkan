#!/usr/bin/env python3
"""Analizador de Mantenibilidad y Complejidad (ISO/IEC 25023 e ISO/IEC 14764) para StreetVulkan."""

import argparse
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THIRD_PARTY = {"cgltf.h", "stb_image.h"}
BRANCH_RE = re.compile(r"\b(if|else\s+if|for|while|case)\b|&&|\|\||\?")
FUNC_HDR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\s\*]*?\b([A-Za-z_][A-Za-z0-9_]*)\s*\(.*\)\s*$")
NON_FUNC_NAMES = {"if", "for", "while", "switch", "return", "sizeof", "struct", "enum", "union"}


def strip_comments_and_strings(line, in_block):
    """Elimina comentarios y literales de cadena/caracter para analisis sintactico limpio."""
    out = []
    i = 0
    n = len(line)
    has_comment = False

    if in_block:
        has_comment = True
        idx = line.find("*/")
        if idx == -1:
            return "", True, True
        in_block = False
        i = idx + 2

    while i < n:
        ch = line[i]
        if ch in ('"', "'"):
            out.append(" ")
            i += 1
            while i < n:
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i] == ch:
                    i += 1
                    break
                i += 1
            continue
        if line.startswith("//", i):
            has_comment = True
            break
        if line.startswith("/*", i):
            has_comment = True
            end = line.find("*/", i + 2)
            if end == -1:
                in_block = True
                break
            i = end + 2
            continue
        out.append(ch)
        i += 1

    code = "".join(out)
    only_comment = (not code.strip()) and has_comment
    return code, in_block, only_comment


def extract_function_name(hdr):
    """Devuelve el nombre de funcion si el encabezado representa una definicion C valida."""
    if not hdr or "(" not in hdr:
        return None
    if "=" in hdr.split("(", 1)[0]:
        return None
    match = FUNC_HDR_RE.match(hdr)
    if not match:
        return None
    name = match.group(1)
    if name in NON_FUNC_NAMES:
        return None
    return name


def analyze_c_file(path):
    """Analiza lineas totales, comentarios y complejidad ciclomática (McCabe aprox.) de un .c o .h."""
    total_lines = 0
    comment_lines = 0
    in_block = False
    in_macro = False
    brace_depth = 0
    hdr_parts = []
    hdr_start = None
    cur_func = None
    functions = []
    rel_path = os.path.relpath(path, ROOT)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for lineno, raw in enumerate(f, 1):
            total_lines += 1
            code, in_block, only_comment = strip_comments_and_strings(raw, in_block)
            if only_comment:
                comment_lines += 1
                continue

            sc = code.strip()
            if not sc:
                continue

            if cur_func is None and brace_depth == 0:
                if in_macro:
                    in_macro = sc.endswith("\\")
                    continue
                if sc.startswith("#"):
                    in_macro = sc.endswith("\\")
                    hdr_parts.clear()
                    hdr_start = None
                    continue

                if "{" in sc:
                    before, after = sc.split("{", 1)
                    if before.strip():
                        if hdr_start is None:
                            hdr_start = lineno
                        hdr_parts.append(before.strip())
                    hdr = " ".join(hdr_parts).strip()
                    hdr_parts.clear()
                    if ";" in hdr:
                        hdr = hdr.rsplit(";", 1)[-1].strip()

                    func_name = extract_function_name(hdr)
                    if func_name:
                        cur_func = {
                            "name": func_name,
                            "cc": 1 + len(BRANCH_RE.findall(after)),
                            "start": hdr_start or lineno,
                        }
                    hdr_start = None
                    brace_depth += 1 + after.count("{") - after.count("}")
                    if brace_depth <= 0:
                        if cur_func is not None:
                            functions.append({
                                "name": cur_func["name"],
                                "cc": cur_func["cc"],
                                "lines": lineno - cur_func["start"] + 1,
                            })
                            cur_func = None
                        brace_depth = 0
                else:
                    if ";" in sc:
                        hdr_parts.clear()
                        hdr_start = None
                    else:
                        if hdr_start is None:
                            hdr_start = lineno
                        hdr_parts.append(sc)
            else:
                if cur_func is not None:
                    cur_func["cc"] += len(BRANCH_RE.findall(sc))
                brace_depth += sc.count("{") - sc.count("}")
                if brace_depth <= 0:
                    if cur_func is not None:
                        functions.append({
                            "name": cur_func["name"],
                            "cc": cur_func["cc"],
                            "lines": lineno - cur_func["start"] + 1,
                        })
                        cur_func = None
                    brace_depth = 0

    return {
        "file": rel_path,
        "total_lines": total_lines,
        "comment_lines": comment_lines,
        "functions": functions,
    }


def collect_source_files(root=ROOT):
    """Recopila archivos fuente propios src/*.c e include/*.h (excluyendo terceros)."""
    files = []
    for folder, ext in (("src", ".c"), ("include", ".h")):
        directory = os.path.join(root, folder)
        if not os.path.isdir(directory):
            continue
        for fn in sorted(os.listdir(directory)):
            if fn in THIRD_PARTY:
                continue
            if fn.endswith(ext):
                files.append(os.path.join(directory, fn))
    return files


def evaluate_maintainability(root=ROOT, cc_threshold=20, min_comment_pct=5.0):
    """Evalua mantenibilidad consolidada sobre src/*.c e include/*.h."""
    files = collect_source_files(root)
    reports = [analyze_c_file(p) for p in files]

    all_funcs = []
    for rep in reports:
        for fn in rep["functions"]:
            all_funcs.append({
                "file": rep["file"],
                "name": fn["name"],
                "cc": fn["cc"],
                "lines": fn["lines"],
            })

    total_lines = sum(r["total_lines"] for r in reports)
    total_comments = sum(r["comment_lines"] for r in reports)
    comment_ratio = (total_comments / total_lines * 100.0) if total_lines else 0.0
    avg_cc = (sum(f["cc"] for f in all_funcs) / len(all_funcs)) if all_funcs else 0.0
    max_func = max(all_funcs, key=lambda x: x["cc"], default={"file": "-", "name": "-", "cc": 0, "lines": 0})
    high_cc = sorted((f for f in all_funcs if f["cc"] > cc_threshold), key=lambda x: (-x["cc"], x["file"], x["name"]))

    reasons = []
    if high_cc:
        reasons.append(f"{len(high_cc)} funciones con CC > {cc_threshold}")
    if comment_ratio < min_comment_pct:
        reasons.append(f"densidad de comentarios {comment_ratio:.1f}% < {min_comment_pct:.1f}%")

    return {
        "reports": reports,
        "c_count": sum(1 for r in reports if r["file"].endswith(".c")),
        "h_count": sum(1 for r in reports if r["file"].endswith(".h")),
        "all_funcs": all_funcs,
        "total_lines": total_lines,
        "total_comments": total_comments,
        "comment_ratio": comment_ratio,
        "avg_cc": avg_cc,
        "max_func": max_func,
        "high_cc": high_cc,
        "has_debt": bool(reasons),
        "reasons": reasons,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analizador de Mantenibilidad ISO/IEC 25023")
    parser.add_argument("--strict", action="store_true", help="Retorna exit code 1 si existe deuda tecnica")
    args = parser.parse_args(argv)

    res = evaluate_maintainability()
    status = ("FAIL" if args.strict else "WARN") if res["has_debt"] else "PASS"

    print("=== Analizador ISO/IEC 25023 (Mantenibilidad) & ISO/IEC 14764 ===")
    print(f"  Archivos analizados  : {len(res['reports'])} ({res['c_count']} .c, {res['h_count']} .h propios)")
    print(f"  Funciones detectadas : {len(res['all_funcs'])}")
    print(f"  Densidad comentarios : {res['comment_ratio']:.1f}% ({res['total_comments']}/{res['total_lines']} lineas)")
    print(f"  Complejidad promedio : {res['avg_cc']:.2f} (McCabe aprox.)")
    print(f"  Complejidad maxima   : {res['max_func']['cc']} ({res['max_func']['file']}::{res['max_func']['name']})")
    print(f"  Funciones CC > 20    : {len(res['high_cc'])}")
    if res["high_cc"]:
        print("  Detalle funciones CC > 20 (deuda tecnica abierta):")
        for fn in res["high_cc"]:
            print(f"    - {fn['file']} :: {fn['name']} (CC={fn['cc']}, {fn['lines']} lineas)")
    if res["has_debt"]:
        print(f"  [{status}] Deuda tecnica abierta: {'; '.join(res['reasons'])}")
    else:
        print("  [PASS] Sin deuda tecnica abierta")

    if res["has_debt"]:
        return 1 if args.strict else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
