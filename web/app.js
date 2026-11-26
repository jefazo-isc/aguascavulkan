// ============================================================================
// StreetVulkan Web Client Application
// Orchestrates:
//   - street_vulkan_core.wasm (WAT math, camera, frustum culling, traffic_tick)
//   - WebGPU (Vulkan) primary renderer with automatic WebGL2 fallback
//   - Modular GLB sector streaming prioritizing Sector (0, 0) Paseo de la Cruz
//   - City basemap LOD + Overture buildings + Road-graph traffic simulation
//   - ISO/IEC 25010:2023 real-time telemetry HUD
// ============================================================================

import { WebGPURenderer } from './renderer_webgpu.js';
import { WebGL2Renderer } from './renderer_webgl2.js';
import { CAR_TYPES, CAR_INSTANCE_FLOATS, TrafficSimulation, stageCorridorInstances } from './traffic_sim.js';
import { BASEMAP_MACRO_SIZE, basemapRoadHeight, bucketRoadSegments, buildBasemapCell, basemapCellKeys } from './city_basemap.js';
import {
    INITIAL_CAMERA,
    MEM_POS_PTR,
    MEM_SIM_TIME_PTR,
    MEM_FWD_PTR,
    MEM_RIGHT_PTR,
    MEM_UP_PTR,
    MEM_VIEW_PTR,
    MEM_PROJ_WGPU_PTR,
    MEM_MVP_WGPU_PTR,
    MEM_PLANES_PTR,
    MEM_PROJ_WGL_PTR,
    MEM_MVP_WGL_PTR,
    MEM_AABBS_PTR,
    MEM_FLAGS_PTR,
    MEM_CARS_PTR,
    MAX_CULL_BATCH,
    TRAFFIC_PHASE_LABELS,
    degToRad,
    loadStreetVulkanWasm,
} from './wasm-core.js';
import {
    generateFallbackSatelliteRGBA,
    loadTextureAtlasWithFallback,
    loadVehicleModelWithFallback,
    loadCityBasemap,
    loadCityBuildings,
    loadRoadGraph,
    computeSunAndSky,
    loadOptionalTrafficSignals,
} from './scene.js';
import {
    initHUD,
    getLoaderTextEl,
    getLoaderBarEl,
    setLoaderText,
    hideLoader,
    setBackendBadge,
    showToast,
    tickToast,
    updateCanvasSize,
    updateTelemetry,
} from './hud.js';
import {
    STREAM_LOAD_RADIUS,
    resolveSectorManifest,
    SectorManager,
} from './sector-manager.js';
import {
    PRIMER_ANILLO_WAYPOINTS,
    TERCER_ANILLO_WAYPOINTS,
    createCameraInput,
} from './camera-input.js';

// ----------------------------------------------------------------------------
// Main Application Bootstrap
// ----------------------------------------------------------------------------
async function main() {
    const canvas = document.getElementById('viewport');
    initHUD({
        elBackend:    document.getElementById('hud-backend'),
        elGpu:        document.getElementById('hud-gpu'),
        elRes:        document.getElementById('hud-res'),
        elTime:       document.getElementById('hud-time'),
        elTraffic:    document.getElementById('hud-traffic'),
        elFps:        document.getElementById('hud-fps'),
        elCpuDraw:    document.getElementById('hud-cpu-draw'),
        elChunks:     document.getElementById('hud-chunks'),
        elVerts:      document.getElementById('hud-verts'),
        elPos:        document.getElementById('hud-pos'),
        elCars:       document.getElementById('hud-cars'),
        elLoader:     document.getElementById('loader-overlay'),
        elLoaderText: document.getElementById('loader-text'),
        elLoaderBar:  document.getElementById('loader-bar'),
        elHud:        document.getElementById('telemetry-hud'),
        elToast:      document.getElementById('toast-msg'),
    });

    updateCanvasSize(canvas);

    // 1. Load WebAssembly Core (.wat -> .wasm)
    setLoaderText('Inicializando kernel street_vulkan_core.wasm...');
    const wasm = await loadStreetVulkanWasm();
    const f32Mem = new Float32Array(wasm.memory.buffer);
    const u8Mem = new Uint8Array(wasm.memory.buffer);

    // 2. Initialize GPU Renderer: WebGPU (Vulkan) primary with automatic WebGL2 fallback
    setLoaderText('Inicializando adaptador GPU (WebGPU / WebGL2)...');
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
    setBackendBadge(backendInfo.backend, isWebGPU, backendInfo.gpuName);

    window.addEventListener('resize', () => {
        const { w, h } = updateCanvasSize(canvas);
        renderer.resize(w, h);
    });

    // 3. Upload Texture Atlas + Satellite Fallback
    setLoaderText('Cargando atlas de texturas PBR...');
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
        _camPos: { camX: INITIAL_CAMERA.pos[0], camY: INITIAL_CAMERA.pos[1], camZ: INITIAL_CAMERA.pos[2], yaw: INITIAL_CAMERA.yaw },
    };

    // WASM corridor vehicle stream (50 cars x 24 B at 0x9000) fallback when road_network.bin is unavailable
    const carsBaseFloat = MEM_CARS_PTR >> 2;
    for (let i = 0; i < state.carCount; i++) {
        const off = carsBaseFloat + i * 6;
        f32Mem[off + 0] = 200.0 + (i / state.carCount) * 800.0;
        f32Mem[off + 1] = 8.8;
        f32Mem[off + 2] = (i % 2 === 0) ? 795.5 : 952.0;
        f32Mem[off + 3] = (i % 2 === 0) ? 90.0 : 0.0;
        f32Mem[off + 4] = (i / state.carCount);
        f32Mem[off + 5] = (i % 2);
    }

    function togglePause(forced) {
        state.paused = (typeof forced === 'boolean') ? forced : !state.paused;
        const overlay = document.getElementById('pause-menu-overlay');
        if (overlay) overlay.classList.toggle('active', state.paused);
        if (state.paused) {
            if (document.exitPointerLock) document.exitPointerLock();
            showToast('Simulación Pausada [P / ESC]');
        } else {
            showToast('Simulación Reanudada');
        }
    }

    // 5. Sector Manager + City Basemap LOD
    const BUILDING_LOAD_RADIUS = 2300.0;
    const BUILDING_DROP_RADIUS = 3000.0;
    let cityBasemap = null;
    let cityBuildings = null;
    let roadBuckets = null;
    const lodCells = new Map();
    const lodBuildQueue = [];
    let lodDirty = true;
    let lodKeys = [];
    let lodAabbs = new Float32Array(0);
    let lodFlags = new Uint8Array(0);
    const sectorKeyAt = (x, z) => `${Math.floor(x / BASEMAP_MACRO_SIZE)}_${Math.floor(z / BASEMAP_MACRO_SIZE)}`;

    const sectorManager = new SectorManager(
        renderer,
        f32Mem,
        { loaderTextEl: getLoaderTextEl(), loaderBarEl: getLoaderBarEl() },
        backendInfo,
        {
            onSectorLoaded: (key) => hideBasemapCell(key),
            onSectorUnloaded: (key) => queueBasemapCell(key),
        }
    );

    function hideBasemapCell(key) {
        if (!lodCells.has(key)) return;
        renderer.unloadSector(`lod_${key}`);
        sectorManager.cullFlagsBySector.delete(`lod_${key}`);
        lodCells.delete(key);
        lodDirty = true;
    }

    function queueBasemapCell(key) {
        if (!cityBasemap || sectorManager.sectorCache.has(key) || lodBuildQueue.includes(key)) return;
        lodBuildQueue.push(key);
    }

    function cellDistance(key, camX, camZ) {
        const [mx, mz] = key.split('_').map(Number);
        const x0 = mx * BASEMAP_MACRO_SIZE;
        const z0 = mz * BASEMAP_MACRO_SIZE;
        const dx = Math.max(x0 - camX, 0, camX - (x0 + BASEMAP_MACRO_SIZE));
        const dz = Math.max(z0 - camZ, 0, camZ - (z0 + BASEMAP_MACRO_SIZE));
        return Math.hypot(dx, dz);
    }

    function cellWantsBuildings(key, camX, camZ) {
        if (!cityBuildings || !cityBuildings.cells.has(key)) return false;
        const current = lodCells.get(key);
        const radius = (current && current.withBuildings) ? BUILDING_DROP_RADIUS : BUILDING_LOAD_RADIUS;
        return cellDistance(key, camX, camZ) < radius;
    }

    function refreshBasemapBuildings(camX, camZ) {
        for (const [key, cell] of lodCells.entries()) {
            if (cell.withBuildings !== cellWantsBuildings(key, camX, camZ)) queueBasemapCell(key);
        }
    }

    function buildQueuedBasemapCells(camX, camZ, budgetMs) {
        if (!cityBasemap || lodBuildQueue.length === 0) return;
        lodBuildQueue.sort((a, b) => cellDistance(a, camX, camZ) - cellDistance(b, camX, camZ));
        const t0 = performance.now();
        while (lodBuildQueue.length > 0 && performance.now() - t0 < budgetMs) {
            const key = lodBuildQueue.shift();
            if (sectorManager.sectorCache.has(key)) continue;
            const withBuildings = cellWantsBuildings(key, camX, camZ);
            const current = lodCells.get(key);
            if (current && current.withBuildings === withBuildings) continue;
            const [mx, mz] = key.split('_').map(Number);
            const cell = buildBasemapCell(cityBasemap, trafficGraph, roadBuckets, mx, mz,
                withBuildings ? cityBuildings : null);
            if (!cell) continue;
            renderer.uploadSector(`lod_${key}`, cell.meshData, cell.chunks);
            const c = cell.chunks[0];
            lodCells.set(key, { aabbData: [c.min_x, c.min_y, c.min_z, c.max_x, c.max_y, c.max_z], withBuildings });
            lodDirty = true;
        }
    }

    function applyCameraPose(x, y, z, yaw, pitch, toastMsg) {
        const posBase = MEM_POS_PTR >> 2;
        f32Mem[posBase + 0] = x;
        f32Mem[posBase + 1] = y;
        f32Mem[posBase + 2] = z;
        state.yaw = yaw;
        state.pitch = pitch;
        showToast(toastMsg);
        sectorManager.maybeStreamNearby(x, z);
        refreshBasemapBuildings(x, z);
    }

    function resetCamera() {
        applyCameraPose(
            INITIAL_CAMERA.pos[0], INITIAL_CAMERA.pos[1], INITIAL_CAMERA.pos[2],
            INITIAL_CAMERA.yaw, INITIAL_CAMERA.pitch,
            'Cámara: Rolcar Paseo de la Cruz (Sector 0,0)'
        );
    }

    let ring3WaypointIdx = 0;
    function teleportTercerAnillo() {
        const wp = TERCER_ANILLO_WAYPOINTS[ring3WaypointIdx];
        ring3WaypointIdx = (ring3WaypointIdx + 1) % TERCER_ANILLO_WAYPOINTS.length;
        applyCameraPose(wp.x, wp.y, wp.z, wp.yaw, wp.pitch, `Teleport: ${wp.name}`);
    }

    let ring1WaypointIdx = 0;
    function teleportPrimerAnillo() {
        const wp = PRIMER_ANILLO_WAYPOINTS[ring1WaypointIdx];
        ring1WaypointIdx = (ring1WaypointIdx + 1) % PRIMER_ANILLO_WAYPOINTS.length;
        applyCameraPose(wp.x, wp.y, wp.z, wp.yaw, wp.pitch, `Teleport: ${wp.name}`);
    }

    resetCamera();
    f32Mem[MEM_SIM_TIME_PTR >> 2] = 0.0;

    const manifestInfo = await resolveSectorManifest();
    sectorManager.setManifest(manifestInfo);

    const assetPrefix = manifestInfo ? manifestInfo.basePrefix : '../';
    CAR_TYPES.forEach((typeName, typeIndex) => {
        loadVehicleModelWithFallback(assetPrefix, typeName).then((vMesh) => {
            if (renderer && renderer.uploadVehicleModel) {
                renderer.uploadVehicleModel(vMesh, typeIndex);
            }
        });
    });

    // Road-graph traffic & basemap async load
    let trafficSim = null;
    let trafficGraph = null;
    const fallbackInstances = new Float32Array(state.carCount * CAR_INSTANCE_FLOATS);
    const fallbackTypeCounts = new Uint32Array(CAR_TYPES.length);
    const fallbackTypeOffsets = new Uint32Array(CAR_TYPES.length);
    Promise.all([loadRoadGraph(assetPrefix), loadCityBasemap(assetPrefix), loadCityBuildings(assetPrefix)]).then(([graph, basemap, buildings]) => {
        trafficGraph = graph;
        cityBuildings = buildings;
        if (!buildings) console.warn('[Buildings] city_buildings.bin unavailable; basemap without buildings');
        if (basemap) {
            cityBasemap = basemap;
            roadBuckets = graph ? bucketRoadSegments(graph) : null;
            for (const [mx, mz] of basemapCellKeys(basemap)) queueBasemapCell(`${mx}_${mz}`);
        } else {
            console.warn('[Basemap] city_basemap.bin unavailable; only GLB sectors are shown');
        }
        if (!graph) {
            console.warn('[Traffic] road_network.bin unavailable; using WASM corridor vehicles');
            return;
        }
        trafficSim = new TrafficSimulation(graph, state.carCount);
        trafficSim.isDrivable = (x, z) => {
            const key = sectorKeyAt(x, z);
            return sectorManager.sectorCache.has(key) || lodCells.has(key);
        };
        trafficSim.surfaceHeight = (x, roadY, z) => (sectorManager.sectorCache.has(sectorKeyAt(x, z)) || !cityBasemap)
            ? roadY + 0.05
            : basemapRoadHeight(cityBasemap, x, roadY, z);
    });

    try {
        if (manifestInfo) {
            const sectors = manifestInfo.manifest.sectors;
            const sector00 = sectors.find((s) => s.mx === 0 && s.mz === 0) || sectors[0];
            await sectorManager.loadSector(sector00, manifestInfo.basePrefix, true);
        } else {
            throw new Error('No sector manifest or GLB found');
        }
    } catch (err) {
        console.warn('[Loader] Loading standalone fallback scene:', err.message);
        sectorManager.loadFallbackSector(showToast);
    }

    hideLoader();

    loadOptionalTrafficSignals().then((signals) => {
        state.trafficSignals = signals;
    });

    // 6. Input Wiring
    const pauseLogEl = document.getElementById('pause-log-output');
    function logPause(msg) {
        if (!pauseLogEl) return;
        const ts = new Date().toLocaleTimeString();
        pauseLogEl.innerHTML += `<br>[${ts}] ${msg}`;
        pauseLogEl.scrollTop = pauseLogEl.scrollHeight;
    }

    const { keysDown, touchMove } = createCameraInput(canvas, state, wasm, f32Mem, {
        showToast,
        logPause,
        togglePause,
        resetCamera,
        teleportPrimerAnillo,
        teleportTercerAnillo,
        maybeStreamNearby: (x, z) => sectorManager.maybeStreamNearby(x, z),
        getActiveCarCount: () => (trafficSim ? trafficSim.activeCount : state.carCount),
    });

    // 7. Frame Loop
    const uniformData = new Float32Array(2272 / 4);
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

    function vehicleFrame() {
        if (trafficSim) {
            return { instances: trafficSim.instances, typeCounts: trafficSim.typeCounts, typeOffsets: trafficSim.typeOffsets };
        }
        stageCorridorInstances(f32Mem, MEM_CARS_PTR, state.carCount, fallbackInstances, fallbackTypeCounts, fallbackTypeOffsets);
        return { instances: fallbackInstances, typeCounts: fallbackTypeCounts, typeOffsets: fallbackTypeOffsets };
    }

    function frameLoop(now) {
        const dt = Math.min(0.1, Math.max(0.0001, (now - lastTimestamp) / 1000.0));
        lastTimestamp = now;

        const cpuStart = performance.now();
        tickToast(dt);

        if (!state.timeFrozen) {
            state.simHour = (state.simHour + dt / 180.0) % 24.0;
        }

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
        state._camPos = { camX, camY, camZ, yaw: state.yaw };

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
        for (const [sectorKey, secMeta] of sectorManager.sectorCache.entries()) {
            const count = secMeta.chunkCount;
            if (count === 0) continue;
            let flags = sectorManager.cullFlagsBySector.get(sectorKey);
            if (!flags || flags.length !== count) {
                flags = new Uint8Array(count);
                sectorManager.cullFlagsBySector.set(sectorKey, flags);
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

            if (Math.hypot(secMeta.cx - camX, secMeta.cz - camZ) < STREAM_LOAD_RADIUS) {
                secMeta.lastUsed = now;
            }
        }

        // WASM frustum culling for basemap cells
        if (lodDirty) {
            lodKeys = Array.from(lodCells.keys());
            lodAabbs = new Float32Array(lodKeys.length * 6);
            lodFlags = new Uint8Array(lodKeys.length);
            lodKeys.forEach((key, i) => {
                lodAabbs.set(lodCells.get(key).aabbData, i * 6);
                sectorManager.cullFlagsBySector.set(`lod_${key}`, lodFlags.subarray(i, i + 1));
            });
            lodDirty = false;
        }
        if (state.cullingEnabled) {
            for (let offset = 0; offset < lodKeys.length; offset += MAX_CULL_BATCH) {
                const batch = Math.min(MAX_CULL_BATCH, lodKeys.length - offset);
                f32Mem.set(lodAabbs.subarray(offset * 6, (offset + batch) * 6), aabbBaseFloat);
                wasm.cull_chunks(MEM_PLANES_PTR, MEM_AABBS_PTR, MEM_FLAGS_PTR, batch);
                lodFlags.set(u8Mem.subarray(MEM_FLAGS_PTR, MEM_FLAGS_PTR + batch), offset);
            }
        } else {
            lodFlags.fill(1);
        }

        if (!state.paused) {
            state.trafficPhase = wasm.traffic_tick(MEM_SIM_TIME_PTR, dt);
            if (state.carsEnabled) {
                if (trafficSim) {
                    trafficSim.update(dt, camX, camZ, state.trafficPhase);
                } else if (wasm.update_vehicle_stream) {
                    wasm.update_vehicle_stream(MEM_CARS_PTR, state.carCount, dt, state.simSpeed);
                }
            }
        }

        const { sunDir, skyColor, clearColor } = computeSunAndSky(state.simHour);

        uniformData.set(mvpSlice, 0);
        uniformData.set(identityModel, 16);
        uniformData.set(sunDir, 32);
        uniformData.set(skyColor, 36);
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

                const isGroup0 = (sig.phase || 0) === 0;
                let r = 1.0, g = 0.04, b = 0.04;
                if (isGroup0) {
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
            cullFlagsBySector: sectorManager.cullFlagsBySector,
            cullingEnabled: state.cullingEnabled,
            renderMode: state.renderMode || 'all',
            vehicles: state.carsEnabled ? vehicleFrame() : null,
        });

        buildQueuedBasemapCells(camX, camZ, 6.0);

        streamCheckTimer += dt;
        if (streamCheckTimer >= 0.5) {
            streamCheckTimer = 0;
            sectorManager.maybeStreamNearby(camX, camZ);
            refreshBasemapBuildings(camX, camZ);
        }

        fpsAccum += dt;
        fpsFrames++;
        const frameCpuMs = cpuEnd - cpuStart;
        avgCpuMs = avgCpuMs * 0.9 + frameCpuMs * 0.1;
        avgFrameMs = avgFrameMs * 0.9 + (dt * 1000.0) * 0.1;

        if (fpsAccum >= 0.25) {
            currentFps = fpsFrames / fpsAccum;
            fpsAccum = 0;
            fpsFrames = 0;
            const activeCars = trafficSim ? trafficSim.activeCount : state.carCount;
            updateTelemetry(
                stats, state, canvas,
                sectorManager.sectorCache.size, lodCells.size, activeCars,
                currentFps, avgFrameMs, avgCpuMs, TRAFFIC_PHASE_LABELS
            );
        }

        requestAnimationFrame(frameLoop);
    }

    requestAnimationFrame(frameLoop);
}

main().catch((err) => {
    console.error('[StreetVulkan Fatal]', err);
    setLoaderText(`Error inicializando StreetVulkan: ${err.message}`);
    const elLoaderText = getLoaderTextEl();
    if (elLoaderText) elLoaderText.style.color = '#ff6b6b';
});
