/**
 * sector-manager.js — Sector manifest resolution, GLB streaming, LRU cache management.
 *
 * Responsible for:
 *  - Resolving the sector manifest from multiple candidate URLs
 *  - Fetching chunk metadata for each sector
 *  - SectorManager class: load/unload sectors with LRU eviction + proximity streaming
 *
 * Never imports from camera-input.js or hud.js (no circular deps).
 */

import { parseGLB } from './glb-parser.js';
import { buildStandaloneFallbackSector } from './glb-builder.js';
import { fetchArrayBufferWithProgress } from './scene.js';
import { MEM_POS_PTR } from './wasm-core.js';

// ---------------------------------------------------------------------------
// Streaming Configuration
// ---------------------------------------------------------------------------
export const MAX_ACTIVE_SECTORS       = 6;
export const STREAM_LOAD_RADIUS       = 2400.0;
export const STREAM_UNLOAD_RADIUS     = 3800.0;
export const MAX_CONCURRENT_STREAM_LOADS = 2;

// ---------------------------------------------------------------------------
// resolveSectorManifest()
// ---------------------------------------------------------------------------
export async function resolveSectorManifest() {
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

// ---------------------------------------------------------------------------
// fetchChunksForSector(sectorEntry, basePrefix)
// ---------------------------------------------------------------------------
export async function fetchChunksForSector(sectorEntry, basePrefix) {
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

// ---------------------------------------------------------------------------
// SectorManager class
// ---------------------------------------------------------------------------
export class SectorManager {
    /**
     * @param {object} renderer        — WebGPU or WebGL2 renderer instance
     * @param {Float32Array} f32Mem    — WASM linear memory view (Float32)
     * @param {object} loaderEls       — { loaderTextEl, loaderBarEl }
     * @param {object} backendInfo     — { backend: string }
     */
    constructor(renderer, f32Mem, loaderEls, backendInfo) {
        this._renderer   = renderer;
        this._f32Mem     = f32Mem;
        this._loaderTextEl = loaderEls.loaderTextEl;
        this._loaderBarEl  = loaderEls.loaderBarEl;
        this._backendName  = backendInfo.backend;

        /** @type {Map<string, {entry, aabbData, chunkCount, cx, cz, lastUsed}>} */
        this.sectorCache       = new Map();
        /** @type {Map<string, Uint8Array>} */
        this.cullFlagsBySector = new Map();
        /** @type {Set<string>} */
        this._loadingSectors   = new Set();
        /** @type {Set<string>} */
        this._missingSectors   = new Set();
        /** @type {object|null} */
        this.manifestInfo      = null;
    }

    /** Store the resolved manifest so streaming can find candidate sectors. */
    setManifest(manifestInfo) {
        this.manifestInfo = manifestInfo;
    }

    // -----------------------------------------------------------------------
    // unloadSector(key)
    // -----------------------------------------------------------------------
    unloadSector(key) {
        const secMeta = this.sectorCache.get(key);
        if (!secMeta) return;
        this._renderer.unloadSector(key);
        this.sectorCache.delete(key);
        this.cullFlagsBySector.delete(key);
    }

    // -----------------------------------------------------------------------
    // async loadSector(entry, basePrefix, showLoader)
    // -----------------------------------------------------------------------
    async loadSector(entry, basePrefix, showLoader) {
        const key = `${entry.mx}_${entry.mz}`;
        if (this.sectorCache.has(key) || this._loadingSectors.has(key) || this._missingSectors.has(key)) return;
        this._loadingSectors.add(key);

        try {
            let glbUrl = entry.file.startsWith('..') || entry.file.startsWith('./')
                ? entry.file
                : `${basePrefix}${entry.file}`;

            // Safety check: if file path is an absolute /tmp path or non-relative, resolve cleanly
            if (glbUrl.includes('/tmp/') || glbUrl.startsWith('/')) {
                glbUrl = `${basePrefix}models/sectors/sector_${entry.mx}_${entry.mz}.glb`;
            }

            if (showLoader && this._loaderTextEl) {
                const sectorLabel = (entry.mx === 0 && entry.mz === 0)
                    ? 'Sector (0, 0) Paseo de la Cruz'
                    : `Sector (${entry.mx}, ${entry.mz}) Tercer Anillo Metropolitano`;
                this._loaderTextEl.textContent = `Descargando ${sectorLabel}...`;
            }

            const [arrayBuf, chunks] = await Promise.all([
                fetchArrayBufferWithProgress(glbUrl, (loaded, total) => {
                    if (showLoader && this._loaderBarEl && total > 0) {
                        const pct = Math.round((loaded / total) * 100);
                        this._loaderBarEl.style.width = `${pct}%`;
                        if (this._loaderTextEl) {
                            this._loaderTextEl.textContent = `Descargando sector_${key}.glb: ${(loaded / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB (${pct}%)`;
                        }
                    }
                }),
                fetchChunksForSector(entry, basePrefix),
            ]);

            // If camera teleported far away while downloading, discard early
            const posBase = MEM_POS_PTR >> 2;
            const curCamX = this._f32Mem[posBase + 0];
            const curCamZ = this._f32Mem[posBase + 2];
            const macroSize = (this.manifestInfo && this.manifestInfo.manifest && this.manifestInfo.manifest.macro_size) || 1024.0;
            const sectorCenterX = (entry.mx + 0.5) * macroSize;
            const sectorCenterZ = (entry.mz + 0.5) * macroSize;
            if (Math.hypot(sectorCenterX - curCamX, sectorCenterZ - curCamZ) > STREAM_UNLOAD_RADIUS) {
                return;
            }

            if (showLoader && this._loaderTextEl) {
                this._loaderTextEl.textContent = `Subiendo geometría GLB a ${this._backendName}...`;
            }

            const parsed = parseGLB(arrayBuf);
            this._renderer.uploadSector(key, parsed, chunks);

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
            this.sectorCache.set(key, {
                entry,
                aabbData,
                chunkCount: chunks.length,
                cx,
                cz,
                lastUsed: performance.now(),
            });
        } catch (err) {
            this._missingSectors.add(key);
            throw err;
        } finally {
            this._loadingSectors.delete(key);
        }
    }

    // -----------------------------------------------------------------------
    // loadFallbackSector(showToast)
    // -----------------------------------------------------------------------
    loadFallbackSector(showToast) {
        const fallback = buildStandaloneFallbackSector();
        this._renderer.uploadSector('0_0', fallback.mesh, fallback.chunks);
        const c = fallback.chunks[0];
        this.sectorCache.set('0_0', {
            entry: { mx: 0, mz: 0 },
            aabbData: new Float32Array([c.min_x, c.min_y, c.min_z, c.max_x, c.max_y, c.max_z]),
            chunkCount: 1,
            cx: 512.0,
            cz: 512.0,
            lastUsed: performance.now(),
        });
        showToast('Modo standalone (sin sector_0_0.glb)');
    }

    // -----------------------------------------------------------------------
    // maybeStreamNearby(camX, camZ)
    // -----------------------------------------------------------------------
    maybeStreamNearby(camX, camZ) {
        if (!this.manifestInfo || !this.manifestInfo.manifest || !Array.isArray(this.manifestInfo.manifest.sectors)) return;
        const allSectors = this.manifestInfo.manifest.sectors;
        if (allSectors.length <= 1) return;

        const macroSize = this.manifestInfo.manifest.macro_size || 1024.0;

        // 1. Unload distant sectors exceeding STREAM_UNLOAD_RADIUS (preserving at least 1)
        for (const [key, secMeta] of this.sectorCache.entries()) {
            if (this.sectorCache.size <= 1) break;
            const d = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
            if (d > STREAM_UNLOAD_RADIUS) {
                this.unloadSector(key);
            }
        }

        // 2. If cache is full, evict LRU sectors (farthest & least recently used)
        while (this.sectorCache.size + this._loadingSectors.size >= MAX_ACTIVE_SECTORS && this.sectorCache.size > 1) {
            let lruKey = null;
            let oldestTime = Infinity;
            let maxDist = -Infinity;

            // Find closest sector to never evict the sector the camera is standing in
            let closestKey = null;
            let closestDist = Infinity;
            for (const [key, secMeta] of this.sectorCache.entries()) {
                const d = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
                if (d < closestDist) {
                    closestDist = d;
                    closestKey = key;
                }
            }

            for (const [key, secMeta] of this.sectorCache.entries()) {
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
                this.unloadSector(lruKey);
            } else {
                break;
            }
        }

        // 3. Discover nearby sectors within STREAM_LOAD_RADIUS
        if (this._loadingSectors.size >= MAX_CONCURRENT_STREAM_LOADS) return;

        const candidates = [];
        for (const s of allSectors) {
            const key = `${s.mx}_${s.mz}`;
            if (this.sectorCache.has(key) || this._loadingSectors.has(key) || this._missingSectors.has(key)) continue;
            if ((s.vert_count || 0) < 10) continue;

            const cx = (s.mx + 0.5) * macroSize;
            const cz = (s.mz + 0.5) * macroSize;
            const d = Math.hypot(cx - camX, cz - camZ);
            if (d <= STREAM_LOAD_RADIUS) {
                candidates.push({ sector: s, dist: d, key });
            }
        }

        if (candidates.length === 0) return;

        candidates.sort((a, b) => a.dist - b.dist);

        const availableSlots = Math.min(
            MAX_CONCURRENT_STREAM_LOADS - this._loadingSectors.size,
            MAX_ACTIVE_SECTORS - this.sectorCache.size
        );
        if (availableSlots <= 0) return;

        for (let i = 0; i < availableSlots && i < candidates.length; i++) {
            const cand = candidates[i];
            this.loadSector(cand.sector, this.manifestInfo.basePrefix, false).catch((err) => {
                console.warn(`[Streamer] Falló streaming sector ${cand.key}:`, err.message);
            });
        }
    }
}
