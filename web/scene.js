// ============================================================================
// scene.js — Sol/cielo, texturas, vehículos y fetch con progreso
// Funciones puras o de I/O que no guardan estado propio.
// ============================================================================

import { clamp, linearToSrgbChannel } from './wasm-core.js';
import { parseGLB } from './glb-parser.js';
import { buildFallbackVehicleMesh } from './glb-builder.js';

// ----------------------------------------------------------------------------
// Texturas procedurales fallback (coinciden con src/vulkan_texture.c)
// ----------------------------------------------------------------------------
export function generateFallbackFacadeRGBA() {
    const W = 256, H = 256;
    const data = new Uint8Array(W * H * 4);
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const brickW = 32, brickH = 16;
            const by = Math.floor(y / brickH), bx = Math.floor(x / brickW);
            const mortar = (y % brickH < 2) || (x % brickW < 2 && (by % 2 === 0 || x % brickW >= 16));
            let r, g, b;
            if (mortar) {
                r = 180; g = 180; b = 175;
            } else {
                const v = (bx * 17 + by * 31) % 20;
                if ((bx + by) % 2 === 0) { r = 190 + v; g = 165 + (v >> 1); b = 140 + (v >> 1); }
                else                      { r = 185 + v; g = 150 + (v >> 1); b = 120 + (v >> 1); }
            }
            const idx = (y * W + x) * 4;
            data[idx] = r; data[idx + 1] = g; data[idx + 2] = b; data[idx + 3] = 255;
        }
    }
    return { width: W, height: H, data };
}

export function generateFallbackSatelliteRGBA() {
    const W = 64, H = 64;
    const data = new Uint8Array(W * H * 4);
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const n = (((x * 73856093) ^ (y * 19349663)) & 15) - 7;
            const idx = (y * W + x) * 4;
            data[idx]     = clamp(120 + n, 0, 255);
            data[idx + 1] = clamp(125 + n, 0, 255);
            data[idx + 2] = clamp(115 + n, 0, 255);
            data[idx + 3] = 255;
        }
    }
    return { width: W, height: H, data };
}

export async function loadTextureAtlasWithFallback() {
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
            const bmp  = await createImageBitmap(blob);
            const off  = document.createElement('canvas');
            off.width  = bmp.width;
            off.height = bmp.height;
            const ctx  = off.getContext('2d');
            ctx.drawImage(bmp, 0, 0);
            const imgData = ctx.getImageData(0, 0, bmp.width, bmp.height);
            bmp.close?.();
            return { width: imgData.width, height: imgData.height,
                     data: new Uint8Array(imgData.data.buffer), source: url };
        } catch (_err) {
            // Intentar siguiente candidato
        }
    }
    return { ...generateFallbackFacadeRGBA(), source: 'procedural-fallback' };
}

// ----------------------------------------------------------------------------
// Carga del modelo de vehículo con fallback procedural
// ----------------------------------------------------------------------------
export async function loadVehicleModelWithFallback(basePrefix) {
    try {
        const resp = await fetch(`${basePrefix}models/cars/car_sedan.glb`);
        if (resp.ok) {
            const buf    = await resp.arrayBuffer();
            const parsed = parseGLB(buf);
            if (parsed && parsed.vertexCount > 0) return parsed;
        }
    } catch (_err) {
        // Usar fallback procedural
    }
    return buildFallbackVehicleMesh();
}

// ----------------------------------------------------------------------------
// Fetch con callback de progreso (para barra de carga del sector)
// ----------------------------------------------------------------------------
export async function fetchArrayBufferWithProgress(url, onProgress) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status} para ${url}`);

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
    for (const c of chunks) { combined.set(c, pos); pos += c.byteLength; }
    return combined.buffer;
}

// ----------------------------------------------------------------------------
// Sol, cielo e iluminación (espeja src/vulkan.c + include/lighting_system.h)
// ----------------------------------------------------------------------------
export function computeSunAndSky(simHour) {
    const sunAngle = ((simHour - 6.0) / 24.0) * 2.0 * Math.PI;
    const sunY = Math.sin(sunAngle);
    const sunX = Math.cos(sunAngle);

    const sunDir = [sunX, sunY > 0.05 ? sunY : 0.05, 0.35, 0.16 + 0.22 * Math.max(0.0, sunY)];
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
        skyColor:   [skyR, skyG, skyB, nightFactor],
        clearColor: [
            linearToSrgbChannel(skyR),
            linearToSrgbChannel(skyG),
            linearToSrgbChannel(skyB),
        ],
    };
}

// ----------------------------------------------------------------------------
// Carga opcional de señales de tráfico (JSONL, falla silenciosamente)
// ----------------------------------------------------------------------------
export async function loadOptionalTrafficSignals() {
    const candidates = [
        '../models/traffic_signals.json',
        './models/traffic_signals.json',
        './traffic_signals.json',
    ];
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
            // Archivo opcional — continuar
        }
    }
    return [];
}
