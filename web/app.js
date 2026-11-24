// ============================================================================
// StreetVulkan Web Client Application
// Orchestrates:
//   - street_vulkan_core.wasm (WAT math, camera, frustum culling, traffic_tick)
//   - WebGPU (Vulkan) primary renderer with automatic WebGL2 fallback
//   - Modular GLB sector streaming prioritizing Sector (0, 0) Paseo de la Cruz
//   - ISO/IEC 25010:2023 real-time telemetry HUD
// ============================================================================

import { WebGPURenderer } from './renderer_webgpu.js';
import { WebGL2Renderer } from './renderer_webgl2.js';

// Exact initial camera spawn in front of Rolcar Paseo de la Cruz (src/math_camera.c)
const INITIAL_CAMERA = {
    pos: [954.4, 8.8, 793.1],
    yaw: -45.7,
    pitch: 4.9,
    moveSpeed: 35.0,
    sprintMultiplier: 4.0,
    mouseSensitivity: 0.12,
};

// WASM linear memory byte offsets (matching web/street_vulkan_core.wat)
const MEM_POS_PTR = 0x0000;
const MEM_SIM_TIME_PTR = 0x0010;
const MEM_FWD_PTR = 0x0014;
const MEM_RIGHT_PTR = 0x0020;
const MEM_UP_PTR = 0x002C;
const MEM_VIEW_PTR = 0x0040;
const MEM_PROJ_WGPU_PTR = 0x0080;
const MEM_MVP_WGPU_PTR = 0x00C0;
const MEM_PLANES_PTR = 0x0100;
const MEM_PROJ_WGL_PTR = 0x0160;
const MEM_MVP_WGL_PTR = 0x01A0;
const MEM_AABBS_PTR = 0x0200;
const MEM_FLAGS_PTR = 0x8000;
const MAX_CULL_BATCH = 1024;

const TIME_PRESETS = [
    { hour: 14.0, label: '14:00 Día' },
    { hour: 17.5, label: '17:30 Atardecer' },
    { hour: 22.5, label: '22:30 Noche' },
    { hour: 6.5, label: '06:30 Amanecer' },
];

const TRAFFIC_PHASE_LABELS = [
    'F0: N-S Verde',
    'F1: N-S Ámbar',
    'F2: E-O Verde',
    'F3: E-O Ámbar',
];

function degToRad(d) {
    return d * 0.017453292519943295;
}

function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
}

function linearToSrgbChannel(c) {
    return Math.pow(clamp(c, 0.0, 1.0), 1.0 / 2.2);
}

// ----------------------------------------------------------------------------
// WASM Loader (instantiateStreaming with arrayBuffer fallback)
// ----------------------------------------------------------------------------
async function loadStreetVulkanWasm() {
    const wasmUrl = new URL('./street_vulkan_core.wasm', import.meta.url).href;
    let instance;

    if (typeof WebAssembly.instantiateStreaming === 'function') {
        try {
            const resp = await fetch(wasmUrl);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status} fetching ${wasmUrl}`);
            }
            const result = await WebAssembly.instantiateStreaming(resp, {});
            instance = result.instance;
        } catch (streamErr) {
            console.warn('[WASM] instantiateStreaming fallback to arrayBuffer:', streamErr.message);
            const resp = await fetch(wasmUrl);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status} fetching ${wasmUrl}`);
            }
            const bytes = await resp.arrayBuffer();
            const result = await WebAssembly.instantiate(bytes, {});
            instance = result.instance;
        }
    } else {
        const resp = await fetch(wasmUrl);
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status} fetching ${wasmUrl}`);
        }
        const bytes = await resp.arrayBuffer();
        const result = await WebAssembly.instantiate(bytes, {});
        instance = result.instance;
    }

    const exports = instance.exports;
    const version = exports.get_version();
    if (version !== 1) {
        throw new Error(`Unexpected street_vulkan_core.wasm version: ${version}`);
    }
    return exports;
}

// ----------------------------------------------------------------------------
// GLB 2.0 Parser (Zero-copy TypedArray views when 4-byte aligned & tightly packed)
// ----------------------------------------------------------------------------
function extractAccessorTypedArray(gltf, accessorIdx, arrayBuffer, binBaseOffset, numComponents, expectedType) {
    const acc = gltf.accessors[accessorIdx];
    const bv = gltf.bufferViews[acc.bufferView];
    const byteOffset = binBaseOffset + (bv.byteOffset || 0) + (acc.byteOffset || 0);
    const elemCount = acc.count * numComponents;
    const compSize = expectedType.BYTES_PER_ELEMENT;
    const expectedStride = numComponents * compSize;
    const actualStride = bv.byteStride || 0;

    if ((actualStride === 0 || actualStride === expectedStride) && (byteOffset % compSize === 0)) {
        return new expectedType(arrayBuffer, byteOffset, elemCount);
    }

    const out = new expectedType(elemCount);
    const view = new DataView(arrayBuffer);
    const stride = actualStride || expectedStride;
    for (let i = 0; i < acc.count; i++) {
        const rowOff = byteOffset + i * stride;
        for (let c = 0; c < numComponents; c++) {
            const off = rowOff + c * compSize;
            if (expectedType === Float32Array) {
                out[i * numComponents + c] = view.getFloat32(off, true);
            } else if (expectedType === Uint32Array) {
                out[i * numComponents + c] = view.getUint32(off, true);
            } else if (expectedType === Uint16Array) {
                out[i * numComponents + c] = view.getUint16(off, true);
            }
        }
    }
    return out;
}

function parseGLB(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    if (arrayBuffer.byteLength < 20) {
        throw new Error('GLB too small');
    }
    const magic = view.getUint32(0, true);
    const version = view.getUint32(4, true);
    if (magic !== 0x46546C67 || version !== 2) {
        throw new Error(`Invalid GLB header: magic=0x${magic.toString(16)} version=${version}`);
    }

    let offset = 12;
    let gltf = null;
    let binBaseOffset = 0;
    let binByteLength = 0;

    while (offset + 8 <= arrayBuffer.byteLength) {
        const chunkLen = view.getUint32(offset, true);
        const chunkType = view.getUint32(offset + 4, true);
        const dataStart = offset + 8;
        if (chunkType === 0x4E4F534A) {
            const jsonBytes = new Uint8Array(arrayBuffer, dataStart, chunkLen);
            gltf = JSON.parse(new TextDecoder('utf-8').decode(jsonBytes));
        } else if (chunkType === 0x004E4942) {
            binBaseOffset = dataStart;
            binByteLength = chunkLen;
        }
        offset = dataStart + chunkLen;
    }

    if (!gltf || !gltf.meshes || gltf.meshes.length === 0 || binByteLength === 0) {
        throw new Error('GLB missing mesh JSON or BIN chunk');
    }

    const prim = gltf.meshes[0].primitives[0];
    const attrs = prim.attributes;
    if (attrs.POSITION === undefined) {
        throw new Error('GLB primitive missing POSITION attribute');
    }

    const posAcc = gltf.accessors[attrs.POSITION];
    const vertexCount = posAcc.count;

    const pos = extractAccessorTypedArray(gltf, attrs.POSITION, arrayBuffer, binBaseOffset, 3, Float32Array);

    let norm;
    if (attrs.NORMAL !== undefined) {
        norm = extractAccessorTypedArray(gltf, attrs.NORMAL, arrayBuffer, binBaseOffset, 3, Float32Array);
    } else {
        norm = new Float32Array(vertexCount * 3);
        for (let i = 0; i < vertexCount; i++) norm[i * 3 + 1] = 1.0;
    }

    let uv;
    if (attrs.TEXCOORD_0 !== undefined) {
        uv = extractAccessorTypedArray(gltf, attrs.TEXCOORD_0, arrayBuffer, binBaseOffset, 2, Float32Array);
    } else {
        uv = new Float32Array(vertexCount * 2);
    }

    let col;
    if (attrs.COLOR_0 !== undefined) {
        col = extractAccessorTypedArray(gltf, attrs.COLOR_0, arrayBuffer, binBaseOffset, 4, Float32Array);
    } else {
        col = new Float32Array(vertexCount * 4);
        col.fill(1.0);
    }

    let em;
    const emIdx = attrs._EMISSION !== undefined ? attrs._EMISSION : attrs.EMISSION;
    if (emIdx !== undefined) {
        em = extractAccessorTypedArray(gltf, emIdx, arrayBuffer, binBaseOffset, 1, Float32Array);
    } else {
        em = new Float32Array(vertexCount);
    }

    let indices;
    let indexFormat = 'uint32';
    if (prim.indices !== undefined) {
        const idxAcc = gltf.accessors[prim.indices];
        if (idxAcc.componentType === 5123) {
            indices = extractAccessorTypedArray(gltf, prim.indices, arrayBuffer, binBaseOffset, 1, Uint16Array);
            indexFormat = 'uint16';
        } else {
            indices = extractAccessorTypedArray(gltf, prim.indices, arrayBuffer, binBaseOffset, 1, Uint32Array);
            indexFormat = 'uint32';
        }
    } else {
        indices = new Uint32Array(vertexCount);
        for (let i = 0; i < vertexCount; i++) indices[i] = i;
    }

    return {
        pos,
        norm,
        uv,
        col,
        em,
        indices,
        indexFormat,
        vertexCount,
        indexCount: indices.length,
    };
}

// ----------------------------------------------------------------------------
// Procedural Fallback Textures (matching src/vulkan_texture.c)
// ----------------------------------------------------------------------------
function generateFallbackFacadeRGBA() {
    const W = 256;
    const H = 256;
    const data = new Uint8Array(W * H * 4);
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const brickW = 32;
            const brickH = 16;
            const by = Math.floor(y / brickH);
            const bx = Math.floor(x / brickW);
            const mortar = (y % brickH < 2) || (x % brickW < 2 && (by % 2 === 0 || x % brickW >= 16));
            let r, g, b;
            if (mortar) {
                r = 180; g = 180; b = 175;
            } else {
                const v = (bx * 17 + by * 31) % 20;
                if ((bx + by) % 2 === 0) {
                    r = 190 + v; g = 165 + (v >> 1); b = 140 + (v >> 1);
                } else {
                    r = 185 + v; g = 150 + (v >> 1); b = 120 + (v >> 1);
                }
            }
            const idx = (y * W + x) * 4;
            data[idx] = r;
            data[idx + 1] = g;
            data[idx + 2] = b;
            data[idx + 3] = 255;
        }
    }
    return { width: W, height: H, data };
}

function generateFallbackSatelliteRGBA() {
    const W = 64;
    const H = 64;
    const data = new Uint8Array(W * H * 4);
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const n = (((x * 73856093) ^ (y * 19349663)) & 15) - 7;
            const idx = (y * W + x) * 4;
            data[idx] = clamp(120 + n, 0, 255);
            data[idx + 1] = clamp(125 + n, 0, 255);
            data[idx + 2] = clamp(115 + n, 0, 255);
            data[idx + 3] = 255;
        }
    }
    return { width: W, height: H, data };
}

async function loadTextureAtlasWithFallback() {
    const candidates = [
        '../models/texture_atlas_16x16.png',
        './models/texture_atlas_16x16.png',
        './texture_atlas_16x16.png',
    ];
    for (const url of candidates) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) continue;
            const blob = await resp.blob();
            const bmp = await createImageBitmap(blob);
            const off = document.createElement('canvas');
            off.width = bmp.width;
            off.height = bmp.height;
            const ctx = off.getContext('2d');
            ctx.drawImage(bmp, 0, 0);
            const imgData = ctx.getImageData(0, 0, bmp.width, bmp.height);
            bmp.close?.();
            return {
                width: imgData.width,
                height: imgData.height,
                data: new Uint8Array(imgData.data.buffer),
                source: url,
            };
        } catch (_err) {
            // Try next candidate path
        }
    }
    const fallback = generateFallbackFacadeRGBA();
    return { ...fallback, source: 'procedural-fallback' };
}

// ----------------------------------------------------------------------------
// Standalone Fallback Mini-Scene (only if no GLB is reachable over HTTP)
// ----------------------------------------------------------------------------
function buildStandaloneFallbackSector() {
    const positions = [];
    const normals = [];
    const uvs = [];
    const colors = [];
    const emissions = [];

    const pushQuad = (p0, p1, p2, p3, n, col, em = 0.0) => {
        const pts = [p0, p1, p2, p0, p2, p3];
        const qUvs = [[0, 1], [1, 1], [1, 0], [0, 1], [1, 0], [0, 0]];
        for (let i = 0; i < 6; i++) {
            positions.push(pts[i][0], pts[i][1], pts[i][2]);
            normals.push(n[0], n[1], n[2]);
            uvs.push(qUvs[i][0], qUvs[i][1]);
            colors.push(col[0], col[1], col[2], col[3]);
            emissions.push(em);
        }
    };

    // Ground asphalt plaza
    pushQuad([900, 0, 740], [1020, 0, 740], [1020, 0, 840], [900, 0, 840], [0, 1, 0], [0.22, 0.22, 0.24, 0.95]);
    // Rolcar Paseo de la Cruz demo facade & shutter
    pushQuad([964, 0, 770], [982, 0, 784], [982, 7.5, 784], [964, 7.5, 770], [-0.6, 0, 0.8], [0.94, 0.94, 0.92, 1.14]);
    pushQuad([966, 0.2, 771.5], [974, 0.2, 777.8], [974, 4.2, 777.8], [966, 4.2, 771.5], [-0.6, 0, 0.8], [0.48, 0.51, 0.53, 1.18]);
    pushQuad([964, 4.5, 770.1], [982, 4.5, 784.1], [982, 5.6, 784.1], [964, 5.6, 770.1], [-0.6, 0, 0.8], [0.04, 0.45, 0.18, 1.14], 0.4);

    const vertexCount = positions.length / 3;
    const indices = new Uint32Array(vertexCount);
    for (let i = 0; i < vertexCount; i++) indices[i] = i;

    return {
        mesh: {
            pos: new Float32Array(positions),
            norm: new Float32Array(normals),
            uv: new Float32Array(uvs),
            col: new Float32Array(colors),
            em: new Float32Array(emissions),
            indices,
            indexFormat: 'uint32',
            vertexCount,
            indexCount: vertexCount,
        },
        chunks: [{
            cx: 7, cz: 6, start: 0, count: vertexCount,
            min_x: 900, min_y: -1, min_z: 740, max_x: 1020, max_y: 20, max_z: 840,
        }],
    };
}

// ----------------------------------------------------------------------------
// Fetch with progress callback
// ----------------------------------------------------------------------------
async function fetchArrayBufferWithProgress(url, onProgress) {
    const resp = await fetch(url);
    if (!resp.ok) {
        throw new Error(`HTTP ${resp.status} for ${url}`);
    }
    const contentLength = Number(resp.headers.get('content-length') || 0);
    if (!resp.body || !contentLength) {
        const buf = await resp.arrayBuffer();
        onProgress?.(buf.byteLength, buf.byteLength);
        return buf;
    }

    const reader = resp.body.getReader();
    const chunks = [];
    let received = 0;
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.byteLength;
        onProgress?.(received, contentLength);
    }

    const combined = new Uint8Array(received);
    let pos = 0;
    for (const c of chunks) {
        combined.set(c, pos);
        pos += c.byteLength;
    }
    return combined.buffer;
}

// ----------------------------------------------------------------------------
// Sun, Sky, & Lighting Calculation (mirrors src/vulkan.c + include/lighting_system.h)
// ----------------------------------------------------------------------------
function computeSunAndSky(simHour) {
    const sunAngle = ((simHour - 6.0) / 24.0) * 2.0 * Math.PI;
    const sunY = Math.sin(sunAngle);
    const sunX = Math.cos(sunAngle);

    const sunDir = [
        sunX,
        sunY > 0.05 ? sunY : 0.05,
        0.35,
        0.16 + 0.22 * Math.max(0.0, sunY),
    ];

    const nightFactor = clamp(-sunY * 1.5, 0.0, 1.0);
    let skyR, skyG, skyB;
    if (simHour >= 6.0 && simHour < 18.0) {
        if (simHour < 8.0) {
            const t = (simHour - 6.0) / 2.0;
            skyR = 0.90 * (1.0 - t) + 0.52 * t;
            skyG = 0.50 * (1.0 - t) + 0.68 * t;
            skyB = 0.30 * (1.0 - t) + 0.88 * t;
        } else if (simHour > 16.0) {
            const t = (simHour - 16.0) / 2.0;
            skyR = 0.52 * (1.0 - t) + 0.95 * t;
            skyG = 0.68 * (1.0 - t) + 0.45 * t;
            skyB = 0.88 * (1.0 - t) + 0.25 * t;
        } else {
            skyR = 0.52; skyG = 0.68; skyB = 0.88;
        }
    } else {
        let t = simHour >= 18.0 ? (simHour - 18.0) / 2.0 : (6.0 - simHour) / 2.0;
        t = clamp(t, 0.0, 1.0);
        skyR = 0.95 * (1.0 - t) + 0.02 * t;
        skyG = 0.45 * (1.0 - t) + 0.03 * t;
        skyB = 0.25 * (1.0 - t) + 0.08 * t;
    }

    return {
        sunDir,
        skyColor: [skyR, skyG, skyB, nightFactor],
        clearColor: [
            linearToSrgbChannel(skyR),
            linearToSrgbChannel(skyG),
            linearToSrgbChannel(skyB),
        ],
    };
}

// ----------------------------------------------------------------------------
// Manifest & Sector Discovery
// ----------------------------------------------------------------------------
async function resolveSectorManifest() {
    const manifestCandidates = [
        { url: '../models/sectors.json', prefix: '../' },
        { url: './models/sectors.json', prefix: './' },
        { url: './sectors.json', prefix: './' },
    ];

    for (const cand of manifestCandidates) {
        try {
            const resp = await fetch(cand.url);
            if (!resp.ok) continue;
            const data = await resp.json();
            if (data && Array.isArray(data.sectors) && data.sectors.length > 0) {
                return { manifest: data, basePrefix: cand.prefix, source: cand.url };
            }
        } catch (_err) {
            // Try next candidate
        }
    }

    // Direct sector_0_0.glb fallback when no manifest exists
    const directCandidates = [
        { glb: '../models/sectors/sector_0_0.glb', chunks: '../models/sectors/chunks_0_0.json' },
        { glb: './models/sectors/sector_0_0.glb', chunks: './models/sectors/chunks_0_0.json' },
        { glb: './sector_0_0.glb', chunks: './chunks_0_0.json' },
    ];
    for (const d of directCandidates) {
        try {
            const head = await fetch(d.glb, { method: 'HEAD' });
            if (head.ok) {
                return {
                    manifest: {
                        macro_size: 1024.0,
                        chunk_size: 128.0,
                        sectors: [{ mx: 0, mz: 0, file: d.glb, chunksFile: d.chunks, chunks: [] }],
                    },
                    basePrefix: '',
                    source: d.glb,
                };
            }
        } catch (_err) {
            // Continue
        }
    }
    return null;
}

async function fetchChunksForSector(sectorEntry, basePrefix) {
    const candidates = [];
    if (sectorEntry.chunksFile) {
        candidates.push(sectorEntry.chunksFile);
    }
    if (sectorEntry.file) {
        const chunkRel = sectorEntry.file.replace(/sector_(-?\d+)_(-?\d+)\.glb$/, 'chunks_$1_$2.json');
        if (chunkRel !== sectorEntry.file) {
            candidates.push(`${basePrefix}${chunkRel}`);
        }
    }
    if (sectorEntry.mx === 0 && sectorEntry.mz === 0) {
        candidates.push('../models/sectors/chunks_0_0.json', './models/sectors/chunks_0_0.json', './chunks_0_0.json');
    }

    for (const url of candidates) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) continue;
            const data = await resp.json();
            if (data && Array.isArray(data.chunks)) {
                return data.chunks;
            }
        } catch (_err) {
            // Fallback to embedded manifest chunks
        }
    }
    return Array.isArray(sectorEntry.chunks) ? sectorEntry.chunks : [];
}

async function loadOptionalTrafficSignals() {
    const candidates = ['../models/traffic_signals.json', './models/traffic_signals.json', './traffic_signals.json'];
    for (const url of candidates) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) continue;
            const txt = await resp.text();
            const signals = [];
            for (const line of txt.split('\n')) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                const s = JSON.parse(trimmed);
                if (s.x >= -128 && s.x <= 1152 && s.z >= -128 && s.z <= 1152) {
                    signals.push(s);
                }
            }
            return signals;
        } catch (_err) {
            // Optional file
        }
    }
    return [];
}

// ----------------------------------------------------------------------------
// Main Application Bootstrap
// ----------------------------------------------------------------------------
async function main() {
    const canvas = document.getElementById('viewport');
    const elBackend = document.getElementById('hud-backend');
    const elGpu = document.getElementById('hud-gpu');
    const elRes = document.getElementById('hud-res');
    const elTime = document.getElementById('hud-time');
    const elTraffic = document.getElementById('hud-traffic');
    const elFps = document.getElementById('hud-fps');
    const elCpuDraw = document.getElementById('hud-cpu-draw');
    const elChunks = document.getElementById('hud-chunks');
    const elVerts = document.getElementById('hud-verts');
    const elPos = document.getElementById('hud-pos');
    const elLoader = document.getElementById('loader-overlay');
    const elLoaderText = document.getElementById('loader-text');
    const elLoaderBar = document.getElementById('loader-bar');
    const elHud = document.getElementById('telemetry-hud');
    const elToast = document.getElementById('toast-msg');

    let toastTimer = 0;
    function showToast(msg) {
        if (!elToast) return;
        elToast.textContent = msg;
        elToast.classList.add('visible');
        toastTimer = 2.6;
    }

    function updateCanvasSize() {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.max(1, Math.floor(window.innerWidth * dpr));
        const h = Math.max(1, Math.floor(window.innerHeight * dpr));
        if (canvas.width !== w || canvas.height !== h) {
            canvas.width = w;
            canvas.height = h;
        }
        return { w, h };
    }
    updateCanvasSize();

    // 1. Load WebAssembly Core (.wat -> .wasm)
    if (elLoaderText) elLoaderText.textContent = 'Inicializando kernel street_vulkan_core.wasm...';
    const wasm = await loadStreetVulkanWasm();
    let f32Mem = new Float32Array(wasm.memory.buffer);
    let u8Mem = new Uint8Array(wasm.memory.buffer);

    // 2. Initialize GPU Renderer: WebGPU (Vulkan) primary with automatic WebGL2 fallback
    if (elLoaderText) elLoaderText.textContent = 'Inicializando adaptador GPU (WebGPU / WebGL2)...';
    const queryBackend = new URLSearchParams(window.location.search).get('backend');
    let renderer = null;
    let backendInfo = null;

    if (queryBackend !== 'webgl2') {
        try {
            const wgpu = new WebGPURenderer();
            backendInfo = await wgpu.init(canvas);
            renderer = wgpu;
        } catch (err) {
            console.warn('[Renderer] WebGPU unavailable, falling back to WebGL2:', err.message);
        }
    }

    if (!renderer) {
        const wgl2 = new WebGL2Renderer();
        backendInfo = await wgl2.init(canvas);
        renderer = wgl2;
    }

    const isWebGPU = backendInfo.backend.startsWith('WebGPU');
    if (elBackend) {
        elBackend.textContent = backendInfo.backend;
        elBackend.className = isWebGPU ? 'badge badge-vulkan' : 'badge badge-webgl';
    }
    if (elGpu) {
        elGpu.textContent = backendInfo.gpuName;
    }

    window.addEventListener('resize', () => {
        const { w, h } = updateCanvasSize();
        renderer.resize(w, h);
    });

    // 3. Upload Texture Atlas + Satellite Fallback
    if (elLoaderText) elLoaderText.textContent = 'Cargando atlas de texturas PBR...';
    const [satTexData, facTexData] = await Promise.all([
        Promise.resolve(generateFallbackSatelliteRGBA()),
        loadTextureAtlasWithFallback(),
    ]);
    renderer.uploadTextures(satTexData, facTexData);

    // 4. Camera & Simulation State (spawn in front of Rolcar Paseo de la Cruz)
    const state = {
        yaw: INITIAL_CAMERA.yaw,
        pitch: INITIAL_CAMERA.pitch,
        simHour: 14.0,
        timeFrozen: false,
        presetIdx: 0,
        cullingEnabled: true,
        flashlightOn: false,
        hudVisible: true,
        trafficPhase: 0,
        trafficSignals: [],
        paused: false,
        carsEnabled: true,
        carCount: 50,
        simSpeed: 0.05,
    };

    // Allocate memory for dynamic simulated cars (50 cars x 24 B = 1,200 bytes at 0x9000)
    const MEM_CARS_PTR = 0x9000;
    const carsBaseFloat = MEM_CARS_PTR >> 2;
    for (let i = 0; i < state.carCount; i++) {
        const off = carsBaseFloat + i * 6;
        f32Mem[off + 0] = 200.0 + (i / state.carCount) * 800.0; // x
        f32Mem[off + 1] = 8.8;                                 // y
        f32Mem[off + 2] = (i % 2 === 0) ? 795.5 : 952.0;       // z
        f32Mem[off + 3] = (i % 2 === 0) ? 90.0 : 0.0;          // yaw
        f32Mem[off + 4] = (i / state.carCount);                // progress
        f32Mem[off + 5] = (i % 2);                             // corridor_id (0: Paseo Cruz, 1: JM Chávez)
    }

    function togglePause(forced) {
        state.paused = (typeof forced === 'boolean') ? forced : !state.paused;
        const overlay = document.getElementById('pause-menu-overlay');
        if (overlay) {
            overlay.classList.toggle('active', state.paused);
        }
        if (state.paused) {
            if (document.exitPointerLock) document.exitPointerLock();
            showToast('Simulación Pausada [P / ESC]');
        } else {
            showToast('Simulación Reanudada');
        }
    }

    function resetCamera() {
        f32Mem[0] = INITIAL_CAMERA.pos[0];
        f32Mem[1] = INITIAL_CAMERA.pos[1];
        f32Mem[2] = INITIAL_CAMERA.pos[2];
        state.yaw = INITIAL_CAMERA.yaw;
        state.pitch = INITIAL_CAMERA.pitch;
        showToast('Cámara: Rolcar Paseo de la Cruz (Sector 0,0)');
    }
    resetCamera();
    f32Mem[MEM_SIM_TIME_PTR >> 2] = 0.0;

    // 5. Sector Manifest & Streaming Loader (Prioritize Sector 0,0)
    const sectorCache = new Map(); // sectorKey -> { entry, aabbFloat32, chunkCount }
    const loadingSectors = new Set();
    const missingSectors = new Set();
    let manifestInfo = await resolveSectorManifest();

    async function loadSectorEntry(entry, basePrefix, showLoader) {
        const key = `${entry.mx}_${entry.mz}`;
        if (sectorCache.has(key) || loadingSectors.has(key) || missingSectors.has(key)) return;
        loadingSectors.add(key);

        try {
            let glbUrl = entry.file.startsWith('..') || entry.file.startsWith('./')
                ? entry.file
                : `${basePrefix}${entry.file}`;

            // Safety check: if file path is an absolute /tmp path or non-relative, resolve cleanly to models/sectors
            if (glbUrl.includes('/tmp/') || glbUrl.startsWith('/')) {
                glbUrl = `${basePrefix}models/sectors/sector_${entry.mx}_${entry.mz}.glb`;
            }
            if (showLoader && elLoaderText) {
                elLoaderText.textContent = `Descargando Sector (${entry.mx}, ${entry.mz}) Paseo de la Cruz...`;
            }

            const [arrayBuf, chunks] = await Promise.all([
                fetchArrayBufferWithProgress(glbUrl, (loaded, total) => {
                    if (showLoader && elLoaderBar && total > 0) {
                        const pct = Math.round((loaded / total) * 100);
                        elLoaderBar.style.width = `${pct}%`;
                        elLoaderText.textContent = `Descargando sector_${key}.glb: ${(loaded / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB (${pct}%)`;
                    }
                }),
                fetchChunksForSector(entry, basePrefix),
            ]);

            if (showLoader && elLoaderText) {
                elLoaderText.textContent = `Subiendo geometría GLB a ${backendInfo.backend}...`;
            }

            const parsed = parseGLB(arrayBuf);
            renderer.uploadSector(key, parsed, chunks);

            const aabbData = new Float32Array(chunks.length * 6);
            for (let i = 0; i < chunks.length; i++) {
                const c = chunks[i];
                aabbData[i * 6 + 0] = c.min_x;
                aabbData[i * 6 + 1] = c.min_y;
                aabbData[i * 6 + 2] = c.min_z;
                aabbData[i * 6 + 3] = c.max_x;
                aabbData[i * 6 + 4] = c.max_y;
                aabbData[i * 6 + 5] = c.max_z;
            }
            sectorCache.set(key, { entry, aabbData, chunkCount: chunks.length });
        } catch (err) {
            missingSectors.add(key);
            throw err;
        } finally {
            loadingSectors.delete(key);
        }
    }

    try {
        if (manifestInfo) {
            const sectors = manifestInfo.manifest.sectors;
            const sector00 = sectors.find((s) => s.mx === 0 && s.mz === 0) || sectors[0];
            await loadSectorEntry(sector00, manifestInfo.basePrefix, true);
        } else {
            throw new Error('No sector manifest or GLB found');
        }
    } catch (err) {
        console.warn('[Loader] Loading standalone fallback scene:', err.message);
        const fallback = buildStandaloneFallbackSector();
        renderer.uploadSector('0_0', fallback.mesh, fallback.chunks);
        const c = fallback.chunks[0];
        sectorCache.set('0_0', {
            entry: { mx: 0, mz: 0 },
            aabbData: new Float32Array([c.min_x, c.min_y, c.min_z, c.max_x, c.max_y, c.max_z]),
            chunkCount: 1,
        });
        showToast('Modo standalone (sin sector_0_0.glb)');
    }

    if (elLoader) {
        elLoader.classList.add('hidden');
    }

    // Load traffic signals asynchronously after Sector (0,0) renders
    loadOptionalTrafficSignals().then((signals) => {
        state.trafficSignals = signals;
    });

    // 6. Input Wiring: Keyboard + PointerLock + Drag Look + Touch/Buttons
    const keysDown = new Set();
    const touchMove = { fwd: 0, right: 0, up: 0, sprint: false };
    let isDragging = false;
    let lastPointerX = 0;
    let lastPointerY = 0;

    window.addEventListener('keydown', (e) => {
        keysDown.add(e.code);
        if (e.code === 'KeyP' || e.code === 'Escape') {
            togglePause();
            return;
        }
        if (e.code === 'KeyF') {
            state.flashlightOn = !state.flashlightOn;
            showToast(state.flashlightOn ? 'Linterna: ON' : 'Linterna: OFF');
        } else if (e.code === 'KeyK') {
            state.cullingEnabled = !state.cullingEnabled;
            showToast(state.cullingEnabled ? 'Frustum Culling WASM: ON' : 'Frustum Culling WASM: OFF');
        } else if (e.code === 'KeyT') {
            state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
            state.simHour = TIME_PRESETS[state.presetIdx].hour;
            showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
        } else if (e.code === 'KeyR') {
            resetCamera();
        } else if (e.code === 'KeyH') {
            state.hudVisible = !state.hudVisible;
            if (elHud) elHud.classList.toggle('hidden', !state.hudVisible);
        }
    });

    window.addEventListener('keyup', (e) => {
        keysDown.delete(e.code);
    });

    window.addEventListener('blur', () => {
        keysDown.clear();
        isDragging = false;
    });

    canvas.addEventListener('click', () => {
        if (document.pointerLockElement !== canvas && canvas.requestPointerLock) {
            try {
                canvas.requestPointerLock();
            } catch (_err) {
                // Drag fallback remains active
            }
        }
    });

    canvas.addEventListener('mousedown', (e) => {
        if (e.button === 0) {
            isDragging = true;
            lastPointerX = e.clientX;
            lastPointerY = e.clientY;
        }
    });

    window.addEventListener('mouseup', () => {
        isDragging = false;
    });

    window.addEventListener('mousemove', (e) => {
        if (document.pointerLockElement === canvas) {
            state.yaw += e.movementX * INITIAL_CAMERA.mouseSensitivity;
            state.pitch = clamp(state.pitch - e.movementY * INITIAL_CAMERA.mouseSensitivity, -89.0, 89.0);
        } else if (isDragging) {
            const dx = e.clientX - lastPointerX;
            const dy = e.clientY - lastPointerY;
            lastPointerX = e.clientX;
            lastPointerY = e.clientY;
            state.yaw += dx * INITIAL_CAMERA.mouseSensitivity * 1.4;
            state.pitch = clamp(state.pitch - dy * INITIAL_CAMERA.mouseSensitivity * 1.4, -89.0, 89.0);
        }
    });

    // Touch look on canvas
    let activeTouchId = null;
    canvas.addEventListener('touchstart', (e) => {
        if (activeTouchId === null && e.changedTouches.length > 0) {
            const t = e.changedTouches[0];
            activeTouchId = t.identifier;
            lastPointerX = t.clientX;
            lastPointerY = t.clientY;
        }
    }, { passive: true });

    canvas.addEventListener('touchmove', (e) => {
        for (const t of e.changedTouches) {
            if (t.identifier === activeTouchId) {
                const dx = t.clientX - lastPointerX;
                const dy = t.clientY - lastPointerY;
                lastPointerX = t.clientX;
                lastPointerY = t.clientY;
                state.yaw += dx * INITIAL_CAMERA.mouseSensitivity * 1.8;
                state.pitch = clamp(state.pitch - dy * INITIAL_CAMERA.mouseSensitivity * 1.8, -89.0, 89.0);
                break;
            }
        }
    }, { passive: true });

    const endTouch = (e) => {
        for (const t of e.changedTouches) {
            if (t.identifier === activeTouchId) activeTouchId = null;
        }
    };
    canvas.addEventListener('touchend', endTouch, { passive: true });
    canvas.addEventListener('touchcancel', endTouch, { passive: true });

    // On-screen action buttons & virtual D-pad bindings
    const bindHoldButton = (id, onDown, onUp) => {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            onDown();
        });
        const release = (e) => {
            e.preventDefault();
            onUp();
        };
        btn.addEventListener('pointerup', release);
        btn.addEventListener('pointerleave', release);
        btn.addEventListener('pointercancel', release);
    };

    bindHoldButton('btn-fwd', () => { touchMove.fwd = 1; }, () => { touchMove.fwd = 0; });
    bindHoldButton('btn-back', () => { touchMove.fwd = -1; }, () => { touchMove.fwd = 0; });
    bindHoldButton('btn-left', () => { touchMove.right = -1; }, () => { touchMove.right = 0; });
    bindHoldButton('btn-right', () => { touchMove.right = 1; }, () => { touchMove.right = 0; });
    bindHoldButton('btn-up', () => { touchMove.up = 1; }, () => { touchMove.up = 0; });
    bindHoldButton('btn-down', () => { touchMove.up = -1; }, () => { touchMove.up = 0; });
    bindHoldButton('btn-sprint', () => { touchMove.sprint = true; }, () => { touchMove.sprint = false; });

    document.getElementById('btn-rolcar')?.addEventListener('click', resetCamera);
    document.getElementById('btn-pause')?.addEventListener('click', () => togglePause());
    document.getElementById('pause-resume')?.addEventListener('click', () => togglePause(false));

    // Pause Dialog Action Buttons
    const pauseLogEl = document.getElementById('pause-log-output');
    function logPause(msg) {
        if (!pauseLogEl) return;
        const ts = new Date().toLocaleTimeString();
        pauseLogEl.innerHTML += `<br>[${ts}] ${msg}`;
        pauseLogEl.scrollTop = pauseLogEl.scrollHeight;
    }

    document.getElementById('pause-wasm-test')?.addEventListener('click', () => {
        try {
            const v = wasm.get_version();
            const tick = wasm.traffic_tick(MEM_SIM_TIME_PTR, 0.1);
            const carsUpdated = wasm.update_vehicle_stream ? wasm.update_vehicle_stream(MEM_CARS_PTR, state.carCount, 0.016, state.simSpeed) : 0;
            logPause(`✅ Kernel WASM OK: v${v}, Fase Semáforo=${tick}, Vehículos Activos=${carsUpdated}`);
            showToast('Prueba WASM: Superada con éxito');
        } catch (err) {
            logPause(`❌ Error probando WASM: ${err.message}`);
        }
    });

    document.getElementById('pause-toggle-cars')?.addEventListener('click', () => {
        state.carsEnabled = !state.carsEnabled;
        const elCars = document.getElementById('hud-cars');
        if (elCars) {
            elCars.textContent = state.carsEnabled ? `${state.carCount} activos` : 'Pausado';
            elCars.className = state.carsEnabled ? 'metric-good' : 'metric-warn';
        }
        logPause(`🚗 Simulación de tráfico: ${state.carsEnabled ? 'ACTIVADA' : 'DESACTIVADA'}`);
        showToast(state.carsEnabled ? 'Tráfico: ON' : 'Tráfico: OFF');
    });

    document.getElementById('pause-toggle-time')?.addEventListener('click', () => {
        state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
        state.simHour = TIME_PRESETS[state.presetIdx].hour;
        logPause(`☀️ Hora establecida: ${TIME_PRESETS[state.presetIdx].label}`);
        showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
    });

    document.getElementById('pause-force-traffic')?.addEventListener('click', () => {
        const simTimeFloat = MEM_SIM_TIME_PTR >> 2;
        const currentPhase = wasm.traffic_tick(MEM_SIM_TIME_PTR, 0.0);
        const nextPhase = (currentPhase + 1) % 4;
        const phaseTimes = [0.0, 9.5, 12.5, 21.5];
        f32Mem[simTimeFloat] = phaseTimes[nextPhase];
        state.trafficPhase = wasm.traffic_tick(MEM_SIM_TIME_PTR, 0.0);
        logPause(`🚦 Fase semafórica forzada a: ${TRAFFIC_PHASE_LABELS[state.trafficPhase]}`);
        showToast(TRAFFIC_PHASE_LABELS[state.trafficPhase]);
    });

    document.getElementById('pause-toggle-cull')?.addEventListener('click', () => {
        state.cullingEnabled = !state.cullingEnabled;
        logPause(`📦 Frustum Culling AABB: ${state.cullingEnabled ? 'HABILITADO' : 'DESHABILITADO'}`);
        showToast(state.cullingEnabled ? 'Culling: ON' : 'Culling: OFF');
    });

    document.getElementById('pause-reset-cam')?.addEventListener('click', () => {
        resetCamera();
        logPause('📍 Cámara reubicada en Rolcar Paseo de la Cruz');
    });

    document.getElementById('btn-time')?.addEventListener('click', () => {
        state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
        state.simHour = TIME_PRESETS[state.presetIdx].hour;
        showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
    });
    document.getElementById('btn-flash')?.addEventListener('click', () => {
        state.flashlightOn = !state.flashlightOn;
        showToast(state.flashlightOn ? 'Linterna: ON' : 'Linterna: OFF');
    });
    document.getElementById('btn-cull')?.addEventListener('click', () => {
        state.cullingEnabled = !state.cullingEnabled;
        showToast(state.cullingEnabled ? 'Culling WASM: ON' : 'Culling WASM: OFF');
    });

    // 7. Frame Loop
    const uniformData = new Float32Array(2272 / 4); // 568 floats
    const identityModel = new Float32Array([
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1,
    ]);
    const cullFlagsBySector = new Map();

    let lastTimestamp = performance.now();
    let fpsAccum = 0;
    let fpsFrames = 0;
    let currentFps = 60.0;
    let avgFrameMs = 16.6;
    let avgCpuMs = 0.5;
    let streamCheckTimer = 0;

    function maybeStreamNearbySectors(camX, camZ) {
        if (!manifestInfo || manifestInfo.manifest.sectors.length <= 1) return;
        if (sectorCache.size >= 4 || loadingSectors.size > 0) return;

        const macroSize = manifestInfo.manifest.macro_size || 1024.0;
        const loadRadius = 1500.0;
        let best = null;
        let bestDist = Infinity;

        for (const s of manifestInfo.manifest.sectors) {
            const key = `${s.mx}_${s.mz}`;
            if (sectorCache.has(key) || loadingSectors.has(key) || missingSectors.has(key)) continue;
            if ((s.vert_count || 0) < 100) continue;
            const cx = (s.mx + 0.5) * macroSize;
            const cz = (s.mz + 0.5) * macroSize;
            const d = Math.hypot(cx - camX, cz - camZ);
            if (d < loadRadius && d < bestDist) {
                bestDist = d;
                best = s;
            }
        }
        if (best) {
            loadSectorEntry(best, manifestInfo.basePrefix, false).catch(() => {});
        }
    }

    function frameLoop(now) {
        const dt = Math.min(0.1, Math.max(0.0001, (now - lastTimestamp) / 1000.0));
        lastTimestamp = now;

        const cpuStart = performance.now();

        if (toastTimer > 0) {
            toastTimer -= dt;
            if (toastTimer <= 0 && elToast) elToast.classList.remove('visible');
        }

        // Simulation clock (72 min = 24h cycle)
        if (!state.timeFrozen) {
            state.simHour = (state.simHour + dt / 180.0) % 24.0;
        }

        // Camera input vector
        let moveFwd = touchMove.fwd;
        let moveRight = touchMove.right;
        let moveUp = touchMove.up;
        if (keysDown.has('KeyW') || keysDown.has('ArrowUp')) moveFwd += 1;
        if (keysDown.has('KeyS') || keysDown.has('ArrowDown')) moveFwd -= 1;
        if (keysDown.has('KeyD') || keysDown.has('ArrowRight')) moveRight += 1;
        if (keysDown.has('KeyA') || keysDown.has('ArrowLeft')) moveRight -= 1;
        if (keysDown.has('Space') || keysDown.has('KeyE')) moveUp += 1;
        if (keysDown.has('ControlLeft') || keysDown.has('ControlRight') || keysDown.has('KeyC') || keysDown.has('KeyQ')) moveUp -= 1;

        const isSprint = touchMove.sprint || keysDown.has('ShiftLeft') || keysDown.has('ShiftRight');
        const speed = INITIAL_CAMERA.moveSpeed * (isSprint ? INITIAL_CAMERA.sprintMultiplier : 1.0);

        // Execute WASM movement & matrices
        wasm.camera_step(MEM_POS_PTR, state.yaw, state.pitch, moveFwd, moveRight, moveUp, speed, dt);
        wasm.camera_get_vectors(state.yaw, state.pitch, MEM_FWD_PTR, MEM_RIGHT_PTR, MEM_UP_PTR);

        const camX = f32Mem[0];
        const camY = f32Mem[1];
        const camZ = f32Mem[2];
        const fwdX = f32Mem[(MEM_FWD_PTR >> 2) + 0];
        const fwdY = f32Mem[(MEM_FWD_PTR >> 2) + 1];
        const fwdZ = f32Mem[(MEM_FWD_PTR >> 2) + 2];
        const upX = f32Mem[(MEM_UP_PTR >> 2) + 0];
        const upY = f32Mem[(MEM_UP_PTR >> 2) + 1];
        const upZ = f32Mem[(MEM_UP_PTR >> 2) + 2];

        wasm.mat4_lookat(
            MEM_VIEW_PTR,
            camX, camY, camZ,
            camX + fwdX, camY + fwdY, camZ + fwdZ,
            upX, upY, upZ
        );

        const aspect = canvas.width / Math.max(1, canvas.height);
        const fovyRad = degToRad(60.0);
        wasm.mat4_perspective_webgpu(MEM_PROJ_WGPU_PTR, fovyRad, aspect, 1.0, 15000.0);
        wasm.mat4_multiply(MEM_MVP_WGPU_PTR, MEM_PROJ_WGPU_PTR, MEM_VIEW_PTR);
        wasm.frustum_extract(MEM_PLANES_PTR, MEM_MVP_WGPU_PTR);

        let mvpSlice;
        if (isWebGPU) {
            mvpSlice = f32Mem.subarray(MEM_MVP_WGPU_PTR >> 2, (MEM_MVP_WGPU_PTR >> 2) + 16);
        } else {
            wasm.mat4_perspective_webgl(MEM_PROJ_WGL_PTR, fovyRad, aspect, 1.0, 15000.0);
            wasm.mat4_multiply(MEM_MVP_WGL_PTR, MEM_PROJ_WGL_PTR, MEM_VIEW_PTR);
            mvpSlice = f32Mem.subarray(MEM_MVP_WGL_PTR >> 2, (MEM_MVP_WGL_PTR >> 2) + 16);
        }

        // Execute WASM frustum culling across all loaded sectors
        const aabbBaseFloat = MEM_AABBS_PTR >> 2;
        for (const [sectorKey, secMeta] of sectorCache.entries()) {
            const count = secMeta.chunkCount;
            if (count === 0) continue;
            let flags = cullFlagsBySector.get(sectorKey);
            if (!flags || flags.length !== count) {
                flags = new Uint8Array(count);
                cullFlagsBySector.set(sectorKey, flags);
            }
            if (state.cullingEnabled) {
                for (let offset = 0; offset < count; offset += MAX_CULL_BATCH) {
                    const batch = Math.min(MAX_CULL_BATCH, count - offset);
                    f32Mem.set(secMeta.aabbData.subarray(offset * 6, (offset + batch) * 6), aabbBaseFloat);
                    wasm.cull_chunks(MEM_PLANES_PTR, MEM_AABBS_PTR, MEM_FLAGS_PTR, batch);
                    flags.set(u8Mem.subarray(MEM_FLAGS_PTR, MEM_FLAGS_PTR + batch), offset);
                }
            } else {
                flags.fill(1);
            }
        }

        // Execute WASM deterministic traffic simulation tick
        if (!state.paused) {
            state.trafficPhase = wasm.traffic_tick(MEM_SIM_TIME_PTR, dt);
            if (state.carsEnabled && wasm.update_vehicle_stream) {
                wasm.update_vehicle_stream(MEM_CARS_PTR, state.carCount, dt, state.simSpeed);
            }
        }

        // Compute sun, sky, and dynamic lights
        const { sunDir, skyColor, clearColor } = computeSunAndSky(state.simHour);

        uniformData.set(mvpSlice, 0);          // mvp (16 floats @ 0)
        uniformData.set(identityModel, 16);    // model (16 floats @ 16)
        uniformData.set(sunDir, 32);           // sunDir (4 floats @ 32)
        uniformData.set(skyColor, 36);         // skyColor (4 floats @ 36)
        uniformData[40] = camX;
        uniformData[41] = camY;
        uniformData[42] = camZ;
        uniformData[43] = state.simHour;
        uniformData[44] = camX;
        uniformData[45] = camY;
        uniformData[46] = camZ;
        uniformData[47] = 75.0;
        uniformData[48] = fwdX;
        uniformData[49] = fwdY;
        uniformData[50] = fwdZ;
        uniformData[51] = 0.866;

        let lightCount = 0;
        const nightStrength = skyColor[3];
        if (state.trafficSignals.length > 0 && lightCount < 64) {
            for (let i = 0; i < state.trafficSignals.length && lightCount < 48; i++) {
                const sig = state.trafficSignals[i];
                const dx = sig.x - camX;
                const dz = sig.z - camZ;
                if (dx * dx + dz * dz > 450 * 450) continue;

                const isNS = (sig.phase || 0) === 0;
                let r = 1.0, g = 0.04, b = 0.04;
                if (isNS) {
                    if (state.trafficPhase === 0) { r = 0.0; g = 1.0; b = 0.35; }
                    else if (state.trafficPhase === 1) { r = 1.0; g = 0.65; b = 0.0; }
                } else {
                    if (state.trafficPhase === 2) { r = 0.0; g = 1.0; b = 0.35; }
                    else if (state.trafficPhase === 3) { r = 1.0; g = 0.65; b = 0.0; }
                }

                const base = 56 + lightCount * 8;
                uniformData[base + 0] = sig.x;
                uniformData[base + 1] = sig.y;
                uniformData[base + 2] = sig.z;
                uniformData[base + 3] = 22.0;
                uniformData[base + 4] = r;
                uniformData[base + 5] = g;
                uniformData[base + 6] = b;
                uniformData[base + 7] = 3.8;
                lightCount++;
            }
        }

        // Rolcar Paseo de la Cruz warm storefront illumination at dusk/night
        if (nightStrength > 0.05 && lightCount < 64) {
            const base = 56 + lightCount * 8;
            uniformData[base + 0] = 969.0;
            uniformData[base + 1] = 6.5;
            uniformData[base + 2] = 779.0;
            uniformData[base + 3] = 35.0;
            uniformData[base + 4] = 1.0;
            uniformData[base + 5] = 0.92;
            uniformData[base + 6] = 0.78;
            uniformData[base + 7] = 3.2 * nightStrength;
            lightCount++;
        }

        uniformData[52] = lightCount;
        uniformData[53] = state.flashlightOn ? 1.0 : 0.0;
        uniformData[54] = now * 0.001;
        uniformData[55] = 0.0;

        const cpuEnd = performance.now();

        const stats = renderer.render({
            uniformBufferData: uniformData,
            clearColor,
            cullFlagsBySector,
            cullingEnabled: state.cullingEnabled,
        });

        // Background nearby sector streaming check every 1.0s
        streamCheckTimer += dt;
        if (streamCheckTimer >= 1.0) {
            streamCheckTimer = 0;
            maybeStreamNearbySectors(camX, camZ);
        }

        // Update ISO 25010:2023 Telemetry HUD
        fpsAccum += dt;
        fpsFrames++;
        const frameCpuMs = cpuEnd - cpuStart;
        avgCpuMs = avgCpuMs * 0.9 + frameCpuMs * 0.1;
        avgFrameMs = avgFrameMs * 0.9 + (dt * 1000.0) * 0.1;

        if (fpsAccum >= 0.25) {
            currentFps = fpsFrames / fpsAccum;
            fpsAccum = 0;
            fpsFrames = 0;

            if (elRes) elRes.textContent = `${canvas.width}x${canvas.height} px`;
            if (elTime) {
                const hrs = Math.floor(state.simHour);
                const mins = Math.floor((state.simHour - hrs) * 60);
                const phaseLabel = (hrs >= 6 && hrs < 18) ? (hrs < 8 ? 'Amanecer' : hrs > 16 ? 'Atardecer' : 'Día') : 'Noche';
                elTime.textContent = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')} (${phaseLabel})`;
            }
            if (elTraffic) {
                elTraffic.textContent = `${TRAFFIC_PHASE_LABELS[state.trafficPhase] || 'F0'} | ${state.trafficSignals.length} Semaf`;
            }
            if (elFps) {
                elFps.textContent = `${currentFps.toFixed(0)} FPS (${avgFrameMs.toFixed(2)} ms)`;
                elFps.className = currentFps >= 50 ? 'metric-good' : currentFps >= 30 ? 'metric-warn' : 'metric-bad';
            }
            if (elCpuDraw) {
                elCpuDraw.textContent = `${avgCpuMs.toFixed(2)} ms | Draw: ${stats.drawCalls}`;
            }
            if (elChunks) {
                elChunks.textContent = `${stats.visibleChunks}/${stats.totalChunks} (Sectores: ${sectorCache.size})`;
            }
            if (elVerts) {
                const cullPct = stats.totalVerts > 0
                    ? (1.0 - stats.visibleVerts / stats.totalVerts) * 100.0
                    : 0.0;
                elVerts.textContent = `${Math.round(stats.visibleVerts / 1000)}k/${Math.round(stats.totalVerts / 1000)}k (Cull: ${cullPct.toFixed(0)}%)`;
            }
            if (elPos) {
                elPos.textContent = `${camX.toFixed(1)}, ${camY.toFixed(1)}, ${camZ.toFixed(1)} | Yaw ${state.yaw.toFixed(1)}°`;
            }
        }

        requestAnimationFrame(frameLoop);
    }

    requestAnimationFrame(frameLoop);
}

main().catch((err) => {
    console.error('[StreetVulkan Fatal]', err);
    const elLoaderText = document.getElementById('loader-text');
    if (elLoaderText) {
        elLoaderText.textContent = `Error inicializando StreetVulkan: ${err.message}`;
        elLoaderText.style.color = '#ff6b6b';
    }
});
