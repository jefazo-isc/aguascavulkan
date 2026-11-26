// ============================================================================
// StreetVulkan Web Traffic Simulation
// Port of src/car_system.c: vehicles follow the RGP1 road graph
// (models/road_network.bin) polylines with real DEM heights, per-lane offsets,
// traffic-light stops at signalized nodes and simple car-following (IDM-lite).
// Output is a packed per-instance stream matching include/car_system.h
// CarInstanceData (mat4 model + vec4 tint + float brake + pad[3] = 96 B).
// ============================================================================

export const CAR_INSTANCE_FLOATS = 24;

export const CAR_TYPES = ['sedan', 'compacto', 'pickup', 'van', 'taxi', 'bus'];
const CAR_BASE_SPEEDS = [13.9, 12.5, 15.0, 11.1, 13.9, 8.3];
// Spawn weights per type (buses and vans are rarer than sedans/compacts)
const CAR_TYPE_WEIGHTS = [0.30, 0.25, 0.15, 0.10, 0.15, 0.05];

const CAR_TINTS = [
    [0.90, 0.15, 0.15, 1.0], // rojo
    [0.20, 0.45, 0.90, 1.0], // azul
    [0.90, 0.90, 0.90, 1.0], // plata
    [0.95, 0.75, 0.05, 1.0], // amarillo
    [0.20, 0.20, 0.25, 1.0], // oscuro
    [0.10, 0.60, 0.30, 1.0], // verde
    [0.50, 0.30, 0.10, 1.0], // marrón
    [0.80, 0.50, 0.80, 1.0], // morado
];

const LANE_WIDTH = 3.2;
const MIN_FOLLOW_DIST = 5.0;
const SAFE_TIME_HEADWAY = 1.2;
const SIGNAL_LOOKAHEAD = 35.0;
const SPAWN_MIN_DIST = 40.0;
const EDGE_GRID_CELL = 128.0;
const ROAD_Y_OFFSET = 0.05; // street mesh sits ~3 cm above the road graph polyline
export const STOPPED_SPEED_THRESHOLD_MPS = 0.1;

// ----------------------------------------------------------------------------
// RGP1 parser (tools/generate_road_graph.py / include/road_graph.h)
//   header 16 B: "RGP1", u32 n_nodes, n_edges, n_points
//   node   20 B: f32 x, y, z, i32 signal_group, u8 degree, u8 pad[3]
//   edge   28 B: u32 a, b, pt_off, pt_count, f32 speed_ms, width, u8 lanes_fwd, lanes_rev, oneway, pad
//   point  12 B: f32 x, y, z
// ----------------------------------------------------------------------------
export function parseRoadGraph(arrayBuffer) {
    const dv = new DataView(arrayBuffer);
    if (arrayBuffer.byteLength < 16) throw new Error('road_network.bin too small');
    const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
    if (magic !== 'RGP1') throw new Error(`Invalid road graph magic: ${magic}`);
    const nNodes = dv.getUint32(4, true);
    const nEdges = dv.getUint32(8, true);
    const nPoints = dv.getUint32(12, true);
    const expected = 16 + nNodes * 20 + nEdges * 28 + nPoints * 12;
    if (arrayBuffer.byteLength < expected) {
        throw new Error(`road_network.bin truncated: ${arrayBuffer.byteLength} < ${expected}`);
    }

    const nodeX = new Float32Array(nNodes);
    const nodeZ = new Float32Array(nNodes);
    const nodeSignal = new Int32Array(nNodes);
    let off = 16;
    for (let i = 0; i < nNodes; i++, off += 20) {
        nodeX[i] = dv.getFloat32(off, true);
        nodeZ[i] = dv.getFloat32(off + 8, true);
        nodeSignal[i] = dv.getInt32(off + 12, true);
    }

    const edgeA = new Uint32Array(nEdges);
    const edgeB = new Uint32Array(nEdges);
    const edgePtOff = new Uint32Array(nEdges);
    const edgePtCount = new Uint32Array(nEdges);
    const edgeSpeed = new Float32Array(nEdges);
    const edgeWidth = new Float32Array(nEdges);
    const edgeLanesFwd = new Uint8Array(nEdges);
    const edgeLanesRev = new Uint8Array(nEdges);
    const edgeOneway = new Uint8Array(nEdges);
    for (let i = 0; i < nEdges; i++, off += 28) {
        edgeA[i] = dv.getUint32(off, true);
        edgeB[i] = dv.getUint32(off + 4, true);
        edgePtOff[i] = dv.getUint32(off + 8, true);
        edgePtCount[i] = dv.getUint32(off + 12, true);
        edgeSpeed[i] = dv.getFloat32(off + 16, true);
        edgeWidth[i] = dv.getFloat32(off + 20, true);
        edgeLanesFwd[i] = dv.getUint8(off + 24);
        edgeLanesRev[i] = dv.getUint8(off + 25);
        edgeOneway[i] = dv.getUint8(off + 26);
    }

    // Copy points so the graph does not pin the original download buffer
    const points = new Float32Array(nPoints * 3);
    for (let i = 0; i < nPoints * 3; i++) {
        points[i] = dv.getFloat32(off + i * 4, true);
    }

    // Validity, 3D polyline length and midpoint per edge
    const edgeValid = new Uint8Array(nEdges);
    const edgeLen = new Float32Array(nEdges);
    const edgeMidX = new Float32Array(nEdges);
    const edgeMidZ = new Float32Array(nEdges);
    for (let e = 0; e < nEdges; e++) {
        const po = edgePtOff[e];
        const pc = edgePtCount[e];
        if (pc < 2 || po + pc > nPoints || edgeA[e] >= nNodes || edgeB[e] >= nNodes) continue;
        edgeValid[e] = 1;
        let len = 0;
        for (let k = 0; k < pc - 1; k++) {
            const a = (po + k) * 3;
            const b = a + 3;
            len += Math.hypot(points[b] - points[a], points[b + 1] - points[a + 1], points[b + 2] - points[a + 2]);
        }
        edgeLen[e] = Math.max(0.1, len);
        const mid = (po + (pc >> 1)) * 3;
        edgeMidX[e] = points[mid];
        edgeMidZ[e] = points[mid + 2];
    }

    // CSR incidence: an edge can be entered from `a` (dir 0) or, if two-way, from `b` (dir 1)
    const counts = new Uint32Array(nNodes + 1);
    for (let e = 0; e < nEdges; e++) {
        if (!edgeValid[e]) continue;
        counts[edgeA[e]]++;
        if (!edgeOneway[e]) counts[edgeB[e]]++;
    }
    const nodeEdgeOffsets = new Uint32Array(nNodes + 1);
    for (let n = 0; n < nNodes; n++) nodeEdgeOffsets[n + 1] = nodeEdgeOffsets[n] + counts[n];
    const nodeEdgeIdx = new Uint32Array(nodeEdgeOffsets[nNodes]);
    const nodeEdgeDir = new Uint8Array(nodeEdgeOffsets[nNodes]);
    const cursor = nodeEdgeOffsets.slice(0, nNodes);
    for (let e = 0; e < nEdges; e++) {
        if (!edgeValid[e]) continue;
        let c = cursor[edgeA[e]]++;
        nodeEdgeIdx[c] = e;
        nodeEdgeDir[c] = 0;
        if (!edgeOneway[e]) {
            c = cursor[edgeB[e]]++;
            nodeEdgeIdx[c] = e;
            nodeEdgeDir[c] = 1;
        }
    }

    // Coarse grid of edge midpoints for spawning near the camera
    const edgeGrid = new Map();
    for (let e = 0; e < nEdges; e++) {
        if (!edgeValid[e]) continue;
        const key = `${Math.floor(edgeMidX[e] / EDGE_GRID_CELL)},${Math.floor(edgeMidZ[e] / EDGE_GRID_CELL)}`;
        let list = edgeGrid.get(key);
        if (!list) {
            list = [];
            edgeGrid.set(key, list);
        }
        list.push(e);
    }

    return {
        nNodes, nEdges, nPoints,
        nodeX, nodeZ, nodeSignal,
        edgeA, edgeB, edgePtOff, edgePtCount, edgeSpeed, edgeWidth,
        edgeLanesFwd, edgeLanesRev, edgeOneway,
        edgeValid, edgeLen, edgeMidX, edgeMidZ,
        points, nodeEdgeOffsets, nodeEdgeIdx, nodeEdgeDir, edgeGrid,
    };
}

function wrapAngle(a) {
    while (a > Math.PI) a -= 2 * Math.PI;
    while (a < -Math.PI) a += 2 * Math.PI;
    return a;
}

// ----------------------------------------------------------------------------
// Vehicle simulation
// ----------------------------------------------------------------------------
export class TrafficSimulation {
    constructor(graph, maxCars = 60, rng = Math.random) {
        this.graph = graph;
        this.maxCars = maxCars;
        this.rng = rng;
        this.cars = [];
        this.instances = new Float32Array(maxCars * CAR_INSTANCE_FLOATS);
        this.typeCounts = new Uint32Array(CAR_TYPES.length);
        this.typeOffsets = new Uint32Array(CAR_TYPES.length);
        this.activeCount = 0;
        this.spawnRadius = 450.0;
        this.despawnRadius = 650.0;
        // Optional predicate (x, z) => boolean restricting cars to loaded terrain
        this.isDrivable = null;
        // Optional (x, roadY, z) => y for the rendered road surface (e.g. the city basemap)
        this.surfaceHeight = null;
        this._sample = { x: 0, y: 0, z: 0, fx: 0, fz: 1 };
        for (let i = 0; i < maxCars; i++) {
            this.cars.push({
                alive: false, edge: 0, dir: 0, t: 0, lane: 0, nextEdge: -1,
                v: 0, vDesired: 0, brake: 0, type: 0, tint: CAR_TINTS[0],
                x: 0, y: 0, z: 0, heading: 0,
            });
        }
    }

    _edgeDrivable(e) {
        if (!this.isDrivable) return true;
        const g = this.graph;
        return this.isDrivable(g.nodeX[g.edgeA[e]], g.nodeZ[g.edgeA[e]]) &&
               this.isDrivable(g.nodeX[g.edgeB[e]], g.nodeZ[g.edgeB[e]]);
    }

    _laneCount(e, dir) {
        const g = this.graph;
        return Math.max(1, dir === 0 ? g.edgeLanesFwd[e] : g.edgeLanesRev[e]);
    }

    _laneOffset(car) {
        const g = this.graph;
        const n = this._laneCount(car.edge, car.dir);
        // Two-way streets keep to the right of the centerline; one-way streets spread lanes across it
        return g.edgeOneway[car.edge]
            ? (car.lane + 0.5 - n * 0.5) * LANE_WIDTH
            : (car.lane + 0.5) * LANE_WIDTH;
    }

    _polylineSample(e, t, dir, out) {
        const g = this.graph;
        const po = g.edgePtOff[e];
        const pc = g.edgePtCount[e];
        const pts = g.points;
        const effT = Math.max(0, Math.min(1, dir ? 1 - t : t));
        const target = effT * g.edgeLen[e];
        let accum = 0;
        for (let k = 0; k < pc - 1; k++) {
            const a = (po + k) * 3;
            const dx = pts[a + 3] - pts[a];
            const dy = pts[a + 4] - pts[a + 1];
            const dz = pts[a + 5] - pts[a + 2];
            const seg = Math.hypot(dx, dy, dz);
            if (accum + seg >= target || k === pc - 2) {
                const u = seg > 1e-4 ? Math.max(0, Math.min(1, (target - accum) / seg)) : 0;
                out.x = pts[a] + u * dx;
                out.y = pts[a + 1] + u * dy;
                out.z = pts[a + 2] + u * dz;
                const hl = Math.hypot(dx, dz);
                if (hl > 1e-4) {
                    out.fx = (dir ? -dx : dx) / hl;
                    out.fz = (dir ? -dz : dz) / hl;
                }
                return out;
            }
            accum += seg;
        }
        return out;
    }

    // Heading (atan2(x, z)) of an edge as seen when entering it in direction `dir`
    _entryHeading(e, dir) {
        const g = this.graph;
        const po = g.edgePtOff[e];
        const pc = g.edgePtCount[e];
        const i0 = (po + (dir ? pc - 1 : 0)) * 3;
        const i1 = (po + (dir ? pc - 2 : 1)) * 3;
        return Math.atan2(g.points[i1] - g.points[i0], g.points[i1 + 2] - g.points[i0 + 2]);
    }

    _pickNextEdge(curEdge, reachNode, curHeading) {
        const g = this.graph;
        const start = g.nodeEdgeOffsets[reachNode];
        const end = g.nodeEdgeOffsets[reachNode + 1];
        const cands = [];
        for (let k = start; k < end; k++) {
            const e = g.nodeEdgeIdx[k];
            if (e === curEdge || !this._edgeDrivable(e)) continue;
            cands.push(k);
        }
        if (cands.length === 0) return -1;
        // 70% keep "straight" (smallest heading change), like the native engine
        if (this.rng() < 0.7) {
            let best = cands[0];
            let bestDiff = Infinity;
            for (const k of cands) {
                const diff = Math.abs(wrapAngle(this._entryHeading(g.nodeEdgeIdx[k], g.nodeEdgeDir[k]) - curHeading));
                if (diff < bestDiff) {
                    bestDiff = diff;
                    best = k;
                }
            }
            return best;
        }
        return cands[Math.floor(this.rng() * cands.length)];
    }

    _randomType() {
        let r = this.rng();
        for (let i = 0; i < CAR_TYPE_WEIGHTS.length; i++) {
            r -= CAR_TYPE_WEIGHTS[i];
            if (r <= 0) return i;
        }
        return 0;
    }

    _spawn(car, camX, camZ) {
        const g = this.graph;
        const cx = Math.floor(camX / EDGE_GRID_CELL);
        const cz = Math.floor(camZ / EDGE_GRID_CELL);
        const reach = Math.ceil(this.spawnRadius / EDGE_GRID_CELL);
        const pool = [];
        for (let dz = -reach; dz <= reach; dz++) {
            for (let dx = -reach; dx <= reach; dx++) {
                const list = g.edgeGrid.get(`${cx + dx},${cz + dz}`);
                if (list) pool.push(list);
            }
        }
        car.alive = false;
        if (pool.length === 0) return false;

        for (let attempt = 0; attempt < 48; attempt++) {
            const list = pool[Math.floor(this.rng() * pool.length)];
            const e = list[Math.floor(this.rng() * list.length)];
            const d = Math.hypot(g.edgeMidX[e] - camX, g.edgeMidZ[e] - camZ);
            if (d < SPAWN_MIN_DIST || d > this.spawnRadius || !this._edgeDrivable(e)) continue;

            car.edge = e;
            car.dir = g.edgeOneway[e] ? 0 : (this.rng() < 0.5 ? 0 : 1);
            car.lane = Math.floor(this.rng() * this._laneCount(e, car.dir));
            car.t = 0.05 + this.rng() * 0.85;
            car.type = this._randomType();
            const base = g.edgeSpeed[e] > 0 ? g.edgeSpeed[e] : CAR_BASE_SPEEDS[car.type];
            car.vDesired = base * (0.85 + this.rng() * 0.3);
            car.v = car.vDesired;
            car.brake = 0;
            car.tint = CAR_TINTS[Math.floor(this.rng() * CAR_TINTS.length)];
            car.alive = true;
            this._placeOnEdge(car);
            const reachNode = car.dir === 0 ? g.edgeB[e] : g.edgeA[e];
            car.nextEdge = this._pickNextEdge(e, reachNode, car.heading);
            return true;
        }
        return false;
    }

    _placeOnEdge(car) {
        const s = this._polylineSample(car.edge, car.t, car.dir, this._sample);
        const off = this._laneOffset(car);
        car.x = s.x - s.fz * off;
        car.z = s.z + s.fx * off;
        car.y = this.surfaceHeight ? this.surfaceHeight(car.x, s.y, car.z) : s.y + ROAD_Y_OFFSET;
        car.heading = Math.atan2(s.fx, s.fz);
    }

    _findLead(ci) {
        const car = this.cars[ci];
        const g = this.graph;
        let dist = 999.0;
        let leadV = car.vDesired;
        const fdx = Math.sin(car.heading);
        const fdz = Math.cos(car.heading);
        for (let oi = 0; oi < this.cars.length; oi++) {
            if (oi === ci) continue;
            const o = this.cars[oi];
            if (!o.alive) continue;
            if (o.edge === car.edge && o.dir === car.dir && o.lane === car.lane) {
                if (o.t > car.t) {
                    const d = (o.t - car.t) * g.edgeLen[car.edge];
                    if (d < dist) { dist = d; leadV = o.v; }
                }
                continue;
            }
            // Cars ahead on another edge (intersections): 7 m frontal proximity, like native
            const cdx = o.x - car.x;
            const cdz = o.z - car.z;
            const d2 = cdx * cdx + cdz * cdz;
            if (d2 < 49.0 && cdx * fdx + cdz * fdz > 0.5) {
                const d = Math.sqrt(d2);
                if (d < dist) { dist = d; leadV = o.v; }
            }
        }
        return { dist, leadV };
    }

    // Traffic light state for a car approaching a signalized node.
    // Signal group 0 controls roads running along X (tools/sector_roads.py), group 1 along Z.
    // trafficPhase (street_vulkan_core.wasm traffic_tick): 0 G0 green, 1 G0 amber, 2 G1 green, 3 G1 amber.
    static lightIsStop(trafficPhase, fwdX, fwdZ) {
        const group = Math.abs(fwdX) >= Math.abs(fwdZ) ? 0 : 1;
        const greenPhase = group === 0 ? 0 : 2;
        return trafficPhase !== greenPhase;
    }

    update(dt, camX, camZ, trafficPhase) {
        const g = this.graph;
        let alive = 0;
        for (const car of this.cars) {
            if (car.alive && Math.hypot(car.x - camX, car.z - camZ) > this.despawnRadius) car.alive = false;
            if (!car.alive) this._spawn(car, camX, camZ);
            if (car.alive) alive++;
        }

        for (let ci = 0; ci < this.cars.length; ci++) {
            const car = this.cars[ci];
            if (!car.alive) continue;
            let elen = g.edgeLen[car.edge];
            let targetSpeed = car.vDesired;

            // Traffic lights at the destination node
            const targetNode = car.dir === 0 ? g.edgeB[car.edge] : g.edgeA[car.edge];
            const distToNode = (1.0 - car.t) * elen;
            if (g.nodeSignal[targetNode] >= 0 && distToNode <= SIGNAL_LOOKAHEAD &&
                TrafficSimulation.lightIsStop(trafficPhase, Math.sin(car.heading), Math.cos(car.heading))) {
                if (distToNode <= 5.0) {
                    targetSpeed = 0.0;
                } else {
                    const ratio = (distToNode - 5.0) / (SIGNAL_LOOKAHEAD - 5.0);
                    targetSpeed = car.vDesired * ratio * ratio;
                }
            }

            // Car following
            const { dist, leadV } = this._findLead(ci);
            const desiredGap = MIN_FOLLOW_DIST + car.v * SAFE_TIME_HEADWAY;
            if (dist < desiredGap) {
                if (dist <= MIN_FOLLOW_DIST) {
                    targetSpeed = 0.0;
                } else {
                    const ratio = (dist - MIN_FOLLOW_DIST) / (desiredGap - MIN_FOLLOW_DIST);
                    targetSpeed = Math.min(targetSpeed, leadV * ratio * ratio);
                }
            }

            if (car.v > targetSpeed) {
                car.v = Math.max(targetSpeed, car.v - 8.5 * dt);
                car.brake = 1.0;
            } else if (car.v < targetSpeed) {
                car.v = Math.min(targetSpeed, car.v + 4.0 * dt);
                car.brake = 0.0;
            } else {
                car.brake = car.v < 0.1 ? 1.0 : 0.0;
            }
            if (car.v > 0.001) car.t += (car.v * dt) / elen;

            // Reached the destination node: continue onto the pre-picked edge
            if (car.t >= 1.0) {
                if (car.nextEdge < 0) {
                    car.alive = false; // dead end or leaving loaded terrain
                    continue;
                }
                const k = car.nextEdge;
                car.t = Math.min(0.99, (car.t - 1.0) * elen / g.edgeLen[g.nodeEdgeIdx[k]]);
                car.edge = g.nodeEdgeIdx[k];
                car.dir = g.nodeEdgeDir[k];
                car.lane = Math.min(car.lane, this._laneCount(car.edge, car.dir) - 1);
                elen = g.edgeLen[car.edge];
                const reach = car.dir === 0 ? g.edgeB[car.edge] : g.edgeA[car.edge];
                car.nextEdge = this._pickNextEdge(car.edge, reach, this._entryHeading(car.edge, car.dir));
            }

            this._placeOnEdge(car);

            // Smooth heading over the last 8 m before turning onto the next edge
            if (car.nextEdge >= 0) {
                const blend = 8.0 / elen;
                if (car.t >= 1.0 - blend) {
                    const k = car.nextEdge;
                    const targetH = this._entryHeading(g.nodeEdgeIdx[k], g.nodeEdgeDir[k]);
                    const alpha = Math.max(0, Math.min(1, (car.t - (1.0 - blend)) / blend));
                    car.heading += alpha * 0.5 * wrapAngle(targetH - car.heading);
                }
            }
        }
        this.activeCount = alive;
        this._stageInstances();
        return alive;
    }

    // Compute telemetry from the current car state instead of activeCount,
    // which is updated before cars can be deactivated at a dead end.
    getStats() {
        let activeCount = 0;
        let stoppedCount = 0;
        let speedSumMps = 0.0;

        for (const car of this.cars) {
            if (!car.alive) continue;
            activeCount++;
            speedSumMps += car.v;
            if (car.v < STOPPED_SPEED_THRESHOLD_MPS) stoppedCount++;
        }

        return {
            activeCount,
            stoppedCount,
            averageSpeedKmh: activeCount > 0 ? (speedSumMps / activeCount) * 3.6 : 0.0,
        };
    }

    // Pack alive cars grouped by type (one instanced draw per type), as car_system_stage_instances()
    _stageInstances() {
        this.typeCounts.fill(0);
        for (const car of this.cars) if (car.alive) this.typeCounts[car.type]++;
        let running = 0;
        for (let t = 0; t < CAR_TYPES.length; t++) {
            this.typeOffsets[t] = running;
            running += this.typeCounts[t];
        }
        const write = Array.from(this.typeOffsets);
        const inst = this.instances;
        for (const car of this.cars) {
            if (!car.alive) continue;
            const o = write[car.type]++ * CAR_INSTANCE_FLOATS;
            const c = Math.cos(car.heading);
            const s = Math.sin(car.heading);
            // Column-major Translate(pos) * Ry(heading): local +Z (car front) -> (sin h, 0, cos h)
            inst[o + 0] = c;  inst[o + 1] = 0;  inst[o + 2] = -s; inst[o + 3] = 0;
            inst[o + 4] = 0;  inst[o + 5] = 1;  inst[o + 6] = 0;  inst[o + 7] = 0;
            inst[o + 8] = s;  inst[o + 9] = 0;  inst[o + 10] = c; inst[o + 11] = 0;
            inst[o + 12] = car.x; inst[o + 13] = car.y; inst[o + 14] = car.z; inst[o + 15] = 1;
            inst[o + 16] = car.tint[0];
            inst[o + 17] = car.tint[1];
            inst[o + 18] = car.tint[2];
            inst[o + 19] = car.tint[3];
            inst[o + 20] = car.brake;
            inst[o + 21] = 0; inst[o + 22] = 0; inst[o + 23] = 0;
        }
    }
}

// Converts the WASM corridor stream (update_vehicle_stream: 6 x f32 per car
// [x, y, z, yaw_deg, progress, corridor]) into the same instance layout, used
// only when road_network.bin cannot be loaded.
export function stageCorridorInstances(f32Mem, carsPtr, count, out, typeCounts, typeOffsets) {
    const base = carsPtr >> 2;
    const n = Math.min(count, Math.floor(out.length / CAR_INSTANCE_FLOATS));
    for (let i = 0; i < n; i++) {
        const src = base + i * 6;
        const h = f32Mem[src + 3] * 0.017453292519943295;
        const c = Math.cos(h);
        const s = Math.sin(h);
        const o = i * CAR_INSTANCE_FLOATS;
        out.set([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, f32Mem[src], f32Mem[src + 1], f32Mem[src + 2], 1], o);
        out.set(CAR_TINTS[i % CAR_TINTS.length], o + 16);
        out[o + 20] = 0; out[o + 21] = 0; out[o + 22] = 0; out[o + 23] = 0;
    }
    typeCounts.fill(0);
    typeOffsets.fill(0);
    typeCounts[0] = n;
    return n;
}
