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
            "cull_chunks",
            "sector_0_0.glb",
            "submeshes",
            "buildingIndices",
        ):
            self.assertIn(token, app_js)

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
const appContent = fs.readFileSync('web/app.js', 'utf-8');
const m1 = appContent.indexOf('function extractAccessorTypedArray');
const m2 = appContent.indexOf('function generateFallbackFacadeRGBA');
const fnCode = appContent.slice(m1, m2);

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
        self.assertEqual(sec["vertCount"], 1299591)
        self.assertEqual(sec["posLen"], 1299591 * 3)
        self.assertEqual(sec["colLen"], 1299591 * 4)
        self.assertEqual(sec["emLen"], 1299591)
        self.assertEqual(sec["buildingIndicesCount"], 457395)
        self.assertTrue(sec["hasBuildingSubmesh"])
        self.assertEqual(sec["submeshesCount"], 2)
        sub0 = sec["submeshes"][0]
        sub1 = sec["submeshes"][1]
        self.assertEqual(sub0["name"], "sector_terrain")
        self.assertFalse(sub0["isBuilding"])
        self.assertEqual(sub0["indexCount"], 842196)
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
    statsNorm.drawCalls === 2 &&
    statsNorm.visibleVerts === 64000 &&
    mockGl.draws[0].program === renderer.program &&
    mockGl.draws[1].program === renderer.buildingProgram
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

// 7. Vehicle model upload and dynamic car rendering
renderer.uploadVehicleModel({
    pos: new Float32Array(18), norm: new Float32Array(18), uv: new Float32Array(12),
    col: new Float32Array(24), em: new Float32Array(6),
    indices: new Uint16Array([0, 1, 2, 0, 2, 3]),
    indexCount: 6, vertexCount: 4, indexFormat: 'uint16'
});
const fakeCarsMem = new Float32Array(50 * 6);
for (let i = 0; i < 50; i++) {
    fakeCarsMem[i * 6 + 0] = 500.0 + i;
    fakeCarsMem[i * 6 + 1] = 8.8;
    fakeCarsMem[i * 6 + 2] = 795.5;
    fakeCarsMem[i * 6 + 3] = 90.0;
}
mockGl.draws = [];
renderer.render({
    uniformBufferData: new Float32Array(568),
    clearColor: [0, 0, 0],
    cullingEnabled: false,
    renderMode: 'all',
    cars: { ptr: 0, count: 50, memory: fakeCarsMem }
});
const vehicleOk = (mockGl.draws.length === 52); // 2 submeshes + 50 cars

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
        """Verifica que todos los sectores de Tercer Anillo existen, son < 95 MB y tienen chunks válidos."""
        coords = self._extract_workflow_coords()
        self.assertGreaterEqual(len(coords), 148, "Must cover at least 148 macro-sectors of Tercer Anillo")

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest_map = {(s["mx"], s["mz"]): s for s in manifest.get("sectors", [])}

        sectors_dir = os.path.join(ROOT, "models", "sectors")
        max_bytes = 95 * 1024 * 1024

        for mx, mz in coords:
            self.assertIn((mx, mz), manifest_map, f"Sector ({mx}, {mz}) missing in models/sectors.json")
            entry = manifest_map[(mx, mz)]
            self.assertGreater(entry.get("vert_count", 0), 0, f"Sector ({mx}, {mz}) has zero vertices")

            glb_file = os.path.join(sectors_dir, f"sector_{mx}_{mz}.glb")
            self.assertTrue(os.path.isfile(glb_file), f"Sector GLB missing: {glb_file}")
            sz = os.path.getsize(glb_file)
            self.assertGreater(sz, 0, f"Empty GLB: {glb_file}")
            self.assertLess(sz, max_bytes, f"Sector GLB exceeds 95 MB limit: {glb_file} ({sz} bytes)")

            chunk_file = os.path.join(sectors_dir, f"chunks_{mx}_{mz}.json")
            self.assertTrue(os.path.isfile(chunk_file), f"Chunks JSON missing: {chunk_file}")
            with open(chunk_file, "r", encoding="utf-8") as cf:
                cdata = json.load(cf)
            self.assertIn("chunks", cdata)
            self.assertGreater(len(cdata["chunks"]), 0, f"No chunks in {chunk_file}")

    def test_tercer_anillo_web_waypoints_elevation_and_coords(self):
        """Verifica que los waypoints de Tercer Anillo en web/app.js apuntan a coordenadas reales y ras del suelo DEM."""
        from geo_dem import TerrainElevation, DEFAULT_ORIGIN_LAT, DEFAULT_ORIGIN_LON

        terrain = TerrainElevation(
            21.8000, 21.9500, -102.3700, -102.2450, nx=64, ny=64,
            origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON
        )

        app_js_path = os.path.join(ROOT, "web", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(r"const TERCER_ANILLO_WAYPOINTS\s*=\s*\[(.*?)\];", content, re.DOTALL)
        self.assertIsNotNone(m, "TERCER_ANILLO_WAYPOINTS must exist in web/app.js")
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


if __name__ == "__main__":
    unittest.main()
