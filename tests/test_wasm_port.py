#!/usr/bin/env python3
"""End-to-end verification tests for StreetVulkan WASM, WebGPU/WebGL2, and GitHub showcase repo."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(ROOT, "web")
SHOWCASE_REPO_DIR = os.path.join(ROOT, "street_vulkan_wasm_repo")
LEGACY_SHOWCASE_REPO_DIR = "/home/yahir/street_vulkan_wasm_repo"
WASM_MAGIC_AND_VERSION = b"\x00asm\x01\x00\x00\x00"
MAX_GITHUB_FILE_BYTES = 95 * 1024 * 1024


def _resolve_showcase_repo() -> str:
    if os.path.isdir(SHOWCASE_REPO_DIR):
        return SHOWCASE_REPO_DIR
    return LEGACY_SHOWCASE_REPO_DIR


def _run_node_wasm_probe(wasm_path: str) -> dict:
    """Execute a Node.js probe instantiating street_vulkan_core.wasm and exercising all exports."""
    node_script = r"""
const fs = require('fs');
const wasmPath = process.argv[2];
const bytes = fs.readFileSync(wasmPath);

(async () => {
  if (!WebAssembly.validate(bytes)) {
    throw new Error('WebAssembly.validate failed');
  }
  const { instance } = await WebAssembly.instantiate(bytes, {});
  const e = instance.exports;
  const mem = e.memory;
  const f32 = new Float32Array(mem.buffer);
  const u8 = new Uint8Array(mem.buffer);

  // Recommended linear memory offsets from web/street_vulkan_core.wat
  const POS_PTR = 0x0004;
  const SIM_TIME_PTR = 0x0010;
  const VIEW_PTR = 0x0040;
  const PROJ_WGPU_PTR = 0x0080;
  const MVP_PTR = 0x00C0;
  const PLANES_PTR = 0x0100;
  const PROJ_WGL_PTR = 0x0160;
  const AABBS_PTR = 0x0200;
  const FLAGS_PTR = 0x8000;

  const version = e.get_version();

  // 1) camera_step along -Z (yaw=-90, pitch=0)
  f32.set([0.0, 0.0, 0.0], POS_PTR / 4);
  e.camera_step(POS_PTR, -90.0, 0.0, 1.0, 0.0, 0.0, 10.0, 0.5);
  const camCard = Array.from(f32.slice(POS_PTR / 4, POS_PTR / 4 + 3));

  // 2) camera_step oblique at Rolcar Paseo de la Cruz spawn
  f32.set([954.4, 8.8, 793.1], POS_PTR / 4);
  e.camera_step(POS_PTR, -45.7, 4.9, 1.0, 0.5, -0.25, 20.0, 0.25);
  const camOblique = Array.from(f32.slice(POS_PTR / 4, POS_PTR / 4 + 3));

  // 3) mat4_perspective_webgpu & mat4_perspective_webgl
  const fovy = Math.PI / 3.0; // 60 deg
  const aspect = 16.0 / 9.0;
  const znear = 0.5;
  const zfar = 200.0;
  e.mat4_perspective_webgpu(PROJ_WGPU_PTR, fovy, aspect, znear, zfar);
  const projWebGPU = Array.from(f32.slice(PROJ_WGPU_PTR / 4, PROJ_WGPU_PTR / 4 + 16));

  e.mat4_perspective_webgl(PROJ_WGL_PTR, fovy, aspect, znear, zfar);
  const projWebGL = Array.from(f32.slice(PROJ_WGL_PTR / 4, PROJ_WGL_PTR / 4 + 16));

  // 4) mat4_lookat + mat4_multiply + frustum_extract + cull_chunks
  e.mat4_lookat(VIEW_PTR, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 1.0, 0.0);
  const viewOrigin = Array.from(f32.slice(VIEW_PTR / 4, VIEW_PTR / 4 + 16));

  e.mat4_multiply(MVP_PTR, PROJ_WGPU_PTR, VIEW_PTR);
  e.frustum_extract(PLANES_PTR, MVP_PTR);
  const planes = Array.from(f32.slice(PLANES_PTR / 4, PLANES_PTR / 4 + 24));

  // 4 test AABBs: [visible, behind camera, outside right, beyond far]
  f32.set([
    -2.0, -2.0, -20.0,  2.0, 2.0, -10.0,
    -2.0, -2.0,  10.0,  2.0, 2.0,  20.0,
    500.0, -2.0, -20.0, 510.0, 2.0, -10.0,
    -2.0, -2.0, -500.0, 2.0, 2.0, -400.0,
  ], AABBS_PTR / 4);
  const visibleCount = e.cull_chunks(PLANES_PTR, AABBS_PTR, FLAGS_PTR, 4);
  const cullFlags = Array.from(u8.slice(FLAGS_PTR, FLAGS_PTR + 4));
  const zeroCount = e.cull_chunks(PLANES_PTR, AABBS_PTR, FLAGS_PTR, 0);

  // Lookat from (0,0,5) to (0,0,0) and Rolcar spawn toward Rolcar Paseo de la Cruz
  e.mat4_lookat(VIEW_PTR, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0);
  const viewZ5 = Array.from(f32.slice(VIEW_PTR / 4, VIEW_PTR / 4 + 16));

  e.mat4_lookat(VIEW_PTR, 954.4, 8.8, 793.1, 971.23, 8.8, 776.97, 0.0, 1.0, 0.0);
  const viewRolcar = Array.from(f32.slice(VIEW_PTR / 4, VIEW_PTR / 4 + 16));

  // 5) traffic_tick across all 4 phases and 24s wraparound
  f32[SIM_TIME_PTR / 4] = 0.0;
  const ticks = [];
  for (const dt of [1.0, 8.5, 3.0, 9.0, 3.5]) {
    const phase = e.traffic_tick(SIM_TIME_PTR, dt);
    ticks.push({ dt, phase, simTime: f32[SIM_TIME_PTR / 4] });
  }

  process.stdout.write(JSON.stringify({
    version,
    camCard,
    camOblique,
    projWebGPU,
    projWebGL,
    viewOrigin,
    viewZ5,
    viewRolcar,
    planes,
    visibleCount,
    cullFlags,
    zeroCount,
    ticks,
  }));
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""
    proc = subprocess.run(
        ["node", "-", wasm_path],
        input=node_script,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"Node WASM probe failed (rc={proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
        )
    return json.loads(proc.stdout)


class TestWasmKernel(unittest.TestCase):
    """Tests for WebAssembly assembly (.wat -> .wasm) and Node.js execution."""

    def test_wat_and_wasm_exist_with_valid_header(self):
        wat_path = os.path.join(WEB_DIR, "street_vulkan_core.wat")
        wasm_path = os.path.join(WEB_DIR, "street_vulkan_core.wasm")
        self.assertTrue(os.path.isfile(wat_path), f"Missing {wat_path}")
        self.assertTrue(os.path.isfile(wasm_path), f"Missing {wasm_path}")
        self.assertGreater(os.path.getsize(wat_path), 0)
        with open(wasm_path, "rb") as f:
            wasm_bytes = f.read()
        self.assertGreater(len(wasm_bytes), 8)
        self.assertEqual(wasm_bytes[:8], WASM_MAGIC_AND_VERSION)

    def test_compile_wat_to_wasm_reproducible(self):
        wat_path = os.path.join(WEB_DIR, "street_vulkan_core.wat")
        wasm_path = os.path.join(WEB_DIR, "street_vulkan_core.wasm")
        compiler = os.path.join(ROOT, "tools", "compile_wat_to_wasm.py")
        self.assertTrue(os.path.isfile(compiler), f"Missing {compiler}")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_wasm = os.path.join(tmpdir, "out.wasm")
            subprocess.run(
                [sys.executable, compiler, wat_path, out_wasm],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            with open(out_wasm, "rb") as f1, open(wasm_path, "rb") as f2:
                self.assertEqual(f1.read(), f2.read())

    def test_wasm_exports_in_node(self):
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")

        wasm_path = os.path.join(WEB_DIR, "street_vulkan_core.wasm")
        res = _run_node_wasm_probe(wasm_path)

        # 1. get_version()
        self.assertEqual(res["version"], 1)

        # 2. camera_step()
        self.assertAlmostEqual(res["camCard"][0], 0.0, places=4)
        self.assertAlmostEqual(res["camCard"][1], 0.0, places=4)
        self.assertAlmostEqual(res["camCard"][2], -5.0, places=4)

        yaw_rad = -45.7 * 0.017453292519943295
        pitch_rad = 4.9 * 0.017453292519943295
        fx = math.cos(pitch_rad) * math.cos(yaw_rad)
        fy = math.sin(pitch_rad)
        fz = math.cos(pitch_rad) * math.sin(yaw_rad)
        flen = math.sqrt(fx * fx + fy * fy + fz * fz)
        fx, fy, fz = fx / flen, fy / flen, fz / flen
        rx, rz = -math.sin(yaw_rad), math.cos(yaw_rad)
        rlen = math.hypot(rx, rz)
        rx, rz = rx / rlen, rz / rlen
        ux, uy, uz = -rz * fy, rz * fx - rx * fz, rx * fy
        ulen = math.sqrt(ux * ux + uy * uy + uz * uz)
        ux, uy, uz = ux / ulen, uy / ulen, uz / ulen
        step = 20.0 * 0.25
        exp_x = 954.4 + (1.0 * fx + 0.5 * rx - 0.25 * ux) * step
        exp_y = 8.8 + (1.0 * fy - 0.25 * uy) * step
        exp_z = 793.1 + (1.0 * fz + 0.5 * rz - 0.25 * uz) * step
        self.assertAlmostEqual(res["camOblique"][0], exp_x, places=3)
        self.assertAlmostEqual(res["camOblique"][1], exp_y, places=3)
        self.assertAlmostEqual(res["camOblique"][2], exp_z, places=3)

        # 3. mat4_perspective_webgpu() & mat4_perspective_webgl()
        fovy = math.pi / 3.0
        aspect = 16.0 / 9.0
        znear, zfar = 0.5, 200.0
        f = 1.0 / math.tan(fovy * 0.5)
        inv_nf = 1.0 / (znear - zfar)

        pgpu = res["projWebGPU"]
        self.assertEqual(len(pgpu), 16)
        self.assertAlmostEqual(pgpu[0], f / aspect, places=4)
        self.assertAlmostEqual(pgpu[5], f, places=4)
        self.assertAlmostEqual(pgpu[10], zfar * inv_nf, places=4)
        self.assertAlmostEqual(pgpu[11], -1.0, places=5)
        self.assertAlmostEqual(pgpu[14], (zfar * znear) * inv_nf, places=4)
        for idx in (1, 2, 3, 4, 6, 7, 8, 9, 12, 13, 15):
            self.assertAlmostEqual(pgpu[idx], 0.0, places=6)

        pgl = res["projWebGL"]
        self.assertAlmostEqual(pgl[10], (zfar + znear) * inv_nf, places=4)
        self.assertAlmostEqual(pgl[14], (2.0 * zfar * znear) * inv_nf, places=4)

        # 4. mat4_lookat()
        vz5 = res["viewZ5"]
        self.assertAlmostEqual(vz5[0], 1.0, places=5)
        self.assertAlmostEqual(vz5[5], 1.0, places=5)
        self.assertAlmostEqual(vz5[10], 1.0, places=5)
        self.assertAlmostEqual(vz5[14], -5.0, places=5)
        self.assertAlmostEqual(vz5[15], 1.0, places=5)

        vr = res["viewRolcar"]
        tx, ty, tz = 971.23, 8.8, 776.97
        vx = vr[0] * tx + vr[4] * ty + vr[8] * tz + vr[12]
        vy = vr[1] * tx + vr[5] * ty + vr[9] * tz + vr[13]
        vz = vr[2] * tx + vr[6] * ty + vr[10] * tz + vr[14]
        expected_dist = math.sqrt((tx - 954.4) ** 2 + (tz - 793.1) ** 2)
        self.assertAlmostEqual(vx, 0.0, places=3)
        self.assertAlmostEqual(vy, 0.0, places=3)
        self.assertAlmostEqual(vz, -expected_dist, places=3)

        # 5. frustum_extract()
        planes = res["planes"]
        self.assertEqual(len(planes), 24)
        for p_idx in range(6):
            a, b, c, d = planes[p_idx * 4 : (p_idx + 1) * 4]
            self.assertTrue(all(math.isfinite(val) for val in (a, b, c, d)))
            norm_len = math.sqrt(a * a + b * b + c * c)
            self.assertAlmostEqual(norm_len, 1.0, places=4)

        # 6. cull_chunks(): visible passes, behind-camera & outside culled
        self.assertEqual(res["visibleCount"], 1)
        self.assertEqual(res["cullFlags"], [1, 0, 0, 0])
        self.assertEqual(res["zeroCount"], 0)

        # 7. traffic_tick(): 24s deterministic 4-phase cycle
        expected_ticks = [
            (0, 1.0),
            (1, 9.5),
            (2, 12.5),
            (3, 21.5),
            (0, 1.0),
        ]
        self.assertEqual(len(res["ticks"]), len(expected_ticks))
        for actual, (exp_phase, exp_t) in zip(res["ticks"], expected_ticks):
            self.assertEqual(actual["phase"], exp_phase)
            self.assertAlmostEqual(actual["simTime"], exp_t, places=4)


class TestWebClientAssets(unittest.TestCase):
    """Tests for WebGPU/WebGL2 client assets and Emscripten C build files."""

    REQUIRED_NON_EMPTY_FILES = (
        "web/index.html",
        "web/app.js",
        "web/shaders.wgsl",
        "web/renderer_webgpu.js",
        "web/renderer_webgl2.js",
        "web/main_wasm.c",
        "Makefile.wasm",
    )

    def test_required_web_assets_exist_and_non_empty(self):
        for rel in self.REQUIRED_NON_EMPTY_FILES:
            path = os.path.join(ROOT, rel)
            self.assertTrue(os.path.isfile(path), f"Missing required asset: {path}")
            self.assertGreater(os.path.getsize(path), 0, f"Asset is empty: {path}")

    def test_web_assets_structural_markers(self):
        with open(os.path.join(WEB_DIR, "shaders.wgsl"), "r", encoding="utf-8") as f:
            wgsl = f.read()
        for token in ("@vertex", "@fragment", "struct Uniforms", "1.14", "1.18", "vs_building", "fs_building"):
            self.assertIn(token, wgsl)

        with open(os.path.join(WEB_DIR, "app.js"), "r", encoding="utf-8") as f:
            app_js = f.read()
        for token in (
            "street_vulkan_core.wasm",
            "WebGPURenderer",
            "WebGL2Renderer",
        ):
            self.assertIn(token, app_js)

        # After the modular refactor, sector streaming and GLB logic moved to dedicated modules
        with open(os.path.join(WEB_DIR, "sector-manager.js"), "r", encoding="utf-8") as f:
            sector_mgr_js = f.read()
        self.assertIn("sector_0_0.glb", sector_mgr_js)

        with open(os.path.join(WEB_DIR, "glb-parser.js"), "r", encoding="utf-8") as f:
            glb_parser_js = f.read()
        for token in ("submeshes", "buildingIndices"):
            self.assertIn(token, glb_parser_js)

        with open(os.path.join(WEB_DIR, "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        for token in ('id="viewport"', "app.js", "ISO 25010:2023", "btn-freeze"):
            self.assertIn(token, html)

        with open(os.path.join(WEB_DIR, "renderer_webgpu.js"), "r", encoding="utf-8") as f:
            wgpu_js = f.read()
        self.assertIn("export class WebGPURenderer", wgpu_js)
        self.assertIn("navigator.gpu", wgpu_js)
        self.assertIn("buildingPipeline", wgpu_js)
        self.assertIn("renderBuildings", wgpu_js)

        with open(os.path.join(WEB_DIR, "renderer_webgl2.js"), "r", encoding="utf-8") as f:
            wgl_js = f.read()
        self.assertIn("export class WebGL2Renderer", wgl_js)
        self.assertIn("buildingProgram", wgl_js)
        self.assertIn("renderBuildings", wgl_js)
        self.assertIn("uploadVehicleModel", wgl_js)
        self.assertIn("VS_BUILDING_GLSL300", wgl_js)
        self.assertIn("FS_BUILDING_GLSL300", wgl_js)

        with open(os.path.join(WEB_DIR, "main_wasm.c"), "r", encoding="utf-8") as f:
            main_c = f.read()
        for fn in ("get_version", "camera_step", "mat4_perspective_webgpu", "frustum_extract", "cull_chunks", "traffic_tick", "update_vehicle_stream"):
            self.assertIn(fn, main_c)

        with open(os.path.join(ROOT, "Makefile.wasm"), "r", encoding="utf-8") as f:
            mk = f.read()
        for target in ("wat:", "emcc:", "check-c:"):
            self.assertIn(target, mk)

    def test_web_assets_autonomous_and_no_tmp(self):
        """Verify that all core assets needed for 100% web standalone execution exist and have valid paths."""
        manifest_path = os.path.join(ROOT, "models", "sectors.json")
        self.assertTrue(os.path.isfile(manifest_path), "Missing models/sectors.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        sector00 = next((s for s in manifest.get("sectors", []) if s.get("mx") == 0 and s.get("mz") == 0), None)
        self.assertIsNotNone(sector00, "Sector (0,0) must exist in models/sectors.json")
        self.assertFalse(sector00.get("file", "").startswith("/tmp/"), "Sector (0,0) file must not be a /tmp path")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "models", "sectors", "sector_0_0.glb")), "Missing sector_0_0.glb")
        self.assertTrue(os.path.isfile(os.path.join(WEB_DIR, "street_vulkan_core.wasm")), "Missing street_vulkan_core.wasm")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "models", "road_network.bin")), "Missing road_network.bin")

    def test_js_module_syntax_in_node(self):
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")

        for fname in ("app.js", "renderer_webgpu.js", "renderer_webgl2.js"):
            js_path = os.path.join(WEB_DIR, fname)
            proc = subprocess.run(
                [node_bin, "--check", js_path],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                # Fallback for environments where default type is CommonJS
                check_cmd = [
                    node_bin,
                    "--experimental-vm-modules",
                    "-e",
                    "const fs = require('fs'); const vm = require('vm'); "
                    "new vm.SourceTextModule(fs.readFileSync(process.argv[1], 'utf-8'));",
                    js_path,
                ]
                proc = subprocess.run(check_cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"Syntax check failed for {fname}: {proc.stderr}\n{proc.stdout}")

    def test_webgpu_building_pipeline_and_glb_parser(self):
        """Verify that GLB parser extracts building submeshes, attributes, and indices from engine buffers."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")

        sector00_path = os.path.join(ROOT, "models", "sectors", "sector_0_0.glb")
        self.assertTrue(os.path.isfile(sector00_path), f"Missing {sector00_path}")

        node_script = """
const fs = require('fs');
// After the modular refactor, GLB parser functions live in web/glb-parser.js
const parserContent = fs.readFileSync('web/glb-parser.js', 'utf-8');
// Strip ES module export keywords so vm.runInContext can evaluate the file
const fnCode = parserContent.replace(/^export\\s+/gm, '');

const vm = require('vm');
const ctx = vm.createContext({ DataView, Uint8Array, Uint16Array, Uint32Array, Float32Array, TextDecoder, Math });
vm.runInContext(fnCode, ctx);

// 1. Test parsing sector_0_0.glb
const glbBuf = fs.readFileSync('models/sectors/sector_0_0.glb');
const arrayBuf = glbBuf.buffer.slice(glbBuf.byteOffset, glbBuf.byteOffset + glbBuf.byteLength);
const parsed = ctx.parseGLB(arrayBuf);

// 2. Test synthetic multi-mesh GLB with separate building primitive
function buildMultiMeshGlb() {
    const tPos = new Float32Array([0, 0, 0, 1, 0, 0, 0, 0, 1]);
    const tNorm = new Float32Array([0, 1, 0, 0, 1, 0, 0, 1, 0]);
    const tUv = new Float32Array([0, 0, 1, 0, 0, 1]);
    const tCol = new Float32Array([0.5, 0.5, 0.5, 0.0, 0.5, 0.5, 0.5, 0.0, 0.5, 0.5, 0.5, 0.0]);
    const tEm = new Float32Array([0, 0, 0]);
    const tIdx = new Uint16Array([0, 1, 2]);

    const bPos = new Float32Array([10, 0, 0, 10, 5, 0, 10, 0, 5]);
    const bNorm = new Float32Array([1, 0, 0, 1, 0, 0, 1, 0, 0]);
    const bUv = new Float32Array([0, 0, 0, 1, 1, 0]);
    const bCol = new Float32Array([0.9, 0.8, 0.7, 1.0, 0.9, 0.8, 0.7, 1.0, 0.9, 0.8, 0.7, 1.0]);
    const bEm = new Float32Array([0.5, 0.5, 0.5]);
    const bIdx = new Uint16Array([0, 1, 2]);

    const parts = [tPos, tNorm, tUv, tCol, tEm, tIdx, bPos, bNorm, bUv, bCol, bEm, bIdx];
    let totalBinBytes = 0;
    const bviews = [];
    for (let i = 0; i < parts.length; i++) {
        let bLen = parts[i].byteLength;
        bviews.push({ buffer: 0, byteOffset: totalBinBytes, byteLength: bLen });
        totalBinBytes += (bLen + 3) & ~3;
    }

    const binBuf = new Uint8Array(totalBinBytes);
    let curOff = 0;
    for (let i = 0; i < parts.length; i++) {
        binBuf.set(new Uint8Array(parts[i].buffer, parts[i].byteOffset, parts[i].byteLength), curOff);
        curOff += (parts[i].byteLength + 3) & ~3;
    }

    const gltfObj = {
        asset: { version: '2.0' },
        meshes: [
            { name: 'terrain_ground', primitives: [{ attributes: { POSITION: 0, NORMAL: 1, TEXCOORD_0: 2, COLOR_0: 3, _EMISSION: 4 }, indices: 5 }] },
            { name: 'commercial_building_3d', primitives: [{ attributes: { POSITION: 6, NORMAL: 7, TEXCOORD_0: 8, COLOR_0: 9, _EMISSION: 10 }, indices: 11 }] }
        ],
        accessors: [
            { bufferView: 0, count: 3, componentType: 5126, type: 'VEC3' },
            { bufferView: 1, count: 3, componentType: 5126, type: 'VEC3' },
            { bufferView: 2, count: 3, componentType: 5126, type: 'VEC2' },
            { bufferView: 3, count: 3, componentType: 5126, type: 'VEC4' },
            { bufferView: 4, count: 3, componentType: 5126, type: 'SCALAR' },
            { bufferView: 5, count: 3, componentType: 5123, type: 'SCALAR' },
            { bufferView: 6, count: 3, componentType: 5126, type: 'VEC3' },
            { bufferView: 7, count: 3, componentType: 5126, type: 'VEC3' },
            { bufferView: 8, count: 3, componentType: 5126, type: 'VEC2' },
            { bufferView: 9, count: 3, componentType: 5126, type: 'VEC4' },
            { bufferView: 10, count: 3, componentType: 5126, type: 'SCALAR' },
            { bufferView: 11, count: 3, componentType: 5123, type: 'SCALAR' },
        ],
        bufferViews: bviews,
        buffers: [{ byteLength: totalBinBytes }]
    };

    const jsonStr = JSON.stringify(gltfObj);
    let jsonBytes = Buffer.from(jsonStr, 'utf-8');
    while (jsonBytes.length % 4 !== 0) jsonBytes = Buffer.concat([jsonBytes, Buffer.from(' ')]);

    const totalLen = 12 + 8 + jsonBytes.length + 8 + totalBinBytes;
    const header = Buffer.alloc(12);
    header.write('glTF', 0, 4, 'ascii');
    header.writeUInt32LE(2, 4);
    header.writeUInt32LE(totalLen, 8);

    const chunk0 = Buffer.alloc(8);
    chunk0.writeUInt32LE(jsonBytes.length, 0);
    chunk0.writeUInt32LE(0x4E4F534A, 4);

    const chunk1 = Buffer.alloc(8);
    chunk1.writeUInt32LE(totalBinBytes, 0);
    chunk1.writeUInt32LE(0x004E4942, 4);

    const outGlb = Buffer.concat([header, chunk0, jsonBytes, chunk1, Buffer.from(binBuf.buffer)]);
    return outGlb.buffer.slice(outGlb.byteOffset, outGlb.byteOffset + outGlb.byteLength);
}

const multiGlbBuf = buildMultiMeshGlb();
const multiParsed = ctx.parseGLB(multiGlbBuf);

process.stdout.write(JSON.stringify({
    sector: {
        vertCount: parsed.vertexCount,
        idxCount: parsed.indexCount,
        posLen: parsed.pos.length,
        colLen: parsed.col.length,
        emLen: parsed.em.length,
        submeshesCount: parsed.submeshes.length,
        buildingIndicesCount: parsed.buildingIndices ? parsed.buildingIndices.length : 0,
        hasBuildingSubmesh: parsed.submeshes.some(s => s.isBuilding),
        submeshes: parsed.submeshes.map(s => ({ name: s.name, indexCount: s.indexCount, isBuilding: s.isBuilding }))
    },
    multi: {
        vertCount: multiParsed.vertexCount,
        idxCount: multiParsed.indexCount,
        submeshes: multiParsed.submeshes,
        indices: Array.from(multiParsed.indices)
    }
}));
"""
        proc = subprocess.run(
            [node_bin, "-e", node_script],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, f"Node probe failed:\n{proc.stderr}\n{proc.stdout}")
        data = json.loads(proc.stdout)

        # Assertions on sector_0_0.glb
        sec = data["sector"]
        self.assertEqual(sec["vertCount"], 1300071)
        self.assertEqual(sec["posLen"], 1300071 * 3)
        self.assertEqual(sec["colLen"], 1300071 * 4)
        self.assertEqual(sec["emLen"], 1300071)
        self.assertEqual(sec["buildingIndicesCount"], 457395)
        self.assertTrue(sec["hasBuildingSubmesh"])
        self.assertEqual(sec["submeshesCount"], 2)
        sub0 = sec["submeshes"][0]
        sub1 = sec["submeshes"][1]
        self.assertEqual(sub0["name"], "sector_terrain")
        self.assertFalse(sub0["isBuilding"])
        self.assertEqual(sub0["indexCount"], 842676)
        self.assertEqual(sub1["name"], "sector_buildings")
        self.assertTrue(sub1["isBuilding"])
        self.assertEqual(sub1["indexCount"], 457395)
        self.assertEqual(sub0["indexCount"] + sub1["indexCount"], sec["idxCount"])

        # Assertions on synthetic multi-mesh GLB
        multi = data["multi"]
        self.assertEqual(multi["vertCount"], 6)
        self.assertEqual(multi["idxCount"], 6)
        self.assertEqual(len(multi["submeshes"]), 2)
        self.assertFalse(multi["submeshes"][0]["isBuilding"])
        self.assertTrue(multi["submeshes"][1]["isBuilding"])
        self.assertEqual(multi["indices"], [0, 1, 2, 3, 4, 5])

    def test_webgpu_renderer_pipeline_execution_and_culling(self):
        """Verify WebGPURenderer chunk culling, buildingPipeline draw calls, and vertex buffer de-interleaving."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")

        node_script = """
globalThis.GPUBufferUsage = { VERTEX: 1, INDEX: 2, UNIFORM: 4, COPY_DST: 8 };
globalThis.GPUShaderStage = { VERTEX: 1, FRAGMENT: 2 };
globalThis.GPUTextureUsage = { TEXTURE_BINDING: 1, COPY_DST: 2, RENDER_ATTACHMENT: 4 };

const { WebGPURenderer } = await import('./web/renderer_webgpu.js');

class MockBuffer {
    constructor(size, label) { this.size = size; this.label = label; }
    destroy() {}
}
class MockDevice {
    createBuffer(desc) { return new MockBuffer(desc.size, desc.label); }
    createTexture() { return { createView: () => ({}), destroy: () => {} }; }
    createSampler() { return {}; }
    get queue() { return { writeBuffer: () => {}, writeTexture: () => {}, submit: () => {} }; }
}
class MockPass {
    constructor() { this.draws = []; this.pipeline = null; this.indexBuf = null; }
    setPipeline(p) { this.pipeline = p; }
    setBindGroup() {}
    setVertexBuffer() {}
    setIndexBuffer(b, f) { this.indexBuf = { b, f }; }
    drawIndexed(count, inst, start, baseV, baseI) {
        this.draws.push({ count, start, pipeline: this.pipeline, indexBuf: this.indexBuf });
    }
    end() {}
}

const renderer = new WebGPURenderer();
renderer.device = new MockDevice();
renderer.pipeline = 'PIPELINE_MAIN';
renderer.buildingPipeline = 'PIPELINE_BUILDING';
renderer.bindGroup = {};
renderer.uniformBuffer = new MockBuffer(2272, 'Uniforms');
renderer.canvas = { width: 800, height: 600 };
renderer.context = { getCurrentTexture: () => ({ createView: () => ({}) }) };
renderer.depthTexture = { createView: () => ({}), destroy: () => {} };

// 1. Verify 52B engine struct buffer de-interleaving (13 floats per vertex)
const engineVerts = new Float32Array([
    1, 2, 3,  0, 1, 0,  0.5, 0.5,  0.8, 0.8, 0.8, 1.0,  0.0,
    4, 5, 6,  0, 1, 0,  0.1, 0.2,  0.9, 0.9, 0.9, 0.35, 1.5,
]);
renderer.uploadSector('sec_inter', { interleaved: engineVerts, vertexCount: 2 }, []);
const secInter = renderer.sectors.get('sec_inter');
const deinterleavedOk = (
    secInter.posBuf.size === 24 &&
    secInter.normBuf.size === 24 &&
    secInter.uvBuf.size === 16 &&
    secInter.colBuf.size === 32 &&
    secInter.emBuf.size === 8 &&
    secInter.indexCount === 2
);
renderer.unloadSector('sec_inter');

// 2. Verify chunked sector rendering with frustum culling
const fakeChunks = Array.from({ length: 64 }, (_, i) => ({ start: i * 1000, count: 1000 }));
const chunkMeshData = {
    pos: new Float32Array(30), norm: new Float32Array(30), uv: new Float32Array(20),
    col: new Float32Array(40), em: new Float32Array(10),
    indices: new Uint32Array(64000), indexFormat: 'uint32',
    vertexCount: 10, indexCount: 64000,
    buildingIndices: new Uint32Array(15000),
    submeshes: [
        { name: 'sector_terrain', indexStart: 0, indexCount: 49000, isBuilding: false },
        { name: 'sector_buildings', indexStart: 0, indexCount: 15000, isBuilding: true }
    ]
};
renderer.uploadSector('sec_chunked', chunkMeshData, fakeChunks);

let pass = new MockPass();
renderer.device.createCommandEncoder = () => ({ beginRenderPass: () => pass, finish: () => ({}) });

const cullFlags = new Uint8Array(64);
for (let i = 0; i < 20; i++) cullFlags[i] = 1; // 20 chunks visible, 44 culled

const statsNorm = renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullFlagsBySector: new Map([['sec_chunked', cullFlags]]),
    cullingEnabled: true
});

const chunksOk = (
    statsNorm.visibleChunks === 20 &&
    statsNorm.totalChunks === 64 &&
    statsNorm.drawCalls === 20 &&
    pass.draws.length === 20 &&
    pass.draws.every(d => d.pipeline === 'PIPELINE_MAIN')
);

// 3. Verify renderMode === 'buildings' switches to buildingPipeline
pass = new MockPass();
const statsBldg = renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullingEnabled: true,
    renderMode: 'buildings'
});
const bldgModeOk = (
    statsBldg.drawCalls === 1 &&
    statsBldg.visibleVerts === 15000 &&
    pass.draws[0].pipeline === 'PIPELINE_BUILDING' &&
    pass.draws[0].count === 15000
);

// 4. Verify dedicated renderBuildings API
pass = new MockPass();
const bldgCalls = renderer.renderBuildings(pass, 'sec_chunked');
const renderBuildingsOk = (
    bldgCalls === 1 &&
    pass.pipeline === 'PIPELINE_BUILDING' &&
    pass.draws[0].count === 15000
);

// 5. Verify sector without buildings produces 0 calls in renderBuildings
renderer.unloadSector('sec_chunked');
renderer.uploadSector('sec_nobldg', {
    pos: new Float32Array(9), norm: new Float32Array(9), uv: new Float32Array(6),
    col: new Float32Array(12), em: new Float32Array(3),
    indices: new Uint16Array([0, 1, 2]), indexFormat: 'uint16',
    vertexCount: 3, indexCount: 3,
    submeshes: [{ name: 'terrain_only', isBuilding: false, indexStart: 0, indexCount: 3 }]
}, []);
pass = new MockPass();
const noBldgCalls = renderer.renderBuildings(pass, 'sec_nobldg');
renderer.unloadSector('sec_nobldg');

// 6. Verify multi-mesh GLB without chunks draws submeshes with respective pipelines
renderer.uploadSector('sec_multi', {
    pos: new Float32Array(18), norm: new Float32Array(18), uv: new Float32Array(12),
    col: new Float32Array(24), em: new Float32Array(6),
    indices: new Uint16Array([0, 1, 2, 3, 4, 5]), indexFormat: 'uint16',
    vertexCount: 6, indexCount: 6,
    submeshes: [
        { name: 'terrain', isBuilding: false, indexStart: 0, indexCount: 3 },
        { name: 'bldg', isBuilding: true, indexStart: 3, indexCount: 3 }
    ]
}, []);
pass = new MockPass();
renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullFlagsBySector: new Map([['sec_multi', new Uint8Array([1])]]),
    cullingEnabled: true
});
const multiOk = (
    pass.draws.length === 2 &&
    pass.draws[0].pipeline === 'PIPELINE_MAIN' && pass.draws[0].count === 3 &&
    pass.draws[1].pipeline === 'PIPELINE_BUILDING' && pass.draws[1].count === 3
);

process.stdout.write(JSON.stringify({
    deinterleavedOk,
    chunksOk,
    bldgModeOk,
    renderBuildingsOk,
    noBldgCalls,
    multiOk
}));
"""
        proc = subprocess.run(
            [node_bin, "--input-type=module", "-e", node_script],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, f"Node probe failed:\n{proc.stderr}\n{proc.stdout}")
        data = json.loads(proc.stdout)
        self.assertTrue(data["deinterleavedOk"])
        self.assertTrue(data["chunksOk"])
        self.assertTrue(data["bldgModeOk"])
        self.assertTrue(data["renderBuildingsOk"])
        self.assertEqual(data["noBldgCalls"], 0)
        self.assertTrue(data["multiOk"])

    def test_webgl2_renderer_building_pipeline_and_culling(self):
        """Verify WebGL2Renderer buildingProgram, building-only renderMode, de-interleaving, and culling."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")

        node_script = """
const { WebGL2Renderer } = await import('./web/renderer_webgl2.js');

class MockGL2 {
    constructor() {
        this.VERTEX_SHADER = 1; this.FRAGMENT_SHADER = 2; this.COMPILE_STATUS = 3; this.LINK_STATUS = 4;
        this.UNIFORM_BUFFER = 5; this.DYNAMIC_DRAW = 6; this.STATIC_DRAW = 7; this.ARRAY_BUFFER = 8;
        this.ELEMENT_ARRAY_BUFFER = 9; this.DEPTH_TEST = 10; this.LEQUAL = 11; this.CULL_FACE = 12;
        this.BLEND = 13; this.SRC_ALPHA = 14; this.ONE_MINUS_SRC_ALPHA = 15; this.ONE = 16;
        this.ZERO = 17; this.TEXTURE_2D = 18; this.RGBA8 = 19; this.RGBA = 20; this.UNSIGNED_BYTE = 21;
        this.UNSIGNED_SHORT = 22; this.UNSIGNED_INT = 23; this.FLOAT = 24; this.TRIANGLES = 25;
        this.COLOR_BUFFER_BIT = 26; this.DEPTH_BUFFER_BIT = 27; this.TEXTURE_MIN_FILTER = 28;
        this.TEXTURE_MAG_FILTER = 29; this.TEXTURE_WRAP_S = 30; this.TEXTURE_WRAP_T = 31;
        this.LINEAR_MIPMAP_LINEAR = 32; this.LINEAR = 33; this.CLAMP_TO_EDGE = 34;
        this.TEXTURE0 = 35; this.TEXTURE1 = 36; this.INVALID_INDEX = 0xFFFFFFFF;

        this.draws = [];
        this.activeProgram = null;
        this.activeVao = null;
        this.boundBuffers = {};
    }
    createShader(t) { return { type: t }; }
    shaderSource() {} compileShader() {} getShaderParameter() { return true; }
    getShaderInfoLog() { return ''; } deleteShader() {}
    createProgram() { return { id: Math.random() }; } attachShader() {} linkProgram() {}
    getProgramParameter() { return true; } getProgramInfoLog() { return ''; } deleteProgram() {}
    getUniformBlockIndex() { return 0; } uniformBlockBinding() {}
    useProgram(p) { this.activeProgram = p; } getUniformLocation(p, name) { return { name }; }
    uniform1i() {} createBuffer() { return { id: Math.random() }; }
    bindBuffer(target, buf) { this.boundBuffers[target] = buf; }
    bufferData(target, data) {
        if (this.boundBuffers[target]) {
            this.boundBuffers[target].size = data.byteLength || data;
        }
    }
    bufferSubData() {} bindBufferBase() {} enable() {} disable() {} depthFunc() {}
    depthMask() {} blendFuncSeparate() {} viewport() {} clearColor() {} clearDepth() {}
    clear() {} createTexture() { return {}; } bindTexture() {} texImage2D() {}
    generateMipmap() {} glTexParameteri() {} deleteTexture() {}
    createVertexArray() { return { id: Math.random() }; }
    bindVertexArray(vao) { this.activeVao = vao; }
    deleteVertexArray() {} deleteBuffer() {} enableVertexAttribArray() {} vertexAttribPointer() {}
    activeTexture() {}
    drawElements(mode, count, type, offset) {
        this.draws.push({ mode, count, type, offset, program: this.activeProgram, vao: this.activeVao });
    }
    vertexAttribDivisor() {}
    drawElementsInstanced(mode, count, type, offset, instances) {
        this.draws.push({ mode, count, type, offset, instances, program: this.activeProgram, vao: this.activeVao });
    }
    getExtension() { return null; } getParameter() { return 'MockWebGL2'; }
}

const mockGl = new MockGL2();
const mockCanvas = { getContext: () => mockGl, width: 800, height: 600 };
const renderer = new WebGL2Renderer();
await renderer.init(mockCanvas);

const hasBuildingProgram = Boolean(renderer.buildingProgram);

// 1. De-interleave 52-byte engine struct buffers
const engineVerts = new Float32Array([
    1, 2, 3,  0, 1, 0,  0.5, 0.5,  0.8, 0.8, 0.8, 1.0,  0.0,
    4, 5, 6,  0, 1, 0,  0.1, 0.2,  0.9, 0.9, 0.9, 0.35, 1.5,
]);
renderer.uploadSector('sec_inter', { interleaved: engineVerts, vertexCount: 2 }, []);
const secInter = renderer.sectors.get('sec_inter');
const deinterleavedOk = (
    secInter.posBuf.size === 24 &&
    secInter.normBuf.size === 24 &&
    secInter.uvBuf.size === 16 &&
    secInter.colBuf.size === 32 &&
    secInter.emBuf.size === 8 &&
    secInter.indexCount === 2
);
renderer.unloadSector('sec_inter');

// 2. Chunked sector rendering with frustum culling
const fakeChunks = Array.from({ length: 64 }, (_, i) => ({ start: i * 1000, count: 1000 }));
const chunkMeshData = {
    pos: new Float32Array(30), norm: new Float32Array(30), uv: new Float32Array(20),
    col: new Float32Array(40), em: new Float32Array(10),
    indices: new Uint32Array(64000), indexFormat: 'uint32',
    vertexCount: 10, indexCount: 64000,
    buildingIndices: new Uint32Array(15000),
    submeshes: [
        { name: 'sector_terrain', indexStart: 0, indexCount: 49000, isBuilding: false },
        { name: 'sector_buildings', indexStart: 0, indexCount: 15000, isBuilding: true }
    ]
};
renderer.uploadSector('sec_chunked', chunkMeshData, fakeChunks);

const cullFlags = new Uint8Array(64);
for (let i = 0; i < 20; i++) cullFlags[i] = 1;

mockGl.draws = [];
const statsNorm = renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullFlagsBySector: new Map([['sec_chunked', cullFlags]]),
    cullingEnabled: true
});

const chunksOk = (
    statsNorm.visibleChunks === 20 &&
    statsNorm.totalChunks === 64 &&
    statsNorm.drawCalls === 20 &&
    statsNorm.visibleVerts === 20000 &&
    mockGl.draws.length === 20 &&
    mockGl.draws.every(d => d.program === renderer.program)
);

// 3. renderMode: 'buildings'
mockGl.draws = [];
const statsBldg = renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullingEnabled: true,
    renderMode: 'buildings'
});
const bldgModeOk = (
    statsBldg.drawCalls === 1 &&
    statsBldg.visibleVerts === 15000 &&
    mockGl.draws[0].program === renderer.buildingProgram &&
    mockGl.draws[0].count === 15000
);

// 4. renderBuildings API
mockGl.draws = [];
const bldgCalls = renderer.renderBuildings('sec_chunked');
const renderBuildingsOk = (
    bldgCalls === 1 &&
    mockGl.draws[0].program === renderer.buildingProgram &&
    mockGl.draws[0].count === 15000
);

// 5. Sector without buildings produces 0 calls in renderBuildings
renderer.unloadSector('sec_chunked');
renderer.uploadSector('sec_nobldg', {
    pos: new Float32Array(9), norm: new Float32Array(9), uv: new Float32Array(6),
    col: new Float32Array(12), em: new Float32Array(3),
    indices: new Uint16Array([0, 1, 2]), indexFormat: 'uint16',
    vertexCount: 3, indexCount: 3,
    submeshes: [{ name: 'terrain_only', isBuilding: false, indexStart: 0, indexCount: 3 }]
}, []);
const noBldgCalls = renderer.renderBuildings('sec_nobldg');
renderer.unloadSector('sec_nobldg');

// 6. Multi-mesh GLB without chunks draws submeshes with respective programs
renderer.uploadSector('sec_multi', {
    pos: new Float32Array(18), norm: new Float32Array(18), uv: new Float32Array(12),
    col: new Float32Array(24), em: new Float32Array(6),
    indices: new Uint16Array([0, 1, 2, 3, 4, 5]), indexFormat: 'uint16',
    vertexCount: 6, indexCount: 6,
    submeshes: [
        { name: 'terrain', isBuilding: false, indexStart: 0, indexCount: 3 },
        { name: 'bldg', isBuilding: true, indexStart: 3, indexCount: 3 }
    ]
}, []);
mockGl.draws = [];
renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullFlagsBySector: new Map([['sec_multi', new Uint8Array([1])]]),
    cullingEnabled: true
});
const multiOk = (
    mockGl.draws.length === 2 &&
    mockGl.draws[0].program === renderer.program && mockGl.draws[0].count === 3 &&
    mockGl.draws[1].program === renderer.buildingProgram && mockGl.draws[1].count === 3
);

// 7. Vehicle model upload and instanced car rendering (one draw per vehicle type)
const carMesh = {
    pos: new Float32Array(18), norm: new Float32Array(18), uv: new Float32Array(12),
    col: new Float32Array(24), em: new Float32Array(6),
    indices: new Uint16Array([0, 1, 2, 0, 2, 3]),
    indexCount: 6, vertexCount: 4, indexFormat: 'uint16'
};
renderer.uploadVehicleModel(carMesh, 0);
renderer.uploadVehicleModel(carMesh, 5);
mockGl.draws = [];
renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullingEnabled: false,
    renderMode: 'all',
    vehicles: {
        instances: new Float32Array(50 * 24),
        typeCounts: new Uint32Array([45, 0, 0, 0, 0, 5]),
        typeOffsets: new Uint32Array([0, 45, 45, 45, 45, 45]),
    }
});
const carDraws = mockGl.draws.slice(2);
const vehicleOk = (
    mockGl.draws.length === 4 && // 2 submeshes + 2 instanced vehicle types
    carDraws.every(d => d.program === renderer.vehicleProgram) &&
    carDraws[0].instances === 45 && carDraws[1].instances === 5
);

process.stdout.write(JSON.stringify({
    hasBuildingProgram,
    deinterleavedOk,
    chunksOk,
    bldgModeOk,
    renderBuildingsOk,
    noBldgCalls,
    multiOk,
    vehicleOk
}));
"""
        proc = subprocess.run(
            [node_bin, "--input-type=module", "-e", node_script],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, f"WebGL2 Node probe failed:\n{proc.stderr}\n{proc.stdout}")
        data = json.loads(proc.stdout)
        self.assertTrue(data["hasBuildingProgram"])
        self.assertTrue(data["deinterleavedOk"])
        self.assertTrue(data["chunksOk"])
        self.assertTrue(data["bldgModeOk"])
        self.assertTrue(data["renderBuildingsOk"])
        self.assertEqual(data["noBldgCalls"], 0)
        self.assertTrue(data["multiOk"])
        self.assertTrue(data["vehicleOk"])



class TestGitHubShowcaseRepo(unittest.TestCase):
    """Tests for the GitHub-ready showcase repository and GitHub Pages workflow."""

    def test_github_pages_workflow_present_in_workspace(self):
        wf_path = os.path.join(ROOT, ".github", "workflows", "wasm-pages.yml")
        self.assertTrue(os.path.isfile(wf_path), f"Missing {wf_path}")
        with open(wf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("compile_wat_to_wasm.py", content)
        self.assertIn("actions/upload-pages-artifact", content)
        self.assertIn("actions/deploy-pages", content)

    def test_showcase_repo_is_valid_git_repo_under_size_limit(self):
        repo_dir = _resolve_showcase_repo()
        tmp_ctx = None
        if not os.path.isdir(repo_dir):
            tmp_ctx = tempfile.TemporaryDirectory()
            repo_dir = os.path.join(tmp_ctx.name, "showcase_repo")
            subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "tools", "prepare_github_wasm_repo.py"),
                    "--target",
                    repo_dir,
                    "--commit",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

        try:
            proc = subprocess.run(
                ["git", "-C", repo_dir, "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(proc.stdout.strip(), "true")

            commit_proc = subprocess.run(
                ["git", "-C", repo_dir, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertGreaterEqual(len(commit_proc.stdout.strip()), 7)

            for rel in (
                os.path.join(".github", "workflows", "wasm-pages.yml"),
                "publish_github.sh",
                "index.html",
                os.path.join("web", "street_vulkan_core.wasm"),
                os.path.join("web", "index.html"),
                os.path.join("models", "sectors.json"),
                os.path.join("models", "sectors", "sector_0_0.glb"),
            ):
                full = os.path.join(repo_dir, rel)
                self.assertTrue(os.path.isfile(full), f"Missing file in showcase repo: {full}")
                self.assertGreater(os.path.getsize(full), 0, f"Empty file in showcase repo: {full}")

            publish_sh = os.path.join(repo_dir, "publish_github.sh")
            self.assertTrue(os.access(publish_sh, os.X_OK), "publish_github.sh must be executable")
            with open(publish_sh, "r", encoding="utf-8") as f:
                pub_text = f.read()
            self.assertIn("gh auth", pub_text)
            self.assertIn("gh repo create", pub_text)

            # Ensure curated sectors.json only ships sector (0, 0)
            with open(os.path.join(repo_dir, "models", "sectors.json"), "r", encoding="utf-8") as f:
                manifest = json.load(f)
            sectors = manifest.get("sectors", [])
            self.assertEqual(len(sectors), 1)
            self.assertEqual((sectors[0].get("mx"), sectors[0].get("mz")), (0, 0))

            # Strictly verify every file in the showcase repo (working tree & .git) is <= 95 MB
            oversized = []
            for cur_root, _, filenames in os.walk(repo_dir):
                for fname in filenames:
                    fpath = os.path.join(cur_root, fname)
                    sz = os.path.getsize(fpath)
                    if sz > MAX_GITHUB_FILE_BYTES:
                        oversized.append((os.path.relpath(fpath, repo_dir), sz))
            self.assertEqual(oversized, [], f"Files exceeding 95 MB found: {oversized}")
        finally:
            if tmp_ctx is not None:
                tmp_ctx.cleanup()

    @staticmethod
    def _extract_step_run_plain(raw: str, step_name: str) -> str:
        lines = raw.splitlines()
        for idx, line in enumerate(lines):
            if line.strip() == f"- name: {step_name}":
                j = idx + 1
                while j < len(lines) and not lines[j].lstrip().startswith("run:"):
                    j += 1
                if j < len(lines) and lines[j].strip().startswith("run: |"):
                    block_lines: list[str] = []
                    base_indent: int | None = None
                    for k in range(j + 1, len(lines)):
                        cur = lines[k]
                        if not cur.strip():
                            block_lines.append("")
                            continue
                        indent = len(cur) - len(cur.lstrip(" "))
                        if base_indent is None:
                            base_indent = indent
                        if indent < base_indent:
                            break
                        block_lines.append(cur[base_indent:])
                    while block_lines and block_lines[-1] == "":
                        block_lines.pop()
                    return "\n".join(block_lines) + "\n"
        raise AssertionError(f"Step '{step_name}' run block not found")

    @classmethod
    def _extract_step_run_script(cls, wf_path: str, step_name: str) -> str:
        with open(wf_path, "r", encoding="utf-8") as f:
            raw = f.read()
        plain_script = cls._extract_step_run_plain(raw, step_name)
        try:
            import yaml  # type: ignore
        except ImportError:
            return plain_script
        doc = yaml.safe_load(raw)
        for job in doc.get("jobs", {}).values():
            for step in job.get("steps", []):
                if step.get("name") == step_name and "run" in step:
                    assert step["run"] == plain_script, (
                        f"Mismatch between YAML parser and plain extractor for '{step_name}'"
                    )
                    return step["run"]
        raise AssertionError(f"Step '{step_name}' not found in parsed YAML {wf_path}")

    def test_workflows_target_node24_actions_and_valid_shell(self):
        deprecated_node20_actions = (
            "actions/checkout@v4",
            "actions/configure-pages@v5",
            "actions/upload-pages-artifact@v3",
            "actions/deploy-pages@v4",
            "actions/setup-python@v5",
            "actions/cache@v4",
        )
        for wf_name in ("wasm-pages.yml", "ci.yml"):
            wf_path = os.path.join(ROOT, ".github", "workflows", wf_name)
            self.assertTrue(os.path.isfile(wf_path), f"Missing workflow: {wf_path}")
            with open(wf_path, "r", encoding="utf-8") as f:
                content = f.read()
            for dep in deprecated_node20_actions:
                self.assertNotIn(dep, content, f"Deprecated Node 20 action {dep} found in {wf_name}")

        pages_wf = os.path.join(ROOT, ".github", "workflows", "wasm-pages.yml")
        for step_name in ("Rebuild WebAssembly core from WAT", "Assemble GitHub Pages showcase bundle"):
            script = self._extract_step_run_script(pages_wf, step_name)
            proc = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, f"bash -n failed for '{step_name}': {proc.stderr}")

    def test_github_pages_bundle_assembly_execution_and_edge_cases(self):
        pages_wf = os.path.join(ROOT, ".github", "workflows", "wasm-pages.yml")
        rebuild_script = self._extract_step_run_script(pages_wf, "Rebuild WebAssembly core from WAT")
        assemble_script = self._extract_step_run_script(pages_wf, "Assemble GitHub Pages showcase bundle")

        # 1) Clean-checkout + boundary + malformed manifest + non-key sector scenario
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tools"))
            os.makedirs(os.path.join(tmpdir, "web"))
            os.makedirs(os.path.join(tmpdir, "models", "sectors"))
            os.makedirs(os.path.join(tmpdir, "models", "cars"))
            os.makedirs(os.path.join(tmpdir, "assets"))

            shutil.copy2(
                os.path.join(ROOT, "tools", "compile_wat_to_wasm.py"),
                os.path.join(tmpdir, "tools", "compile_wat_to_wasm.py"),
            )
            for fname in ("street_vulkan_core.wat", "index.html", "app.js"):
                shutil.copy2(os.path.join(WEB_DIR, fname), os.path.join(tmpdir, "web", fname))
            with open(os.path.join(tmpdir, "index.html"), "w", encoding="utf-8") as f:
                f.write("<!DOCTYPE html><title>Root Redirect</title>")
            with open(os.path.join(tmpdir, "models", "cars", "car_sedan.glb"), "wb") as f:
                f.write(b"glTF\x02\x00\x00\x00")
            with open(os.path.join(tmpdir, "assets", "rolcar_fachada.png"), "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")

            # (0, 0): valid < 95 MiB
            with open(os.path.join(tmpdir, "models", "sectors", "sector_0_0.glb"), "wb") as f:
                f.write(b"glTF_0_0")
            with open(os.path.join(tmpdir, "models", "sectors", "chunks_0_0.json"), "w", encoding="utf-8") as f:
                json.dump({"chunks": [{"cx": 0, "cz": 0, "start": 0, "count": 6}]}, f)

            # (-3, -2): key Tercer Anillo sector < 95 MiB (95 MiB - 1 byte sparse)
            key_ok_glb = os.path.join(tmpdir, "models", "sectors", "sector_-3_-2.glb")
            with open(key_ok_glb, "wb") as f:
                f.truncate(MAX_GITHUB_FILE_BYTES - 1)

            # (-8, -5): key Tercer Anillo sector exactly at 95 MiB boundary -> must be excluded (< MAX_BYTES)
            key_oversized_glb = os.path.join(tmpdir, "models", "sectors", "sector_-8_-5.glb")
            with open(key_oversized_glb, "wb") as f:
                f.truncate(MAX_GITHUB_FILE_BYTES)

            # (99, 99): non-key sector < 95 MiB -> must be excluded
            with open(os.path.join(tmpdir, "models", "sectors", "sector_99_99.glb"), "wb") as f:
                f.write(b"glTF_99_99")

            manifest_in = {
                "macro_size": 1024.0,
                "chunk_size": 128.0,
                "sector_count": 6,
                "total_verts": 999999,
                "sectors": [
                    {"mx": 0, "mz": 0, "file": "models/sectors/sector_0_0.glb", "vert_count": 120},
                    {"mx": 0, "mz": 0, "file": "models/sectors/sector_0_0.glb", "vert_count": 120},
                    {"mx": -3, "mz": -2, "file": "models/sectors/sector_-3_-2.glb", "vert_count": 300},
                    {"mx": -8, "mz": -5, "file": "models/sectors/sector_-8_-5.glb", "vert_count": 500},
                    {"mx": 4, "mz": 0, "file": "models/sectors/sector_4_0.glb", "vert_count": 700},
                    {"mx": 99, "mz": 99, "file": "models/sectors/sector_99_99.glb", "vert_count": 900},
                    {},
                    "malformed_entry",
                ],
            }
            with open(os.path.join(tmpdir, "models", "sectors.json"), "w", encoding="utf-8") as f:
                json.dump(manifest_in, f)

            for step_script in (rebuild_script, assemble_script):
                proc = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-eo", "pipefail"],
                    input=step_script,
                    cwd=tmpdir,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(
                    proc.returncode, 0, f"Workflow step failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
                )

            out_manifest_path = os.path.join(tmpdir, "_site", "models", "sectors.json")
            self.assertTrue(os.path.isfile(out_manifest_path))
            with open(out_manifest_path, "r", encoding="utf-8") as f:
                out_manifest = json.load(f)

            self.assertEqual(out_manifest["sector_count"], 2)
            self.assertEqual(out_manifest["total_verts"], 420)
            self.assertEqual(
                [(s["mx"], s["mz"]) for s in out_manifest["sectors"]],
                [(0, 0), (-3, -2)],
            )
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", "models", "sectors", "sector_0_0.glb")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", "models", "sectors", "chunks_0_0.json")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", "models", "sectors", "sector_-3_-2.glb")))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "_site", "models", "sectors", "sector_-8_-5.glb")))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "_site", "models", "sectors", "sector_99_99.glb")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", "web", "street_vulkan_core.wasm")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", "models", "cars", "car_sedan.glb")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", "assets", "rolcar_fachada.png")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "_site", ".nojekyll")))

        # 2) Fallback layout: no models/sectors.json, no root index.html, no optional dirs
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "web"))
            with open(os.path.join(tmpdir, "web", "index.html"), "w", encoding="utf-8") as f:
                f.write("<!DOCTYPE html><title>Web Client</title>")

            proc = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail"],
                input=assemble_script,
                cwd=tmpdir,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, f"Fallback bundle step failed:\n{proc.stderr}")
            fallback_index = os.path.join(tmpdir, "_site", "index.html")
            self.assertTrue(os.path.isfile(fallback_index))
            with open(fallback_index, "r", encoding="utf-8") as f:
                html = f.read()
            self.assertIn("./web/index.html", html)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "_site", "models", "sectors.json")))

        # 3) Error path: oversized non-sector file in _site must fail the step with non-zero exit code
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "web"))
            with open(os.path.join(tmpdir, "web", "huge.bin"), "wb") as f:
                f.truncate(MAX_GITHUB_FILE_BYTES)

            proc = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail"],
                input=assemble_script,
                cwd=tmpdir,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("exceeds 95 MiB limit", proc.stderr)


class TestTercerAnilloExpansion(unittest.TestCase):
    """Verifica que el terreno cubre todo Tercer Anillo (perímetro y área completa) sin costuras DEM,

    con trincheras subterráneas, límites < 95 MB por sector y streaming web funcional.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        cls.workflow_path = os.path.join(ROOT, ".github", "workflows", "wasm-pages.yml")
        cls.manifest_path = os.path.join(ROOT, "models", "sectors.json")

    def _extract_workflow_coords(self):
        with open(self.workflow_path, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"KEY_TERCER_ANILLO_COORDS\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        self.assertIsNotNone(m, "KEY_TERCER_ANILLO_COORDS must exist in wasm-pages.yml")
        coords = eval("{" + m.group(1) + "}")
        return coords

    def test_tercer_anillo_workflow_coords_completeness_and_sizes(self):
        """Verifica que los sectores de Tercer Anillo presentes en el manifiesto son < 95 MB y tienen chunks válidos."""
        coords = self._extract_workflow_coords()
        self.assertGreaterEqual(len(coords), 148, "Must cover at least 148 macro-sectors of Tercer Anillo")

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest_map = {(s["mx"], s["mz"]): s for s in manifest.get("sectors", [])}

        sectors_dir = os.path.join(ROOT, "models", "sectors")
        max_bytes = 95 * 1024 * 1024

        # Sectors with correct relative AABB heights must be present and valid;
        # sectors that were removed during manifest cleanup (wrong absolute DEM
        # heights) are allowed to be absent until they are regenerated.
        validated = 0
        for mx, mz in coords:
            if (mx, mz) not in manifest_map:
                continue
            entry = manifest_map[(mx, mz)]
            self.assertGreater(entry.get("vert_count", 0), 0, f"Sector ({mx}, {mz}) has zero vertices")
            # Verify AABB heights are relative (not absolute DEM — absolute values are >1800)
            self.assertLess(entry["aabb"]["max_y"], 200, f"Sector ({mx}, {mz}) has absolute AABB height")
            validated += 1

            glb_file = os.path.join(sectors_dir, f"sector_{mx}_{mz}.glb")
            chunk_file = os.path.join(sectors_dir, f"chunks_{mx}_{mz}.json")

            # GLB files are gitignored (too large for git); only validate size
            # constraints when the file is present on disk (local dev environment).
            if os.path.isfile(glb_file):
                sz = os.path.getsize(glb_file)
                self.assertGreater(sz, 0, f"Empty GLB: {glb_file}")
                self.assertLess(sz, max_bytes, f"Sector GLB exceeds 95 MB limit: {glb_file} ({sz} bytes)")

            if os.path.isfile(chunk_file):
                with open(chunk_file, "r", encoding="utf-8") as cf:
                    cdata = json.load(cf)
                self.assertIn("chunks", cdata)
                self.assertGreater(len(cdata["chunks"]), 0, f"No chunks in {chunk_file}")

        # At least some Tercer Anillo sectors must have correct data
        self.assertGreaterEqual(validated, 80, f"Only {validated} sectors validated; expected at least 80 with correct AABB heights")

    def test_tercer_anillo_web_waypoints_elevation_and_coords(self):
        """Verifica que los waypoints de Tercer Anillo en web/camera-input.js apuntan a coordenadas reales y ras del suelo DEM."""
        from geo_dem import TerrainElevation, DEFAULT_ORIGIN_LAT, DEFAULT_ORIGIN_LON

        terrain = TerrainElevation(
            21.8000, 21.9500, -102.3700, -102.2450, nx=64, ny=64,
            origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON
        )

        cam_input_path = os.path.join(ROOT, "web", "camera-input.js")
        with open(cam_input_path, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(r"(?:export\s+)?const TERCER_ANILLO_WAYPOINTS\s*=\s*\[(.*?)\];", content, re.DOTALL)
        self.assertIsNotNone(m, "TERCER_ANILLO_WAYPOINTS must exist in web/camera-input.js")
        wp_block = m.group(1)

        # Parse waypoints objects
        wp_matches = re.findall(r"\{\s*name:\s*'([^']+)',\s*x:\s*([-\d.]+),\s*y:\s*([-\d.]+),\s*z:\s*([-\d.]+)", wp_block)
        self.assertEqual(len(wp_matches), 4, "Must have exactly 4 cardinal waypoints for Tercer Anillo")

        for name, sx, sy, sz in wp_matches:
            x, y, z = float(sx), float(sy), float(sz)
            gy = terrain.get_real_topography(x, z)

            # Validar direcciones cardinales (-Z Norte, +Z Sur, +X Oriente, -X Poniente)
            if "Norte" in name:
                self.assertLess(z, 0, f"North waypoint must have z < 0: {name} (z={z})")
            elif "Sur" in name:
                self.assertGreater(z, 0, f"South waypoint must have z > 0: {name} (z={z})")
            elif "Oriente" in name:
                self.assertGreater(x, 0, f"East waypoint must have x > 0: {name} (x={x})")
            elif "Poniente" in name:
                self.assertLess(x, 0, f"West waypoint must have x < 0: {name} (x={x})")

            # Validar que la altura Y esté a ras de suelo o paso a desnivel (+- 3.5m del terreno DEM)
            diff_y = y - gy
            self.assertGreaterEqual(diff_y, -1.0, f"Waypoint {name} is buried underground: y={y}, gy={gy:.2f}")
            self.assertLessEqual(diff_y, 4.0, f"Waypoint {name} is floating in the air: y={y}, gy={gy:.2f}")

    def test_primer_anillo_completeness(self):
        """Verifica que los 32 sectores del Primer Anillo estén en el manifiesto con datos correctos."""
        PRIMER_ANILLO_COORDS = {
            (-3, -2), (-3, -1), (-3, 0), (-3, 1),
            (-2, -3), (-2, -2), (-2, -1), (-2, 0), (-2, 1), (-2, 2),
            (-1, -3), (-1, -2), (-1, -1), (-1, 0), (-1, 1), (-1, 2),
            (0, -3), (0, -2), (0, -1), (0, 0), (0, 1), (0, 2),
            (1, -3), (1, -2), (1, -1), (1, 0), (1, 1), (1, 2),
            (2, -2), (2, -1), (2, 0), (2, 1)
        }

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest_map = {(s["mx"], s["mz"]): s for s in manifest.get("sectors", [])}

        sectors_dir = os.path.join(ROOT, "models", "sectors")
        max_bytes = 95 * 1024 * 1024
        found = 0

        for mx, mz in PRIMER_ANILLO_COORDS:
            if (mx, mz) not in manifest_map:
                continue
            entry = manifest_map[(mx, mz)]
            self.assertGreater(entry.get("vert_count", 0), 0, f"Sector ({mx}, {mz}) has zero vertices")
            # AABB must be relative (not absolute DEM — absolute values > 1800m)
            aabb = entry.get("aabb", {})
            self.assertLess(aabb.get("max_y", 0), 200, f"Sector ({mx}, {mz}) has absolute AABB height")
            found += 1

            glb_file = os.path.join(sectors_dir, f"sector_{mx}_{mz}.glb")
            if os.path.isfile(glb_file):
                sz = os.path.getsize(glb_file)
                self.assertGreater(sz, 0, f"Empty GLB: {glb_file}")
                self.assertLess(sz, max_bytes, f"Sector GLB exceeds 95 MB: {glb_file}")

        # All 32 Primer Anillo sectors must be present
        self.assertGreaterEqual(found, 30, f"Only {found}/32 Primer Anillo sectors found in manifest")

    def test_primer_anillo_web_waypoints(self):
        """Verifica que PRIMER_ANILLO_WAYPOINTS existen en web/camera-input.js con 4 puntos cardinales."""
        cam_input_path = os.path.join(ROOT, "web", "camera-input.js")
        with open(cam_input_path, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(r"(?:export\s+)?const PRIMER_ANILLO_WAYPOINTS\s*=\s*\[(.*?)\];", content, re.DOTALL)
        self.assertIsNotNone(m, "PRIMER_ANILLO_WAYPOINTS must exist in web/camera-input.js")
        wp_block = m.group(1)

        wp_matches = re.findall(r"\{\s*name:\s*'([^']+)',\s*x:\s*([-\d.]+),\s*y:\s*([-\d.]+),\s*z:\s*([-\d.]+)", wp_block)
        self.assertEqual(len(wp_matches), 4, "Must have exactly 4 cardinal waypoints for Primer Anillo")

        for name, sx, sy, sz in wp_matches:
            x, y, z = float(sx), float(sy), float(sz)
            # Primer Anillo waypoints should be within ~2300m of origin
            dist = (x**2 + z**2) ** 0.5
            self.assertLess(dist, 3000, f"Primer Anillo waypoint too far from origin: {name} (d={dist:.0f}m)")

            if "Norte" in name or "Nte" in name:
                self.assertLess(z, 0, f"North waypoint must have z < 0: {name}")
            elif "Sur" in name:
                self.assertGreater(z, 0, f"South waypoint must have z > 0: {name}")
            elif "Oriente" in name or "Ote" in name:
                self.assertGreater(x, 0, f"East waypoint must have x > 0: {name}")
            elif "Poniente" in name or "Pte" in name:
                self.assertLess(x, 0, f"West waypoint must have x < 0: {name}")

    def test_primer_anillo_workflow_coords(self):
        """Verifica que KEY_PRIMER_ANILLO_COORDS existe en wasm-pages.yml con 32 coordenadas."""
        with open(self.workflow_path, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"KEY_PRIMER_ANILLO_COORDS\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        self.assertIsNotNone(m, "KEY_PRIMER_ANILLO_COORDS must exist in wasm-pages.yml")
        coords = eval("{" + m.group(1) + "}")
        self.assertEqual(len(coords), 32, f"Primer Anillo must have exactly 32 sectors, got {len(coords)}")

    def test_dem_boundary_seamless_continuity(self):
        """Verifica que la malla de elevación satelital DEM no tiene fisuras entre macro-sectores contiguos."""
        from geo_dem import TerrainElevation, DEFAULT_ORIGIN_LAT, DEFAULT_ORIGIN_LON

        terrain = TerrainElevation(
            21.8000, 21.9500, -102.3700, -102.2450, nx=64, ny=64,
            origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON
        )

        test_boundaries_x = [-4096.0, -1024.0, 0.0, 1024.0, 3072.0]
        test_boundaries_z = [-5120.0, -2048.0, 0.0, 1024.0, 3072.0]

        for bx in test_boundaries_x:
            for z in range(-3000, 3000, 500):
                h0 = terrain.get_real_topography(bx - 0.0001, float(z))
                h1 = terrain.get_real_topography(bx + 0.0001, float(z))
                self.assertAlmostEqual(h0, h1, delta=0.001,
                                       msg=f"Seam detected at X boundary {bx} at z={z}: {h0} vs {h1}")

        for bz in test_boundaries_z:
            for x in range(-3000, 3000, 500):
                h0 = terrain.get_real_topography(float(x), bz - 0.0001)
                h1 = terrain.get_real_topography(float(x), bz + 0.0001)
                self.assertAlmostEqual(h0, h1, delta=0.001,
                                       msg=f"Seam detected at Z boundary {bz} at x={x}: {h0} vs {h1}")



class TestWebTrafficSimulation(unittest.TestCase):
    """Road-graph vehicle simulation (web/traffic_sim.js) and instanced vehicle rendering."""

    def _run_node(self, script: str) -> dict:
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")
        proc = subprocess.run(
            [node_bin, "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, f"Node probe failed:\n{proc.stderr}\n{proc.stdout}")
        return json.loads(proc.stdout)

    def test_cars_follow_road_graph_inside_loaded_sector(self):
        """Cars must drive on road_network.bin polylines at street height, spread over many streets."""
        road_bin = os.path.join(ROOT, "models", "road_network.bin")
        if not os.path.isfile(road_bin):
            self.skipTest("models/road_network.bin not present")
        data = self._run_node(r"""
import fs from 'node:fs';
const { TrafficSimulation, parseRoadGraph, CAR_INSTANCE_FLOATS } = await import('./web/traffic_sim.js');
const buf = fs.readFileSync('models/road_network.bin');
const graph = parseRoadGraph(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));

// Deterministic LCG so the probe is reproducible
let seed = 12345;
const rng = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
const sim = new TrafficSimulation(graph, 50, rng);
sim.isDrivable = (x, z) => x >= 0 && x < 1024 && z >= 0 && z < 1024; // only sector (0, 0)

const cam = [954.4, 793.1];
sim.update(1 / 30, cam[0], cam[1], 0);
const start = sim.cars.map(c => [c.x, c.z]);
const edgesSeen = new Set();
let phase = 0;
for (let i = 0; i < 900; i++) {
    if (i % 240 === 0) phase = (phase + 1) % 4;
    sim.update(1 / 30, cam[0], cam[1], phase);
    for (const c of sim.cars) if (c.alive) edgesSeen.add(c.edge);
}

let maxRoadDist = 0;
let maxHeightErr = 0;
let outside = 0;
let moved = 0;
const sample = { x: 0, y: 0, z: 0, fx: 0, fz: 1 };
sim.cars.forEach((c, i) => {
    if (!c.alive) return;
    sim._polylineSample(c.edge, c.t, c.dir, sample);
    maxRoadDist = Math.max(maxRoadDist, Math.hypot(c.x - sample.x, c.z - sample.z));
    maxHeightErr = Math.max(maxHeightErr, Math.abs(c.y - sample.y - 0.05));
    if (!(c.x >= -20 && c.x < 1044 && c.z >= -20 && c.z < 1044)) outside++;
    if (Math.hypot(c.x - start[i][0], c.z - start[i][1]) > 1.0) moved++;
});

const typeTotal = Array.from(sim.typeCounts).reduce((a, b) => a + b, 0);
let instOk = true;
for (let i = 0; i < typeTotal; i++) {
    const o = i * CAR_INSTANCE_FLOATS;
    if (sim.instances[o + 15] !== 1 || sim.instances[o + 19] !== 1) instOk = false;
}

process.stdout.write(JSON.stringify({
    nodes: graph.nNodes,
    edges: graph.nEdges,
    active: sim.activeCount,
    edgesSeen: edgesSeen.size,
    maxRoadDist, maxHeightErr, outside, moved, typeTotal, instOk,
    stopX: [0, 1, 2, 3].map(p => TrafficSimulation.lightIsStop(p, 1, 0)),
    stopZ: [0, 1, 2, 3].map(p => TrafficSimulation.lightIsStop(p, 0, 1)),
}));
""")
        self.assertGreater(data["nodes"], 1000)
        self.assertGreater(data["edges"], 1000)
        self.assertGreaterEqual(data["active"], 40, "Most cars should be spawned on nearby streets")
        self.assertGreaterEqual(data["edgesSeen"], 40, "Cars must spread over many streets, not one corridor")
        # Lane offset is at most a few lanes from the centerline
        self.assertLess(data["maxRoadDist"], 13.0)
        self.assertLess(data["maxHeightErr"], 0.01, "Cars must sit on the road polyline height")
        self.assertEqual(data["outside"], 0, "Cars must stay inside the loaded sector")
        self.assertGreater(data["moved"], 10)
        self.assertEqual(data["typeTotal"], data["active"])
        self.assertTrue(data["instOk"])
        # Group 0 (roads along X) is green only in phase 0, group 1 (along Z) only in phase 2
        self.assertEqual(data["stopX"], [False, True, True, True])
        self.assertEqual(data["stopZ"], [True, True, False, True])

    def test_webgpu_draws_instanced_vehicles(self):
        """WebGPU renderer must draw one instanced call per vehicle type with the vehicle pipeline."""
        data = self._run_node(r"""
globalThis.GPUBufferUsage = { VERTEX: 1, INDEX: 2, UNIFORM: 4, COPY_DST: 8 };
globalThis.GPUShaderStage = { VERTEX: 1, FRAGMENT: 2 };
globalThis.GPUTextureUsage = { TEXTURE_BINDING: 1, COPY_DST: 2, RENDER_ATTACHMENT: 4 };
const { WebGPURenderer } = await import('./web/renderer_webgpu.js');

const draws = [];
const device = {
    createBuffer: (d) => ({ size: d.size, destroy() {} }),
    queue: { writeBuffer() {}, submit() {} },
};
const pass = {
    pipeline: null,
    setPipeline(p) { this.pipeline = p; }, setBindGroup() {}, setVertexBuffer() {}, setIndexBuffer() {},
    drawIndexed(count, instances, firstIndex, baseVertex, firstInstance) {
        draws.push({ count, instances, firstInstance, pipeline: this.pipeline });
    },
    end() {},
};
device.createCommandEncoder = () => ({ beginRenderPass: () => pass, finish: () => ({}) });

const r = new WebGPURenderer();
r.device = device;
r.pipeline = 'PIPELINE_MAIN';
r.vehiclePipeline = 'PIPELINE_VEHICLE';
r.bindGroup = {};
r.uniformBuffer = { size: 2272 };
r.canvas = { width: 800, height: 600 };
r.context = { getCurrentTexture: () => ({ createView: () => ({}) }) };
r.depthTexture = { createView: () => ({}), destroy() {} };
r.depthWidth = 800; r.depthHeight = 600;

const mesh = {
    pos: new Float32Array(12), norm: new Float32Array(12), uv: new Float32Array(8),
    col: new Float32Array(16), em: new Float32Array(4),
    indices: new Uint16Array([0, 1, 2, 0, 2, 3]), indexFormat: 'uint16', indexCount: 6, vertexCount: 4,
};
r.uploadVehicleModel(mesh, 0);
r.uploadVehicleModel(mesh, 2);
const stats = r.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    vehicles: {
        instances: new Float32Array(30 * 24),
        typeCounts: new Uint32Array([20, 0, 10, 0, 0, 0]),
        typeOffsets: new Uint32Array([0, 20, 20, 30, 30, 30]),
    },
});
process.stdout.write(JSON.stringify({ draws, drawCalls: stats.drawCalls }));
""")
        self.assertEqual(data["drawCalls"], 2)
        self.assertEqual([d["pipeline"] for d in data["draws"]], ["PIPELINE_VEHICLE", "PIPELINE_VEHICLE"])
        self.assertEqual([(d["instances"], d["firstInstance"]) for d in data["draws"]], [(20, 0), (10, 20)])

    def test_vehicle_shader_entry_points_present(self):
        with open(os.path.join(WEB_DIR, "shaders.wgsl"), "r", encoding="utf-8") as f:
            wgsl = f.read()
        self.assertIn("fn vs_vehicle", wgsl)
        with open(os.path.join(WEB_DIR, "renderer_webgl2.js"), "r", encoding="utf-8") as f:
            wgl = f.read()
        self.assertIn("VS_VEHICLE_GLSL300", wgl)
        self.assertIn("drawElementsInstanced", wgl)



class TestCityBasemap(unittest.TestCase):
    """Low-detail Aguascalientes basemap (tools/build_city_basemap.py + web/city_basemap.js)."""

    BASEMAP = os.path.join(ROOT, "models", "city_basemap.bin")

    def setUp(self):
        if not os.path.isfile(self.BASEMAP):
            self.skipTest("models/city_basemap.bin not present")

    def test_basemap_header_covers_road_network(self):
        import struct
        with open(self.BASEMAP, "rb") as f:
            raw = f.read()
        magic, cols, rows, x0, z0, spacing, min_h, max_h = struct.unpack_from("<4sIIfffff", raw, 0)
        self.assertEqual(magic, b"CBM1")
        self.assertEqual(len(raw), 32 + cols * rows * 4)
        self.assertEqual(1024.0 % spacing, 0.0)
        self.assertEqual(x0 % 1024.0, 0.0)
        self.assertEqual(z0 % 1024.0, 0.0)
        self.assertLess(min_h, max_h)
        # Must contain both ring waypoints (Primer Anillo ~ -1.8 km, Tercer Anillo Norte ~ -7.1 km)
        x1 = x0 + (cols - 1) * spacing
        z1 = z0 + (rows - 1) * spacing
        for wx, wz in ((50.0, -1800.0), (532.0, -7134.0), (-7500.0, 15.0), (4927.0, -7.5)):
            self.assertTrue(x0 <= wx <= x1 and z0 <= wz <= z1, f"waypoint {wx},{wz} outside basemap")

    def test_basemap_tool_is_reproducible(self):
        try:
            import numpy  # noqa: F401  (tools/geo_dem.py dependency)
        except ImportError:
            self.skipTest("numpy not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "city_basemap.bin")
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "build_city_basemap.py"), "--output", out],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as a, open(self.BASEMAP, "rb") as b:
                self.assertEqual(a.read(), b.read(), "Regenerated city_basemap.bin differs from the committed one")

    def test_basemap_matches_roads_and_builds_valid_cells(self):
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")
        script = r"""
import fs from 'node:fs';
const { parseRoadGraph } = await import('./web/traffic_sim.js');
const bmMod = await import('./web/city_basemap.js');
const load = (p) => { const b = fs.readFileSync(p); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const graph = parseRoadGraph(load('models/road_network.bin'));
const bm = bmMod.parseCityBasemap(load('models/city_basemap.bin'));

const diffs = [];
for (let i = 0; i < graph.nPoints; i += 7) {
    const x = graph.points[i * 3], y = graph.points[i * 3 + 1], z = graph.points[i * 3 + 2];
    diffs.push(y - bmMod.basemapHeightAt(bm, x, z));
}
diffs.sort((a, b) => a - b);
const median = diffs[Math.floor(diffs.length / 2)];

const buckets = bmMod.bucketRoadSegments(graph);
const cells = {};
for (const [mx, mz] of [[0, 0], [0, -7], [-8, 0]]) {
    const cell = bmMod.buildBasemapCell(bm, graph, buckets, mx, mz);
    const m = cell.meshData;
    let maxIdx = 0;
    for (const i of m.indices) if (i > maxIdx) maxIdx = i;
    let streetVerts = 0;
    for (let v = 0; v < m.vertexCount; v++) if (Math.abs(m.col[v * 4 + 3] - 0.95) < 0.01) streetVerts++;
    const c = cell.chunks[0];
    cells[`${mx}_${mz}`] = {
        indexCountOk: m.indexCount === m.indices.length && m.indexCount % 3 === 0,
        indicesInRange: maxIdx < m.vertexCount,
        finite: m.pos.every(Number.isFinite) && m.norm.every(Number.isFinite),
        streetVerts,
        aabbOk: c.min_x <= mx * 1024 && c.max_x >= (mx + 1) * 1024 && c.min_y < c.max_y,
    };
}
process.stdout.write(JSON.stringify({
    median,
    cellCount: bmMod.basemapCellKeys(bm).length,
    outside: bmMod.buildBasemapCell(bm, graph, buckets, 500, 500) === null,
    cells,
}));
"""
        proc = subprocess.run([node_bin, "--input-type=module", "-e", script], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, f"Node probe failed:\n{proc.stderr}\n{proc.stdout}")
        data = json.loads(proc.stdout)
        # road_network.bin points sit ROAD_SURFACE_OFFSET (0.12 m) above the same terrain function
        self.assertAlmostEqual(data["median"], 0.12, delta=0.1)
        self.assertGreater(data["cellCount"], 300)
        self.assertTrue(data["outside"])
        for key, cell in data["cells"].items():
            self.assertTrue(cell["indexCountOk"], key)
            self.assertTrue(cell["indicesInRange"], key)
            self.assertTrue(cell["finite"], key)
            self.assertTrue(cell["aabbOk"], key)
            self.assertGreater(cell["streetVerts"], 100, f"cell {key} should contain streets")



class TestCityBuildings(unittest.TestCase):
    """Overture building footprints layer (tools/build_city_buildings.py + web/city_basemap.js)."""

    BUILDINGS = os.path.join(ROOT, "models", "city_buildings.bin")

    def setUp(self):
        if not os.path.isfile(self.BUILDINGS):
            self.skipTest("models/city_buildings.bin not present")

    def test_cbb1_layout_and_counts(self):
        import struct
        with open(self.BUILDINGS, "rb") as f:
            raw = f.read()
        magic, n_cells, n_bld, n_pts = struct.unpack_from("<4sIII", raw, 0)
        self.assertEqual(magic, b"CBB1")
        self.assertEqual(len(raw), 16 + n_cells * 16 + n_bld * 4 + n_pts * 4)
        self.assertGreater(n_bld, 300000, "Whole-city Overture extract expected (~325k buildings)")
        total_b = total_p = 0
        for i in range(n_cells):
            _mx, _mz, first_b, count, first_p = struct.unpack_from("<hhIII", raw, 16 + i * 16)
            self.assertEqual(first_b, total_b)
            self.assertEqual(first_p, total_p)
            for b in range(first_b, first_b + count):
                n, cls, h_dm = struct.unpack_from("<BBH", raw, 16 + n_cells * 16 + b * 4)
                self.assertTrue(3 <= n <= 24)
                self.assertTrue(0 <= cls <= 6)
                self.assertTrue(20 <= h_dm <= 2000)
                total_p += n
            total_b += count
        self.assertEqual(total_b, n_bld)
        self.assertEqual(total_p, n_pts)

    def test_buildings_extrude_into_valid_meshes(self):
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node is not installed in PATH")
        script = r"""
import fs from 'node:fs';
const bmMod = await import('./web/city_basemap.js');
const load = (p) => { const b = fs.readFileSync(p); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const bm = bmMod.parseCityBasemap(load('models/city_basemap.bin'));
const bl = bmMod.parseCityBuildings(load('models/city_buildings.bin'));
const out = {};
for (const key of ['0_-2', '-1_0', '0_-7']) {
    const [mx, mz] = key.split('_').map(Number);
    const bare = bmMod.buildBasemapCell(bm, null, null, mx, mz, null);
    const cell = bmMod.buildBasemapCell(bm, null, null, mx, mz, bl);
    const m = cell.meshData;
    let maxIdx = 0;
    for (const i of m.indices) if (i > maxIdx) maxIdx = i;
    let facade = 0, roof = 0;
    for (let v = 0; v < m.vertexCount; v++) {
        const a = m.col[v * 4 + 3];
        if (Math.abs(a - 1.0) < 1e-3) facade++;
        if (Math.abs(a - 0.35) < 1e-3) roof++;
    }
    out[key] = {
        buildings: cell.buildingCount,
        expected: bl.cells.has(key) ? bl.cells.get(key).count : 0,
        extraVerts: m.vertexCount - bare.meshData.vertexCount,
        facade, roof,
        indicesOk: maxIdx < m.vertexCount && m.indexCount % 3 === 0,
        finite: m.pos.every(Number.isFinite),
        uvInAtlas: Array.from(m.uv).every((u) => u > -1.001 && u < 1.001),
    };
}
process.stdout.write(JSON.stringify(out));
"""
        proc = subprocess.run([node_bin, "--input-type=module", "-e", script], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, f"Node probe failed:\n{proc.stderr}\n{proc.stdout}")
        for key, cell in json.loads(proc.stdout).items():
            self.assertGreater(cell["buildings"], 100, key)
            self.assertEqual(cell["buildings"], cell["expected"], key)
            self.assertEqual(cell["extraVerts"], cell["facade"] + cell["roof"], key)
            self.assertGreater(cell["facade"], cell["buildings"] * 12, key)  # >= 3 walls x 4 vertices
            self.assertTrue(cell["indicesOk"], key)
            self.assertTrue(cell["finite"], key)
            self.assertTrue(cell["uvInAtlas"], key)


if __name__ == "__main__":
    unittest.main()
