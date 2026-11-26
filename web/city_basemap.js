// ============================================================================
// StreetVulkan City Basemap (low-detail Aguascalientes map)
// Builds per-macro-sector (1024 m) meshes of the whole city from data that
// ships with the web bundle:
//   - models/city_basemap.bin  (CBM1 heightfield, tools/build_city_basemap.py)
//   - models/road_network.bin  (RGP1 road polylines, web/traffic_sim.js parser)
//   - models/city_buildings.bin (CBB1 Overture footprints, tools/build_city_buildings.py)
// Cells covered by a full-detail GLB sector are not drawn, so the basemap only
// fills the rest of the city (Primer / Tercer Anillo, etc.).
// Meshes use the engine material IDs: 0.0 terrain, 0.95 street/sidewalk, 0.35 roof,
// 1.0 atlas facade, 0.6 shadow, 0.7 trunk, 0.8 foliage (same as tools/procedural_props.py).
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
const ROOF_COLOR = [0.76, 0.74, 0.70, 0.35];   // dominant rooftop colour of the GLB sectors

// Street furniture copied from tools/procedural_props.py (make_sidewalk_3d / make_tree_3d)
const SIDEWALK_WIDTH = 1.6;
const CURB_HEIGHT = 0.15;
const SIDEWALK_COLOR = [0.58, 0.56, 0.54, 0.95];
const CURB_COLOR = [0.52, 0.50, 0.48, 0.95];
const INTERSECTION_TRIM = 7.0;   // sidewalks stop this far from a node shared by 3+ edges
const TREE_SPACING = 30.0;
const TREE_BUILDING_CLEARANCE = 2.5;
const SHADOW_COLOR = [0.05, 0.08, 0.05, 0.6];
const TRUNK_COLOR = [0.28, 0.18, 0.11, 0.7];
const LEAF_COLORS = [   // fresno, encino, pirul/olivo, jacaranda
    [0.16, 0.54, 0.18], [0.10, 0.42, 0.15], [0.28, 0.48, 0.16], [0.42, 0.22, 0.58],
];
const BARK_TILE = [6, 1];  // "madera_arbol" in the facade atlas

// Deterministic 0..1 hash so the same street always gets the same trees
function hash01(a, b) {
    let h = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(b + 0x632be5ab, 0xc2b2ae35);
    h ^= h >>> 15;
    h = Math.imul(h, 0x2c1b3c6d);
    h ^= h >>> 12;
    return (h >>> 0) / 4294967296;
}

const ICO = (() => {
    const t = (1 + Math.sqrt(5)) / 2;
    const v = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
               [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]].map(([x, y, z]) => {
        const l = Math.hypot(x, y, z);
        return [x / l, y / l, z / l];
    });
    const f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
               [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
               [8, 6, 7], [9, 8, 1]];
    return { v, f };
})();
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

function addBuildings(mb, bm, buildings, cellKey, footprints) {
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
        if (footprints) footprints.add(xz.slice(0, n * 2));
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

// Spatial grid of building footprints (flat [x0, z0, x1, z1, ...] rings) for tree placement
class FootprintGrid {
    constructor(cell = 16) {
        this.cell = cell;
        this.map = new Map();
    }

    add(ring) {
        let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity;
        for (let i = 0; i < ring.length; i += 2) {
            x0 = Math.min(x0, ring[i]); x1 = Math.max(x1, ring[i]);
            z0 = Math.min(z0, ring[i + 1]); z1 = Math.max(z1, ring[i + 1]);
        }
        const entry = { ring, x0, z0, x1, z1 };
        for (let gx = Math.floor(x0 / this.cell); gx <= Math.floor(x1 / this.cell); gx++) {
            for (let gz = Math.floor(z0 / this.cell); gz <= Math.floor(z1 / this.cell); gz++) {
                const k = gx * 100003 + gz;
                let list = this.map.get(k);
                if (!list) this.map.set(k, (list = []));
                list.push(entry);
            }
        }
    }

    // True if (x, z) is inside a footprint or closer than `margin` to one
    near(x, z, margin) {
        const gx = Math.floor(x / this.cell);
        const gz = Math.floor(z / this.cell);
        for (let dx = -1; dx <= 1; dx++) {
            for (let dz = -1; dz <= 1; dz++) {
                const list = this.map.get((gx + dx) * 100003 + gz + dz);
                if (!list) continue;
                for (const e of list) {
                    if (x < e.x0 - margin || x > e.x1 + margin || z < e.z0 - margin || z > e.z1 + margin) continue;
                    if (pointNearRing(e.ring, x, z, margin)) return true;
                }
            }
        }
        return false;
    }
}

function pointNearRing(ring, x, z, margin) {
    let inside = false;
    const n = ring.length / 2;
    for (let i = 0, j = n - 1; i < n; j = i++) {
        const xi = ring[i * 2], zi = ring[i * 2 + 1], xj = ring[j * 2], zj = ring[j * 2 + 1];
        if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) inside = !inside;
        const ex = xj - xi, ez = zj - zi;
        const l2 = ex * ex + ez * ez;
        const t = l2 > 0 ? Math.max(0, Math.min(1, ((x - xi) * ex + (z - zi) * ez) / l2)) : 0;
        if (Math.hypot(x - (xi + t * ex), z - (zi + t * ez)) < margin) return true;
    }
    return inside;
}

function addSidewalks(mb, ax, az, bx, bz, ya, yb, halfWidth, t0, t1) {
    const dx = bx - ax;
    const dz = bz - az;
    const len = Math.hypot(dx, dz);
    const fx = dx / len;
    const fz = dz / len;
    // Interior joints of a polyline get a short overlap so bends do not open gaps
    const e0 = t0 > 0 ? 0 : -0.6 / len;
    const e1 = t1 < 1 ? 0 : 0.6 / len;
    const sx = ax + dx * (t0 + e0), sz = az + dz * (t0 + e0), sy = ya + (yb - ya) * t0 + CURB_HEIGHT;
    const ex = ax + dx * (t1 + e1), ez = az + dz * (t1 + e1), ey = ya + (yb - ya) * t1 + CURB_HEIGHT;
    for (const side of [1, -1]) {
        const px = -fz * side;
        const pz = fx * side;
        const inner = halfWidth;
        const outer = halfWidth + SIDEWALK_WIDTH;
        const s0 = mb.vertex(sx + px * inner, sy, sz + pz * inner, 0, 1, 0, SIDEWALK_COLOR);
        const s1 = mb.vertex(sx + px * outer, sy, sz + pz * outer, 0, 1, 0, SIDEWALK_COLOR);
        const s2 = mb.vertex(ex + px * inner, ey, ez + pz * inner, 0, 1, 0, SIDEWALK_COLOR);
        const s3 = mb.vertex(ex + px * outer, ey, ez + pz * outer, 0, 1, 0, SIDEWALK_COLOR);
        mb.idx.push(s0, s1, s2, s2, s1, s3);
        // Curb face looking at the roadway
        const c0 = mb.vertex(sx + px * inner, sy, sz + pz * inner, -px, 0, -pz, CURB_COLOR);
        const c1 = mb.vertex(ex + px * inner, ey, ez + pz * inner, -px, 0, -pz, CURB_COLOR);
        const c2 = mb.vertex(sx + px * inner, sy - CURB_HEIGHT - 0.1, sz + pz * inner, -px, 0, -pz, CURB_COLOR);
        const c3 = mb.vertex(ex + px * inner, ey - CURB_HEIGHT - 0.1, ez + pz * inner, -px, 0, -pz, CURB_COLOR);
        mb.idx.push(c0, c2, c1, c1, c2, c3);
    }
}

function addTree(mb, x, gy, z, radius, species, shade) {
    // Shadow disc on the sidewalk (matID 0.6)
    const sr = radius * 1.25;
    const centre = mb.vertex(x, gy + 0.03, z, 0, 1, 0, SHADOW_COLOR);
    const ring = [];
    for (let k = 0; k < 8; k++) {
        const a = k * Math.PI / 4;
        ring.push(mb.vertex(x + sr * Math.cos(a), gy + 0.03, z + sr * Math.sin(a), 0, 1, 0, SHADOW_COLOR));
    }
    for (let k = 0; k < 8; k++) mb.idx.push(centre, ring[k], ring[(k + 1) % 8]);

    // Trunk: square prism with the bark tile of the atlas (matID 0.7)
    const th = 3.5 + shade * 1.2;
    const tr = 0.3;
    const [tu, tv] = BARK_TILE;
    const u0 = tu * ATLAS_TILE + ATLAS_INSET, u1 = (tu + 1) * ATLAS_TILE - ATLAS_INSET;
    const v0 = tv * ATLAS_TILE + ATLAS_INSET, v1 = (tv + 1) * ATLAS_TILE - ATLAS_INSET;
    const corners = [[-tr, -tr], [tr, -tr], [tr, tr], [-tr, tr]];
    for (let k = 0; k < 4; k++) {
        const [ax, az] = corners[k];
        const [bx, bz] = corners[(k + 1) % 4];
        const nx = (bz - az) / (2 * tr), nz = -(bx - ax) / (2 * tr);
        const w0 = mb.vertexUV(x + ax, gy, z + az, nx, 0, nz, u0, v1, TRUNK_COLOR);
        const w1 = mb.vertexUV(x + bx, gy, z + bz, nx, 0, nz, u1, v1, TRUNK_COLOR);
        const w2 = mb.vertexUV(x + bx, gy + th, z + bz, nx, 0, nz, u1, v0, TRUNK_COLOR);
        const w3 = mb.vertexUV(x + ax, gy + th, z + az, nx, 0, nz, u0, v0, TRUNK_COLOR);
        mb.idx.push(w0, w1, w2, w0, w2, w3);
    }

    // Crown: low-poly icosahedron with flat normals (matID 0.8)
    const base = LEAF_COLORS[species];
    const k = 0.9 + shade * 0.2;
    const leaf = [base[0] * k, base[1] * k, base[2] * k, 0.8];
    const cy = gy + th + radius * 0.75;
    for (const [i0, i1, i2] of ICO.f) {
        const a = ICO.v[i0], b = ICO.v[i1], c = ICO.v[i2];
        const nx = a[0] + b[0] + c[0], ny = a[1] + b[1] + c[1], nz = a[2] + b[2] + c[2];
        const nl = Math.hypot(nx, ny, nz);
        for (const p of [a, b, c]) {
            mb.idx.push(mb.vertex(x + p[0] * radius, cy + p[1] * radius * 0.9, z + p[2] * radius,
                nx / nl, ny / nl, nz / nl, leaf));
        }
    }
}

function addRoadSegment(mb, bm, ax, ay, az, bx, by, bz, halfWidth, color, walk = null) {
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
    const isBridge = ya - ta > BRIDGE_MIN_CLEARANCE || yb - tb > BRIDGE_MIN_CLEARANCE;
    if (walk && !isBridge) {
        // Sidewalk span [t0, t1] of this segment, trimmed near intersections
        const t0 = Math.max(0, Math.min(1, (walk.trimA - walk.s0) / len));
        const t1 = Math.max(0, Math.min(1, (walk.edgeLen - walk.trimB - walk.s0) / len));
        if (t1 - t0 > 0.02) addSidewalks(mb, ax, az, bx, bz, ya, yb, halfWidth, t0, t1);
    }
    if (walk) walk.isBridge = isBridge;
    if (isBridge) {
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
// Each entry is (edge, point offset, distance along the edge); the map also carries
// `edgeLen` (2D polyline length per edge) and `nodeDegree` for sidewalk trimming.
export function bucketRoadSegments(graph) {
    const buckets = new Map();
    const pts = graph.points;
    const edgeLen = new Float32Array(graph.nEdges);
    const nodeDegree = new Uint8Array(graph.nNodes);
    for (let e = 0; e < graph.nEdges; e++) {
        if (!graph.edgeValid[e]) continue;
        nodeDegree[graph.edgeA[e]] = Math.min(255, nodeDegree[graph.edgeA[e]] + 1);
        nodeDegree[graph.edgeB[e]] = Math.min(255, nodeDegree[graph.edgeB[e]] + 1);
        const po = graph.edgePtOff[e];
        const pc = graph.edgePtCount[e];
        let s = 0;
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
            list.push(e, a, s);
            s += Math.hypot(pts[a + 3] - pts[a], pts[a + 5] - pts[a + 2]);
        }
        edgeLen[e] = s;
    }
    buckets.edgeLen = edgeLen;
    buckets.nodeDegree = nodeDegree;
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

    // Buildings first: their footprints keep the street trees off the facades
    const footprints = buildings ? new FootprintGrid() : null;
    const buildingCount = buildings ? addBuildings(mb, bm, buildings, `${mx}_${mz}`, footprints) : 0;

    const segs = graph && roadBuckets ? roadBuckets.get(`${mx}_${mz}`) : null;
    if (segs) {
        const pts = graph.points;
        const { edgeLen, nodeDegree } = roadBuckets;
        const walk = { s0: 0, edgeLen: 0, trimA: 0, trimB: 0, isBridge: false };
        for (let i = 0; i < segs.length; i += 3) {
            const e = segs[i];
            const a = segs[i + 1];
            const lanes = graph.edgeLanesFwd[e] + graph.edgeLanesRev[e];
            const width = graph.edgeWidth[e] > 0 ? graph.edgeWidth[e] : Math.max(1, lanes) * 3.2;
            const color = lanes >= 3 ? ARTERIAL_COLOR : STREET_COLOR;
            const halfWidth = width * 0.5;
            walk.s0 = segs[i + 2];
            walk.edgeLen = edgeLen ? edgeLen[e] : Infinity;
            walk.trimA = nodeDegree && nodeDegree[graph.edgeA[e]] >= 3 ? INTERSECTION_TRIM : 0;
            walk.trimB = nodeDegree && nodeDegree[graph.edgeB[e]] >= 3 ? INTERSECTION_TRIM : 0;
            addRoadSegment(mb, bm, pts[a], pts[a + 1], pts[a + 2], pts[a + 3], pts[a + 4], pts[a + 5],
                halfWidth, color, edgeLen ? walk : null);

            // Street trees on the sidewalk, every TREE_SPACING metres along the edge
            if (!footprints || walk.isBridge || !edgeLen) continue;
            const segLen = Math.hypot(pts[a + 3] - pts[a], pts[a + 5] - pts[a + 2]);
            if (segLen < 0.5) continue;
            const phase = hash01(e, 7) * TREE_SPACING;
            const first = Math.ceil((walk.s0 - phase) / TREE_SPACING);
            for (let n = first; phase + n * TREE_SPACING < walk.s0 + segLen; n++) {
                const d = phase + n * TREE_SPACING;
                if (d < walk.trimA + 4 || d > walk.edgeLen - walk.trimB - 4) continue;
                const t = (d - walk.s0) / segLen;
                const fx = (pts[a + 3] - pts[a]) / segLen, fz = (pts[a + 5] - pts[a + 2]) / segLen;
                const side = (n & 1) ? 1 : -1;
                const off = halfWidth + (lanes >= 3 ? 1.8 : 1.4);
                const tx = pts[a] + (pts[a + 3] - pts[a]) * t - fz * side * off;
                const tz = pts[a + 2] + (pts[a + 5] - pts[a + 2]) * t + fx * side * off;
                if (footprints.near(tx, tz, TREE_BUILDING_CLEARANCE)) continue;
                const roadY = pts[a + 1] + (pts[a + 4] - pts[a + 1]) * t;
                const gy = basemapRoadHeight(bm, tx, roadY, tz) + CURB_HEIGHT;
                const h = hash01(e, n);
                const radius = (lanes >= 3 ? 2.1 : 1.8) + h * 0.5;
                addTree(mb, tx, gy, tz, radius, Math.floor(h * 4) % 4, hash01(n, e));
            }
        }
    }

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
