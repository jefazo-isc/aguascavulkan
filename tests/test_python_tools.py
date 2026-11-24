#!/usr/bin/env python3
"""Pruebas unitarias XP para herramientas Python de StreetVulkan."""

import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "metrics"))

import topography_math
import street_wiring
import estimate_cocomo_fp
import measure_maintainability
import evaluate_iso25040
import audit_iso27001_27034
import audit_iso29119
import audit_iso9001_31000


class TestTopographyMath(unittest.TestCase):
    def test_is_convex(self):
        self.assertTrue(topography_math.is_convex((0, 0), (1, 0), (1, 1)))
        self.assertFalse(topography_math.is_convex((0, 0), (1, 0), (1, -1)))

    def test_point_in_triangle(self):
        a, b, c = (0, 0), (4, 0), (0, 4)
        self.assertTrue(topography_math.point_in_triangle((1, 1), a, b, c))
        self.assertFalse(topography_math.point_in_triangle((3, 3), a, b, c))

    def test_triangulate_square(self):
        square = [(0, 0), (2, 0), (2, 2), (0, 2)]
        tris = topography_math.triangulate_2d(square)
        self.assertEqual(len(tris), 2)

    def test_triangulate_degenerate(self):
        self.assertEqual(topography_math.triangulate_2d([(0, 0), (1, 1)]), [])


class TestMetricsCalculators(unittest.TestCase):
    def test_ifpug_ufp(self):
        ufp = estimate_cocomo_fp.compute_ifpug_ufp({"EI": 2, "EO": 1, "ILF": 1})
        # 2*4 + 1*5 + 1*10 = 23
        self.assertEqual(ufp, 23)

    def test_ifpug_catalog_traceable(self):
        catalog = estimate_cocomo_fp.IFPUG_CATALOG
        self.assertGreater(len(catalog), 0)
        seen_ids = set()
        for entry in catalog:
            self.assertIn(entry["type"], estimate_cocomo_fp.IFPUG_WEIGHTS)
            self.assertTrue(entry["id"])
            self.assertNotIn(entry["id"], seen_ids)
            seen_ids.add(entry["id"])
            self.assertTrue(entry["description"].strip())
            sources = [s.strip() for s in entry["source"].split(",") if s.strip()]
            self.assertGreater(len(sources), 0)
            for rel in sources:
                self.assertTrue(
                    os.path.isfile(os.path.join(ROOT, rel)),
                    f"Archivo fuente inexistente en IFPUG_CATALOG ({entry['id']}): {rel}",
                )
        counts = estimate_cocomo_fp.summarize_ifpug_catalog(catalog)
        self.assertEqual(estimate_cocomo_fp.compute_ifpug_ufp(counts), 153)

    def test_cosmic_processes_traceable(self):
        procs = estimate_cocomo_fp.COSMIC_PROCESSES
        self.assertGreater(len(procs), 0)
        for proc in procs:
            self.assertTrue(proc["id"])
            self.assertTrue(proc["name"])
            self.assertTrue(proc["trigger"])
            self.assertGreater(len(proc["modules"]), 0)
            for rel in proc["modules"]:
                self.assertTrue(
                    os.path.isfile(os.path.join(ROOT, rel)),
                    f"Modulo inexistente en COSMIC_PROCESSES ({proc['id']}): {rel}",
                )
            for movement in ("E", "X", "R", "W"):
                self.assertGreaterEqual(proc[movement], 0)
        self.assertEqual(estimate_cocomo_fp.compute_cosmic_cfp(procs), 39)

    def test_cocomo_ii_nominal(self):
        res = estimate_cocomo_fp.compute_cocomo_ii(10.0)
        self.assertAlmostEqual(res["E"], 1.0997, places=4)
        self.assertGreater(res["PM"], 0.0)
        self.assertGreater(res["TDEV_months"], 0.0)

    def test_cosmic_cfp(self):
        cfp = estimate_cocomo_fp.compute_cosmic_cfp([{"E": 2, "X": 1, "R": 3, "W": 1}])
        self.assertEqual(cfp, 7)

    def test_maintainability_analyzer(self):
        rep = measure_maintainability.analyze_c_file(os.path.join(ROOT, "src", "ped_system.c"))
        self.assertGreater(len(rep["functions"]), 0)
        self.assertGreater(rep["total_lines"], 0)

    def test_maintainability_headers_and_debt_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "src")
            inc_dir = os.path.join(tmpdir, "include")
            os.makedirs(src_dir)
            os.makedirs(inc_dir)

            # Cabecera de terceros que debe excluirse del analisis
            with open(os.path.join(inc_dir, "cgltf.h"), "w", encoding="utf-8") as f:
                f.write("void third_party_huge(int x) {\n" + "    if (x) { x++; }\n" * 30 + "}\n")

            # Cabecera propia con struct, comentario en string, firma multilinea y CC > 20
            hdr_path = os.path.join(inc_dir, "sample_menu.h")
            branches = "\n".join("    if (code == %d) return %d;" % (i, i) for i in range(22))
            with open(hdr_path, "w", encoding="utf-8") as f:
                f.write(
                    "typedef struct {\n"
                    "    int a;\n"
                    "} SampleStruct;\n\n"
                    "static inline int simple_helper(int v) {\n"
                    "    const char *s = \"/* no es comentario */\";\n"
                    "    return s[0] ? v : 0;\n"
                    "}\n\n"
                    "static inline int complex_menu_dispatch(\n"
                    "    int code,\n"
                    "    int mode)\n"
                    "{\n"
                    "    (void)mode;\n"
                    f"{branches}\n"
                    "    return 0;\n"
                    "}\n"
                )

            with open(os.path.join(src_dir, "sample.c"), "w", encoding="utf-8") as f:
                f.write("int ok_fn(void) { return 1; }\n")

            files = measure_maintainability.collect_source_files(tmpdir)
            basenames = {os.path.basename(p) for p in files}
            self.assertEqual(basenames, {"sample.c", "sample_menu.h"})

            rep = measure_maintainability.analyze_c_file(hdr_path)
            func_map = {fn["name"]: fn["cc"] for fn in rep["functions"]}
            self.assertIn("simple_helper", func_map)
            self.assertIn("complex_menu_dispatch", func_map)
            self.assertEqual(len(func_map), 2)
            self.assertGreater(func_map["complex_menu_dispatch"], 20)

            summary = measure_maintainability.evaluate_maintainability(root=tmpdir)
            self.assertTrue(summary["has_debt"])
            self.assertEqual(len(summary["high_cc"]), 1)
            self.assertEqual(summary["high_cc"][0]["name"], "complex_menu_dispatch")

            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(measure_maintainability, "evaluate_maintainability", return_value=summary):
                    self.assertEqual(measure_maintainability.main([]), 2)
                    self.assertEqual(measure_maintainability.main(["--strict"]), 1)

                clean_summary = dict(summary, has_debt=False, high_cc=[], reasons=[])
                with mock.patch.object(measure_maintainability, "evaluate_maintainability", return_value=clean_summary):
                    self.assertEqual(measure_maintainability.main([]), 0)

    def test_iso25040_exit_code_classification(self):
        self.assertEqual(evaluate_iso25040.classify_exit_code(0), "PASS")
        self.assertEqual(evaluate_iso25040.classify_exit_code(2), "WARN")
        self.assertEqual(evaluate_iso25040.classify_exit_code(1), "FAIL")

    def test_iso27001_27034_security_audit(self):
        res = audit_iso27001_27034.check_security(ROOT)
        self.assertGreater(res["c_files_scanned"], 0)
        self.assertTrue(res["has_wall_wextra"])
        self.assertEqual(res["critical_findings"], [])
        self.assertEqual(res["secret_findings"], [])
        self.assertTrue(res["passed"])

    def test_iso29119_testing_audit(self):
        res = audit_iso29119.evaluate_testing(ROOT)
        self.assertTrue(res["c_test_exists"])
        self.assertTrue(res["py_test_exists"])
        self.assertGreaterEqual(res["c_test_count"], 10)
        self.assertGreaterEqual(res["py_test_count"], 8)
        self.assertTrue(res["passed"])

    def test_iso9001_31000_qms_risk_audit(self):
        res = audit_iso9001_31000.evaluate_qms_and_risk(ROOT)
        self.assertTrue(res["has_metrics_gate"])
        self.assertTrue(res["has_quality_gate"])
        self.assertTrue(res["passed"])


class TestStreetWiring(unittest.TestCase):
    def test_make_utility_pole_3d(self):
        verts = street_wiring.make_utility_pole_3d(10.0, 5.0, 20.0, angle=0.5, has_transformer=False)
        verts_tx = street_wiring.make_utility_pole_3d(10.0, 5.0, 20.0, angle=0.5, has_transformer=True)
        self.assertGreater(len(verts), 0)
        self.assertEqual(len(verts) % 3, 0)
        self.assertGreater(len(verts_tx), len(verts))
        ys = []
        for pos, norm, uv, col, em in verts_tx:
            self.assertEqual(len(pos), 3)
            self.assertEqual(len(norm), 3)
            self.assertEqual(len(uv), 2)
            self.assertEqual(len(col), 4)
            self.assertAlmostEqual(col[3], street_wiring.MAT_SOLID, places=4)
            self.assertTrue(all(math.isfinite(v) for v in (*pos, *norm, *uv, *col, em)))
            ys.append(pos[1])
        self.assertAlmostEqual(max(ys), 5.0 + street_wiring.POLE_HEIGHT, places=2)

    def test_make_catenary_cable_3d(self):
        p0 = (0.0, 10.0, 0.0)
        p1 = (30.0, 10.0, 0.0)
        sag = 0.45
        verts = street_wiring.make_catenary_cable_3d(p0, p1, sag=sag, radius=0.025, segments=8)
        self.assertGreater(len(verts), 0)
        self.assertEqual(len(verts) % 3, 0)
        mid_ys = []
        for pos, norm, uv, col, em in verts:
            self.assertTrue(all(math.isfinite(v) for v in (*pos, *norm, *uv, *col, em)))
            if abs(pos[0] - 15.0) < 0.1:
                mid_ys.append(pos[1])
        self.assertGreater(len(mid_ys), 0)
        mid_center_y = sum(mid_ys) / len(mid_ys)
        self.assertGreater(10.0 - mid_center_y, 0.35)
        self.assertEqual(street_wiring.make_catenary_cable_3d(p0, p0), [])

    def test_utility_poles_rolcar_json_schema(self):
        json_path = os.path.join(ROOT, "models", "utility_poles_rolcar.json")
        self.assertTrue(os.path.isfile(json_path))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("poles", data)
        self.assertIn("spans", data)
        poles = data["poles"]
        spans = data["spans"]
        self.assertGreater(len(poles), 0)
        self.assertGreater(len(spans), 0)
        req_pole_keys = {"id", "lat", "lon", "x", "z", "mx", "mz", "angle", "source", "has_transformer"}
        pole_ids = set()
        paseo_poles = 0
        for p in poles:
            self.assertTrue(req_pole_keys.issubset(p.keys()))
            pole_ids.add(p["id"])
            self.assertIn(p["source"], ("osm_real", "osm_street_curb"))
            for k in ("lat", "lon", "x", "z", "angle"):
                self.assertTrue(math.isfinite(float(p[k])))
            if p["mx"] == 0 and p["mz"] == 0 and math.hypot(p["x"] - 971.23, p["z"] - 776.97) <= 180.0:
                paseo_poles += 1
        self.assertGreater(paseo_poles, 0)
        req_span_keys = {"a", "b", "mx", "mz", "cables"}
        for s in spans:
            self.assertTrue(req_span_keys.issubset(s.keys()))
            self.assertIn(s["a"], pole_ids)
            self.assertIn(s["b"], pole_ids)
            self.assertGreaterEqual(int(s["cables"]), 1)


if __name__ == "__main__":
    unittest.main()
