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

// WASM linear memory byte offsets (matching web/street_vulkan_core.wat; 0x0000 reserved as NULL guard)
const MEM_POS_PTR = 0x0004;
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
    const compType = acc.componentType || 5126;
    const isNormalized = Boolean(acc.normalized);

    // Fast path: direct typed array view if matching componentType, zero/matching stride, and alignment
    if (expectedType === Float32Array && compType === 5126) {
        const compSize = 4;
        const expectedStride = numComponents * compSize;
        const actualStride = bv.byteStride || 0;
        if ((actualStride === 0 || actualStride === expectedStride) && (byteOffset % compSize === 0)) {
            return new Float32Array(arrayBuffer, byteOffset, elemCount);
        }
    } else if (expectedType === Uint32Array && compType === 5125) {
        const compSize = 4;
        const expectedStride = numComponents * compSize;
        const actualStride = bv.byteStride || 0;
        if ((actualStride === 0 || actualStride === expectedStride) && (byteOffset % compSize === 0)) {
            return new Uint32Array(arrayBuffer, byteOffset, elemCount);
        }
    } else if (expectedType === Uint16Array && compType === 5123) {
        const compSize = 2;
        const expectedStride = numComponents * compSize;
        const actualStride = bv.byteStride || 0;
        if ((actualStride === 0 || actualStride === expectedStride) && (byteOffset % compSize === 0)) {
            return new Uint16Array(arrayBuffer, byteOffset, elemCount);
        }
    } else if (expectedType === Uint8Array && compType === 5121) {
        const compSize = 1;
        const expectedStride = numComponents * compSize;
        const actualStride = bv.byteStride || 0;
        if (actualStride === 0 || actualStride === expectedStride) {
            return new Uint8Array(arrayBuffer, byteOffset, elemCount);
        }
    }

    const out = new expectedType(elemCount);
    const view = new DataView(arrayBuffer);
    let compSize = 4;
    if (compType === 5120 || compType === 5121) compSize = 1;
    else if (compType === 5122 || compType === 5123) compSize = 2;
    const expectedStride = numComponents * compSize;
    const stride = bv.byteStride || expectedStride;

    for (let i = 0; i < acc.count; i++) {
        const rowOff = byteOffset + i * stride;
        for (let c = 0; c < numComponents; c++) {
            const off = rowOff + c * compSize;
            let val = 0;
            if (compType === 5126) {
                val = view.getFloat32(off, true);
            } else if (compType === 5125) {
                val = view.getUint32(off, true);
            } else if (compType === 5123) {
                val = view.getUint16(off, true);
                if (expectedType === Float32Array && isNormalized) val /= 65535.0;
            } else if (compType === 5122) {
                val = view.getInt16(off, true);
                if (expectedType === Float32Array && isNormalized) val = Math.max(-1.0, val / 32767.0);
            } else if (compType === 5121) {
                val = view.getUint8(off);
                if (expectedType === Float32Array && isNormalized) val /= 255.0;
            } else if (compType === 5120) {
                val = view.getInt8(off);
                if (expectedType === Float32Array && isNormalized) val = Math.max(-1.0, val / 127.0);
            }
            out[i * numComponents + c] = val;
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

    // Collect all valid primitives across all meshes
    const primDescriptors = [];
    let totalVertexCount = 0;
    let totalIndexCount = 0;

    for (let m = 0; m < gltf.meshes.length; m++) {
        const mesh = gltf.meshes[m];
        if (!mesh.primitives || mesh.primitives.length === 0) continue;
        for (let p = 0; p < mesh.primitives.length; p++) {
            const prim = mesh.primitives[p];
            const attrs = prim.attributes;
            if (!attrs || attrs.POSITION === undefined) continue;

            const posAcc = gltf.accessors[attrs.POSITION];
            if (!posAcc || !posAcc.count) continue;
            const vertCount = posAcc.count;

            let idxCount = vertCount;
            if (prim.indices !== undefined) {
                const idxAcc = gltf.accessors[prim.indices];
                if (idxAcc) idxCount = idxAcc.count;
            }

            const meshName = mesh.name || '';
            const matName = (prim.material !== undefined && gltf.materials && gltf.materials[prim.material])
                ? (gltf.materials[prim.material].name || '')
                : '';
            const isBuilding = /build|edific|facad|roof|wall|casa|rolcar|comercial|commerc|residen|tienda|store|shop|house/i.test(meshName) ||
                               /build|edific|facad|roof|wall|casa|rolcar|comercial|commerc|residen|tienda|store|shop|house/i.test(matName);

            primDescriptors.push({
                meshIdx: m,
                primIdx: p,
                meshName,
                matName,
                isBuilding,
                attrs,
                indicesAccIdx: prim.indices,
                materialIdx: prim.material,
                vertCount,
                idxCount,
            });

            totalVertexCount += vertCount;
            totalIndexCount += idxCount;
        }
    }

    if (totalVertexCount === 0) {
        throw new Error('GLB contains no valid vertex geometry');
    }

    const pos = new Float32Array(totalVertexCount * 3);
    const norm = new Float32Array(totalVertexCount * 3);
    const uv = new Float32Array(totalVertexCount * 2);
    const col = new Float32Array(totalVertexCount * 4);
    const em = new Float32Array(totalVertexCount);

    const useUint32 = (totalVertexCount > 65535) || primDescriptors.some(d => {
        if (d.indicesAccIdx === undefined) return false;
        const acc = gltf.accessors[d.indicesAccIdx];
        return acc && acc.componentType === 5125;
    });
    const indices = useUint32 ? new Uint32Array(totalIndexCount) : new Uint16Array(totalIndexCount);
    const indexFormat = useUint32 ? 'uint32' : 'uint16';

    const submeshes = [];
    let vertWriteOffset = 0;
    let idxWriteOffset = 0;

    for (const desc of primDescriptors) {
        const { attrs, vertCount, idxCount, isBuilding, meshIdx, primIdx, meshName } = desc;
        const vStart = vertWriteOffset;
        const iStart = idxWriteOffset;

        // POSITION
        const primPos = extractAccessorTypedArray(gltf, attrs.POSITION, arrayBuffer, binBaseOffset, 3, Float32Array);
        pos.set(primPos, vStart * 3);

        // NORMAL
        if (attrs.NORMAL !== undefined) {
            const primNorm = extractAccessorTypedArray(gltf, attrs.NORMAL, arrayBuffer, binBaseOffset, 3, Float32Array);
            norm.set(primNorm, vStart * 3);
        } else {
            for (let i = 0; i < vertCount; i++) norm[(vStart + i) * 3 + 1] = 1.0;
        }

        // TEXCOORD_0
        const uvIdx = attrs.TEXCOORD_0 !== undefined ? attrs.TEXCOORD_0 : attrs.TEXCOORD;
        if (uvIdx !== undefined) {
            const primUv = extractAccessorTypedArray(gltf, uvIdx, arrayBuffer, binBaseOffset, 2, Float32Array);
            uv.set(primUv, vStart * 2);
        }

        // COLOR_0
        const colIdx = attrs.COLOR_0 !== undefined ? attrs.COLOR_0 : attrs.COLOR;
        if (colIdx !== undefined) {
            const acc = gltf.accessors[colIdx];
            const numComp = (acc && acc.type === 'VEC3') ? 3 : 4;
            const primCol = extractAccessorTypedArray(gltf, colIdx, arrayBuffer, binBaseOffset, numComp, Float32Array);
            if (numComp === 4) {
                col.set(primCol, vStart * 4);
            } else {
                for (let i = 0; i < vertCount; i++) {
                    const dstOff = (vStart + i) * 4;
                    const srcOff = i * 3;
                    col[dstOff + 0] = primCol[srcOff + 0];
                    col[dstOff + 1] = primCol[srcOff + 1];
                    col[dstOff + 2] = primCol[srcOff + 2];
                    col[dstOff + 3] = 1.0;
                }
            }
        } else {
            for (let i = 0; i < vertCount; i++) {
                const off = (vStart + i) * 4;
                col[off + 0] = 1.0;
                col[off + 1] = 1.0;
                col[off + 2] = 1.0;
                col[off + 3] = (uvIdx !== undefined) ? 0.0 : 1.0;
            }
        }

        // EMISSION
        let matEmission = 0.0;
        if (desc.materialIdx !== undefined && gltf.materials && gltf.materials[desc.materialIdx]) {
            const mat = gltf.materials[desc.materialIdx];
            if (mat.emissiveFactor) {
                const ef = mat.emissiveFactor;
                if (ef[0] > 0.01 || ef[1] > 0.01 || ef[2] > 0.01) {
                    matEmission = (ef[0] + ef[1] + ef[2]) / 3.0 * 3.0;
                }
            }
        }

        const emIdx = attrs._EMISSION !== undefined ? attrs._EMISSION
                    : (attrs.EMISSION !== undefined ? attrs.EMISSION
                    : attrs._EMISSION_FACTOR);
        if (emIdx !== undefined) {
            const primEm = extractAccessorTypedArray(gltf, emIdx, arrayBuffer, binBaseOffset, 1, Float32Array);
            em.set(primEm, vStart);
        } else if (matEmission > 0.0) {
            em.fill(matEmission, vStart, vStart + vertCount);
        }

        // INDICES
        if (desc.indicesAccIdx !== undefined) {
            const acc = gltf.accessors[desc.indicesAccIdx];
            let primIndices;
            if (acc.componentType === 5125) {
                primIndices = extractAccessorTypedArray(gltf, desc.indicesAccIdx, arrayBuffer, binBaseOffset, 1, Uint32Array);
            } else if (acc.componentType === 5123) {
                primIndices = extractAccessorTypedArray(gltf, desc.indicesAccIdx, arrayBuffer, binBaseOffset, 1, Uint16Array);
            } else {
                primIndices = extractAccessorTypedArray(gltf, desc.indicesAccIdx, arrayBuffer, binBaseOffset, 1, Uint8Array);
            }
            if (vStart === 0) {
                indices.set(primIndices, iStart);
            } else {
                for (let k = 0; k < primIndices.length; k++) {
                    indices[iStart + k] = vStart + primIndices[k];
                }
            }
        } else {
            for (let k = 0; k < vertCount; k++) {
                indices[iStart + k] = vStart + k;
            }
        }

        submeshes.push({
            name: meshName || `mesh_${meshIdx}_prim_${primIdx}`,
            meshIndex: meshIdx,
            primIndex: primIdx,
            vertexStart: vStart,
            vertexCount: vertCount,
            indexStart: iStart,
            indexCount: idxCount,
            isBuilding,
        });

        vertWriteOffset += vertCount;
        idxWriteOffset += idxCount;
    }

    // Identify building sub-mesh geometry from matIDs (color alpha)
    // 0.35 = Roofs, 1.00 = Facades/Walls, 1.14 = Rolcar Stucco, 1.18 = Rolling Steel Shutters
    const buildingTriIndices = [];
    const nonBuildingTriIndices = [];
    for (let i = 0; i < indices.length; i += 3) {
        const i0 = indices[i];
        const i1 = indices[i + 1];
        const i2 = indices[i + 2];
        const m0 = col[i0 * 4 + 3];
        const m1 = col[i1 * 4 + 3];
        const m2 = col[i2 * 4 + 3];
        const avgMat = (m0 + m1 + m2) / 3.0;
        const isBldg = (avgMat > 0.30 && avgMat < 0.40) ||
                       (avgMat > 0.98 && avgMat < 1.05) ||
                       (avgMat > 1.10 && avgMat < 1.25);
        if (isBldg) {
            buildingTriIndices.push(i0, i1, i2);
        } else {
            nonBuildingTriIndices.push(i0, i1, i2);
        }
    }

    const buildingIndices = buildingTriIndices.length > 0
        ? (useUint32 ? new Uint32Array(buildingTriIndices) : new Uint16Array(buildingTriIndices))
        : null;

    if (submeshes.length === 1 && !submeshes[0].isBuilding && buildingTriIndices.length > 0) {
        const nonBuildingIndices = useUint32
            ? new Uint32Array(nonBuildingTriIndices)
            : new Uint16Array(nonBuildingTriIndices);
        submeshes[0].name = 'sector_terrain';
        submeshes[0].indexCount = nonBuildingTriIndices.length;
        submeshes[0].customIndices = nonBuildingIndices;
        submeshes[0].isBuilding = false;

        submeshes.push({
            name: 'sector_buildings',
            meshIndex: 0,
            primIndex: 1,
            vertexStart: 0,
            vertexCount: totalVertexCount,
            indexStart: 0,
            indexCount: buildingTriIndices.length,
            isBuilding: true,
            customIndices: buildingIndices,
        });
    }

    return {
        pos,
        norm,
        uv,
        col,
        em,
        indices,
        indexFormat,
        vertexCount: totalVertexCount,
        indexCount: totalIndexCount,
        submeshes,
        buildingIndices,
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

function buildFallbackVehicleMesh() {
    const positions = [];
    const normals = [];
    const uvs = [];
    const colors = [];
    const emissions = [];

    const pushBox = (minX, minY, minZ, maxX, maxY, maxZ, col, em = 0.0) => {
        const pushFace = (p0, p1, p2, p3, n) => {
            const pts = [p0, p1, p2, p0, p2, p3];
            for (let i = 0; i < 6; i++) {
                positions.push(pts[i][0], pts[i][1], pts[i][2]);
                normals.push(n[0], n[1], n[2]);
                uvs.push(0.5, 0.5);
                colors.push(col[0], col[1], col[2], col[3]);
                emissions.push(em);
            }
        };
        // +Y top, -Y bottom, +Z front, -Z back, +X right, -X left
        pushFace([minX, maxY, minZ], [maxX, maxY, minZ], [maxX, maxY, maxZ], [minX, maxY, maxZ], [0, 1, 0]);
        pushFace([minX, minY, maxZ], [maxX, minY, maxZ], [maxX, minY, minZ], [minX, minY, minZ], [0, -1, 0]);
        pushFace([minX, minY, maxZ], [maxX, minY, maxZ], [maxX, maxY, maxZ], [minX, maxY, maxZ], [0, 0, 1]);
        pushFace([maxX, minY, minZ], [minX, minY, minZ], [minX, maxY, minZ], [maxX, maxY, minZ], [0, 0, -1]);
        pushFace([maxX, minY, maxZ], [maxX, minY, minZ], [maxX, maxY, minZ], [maxX, maxY, maxZ], [1, 0, 0]);
        pushFace([minX, minY, minZ], [minX, minY, maxZ], [minX, maxY, maxZ], [minX, maxY, minZ], [-1, 0, 0]);
    };

    // 1. Lower chassis (4.2m length along Z, 1.8m width along X, 0.7m height)
    pushBox(-0.9, 0.2, -2.1, 0.9, 0.9, 2.1, [0.15, 0.45, 0.85, 2.0], 0.0);
    // 2. Cabin / roof (2.2m length, 1.5m width, 0.65m height)
    pushBox(-0.75, 0.9, -0.9, 0.75, 1.55, 1.3, [0.08, 0.12, 0.18, 2.0], 0.0);
    // 3. Headlights (Z = +2.1, high emission white/amber)
    pushBox(0.45, 0.45, 2.08, 0.75, 0.75, 2.12, [1.0, 0.98, 0.85, 2.0], 8.0);
    pushBox(-0.75, 0.45, 2.08, -0.45, 0.75, 2.12, [1.0, 0.98, 0.85, 2.0], 8.0);
    // 4. Taillights (Z = -2.1, high emission red)
    pushBox(0.45, 0.50, -2.12, 0.75, 0.75, -2.08, [1.0, 0.08, 0.05, 2.0], 6.0);
    pushBox(-0.75, 0.50, -2.12, -0.45, 0.75, -2.08, [1.0, 0.08, 0.05, 2.0], 6.0);

    const vertexCount = positions.length / 3;
    const indices = new Uint16Array(vertexCount);
    for (let i = 0; i < vertexCount; i++) indices[i] = i;

    return {
        pos: new Float32Array(positions),
        norm: new Float32Array(normals),
        uv: new Float32Array(uvs),
        col: new Float32Array(colors),
        em: new Float32Array(emissions),
        indices,
        indexFormat: 'uint16',
        vertexCount,
        indexCount: vertexCount,
    };
}

async function loadVehicleModelWithFallback(basePrefix) {
    try {
        const carGlbUrl = `${basePrefix}models/cars/car_sedan.glb`;
        const resp = await fetch(carGlbUrl);
        if (resp.ok) {
            const buf = await resp.arrayBuffer();
            const parsed = parseGLB(buf);
            if (parsed && parsed.vertexCount > 0) return parsed;
        }
    } catch (_err) {
        // Fallback
    }
    return buildFallbackVehicleMesh();
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
    const queryBackend = (new URLSearchParams(window.location.search).get('backend') || '').toLowerCase();
    let renderer = null;
    let backendInfo = null;

    const preferWebGL = (queryBackend === 'webgl' || queryBackend === 'webgl2');
    if (!preferWebGL) {
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
        renderMode: 'all',
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

    // Declared early so resetCamera→maybeStreamNearbySectors can safely read it
    // before resolveSectorManifest() runs (initially null = no streaming yet).
    let manifestInfo = null;

    function resetCamera() {
        const posBase = MEM_POS_PTR >> 2;
        f32Mem[posBase + 0] = INITIAL_CAMERA.pos[0];
        f32Mem[posBase + 1] = INITIAL_CAMERA.pos[1];
        f32Mem[posBase + 2] = INITIAL_CAMERA.pos[2];
        state.yaw = INITIAL_CAMERA.yaw;
        state.pitch = INITIAL_CAMERA.pitch;
        showToast('Cámara: Rolcar Paseo de la Cruz (Sector 0,0)');
        maybeStreamNearbySectors(INITIAL_CAMERA.x, INITIAL_CAMERA.z);
    }
    resetCamera();
    f32Mem[MEM_SIM_TIME_PTR >> 2] = 0.0;

    const TERCER_ANILLO_WAYPOINTS = [
        { name: 'Tercer Anillo Norte — Paso a Desnivel (Av. Siglo XXI Nte)', x: 532.0, y: 28.0, z: -7134.0, yaw: 0.0, pitch: -5.0 },
        { name: 'Tercer Anillo Oriente (Av. Siglo XXI Ote)', x: 4927.0, y: 69.5, z: -7.5, yaw: -90.0, pitch: -5.0 },
        { name: 'Tercer Anillo Sur (Av. Siglo XXI Sur)', x: -1.5, y: 1.0, z: 4011.0, yaw: 180.0, pitch: -5.0 },
        { name: 'Tercer Anillo Poniente (Av. Siglo XXI Pte)', x: -7500.0, y: 21.0, z: 15.0, yaw: 90.0, pitch: -5.0 },
    ];
    let ring3WaypointIdx = 0;

    function teleportTercerAnillo() {
        const wp = TERCER_ANILLO_WAYPOINTS[ring3WaypointIdx];
        ring3WaypointIdx = (ring3WaypointIdx + 1) % TERCER_ANILLO_WAYPOINTS.length;
        const posBase = MEM_POS_PTR >> 2;
        f32Mem[posBase + 0] = wp.x;
        f32Mem[posBase + 1] = wp.y;
        f32Mem[posBase + 2] = wp.z;
        state.yaw = wp.yaw;
        state.pitch = wp.pitch;
        showToast(`Teleport: ${wp.name}`);
        maybeStreamNearbySectors(wp.x, wp.z);
    }

    // 5. Sector Manifest & Streaming Loader (Prioritize Sector 0,0)
    const sectorCache = new Map(); // sectorKey -> { entry, aabbData, chunkCount, cx, cz, lastUsed }
    const cullFlagsBySector = new Map(); // sectorKey -> Uint8Array(chunkCount)
    const loadingSectors = new Set();
    const missingSectors = new Set();
    manifestInfo = await resolveSectorManifest();

    loadVehicleModelWithFallback(manifestInfo ? manifestInfo.basePrefix : '../').then((vMesh) => {
        if (renderer && renderer.uploadVehicleModel) {
            renderer.uploadVehicleModel(vMesh);
        }
    });

    function unloadSectorEntry(key) {
        const secMeta = sectorCache.get(key);
        if (!secMeta) return;
        renderer.unloadSector(key);
        sectorCache.delete(key);
        cullFlagsBySector.delete(key);
    }

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
                const sectorLabel = (entry.mx === 0 && entry.mz === 0)
                    ? 'Sector (0, 0) Paseo de la Cruz'
                    : `Sector (${entry.mx}, ${entry.mz}) Tercer Anillo Metropolitano`;
                elLoaderText.textContent = `Descargando ${sectorLabel}...`;
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

            // If camera teleported far away while downloading, discard early to avoid GPU upload thrashing
            const posBase = MEM_POS_PTR >> 2;
            const curCamX = f32Mem[posBase + 0];
            const curCamZ = f32Mem[posBase + 2];
            const macroSize = (manifestInfo && manifestInfo.manifest && manifestInfo.manifest.macro_size) || 1024.0;
            const sectorCenterX = (entry.mx + 0.5) * macroSize;
            const sectorCenterZ = (entry.mz + 0.5) * macroSize;
            if (Math.hypot(sectorCenterX - curCamX, sectorCenterZ - curCamZ) > STREAM_UNLOAD_RADIUS) {
                return;
            }

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

            const cx = (entry.mx + 0.5) * macroSize;
            const cz = (entry.mz + 0.5) * macroSize;
            sectorCache.set(key, {
                entry,
                aabbData,
                chunkCount: chunks.length,
                cx,
                cz,
                lastUsed: performance.now(),
            });
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
            cx: 512.0,
            cz: 512.0,
            lastUsed: performance.now(),
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

    function toggleTimeFreeze() {
        state.timeFrozen = !state.timeFrozen;
        showToast(state.timeFrozen ? 'Avance solar: CONGELADO' : 'Avance solar: ACTIVO');
    }

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
        } else if (e.code === 'KeyB') {
            state.renderMode = (state.renderMode === 'buildings') ? 'all' : 'buildings';
            showToast(state.renderMode === 'buildings'
                ? 'Pipeline Edificios: Solo Edificios (WebGPU)'
                : 'Pipeline Edificios: Escena Completa (Terreno + Edificios)');
        } else if (e.code === 'KeyT') {
            state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
            state.simHour = TIME_PRESETS[state.presetIdx].hour;
            showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
        } else if (e.code === 'KeyY') {
            toggleTimeFreeze();
        } else if (e.code === 'KeyR') {
            resetCamera();
        } else if (e.code === 'Digit3' || e.code === 'Numpad3') {
            teleportTercerAnillo();
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
    document.getElementById('btn-tercer-anillo')?.addEventListener('click', teleportTercerAnillo);
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

    document.getElementById('pause-teleport-tercer-anillo')?.addEventListener('click', () => {
        teleportTercerAnillo();
        logPause('🛣️ Teleport a Tercer Anillo (Av. Siglo XXI)');
        togglePause(false);
    });

    document.getElementById('pause-switch-backend')?.addEventListener('click', () => {
        const next = isWebGPU ? 'webgl2' : 'webgpu';
        const url = new URL(window.location.href);
        url.searchParams.set('backend', next);
        window.location.href = url.toString();
    });

    document.getElementById('btn-time')?.addEventListener('click', () => {
        state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
        state.simHour = TIME_PRESETS[state.presetIdx].hour;
        showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
    });
    document.getElementById('btn-freeze')?.addEventListener('click', toggleTimeFreeze);
    document.getElementById('btn-flash')?.addEventListener('click', () => {
        state.flashlightOn = !state.flashlightOn;
        showToast(state.flashlightOn ? 'Linterna: ON' : 'Linterna: OFF');
    });
    document.getElementById('btn-cull')?.addEventListener('click', () => {
        state.cullingEnabled = !state.cullingEnabled;
        showToast(state.cullingEnabled ? 'Culling WASM: ON' : 'Culling WASM: OFF');
    });
    document.getElementById('btn-buildings')?.addEventListener('click', () => {
        state.renderMode = (state.renderMode === 'buildings') ? 'all' : 'buildings';
        showToast(state.renderMode === 'buildings'
            ? 'Pipeline Edificios: Solo Edificios (WebGPU)'
            : 'Pipeline Edificios: Escena Completa (Terreno + Edificios)');
    });
    document.getElementById('pause-toggle-buildings')?.addEventListener('click', () => {
        state.renderMode = (state.renderMode === 'buildings') ? 'all' : 'buildings';
        logPause(`🏢 Modo Render: ${state.renderMode === 'buildings' ? 'Solo Edificios (WebGPU Pipeline)' : 'Escena Completa'}`);
    });

    // 7. Frame Loop
    const uniformData = new Float32Array(2272 / 4); // 568 floats
    const identityModel = new Float32Array([
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1,
    ]);

    let lastTimestamp = performance.now();
    let fpsAccum = 0;
    let fpsFrames = 0;
    let currentFps = 60.0;
    let avgFrameMs = 16.6;
    let avgCpuMs = 0.5;
    let streamCheckTimer = 0;

    // LRU Streaming Buffer Configuration
    // Keeps active macro-sectors in GPU memory while strictly bounding RAM to prevent
    // out-of-memory crashes on Firefox WebGL2 and Chrome WebGPU.
    const MAX_ACTIVE_SECTORS = 6;
    const STREAM_LOAD_RADIUS = 2400.0;
    const STREAM_UNLOAD_RADIUS = 3800.0;
    const MAX_CONCURRENT_STREAM_LOADS = 2;

    function maybeStreamNearbySectors(camX, camZ) {
        if (!manifestInfo || !manifestInfo.manifest || !Array.isArray(manifestInfo.manifest.sectors)) return;
        const allSectors = manifestInfo.manifest.sectors;
        if (allSectors.length <= 1) return;

        const macroSize = manifestInfo.manifest.macro_size || 1024.0;

        // 1. Unload distant sectors exceeding STREAM_UNLOAD_RADIUS (preserving at least 1 sector)
        for (const [key, secMeta] of sectorCache.entries()) {
            if (sectorCache.size <= 1) break;
            const d = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
            if (d > STREAM_UNLOAD_RADIUS) {
                unloadSectorEntry(key);
            }
        }

        // 2. If cache is full, evict LRU sectors (farthest & least recently used, keeping closest to camera)
        while (sectorCache.size + loadingSectors.size >= MAX_ACTIVE_SECTORS && sectorCache.size > 1) {
            let lruKey = null;
            let oldestTime = Infinity;
            let maxDist = -Infinity;

            // Find closest sector to never evict the sector the camera is standing in
            let closestKey = null;
            let closestDist = Infinity;
            for (const [key, secMeta] of sectorCache.entries()) {
                const d = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
                if (d < closestDist) {
                    closestDist = d;
                    closestKey = key;
                }
            }

            for (const [key, secMeta] of sectorCache.entries()) {
                if (key === closestKey) continue;
                const d = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
                const t = secMeta.lastUsed || 0;
                if (t < oldestTime || (t === oldestTime && d > maxDist)) {
                    oldestTime = t;
                    maxDist = d;
                    lruKey = key;
                }
            }

            if (lruKey) {
                unloadSectorEntry(lruKey);
            } else {
                break;
            }
        }

        // 3. Discover nearby sectors within STREAM_LOAD_RADIUS
        if (loadingSectors.size >= MAX_CONCURRENT_STREAM_LOADS) return;

        const candidates = [];
        for (const s of allSectors) {
            const key = `${s.mx}_${s.mz}`;
            if (sectorCache.has(key) || loadingSectors.has(key) || missingSectors.has(key)) continue;
            if ((s.vert_count || 0) < 10) continue;

            const cx = (s.mx + 0.5) * macroSize;
            const cz = (s.mz + 0.5) * macroSize;
            const d = Math.hypot(cx - camX, cz - camZ);
            if (d <= STREAM_LOAD_RADIUS) {
                candidates.push({ sector: s, dist: d, key });
            }
        }

        if (candidates.length === 0) return;

        // Sort candidates so the nearest macro-sector is requested first
        candidates.sort((a, b) => a.dist - b.dist);

        const availableSlots = Math.min(
            MAX_CONCURRENT_STREAM_LOADS - loadingSectors.size,
            MAX_ACTIVE_SECTORS - sectorCache.size
        );
        if (availableSlots <= 0) return;

        for (let i = 0; i < availableSlots && i < candidates.length; i++) {
            const cand = candidates[i];
            loadSectorEntry(cand.sector, manifestInfo.basePrefix, false).catch((err) => {
                console.warn(`[Streamer] Falló streaming sector ${cand.key}:`, err.message);
            });
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

        const posBase = MEM_POS_PTR >> 2;
        const camX = f32Mem[posBase + 0];
        const camY = f32Mem[posBase + 1];
        const camZ = f32Mem[posBase + 2];
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

            // Update LRU access recency if camera is close to this sector
            const dCam = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
            if (dCam < STREAM_LOAD_RADIUS) {
                secMeta.lastUsed = now;
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
            renderMode: state.renderMode || 'all',
            cars: state.carsEnabled ? { ptr: MEM_CARS_PTR, count: state.carCount, memory: f32Mem } : null,
        });

        // Background nearby sector streaming check every 0.5s
        streamCheckTimer += dt;
        if (streamCheckTimer >= 0.5) {
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
                elTime.textContent = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')} (${phaseLabel})${state.timeFrozen ? ' [Fijo]' : ''}`;
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
