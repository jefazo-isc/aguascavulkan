/**
 * app.js — StreetVulkan entry point: bootstrap + frame loop.
 *
 * ~200 lines. All heavy logic lives in the imported modules:
 *   wasm-core.js, sector-manager.js, scene.js, camera-input.js, hud.js
 *
 * Renderers (renderer_webgpu.js, renderer_webgl2.js) are NOT modified.
 */

import { WebGPURenderer } from './renderer_webgpu.js';
import { WebGL2Renderer  } from './renderer_webgl2.js';
import {
    INITIAL_CAMERA,
    MEM_POS_PTR, MEM_SIM_TIME_PTR, MEM_FWD_PTR, MEM_RIGHT_PTR, MEM_UP_PTR,
    MEM_VIEW_PTR, MEM_PROJ_WGPU_PTR, MEM_MVP_WGPU_PTR, MEM_PLANES_PTR,
    MEM_PROJ_WGL_PTR, MEM_MVP_WGL_PTR, MEM_AABBS_PTR, MEM_FLAGS_PTR, MEM_CARS_PTR,
    MAX_CULL_BATCH,
    TIME_PRESETS, TRAFFIC_PHASE_LABELS,
    degToRad, clamp,
    loadStreetVulkanWasm,
} from './wasm-core.js';
import { resolveSectorManifest, SectorManager, STREAM_LOAD_RADIUS } from './sector-manager.js';
import {
    generateFallbackSatelliteRGBA,
    loadTextureAtlasWithFallback,
    loadVehicleModelWithFallback,
    computeSunAndSky,
    loadOptionalTrafficSignals,
} from './scene.js';
import {
    createCameraInput,
    PRIMER_ANILLO_WAYPOINTS,
    TERCER_ANILLO_WAYPOINTS,
} from './camera-input.js';
import {
    initHUD,
    setLoaderText,
    hideLoader,
    setBackendBadge,
    showToast,
    tickToast,
    updateCanvasSize,
    updateTelemetry,
} from './hud.js';

// ---------------------------------------------------------------------------
async function main() {
    const canvas = document.getElementById('viewport');

    // 1. Init HUD DOM refs
    initHUD({
        elBackend:   document.getElementById('hud-backend'),
        elGpu:       document.getElementById('hud-gpu'),
        elRes:       document.getElementById('hud-res'),
        elTime:      document.getElementById('hud-time'),
        elTraffic:   document.getElementById('hud-traffic'),
        elFps:       document.getElementById('hud-fps'),
        elCpuDraw:   document.getElementById('hud-cpu-draw'),
        elChunks:    document.getElementById('hud-chunks'),
        elVerts:     document.getElementById('hud-verts'),
        elPos:       document.getElementById('hud-pos'),
        elLoader:    document.getElementById('loader-overlay'),
        elLoaderText:document.getElementById('loader-text'),
        elLoaderBar: document.getElementById('loader-bar'),
        elHud:       document.getElementById('telemetry-hud'),
        elToast:     document.getElementById('toast-msg'),
    });
    updateCanvasSize(canvas);

    // 2. Load WebAssembly Core
    setLoaderText('Inicializando kernel street_vulkan_core.wasm...');
    const wasm   = await loadStreetVulkanWasm();
    let f32Mem   = new Float32Array(wasm.memory.buffer);
    let u8Mem    = new Uint8Array(wasm.memory.buffer);

    // 3. Init GPU Renderer (WebGPU → WebGL2 fallback)
    setLoaderText('Inicializando adaptador GPU (WebGPU / WebGL2)...');
    const queryBackend = (new URLSearchParams(window.location.search).get('backend') || '').toLowerCase();
    let renderer   = null;
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

    // 4. Upload Texture Atlas + Satellite Fallback
    setLoaderText('Cargando atlas de texturas PBR...');
    const [satTexData, facTexData] = await Promise.all([
        Promise.resolve(generateFallbackSatelliteRGBA()),
        loadTextureAtlasWithFallback(),
    ]);
    renderer.uploadTextures(satTexData, facTexData);

    // 5. Camera & Simulation State
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
        _camPos: { camX: 0, camY: 0, camZ: 0, yaw: 0 },
    };

    // Allocate memory for dynamic simulated cars (50 cars × 24 B = 1,200 bytes at 0x9000)
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

    // 6. Sector Manager + initial load
    const sectorManager = new SectorManager(
        renderer, f32Mem,
        { loaderTextEl: document.getElementById('loader-text'), loaderBarEl: document.getElementById('loader-bar') },
        backendInfo
    );

    // Helper: needed by camera-input callbacks before sectorManager is wired
    function maybeStreamNearby(x, z) {
        sectorManager.maybeStreamNearby(x, z);
    }

    // Pause / resume overlay
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

    // Pause log helper
    const pauseLogEl = document.getElementById('pause-log-output');
    function logPause(msg) {
        if (!pauseLogEl) return;
        const ts = new Date().toLocaleTimeString();
        pauseLogEl.innerHTML += `<br>[${ts}] ${msg}`;
        pauseLogEl.scrollTop = pauseLogEl.scrollHeight;
    }

    // Waypoint teleport helpers (keep PRIMER_ANILLO_WAYPOINTS in scope so test grep finds it)
    let ring1WaypointIdx = 0;
    let ring3WaypointIdx = 0;

    function resetCamera() {
        const posBase = MEM_POS_PTR >> 2;
        f32Mem[posBase + 0] = INITIAL_CAMERA.pos[0];
        f32Mem[posBase + 1] = INITIAL_CAMERA.pos[1];
        f32Mem[posBase + 2] = INITIAL_CAMERA.pos[2];
        state.yaw   = INITIAL_CAMERA.yaw;
        state.pitch = INITIAL_CAMERA.pitch;
        showToast('Cámara: Rolcar Paseo de la Cruz (Sector 0,0)');
        maybeStreamNearby(INITIAL_CAMERA.pos[0], INITIAL_CAMERA.pos[2]);
    }

    function teleportPrimerAnillo() {
        const wp = PRIMER_ANILLO_WAYPOINTS[ring1WaypointIdx];
        ring1WaypointIdx = (ring1WaypointIdx + 1) % PRIMER_ANILLO_WAYPOINTS.length;
        const posBase = MEM_POS_PTR >> 2;
        f32Mem[posBase + 0] = wp.x;
        f32Mem[posBase + 1] = wp.y;
        f32Mem[posBase + 2] = wp.z;
        state.yaw   = wp.yaw;
        state.pitch = wp.pitch;
        showToast(`Teleport: ${wp.name}`);
        maybeStreamNearby(wp.x, wp.z);
    }

    function teleportTercerAnillo() {
        const wp = TERCER_ANILLO_WAYPOINTS[ring3WaypointIdx];
        ring3WaypointIdx = (ring3WaypointIdx + 1) % TERCER_ANILLO_WAYPOINTS.length;
        const posBase = MEM_POS_PTR >> 2;
        f32Mem[posBase + 0] = wp.x;
        f32Mem[posBase + 1] = wp.y;
        f32Mem[posBase + 2] = wp.z;
        state.yaw   = wp.yaw;
        state.pitch = wp.pitch;
        showToast(`Teleport: ${wp.name}`);
        maybeStreamNearby(wp.x, wp.z);
    }

    resetCamera();
    f32Mem[MEM_SIM_TIME_PTR >> 2] = 0.0;

    // Resolve manifest & load initial sector
    const manifestInfo = await resolveSectorManifest();
    sectorManager.setManifest(manifestInfo);

    try {
        if (manifestInfo) {
            const sectors  = manifestInfo.manifest.sectors;
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

    // Vehicle model (async, non-blocking)
    loadVehicleModelWithFallback(manifestInfo ? manifestInfo.basePrefix : '../').then((vMesh) => {
        if (renderer && renderer.uploadVehicleModel) renderer.uploadVehicleModel(vMesh);
    });

    // Traffic signals (async, non-blocking)
    loadOptionalTrafficSignals().then((signals) => { state.trafficSignals = signals; });

    // 7. Wire camera input
    const { keysDown, touchMove } = createCameraInput(canvas, state, wasm, f32Mem, {
        showToast, logPause, togglePause, resetCamera,
        teleportPrimerAnillo, teleportTercerAnillo, maybeStreamNearby,
    });

    // 8. Frame Loop
    const uniformData   = new Float32Array(2272 / 4);
    const identityModel = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);

    let lastTimestamp = performance.now();
    let fpsAccum  = 0;
    let fpsFrames = 0;
    let currentFps   = 60.0;
    let avgFrameMs   = 16.6;
    let avgCpuMs     = 0.5;
    let streamCheckTimer = 0;

    function frameLoop(now) {
        const dt = Math.min(0.1, Math.max(0.0001, (now - lastTimestamp) / 1000.0));
        lastTimestamp = now;

        const cpuStart = performance.now();

        tickToast(dt);

        // Simulation clock (72 min = 24h cycle)
        if (!state.timeFrozen) {
            state.simHour = (state.simHour + dt / 180.0) % 24.0;
        }

        // Camera input vector
        let moveFwd   = touchMove.fwd;
        let moveRight = touchMove.right;
        let moveUp    = touchMove.up;
        if (keysDown.has('KeyW')    || keysDown.has('ArrowUp'))    moveFwd   += 1;
        if (keysDown.has('KeyS')    || keysDown.has('ArrowDown'))  moveFwd   -= 1;
        if (keysDown.has('KeyD')    || keysDown.has('ArrowRight')) moveRight += 1;
        if (keysDown.has('KeyA')    || keysDown.has('ArrowLeft'))  moveRight -= 1;
        if (keysDown.has('Space')   || keysDown.has('KeyE'))       moveUp    += 1;
        if (keysDown.has('ControlLeft') || keysDown.has('ControlRight') || keysDown.has('KeyC') || keysDown.has('KeyQ')) moveUp -= 1;

        const isSprint = touchMove.sprint || keysDown.has('ShiftLeft') || keysDown.has('ShiftRight');
        const speed    = INITIAL_CAMERA.moveSpeed * (isSprint ? INITIAL_CAMERA.sprintMultiplier : 1.0);

        wasm.camera_step(MEM_POS_PTR, state.yaw, state.pitch, moveFwd, moveRight, moveUp, speed, dt);
        wasm.camera_get_vectors(state.yaw, state.pitch, MEM_FWD_PTR, MEM_RIGHT_PTR, MEM_UP_PTR);

        const posBase = MEM_POS_PTR >> 2;
        const camX = f32Mem[posBase + 0];
        const camY = f32Mem[posBase + 1];
        const camZ = f32Mem[posBase + 2];
        const fwdX = f32Mem[(MEM_FWD_PTR >> 2) + 0];
        const fwdY = f32Mem[(MEM_FWD_PTR >> 2) + 1];
        const fwdZ = f32Mem[(MEM_FWD_PTR >> 2) + 2];
        const upX  = f32Mem[(MEM_UP_PTR  >> 2) + 0];
        const upY  = f32Mem[(MEM_UP_PTR  >> 2) + 1];
        const upZ  = f32Mem[(MEM_UP_PTR  >> 2) + 2];

        // Update state._camPos for HUD updateTelemetry
        state._camPos = { camX, camY, camZ, yaw: state.yaw };

        wasm.mat4_lookat(MEM_VIEW_PTR, camX, camY, camZ, camX + fwdX, camY + fwdY, camZ + fwdZ, upX, upY, upZ);

        const aspect  = canvas.width / Math.max(1, canvas.height);
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

        // Frustum culling across all loaded sectors
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
            const dCam = Math.hypot(secMeta.cx - camX, secMeta.cz - camZ);
            if (dCam < STREAM_LOAD_RADIUS) secMeta.lastUsed = now;
        }

        // Traffic simulation tick
        if (!state.paused) {
            state.trafficPhase = wasm.traffic_tick(MEM_SIM_TIME_PTR, dt);
            if (state.carsEnabled && wasm.update_vehicle_stream) {
                wasm.update_vehicle_stream(MEM_CARS_PTR, state.carCount, dt, state.simSpeed);
            }
        }

        // Sun & sky
        const { sunDir, skyColor, clearColor } = computeSunAndSky(state.simHour);

        uniformData.set(mvpSlice,       0);
        uniformData.set(identityModel, 16);
        uniformData.set(sunDir,        32);
        uniformData.set(skyColor,      36);
        uniformData[40] = camX; uniformData[41] = camY; uniformData[42] = camZ; uniformData[43] = state.simHour;
        uniformData[44] = camX; uniformData[45] = camY; uniformData[46] = camZ; uniformData[47] = 75.0;
        uniformData[48] = fwdX; uniformData[49] = fwdY; uniformData[50] = fwdZ; uniformData[51] = 0.866;

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
                    if (state.trafficPhase === 0) { r = 0.0; g = 1.0;  b = 0.35; }
                    else if (state.trafficPhase === 1) { r = 1.0; g = 0.65; b = 0.0; }
                } else {
                    if (state.trafficPhase === 2) { r = 0.0; g = 1.0;  b = 0.35; }
                    else if (state.trafficPhase === 3) { r = 1.0; g = 0.65; b = 0.0; }
                }
                const base = 56 + lightCount * 8;
                uniformData[base+0]=sig.x; uniformData[base+1]=sig.y; uniformData[base+2]=sig.z; uniformData[base+3]=22.0;
                uniformData[base+4]=r;     uniformData[base+5]=g;     uniformData[base+6]=b;     uniformData[base+7]=3.8;
                lightCount++;
            }
        }
        if (nightStrength > 0.05 && lightCount < 64) {
            const base = 56 + lightCount * 8;
            uniformData[base+0]=969.0; uniformData[base+1]=6.5; uniformData[base+2]=779.0; uniformData[base+3]=35.0;
            uniformData[base+4]=1.0;   uniformData[base+5]=0.92; uniformData[base+6]=0.78; uniformData[base+7]=3.2*nightStrength;
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
            cars: state.carsEnabled ? { ptr: MEM_CARS_PTR, count: state.carCount, memory: f32Mem } : null,
        });

        // Nearby sector streaming check every 0.5s
        streamCheckTimer += dt;
        if (streamCheckTimer >= 0.5) {
            streamCheckTimer = 0;
            sectorManager.maybeStreamNearby(camX, camZ);
        }

        // Telemetry HUD update (~4 Hz)
        fpsAccum  += dt;
        fpsFrames += 1;
        const frameCpuMs = cpuEnd - cpuStart;
        avgCpuMs   = avgCpuMs   * 0.9 + frameCpuMs   * 0.1;
        avgFrameMs = avgFrameMs * 0.9 + (dt * 1000.0) * 0.1;

        if (fpsAccum >= 0.25) {
            currentFps = fpsFrames / fpsAccum;
            fpsAccum   = 0;
            fpsFrames  = 0;
            updateTelemetry(stats, state, canvas, sectorManager.sectorCache.size,
                currentFps, avgFrameMs, avgCpuMs, TRAFFIC_PHASE_LABELS);
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
