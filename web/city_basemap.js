// ============================================================================
// StreetVulkan City Basemap (low-detail Aguascalientes map)
// Builds per-macro-sector (1024 m) meshes of the whole city from data that
// ships with the web bundle:
//   - models/city_basemap.bin  (CBM1 heightfield, tools/build_city_basemap.py)
//   - models/road_network.bin  (RGP1 road polylines, web/traffic_sim.js parser)
//   - models/city_buildings.bin (CBB1 Overture footprints, tools/build_city_buildings.py)
// Cells covered by a full-detail GLB sector are not drawn, so the basemap only
// fills the rest of the city (Primer / Tercer Anillo, etc.).
// Meshes use the engine material IDs: 0.0 terrain, 0.95 street, 0.35 roof, 1.0 atlas facade.
// ============================================================================

export const BASEMAP_MACRO_SIZE = 1024.0;
const TERRAIN_COLOR = [0.36, 0.33, 0.25, 0.0];
const STREET_COLOR = [0.22, 0.22, 0.24, 0.95];
const ARTERIAL_COLOR = [0.26, 0.26, 0.28, 0.95];
const ROAD_LIFT = 0.25;          // keep ribbons above the coarse 64 m terrain
const BRIDGE_MIN_CLEARANCE = 2.0; // overpasses higher than this get embankment walls
const BRIDGE_WALL_COLOR = [0.58, 0.57, 0.54, 0.95];
const TERRAIN_CLEARANCE = 0.12;  // road_network.bin points are terrain + 0.12 m

// Facade atlas tiles (tools/procedural_props.py CATEGORY_TILES, 8x8 atlas) per CBB1 class:
// residencial, comercial, escuela, templo, hospital, oficina/gobierno, industrial
const FACADE_TILES = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0]];
const WALL_COLORS = [
    [0.80, 0.76, 0.70], [0.75, 0.72, 0.68], [0.82, 0.75, 0.45], [0.88, 0.82, 0.72],
    [0.70, 0.78, 0.85], [0.78, 0.68, 0.58], [0.70, 0.72, 0.75],
];
const ROOF_COLOR = [0.62, 0.60, 0.57, 0.35];
const ATLAS_TILE = 0.125;
const ATLAS_INSET = 0.004;
const CBB_QUANT = 32.0;
const CBB_MARGIN = 512.0;

export function parseCityBuildings(arrayBuffer) {
    const dv = new DataView(arrayBuffer);
    if (arrayBuffer.byteLength < 16) throw new Error('city_buildings.bin too small');
    const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
    if (magic !== 'CBB1') throw new Error(`Invalid buildings magic: ${magic}`);
    const cellCount = dv.getUint32(4, true);
    const buildingCount = dv.getUint32(8, true);
    const pointCount = dv.getUint32(12, true);
    const cellsOff = 16;
    const bldOff = cellsOff + cellCount * 16;
    const ptsOff = bldOff + buildingCount * 4;
    if (arrayBuffer.byteLength < ptsOff + pointCount * 4) throw new Error('city_buildings.bin truncated');
    const cells = new Map();
    for (let i = 0; i < cellCount; i++) {
        const o = cellsOff + i * 16;
        const mx = dv.getInt16(o, true);
        const mz = dv.getInt16(o + 2, true);
        cells.set(`${mx}_${mz}`, {
            mx, mz,
            firstBuilding: dv.getUint32(o + 4, true),
            count: dv.getUint32(o + 8, true),
            firstPoint: dv.getUint32(o + 12, true),
        });
    }
    const meta = new Uint8Array(arrayBuffer.slice(bldOff, bldOff + buildingCount * 4));
    const points = new Uint16Array(arrayBuffer.slice(ptsOff, ptsOff + pointCount * 4));
    return { cells, meta, points, buildingCount, pointCount };
}

// Ear clipping for small CCW polygons (n <= 24) given as flat [x0, z0, x1, z1, ...]
function triangulatePolygon(xz, n, out, base) {
    const idx = [];
    for (let i = 0; i < n; i++) idx.push(i);
    const cross = (a, b, c) => (xz[b * 2] - xz[a * 2]) * (xz[c * 2 + 1] - xz[a * 2 + 1]) -
                               (xz[b * 2 + 1] - xz[a * 2 + 1]) * (xz[c * 2] - xz[a * 2]);
    const inside = (p, a, b, c) => cross(a, b, p) >= 0 && cross(b, c, p) >= 0 && cross(c, a, p) >= 0;
    let guard = n * n;
    while (idx.length > 3 && guard-- > 0) {
        let clipped = false;
        for (let i = 0; i < idx.length; i++) {
            const a = idx[(i + idx.length - 1) % idx.length];
            const b = idx[i];
            const c = idx[(i + 1) % idx.length];
            if (cross(a, b, c) <= 1e-9) continue; // reflex or degenerate
            let ear = true;
            for (const p of idx) {
                if (p !== a && p !== b && p !== c && inside(p, a, b, c)) { ear = false; break; }
            }
            if (!ear) continue;
            out.push(base + a, base + b, base + c);
            idx.splice(i, 1);
            clipped = true;
            break;
        }
        if (!clipped) break; // self-intersecting footprint: fan the rest
    }
    for (let i = 1; i + 1 < idx.length; i++) out.push(base + idx[0], base + idx[i], base + idx[i + 1]);
}

function addBuildings(mb, bm, buildings, cellKey) {
    const cell = buildings.cells.get(cellKey);
    if (!cell) return 0;
    const ox = cell.mx * BASEMAP_MACRO_SIZE - CBB_MARGIN;
    const oz = cell.mz * BASEMAP_MACRO_SIZE - CBB_MARGIN;
    const xz = new Float64Array(64);
    let pIdx = cell.firstPoint;
    for (let b = cell.firstBuilding; b < cell.firstBuilding + cell.count; b++) {
        const n = buildings.meta[b * 4];
        const cls = Math.min(buildings.meta[b * 4 + 1], FACADE_TILES.length - 1);
        const height = (buildings.meta[b * 4 + 2] | (buildings.meta[b * 4 + 3] << 8)) / 10.0;
        let minT = Infinity;
        let maxT = -Infinity;
        for (let i = 0; i < n; i++) {
            const x = ox + buildings.points[(pIdx + i) * 2] / CBB_QUANT;
            const z = oz + buildings.points[(pIdx + i) * 2 + 1] / CBB_QUANT;
            xz[i * 2] = x;
            xz[i * 2 + 1] = z;
            const t = basemapHeightAt(bm, x, z);
            if (t < minT) minT = t;
            if (t > maxT) maxT = t;
        }
        pIdx += n;
        const y0 = minT - 0.5;
        const y1 = maxT + height;
        const [tu, tv] = FACADE_TILES[cls];
        const u0 = tu * ATLAS_TILE + ATLAS_INSET;
        const u1 = (tu + 1) * ATLAS_TILE - ATLAS_INSET;
        const vTop = tv * ATLAS_TILE + ATLAS_INSET;
        const vBottom = (tv + 1) * ATLAS_TILE - ATLAS_INSET;
        const wc = WALL_COLORS[cls];
        const wallColor = [wc[0], wc[1], wc[2], 1.0];

        // Walls: outward normal of a CCW (x, z) ring is (dz, -dx)
        for (let i = 0; i < n; i++) {
            const j = (i + 1) % n;
            const ax = xz[i * 2], az = xz[i * 2 + 1];
            const bx = xz[j * 2], bz = xz[j * 2 + 1];
            const len = Math.hypot(bx - ax, bz - az);
            if (len < 1e-3) continue;
            const nx = (bz - az) / len;
            const nz = -(bx - ax) / len;
            const w0 = mb.vertexUV(ax, y0, az, nx, 0, nz, u0, vBottom, wallColor);
            const w1 = mb.vertexUV(bx, y0, bz, nx, 0, nz, u1, vBottom, wallColor);
            const w2 = mb.vertexUV(bx, y1, bz, nx, 0, nz, u1, vTop, wallColor);
            const w3 = mb.vertexUV(ax, y1, az, nx, 0, nz, u0, vTop, wallColor);
            mb.idx.push(w0, w1, w2, w0, w2, w3);
        }

        // Flat roof
        const roofBase = mb.pos.length / 3;
        for (let i = 0; i < n; i++) mb.vertex(xz[i * 2], y1, xz[i * 2 + 1], 0, 1, 0, ROOF_COLOR);
        triangulatePolygon(xz, n, mb.idx, roofBase);
    }
    return cell.count;
}

export function parseCityBasemap(arrayBuffer) {
    const dv = new DataView(arrayBuffer);
    if (arrayBuffer.byteLength < 32) throw new Error('city_basemap.bin too small');
    const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
    if (magic !== 'CBM1') throw new Error(`Invalid basemap magic: ${magic}`);
    const cols = dv.getUint32(4, true);
    const rows = dv.getUint32(8, true);
    const x0 = dv.getFloat32(12, true);
    const z0 = dv.getFloat32(16, true);
    const spacing = dv.getFloat32(20, true);
    if (arrayBuffer.byteLength < 32 + cols * rows * 4) throw new Error('city_basemap.bin truncated');
    const heights = new Float32Array(arrayBuffer.slice(32, 32 + cols * rows * 4));
    return {
        cols, rows, x0, z0, spacing, heights,
        minH: dv.getFloat32(24, true),
        maxH: dv.getFloat32(28, true),
        x1: x0 + (cols - 1) * spacing,
        z1: z0 + (rows - 1) * spacing,
    };
}

export function basemapHeightAt(bm, x, z) {
    const u = Math.max(0, Math.min(bm.cols - 1.001, (x - bm.x0) / bm.spacing));
    const v = Math.max(0, Math.min(bm.rows - 1.001, (z - bm.z0) / bm.spacing));
    const i = Math.floor(u);
    const j = Math.floor(v);
    const du = u - i;
    const dv = v - j;
    const h = bm.heights;
    const r0 = j * bm.cols + i;
    const r1 = r0 + bm.cols;
    const h0 = h[r0] * (1 - du) + h[r0 + 1] * du;
    const h1 = h[r1] * (1 - du) + h[r1 + 1] * du;
    return h0 * (1 - dv) + h1 * dv;
}

// Road surface height over the basemap: the road polyline height, but never
// buried under the coarse terrain (which smooths valleys and river channels).
export function basemapRoadHeight(bm, x, roadY, z) {
    return Math.max(roadY, basemapHeightAt(bm, x, z) + TERRAIN_CLEARANCE) + ROAD_LIFT;
}

class MeshBuilder {
    constructor() {
        this.pos = [];
        this.norm = [];
        this.uv = [];
        this.col = [];
        this.idx = [];
        this.minY = Infinity;
        this.maxY = -Infinity;
    }

    vertex(x, y, z, nx, ny, nz, color) {
        return this.vertexUV(x, y, z, nx, ny, nz, (x / BASEMAP_MACRO_SIZE) % 1, (z / BASEMAP_MACRO_SIZE) % 1, color);
    }

    vertexUV(x, y, z, nx, ny, nz, u, v, color) {
        this.pos.push(x, y, z);
        this.norm.push(nx, ny, nz);
        this.uv.push(u, v);
        this.col.push(color[0], color[1], color[2], color[3]);
        if (y < this.minY) this.minY = y;
        if (y > this.maxY) this.maxY = y;
        return this.pos.length / 3 - 1;
    }

    toMeshData() {
        const vertexCount = this.pos.length / 3;
        const useUint32 = vertexCount > 65535;
        return {
            pos: new Float32Array(this.pos),
            norm: new Float32Array(this.norm),
            uv: new Float32Array(this.uv),
            col: new Float32Array(this.col),
            em: new Float32Array(vertexCount),
            indices: useUint32 ? new Uint32Array(this.idx) : new Uint16Array(this.idx),
            indexFormat: useUint32 ? 'uint32' : 'uint16',
            vertexCount,
            indexCount: this.idx.length,
        };
    }
}

function addTerrain(mb, bm, cellX0, cellZ0) {
    const n = Math.round(BASEMAP_MACRO_SIZE / bm.spacing);
    const s = bm.spacing;
    const base = mb.pos.length / 3;
    for (let r = 0; r <= n; r++) {
        for (let c = 0; c <= n; c++) {
            const x = cellX0 + c * s;
            const z = cellZ0 + r * s;
            const y = basemapHeightAt(bm, x, z);
            const dx = basemapHeightAt(bm, x + s, z) - basemapHeightAt(bm, x - s, z);
            const dz = basemapHeightAt(bm, x, z + s) - basemapHeightAt(bm, x, z - s);
            const nx = -dx;
            const ny = 2 * s;
            const nz = -dz;
            const inv = 1 / Math.hypot(nx, ny, nz);
            mb.vertex(x, y, z, nx * inv, ny * inv, nz * inv, TERRAIN_COLOR);
        }
    }
    for (let r = 0; r < n; r++) {
        for (let c = 0; c < n; c++) {
            const a = base + r * (n + 1) + c;
            const b = a + 1;
            const d = a + (n + 1);
            const e = d + 1;
            mb.idx.push(a, d, b, b, d, e);
        }
    }
}

function addRoadSegment(mb, bm, ax, ay, az, bx, by, bz, halfWidth, color) {
    const dx = bx - ax;
    const dz = bz - az;
    const len = Math.hypot(dx, dz);
    if (len < 0.05) return;
    const fx = dx / len;
    const fz = dz / len;
    // Extend each segment by half the width to close gaps at polyline bends
    const ext = Math.min(halfWidth, len * 0.5);
    const sx = ax - fx * ext;
    const sz = az - fz * ext;
    const ex = bx + fx * ext;
    const ez = bz + fz * ext;
    const ya = basemapRoadHeight(bm, ax, ay, az);
    const yb = basemapRoadHeight(bm, bx, by, bz);
    const px = -fz * halfWidth;
    const pz = fx * halfWidth;
    const i0 = mb.vertex(sx + px, ya, sz + pz, 0, 1, 0, color);
    const i1 = mb.vertex(sx - px, ya, sz - pz, 0, 1, 0, color);
    const i2 = mb.vertex(ex + px, yb, ez + pz, 0, 1, 0, color);
    const i3 = mb.vertex(ex - px, yb, ez - pz, 0, 1, 0, color);
    mb.idx.push(i0, i1, i2, i2, i1, i3);

    // Overpasses (pasos a desnivel): close the deck down to the terrain so it does not float
    const ta = basemapHeightAt(bm, ax, az);
    const tb = basemapHeightAt(bm, bx, bz);
    if (ya - ta > BRIDGE_MIN_CLEARANCE || yb - tb > BRIDGE_MIN_CLEARANCE) {
        for (const side of [1, -1]) {
            const ox = px * side;
            const oz = pz * side;
            const nx = -fz * side;
            const nz = fx * side;
            const w0 = mb.vertex(sx + ox, ya, sz + oz, nx, 0, nz, BRIDGE_WALL_COLOR);
            const w1 = mb.vertex(ex + ox, yb, ez + oz, nx, 0, nz, BRIDGE_WALL_COLOR);
            const w2 = mb.vertex(sx + ox, ta - 0.5, sz + oz, nx, 0, nz, BRIDGE_WALL_COLOR);
            const w3 = mb.vertex(ex + ox, tb - 0.5, ez + oz, nx, 0, nz, BRIDGE_WALL_COLOR);
            mb.idx.push(w0, w2, w1, w1, w2, w3);
        }
    }
}

// Assigns every road polyline segment to the macro cell containing its midpoint.
export function bucketRoadSegments(graph) {
    const buckets = new Map();
    const pts = graph.points;
    for (let e = 0; e < graph.nEdges; e++) {
        if (!graph.edgeValid[e]) continue;
        const po = graph.edgePtOff[e];
        const pc = graph.edgePtCount[e];
        for (let k = 0; k < pc - 1; k++) {
            const a = (po + k) * 3;
            const mx = Math.floor((pts[a] + pts[a + 3]) * 0.5 / BASEMAP_MACRO_SIZE);
            const mz = Math.floor((pts[a + 2] + pts[a + 5]) * 0.5 / BASEMAP_MACRO_SIZE);
            const key = `${mx}_${mz}`;
            let list = buckets.get(key);
            if (!list) {
                list = [];
                buckets.set(key, list);
            }
            list.push(e, a);
        }
    }
    return buckets;
}

// Builds the mesh of one macro cell. Returns { meshData, chunks, buildingCount } in the
// same shape the renderers' uploadSector() accepts, or null if the cell is outside the map.
// `buildings` (parseCityBuildings) is optional: pass null to build terrain + roads only.
export function buildBasemapCell(bm, graph, roadBuckets, mx, mz, buildings = null) {
    const cellX0 = mx * BASEMAP_MACRO_SIZE;
    const cellZ0 = mz * BASEMAP_MACRO_SIZE;
    if (cellX0 < bm.x0 - 1 || cellZ0 < bm.z0 - 1 ||
        cellX0 + BASEMAP_MACRO_SIZE > bm.x1 + 1 || cellZ0 + BASEMAP_MACRO_SIZE > bm.z1 + 1) {
        return null;
    }
    const mb = new MeshBuilder();
    addTerrain(mb, bm, cellX0, cellZ0);

    const segs = graph && roadBuckets ? roadBuckets.get(`${mx}_${mz}`) : null;
    if (segs) {
        const pts = graph.points;
        for (let i = 0; i < segs.length; i += 2) {
            const e = segs[i];
            const a = segs[i + 1];
            const lanes = graph.edgeLanesFwd[e] + graph.edgeLanesRev[e];
            const width = graph.edgeWidth[e] > 0 ? graph.edgeWidth[e] : Math.max(1, lanes) * 3.2;
            const color = lanes >= 3 ? ARTERIAL_COLOR : STREET_COLOR;
            addRoadSegment(mb, bm, pts[a], pts[a + 1], pts[a + 2], pts[a + 3], pts[a + 4], pts[a + 5], width * 0.5, color);
        }
    }

    const buildingCount = buildings ? addBuildings(mb, bm, buildings, `${mx}_${mz}`) : 0;

    const meshData = mb.toMeshData();
    const chunks = [{
        cx: mx, cz: mz, start: 0, count: meshData.indexCount,
        min_x: cellX0 - 16, min_y: mb.minY - 1, min_z: cellZ0 - 16,
        max_x: cellX0 + BASEMAP_MACRO_SIZE + 16, max_y: mb.maxY + 1, max_z: cellZ0 + BASEMAP_MACRO_SIZE + 16,
    }];
    return { meshData, chunks, buildingCount };
}

export function basemapCellKeys(bm) {
    const keys = [];
    const mx0 = Math.ceil(bm.x0 / BASEMAP_MACRO_SIZE);
    const mz0 = Math.ceil(bm.z0 / BASEMAP_MACRO_SIZE);
    const mx1 = Math.floor(bm.x1 / BASEMAP_MACRO_SIZE);
    const mz1 = Math.floor(bm.z1 / BASEMAP_MACRO_SIZE);
    for (let mz = mz0; mz < mz1; mz++) {
        for (let mx = mx0; mx < mx1; mx++) keys.push([mx, mz]);
    }
    return keys;
}
