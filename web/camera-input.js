/**
 * camera-input.js — Keyboard, mouse, touch, D-pad, pointer lock, toolbar bindings,
 *                   teleport waypoints, and pause menu wiring.
 *
 * Exports:
 *  - PRIMER_ANILLO_WAYPOINTS  (array of waypoint objects)
 *  - TERCER_ANILLO_WAYPOINTS  (array of waypoint objects)
 *  - createCameraInput(canvas, state, wasm, f32Mem, callbacks) → { keysDown, touchMove }
 */

import { clamp, INITIAL_CAMERA, TIME_PRESETS, TRAFFIC_PHASE_LABELS, MEM_POS_PTR, MEM_SIM_TIME_PTR, MEM_CARS_PTR } from './wasm-core.js';

// ---------------------------------------------------------------------------
// Waypoint Constants
// ---------------------------------------------------------------------------
export const PRIMER_ANILLO_WAYPOINTS = [
    { name: 'Primer Anillo Norte — Av. Convención (Nte)', x: 50.0,    y: 12.0, z: -1800.0, yaw:    0.0, pitch: -5.0 },
    { name: 'Primer Anillo Oriente — Av. Convención (Ote)', x: 1800.0, y: 12.0, z: -200.0,  yaw:  -90.0, pitch: -5.0 },
    { name: 'Primer Anillo Sur — Av. Convención (Sur)', x: -100.0,  y: 12.0, z: 1700.0,  yaw:  180.0, pitch: -5.0 },
    { name: 'Primer Anillo Poniente — Av. Convención (Pte)', x: -2000.0, y: 12.0, z: 100.0,   yaw:   90.0, pitch: -5.0 },
];

export const TERCER_ANILLO_WAYPOINTS = [
    { name: 'Tercer Anillo Norte — Paso a Desnivel (Av. Siglo XXI Nte)', x:  532.0, y: 28.0,  z: -7134.0, yaw:   0.0, pitch: -5.0 },
    { name: 'Tercer Anillo Oriente (Av. Siglo XXI Ote)', x: 4927.0, y: 69.5,  z:    -7.5, yaw: -90.0, pitch: -5.0 },
    { name: 'Tercer Anillo Sur (Av. Siglo XXI Sur)', x:   -1.5, y:  1.0,  z:  4011.0, yaw: 180.0, pitch: -5.0 },
    { name: 'Tercer Anillo Poniente (Av. Siglo XXI Pte)', x: -7500.0, y: 21.0,  z:    15.0, yaw:  90.0, pitch: -5.0 },
];

// ---------------------------------------------------------------------------
// createCameraInput()
// ---------------------------------------------------------------------------
/**
 * Registers all event listeners and toolbar/pause-menu bindings.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {object} state               — shared simulation state (mutated in-place)
 * @param {object} wasm                — WASM exports
 * @param {Float32Array} f32Mem        — WASM linear memory view (Float32)
 * @param {object} callbacks           — { showToast, logPause, togglePause, resetCamera,
 *                                        teleportPrimerAnillo, teleportTercerAnillo,
 *                                        maybeStreamNearby }
 * @returns {{ keysDown: Set<string>, touchMove: object }}
 */
export function createCameraInput(canvas, state, wasm, f32Mem, callbacks) {
    const { showToast, logPause, togglePause, resetCamera, teleportPrimerAnillo, teleportTercerAnillo, maybeStreamNearby } = callbacks;

    const keysDown  = new Set();
    const touchMove = { fwd: 0, right: 0, up: 0, sprint: false };

    let isDragging    = false;
    let lastPointerX  = 0;
    let lastPointerY  = 0;
    let activeTouchId = null;

    // -----------------------------------------------------------------------
    // Time helpers (need local state)
    // -----------------------------------------------------------------------
    function toggleTimeFreeze() {
        state.timeFrozen = !state.timeFrozen;
        showToast(state.timeFrozen ? 'Avance solar: CONGELADO' : 'Avance solar: ACTIVO');
    }

    // -----------------------------------------------------------------------
    // Keyboard
    // -----------------------------------------------------------------------
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
            state.simHour   = TIME_PRESETS[state.presetIdx].hour;
            showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
        } else if (e.code === 'KeyY') {
            toggleTimeFreeze();
        } else if (e.code === 'KeyR') {
            resetCamera();
        } else if (e.code === 'Digit1' || e.code === 'Numpad1') {
            teleportPrimerAnillo();
        } else if (e.code === 'Digit3' || e.code === 'Numpad3') {
            teleportTercerAnillo();
        } else if (e.code === 'KeyH') {
            state.hudVisible = !state.hudVisible;
            const elHud = document.getElementById('telemetry-hud');
            if (elHud) elHud.classList.toggle('hidden', !state.hudVisible);
        }
    });

    window.addEventListener('keyup', (e) => { keysDown.delete(e.code); });

    window.addEventListener('blur', () => {
        keysDown.clear();
        isDragging = false;
    });

    // -----------------------------------------------------------------------
    // Mouse / Pointer Lock
    // -----------------------------------------------------------------------
    canvas.addEventListener('click', () => {
        if (document.pointerLockElement !== canvas && canvas.requestPointerLock) {
            try { canvas.requestPointerLock(); } catch (_err) { /* drag fallback active */ }
        }
    });

    canvas.addEventListener('mousedown', (e) => {
        if (e.button === 0) {
            isDragging   = true;
            lastPointerX = e.clientX;
            lastPointerY = e.clientY;
        }
    });

    window.addEventListener('mouseup', () => { isDragging = false; });

    window.addEventListener('mousemove', (e) => {
        if (document.pointerLockElement === canvas) {
            state.yaw   += e.movementX * INITIAL_CAMERA.mouseSensitivity;
            state.pitch  = clamp(state.pitch - e.movementY * INITIAL_CAMERA.mouseSensitivity, -89.0, 89.0);
        } else if (isDragging) {
            const dx = e.clientX - lastPointerX;
            const dy = e.clientY - lastPointerY;
            lastPointerX = e.clientX;
            lastPointerY = e.clientY;
            state.yaw   += dx * INITIAL_CAMERA.mouseSensitivity * 1.4;
            state.pitch  = clamp(state.pitch - dy * INITIAL_CAMERA.mouseSensitivity * 1.4, -89.0, 89.0);
        }
    });

    // -----------------------------------------------------------------------
    // Touch look on canvas
    // -----------------------------------------------------------------------
    canvas.addEventListener('touchstart', (e) => {
        if (activeTouchId === null && e.changedTouches.length > 0) {
            const t = e.changedTouches[0];
            activeTouchId = t.identifier;
            lastPointerX  = t.clientX;
            lastPointerY  = t.clientY;
        }
    }, { passive: true });

    canvas.addEventListener('touchmove', (e) => {
        for (const t of e.changedTouches) {
            if (t.identifier === activeTouchId) {
                const dx = t.clientX - lastPointerX;
                const dy = t.clientY - lastPointerY;
                lastPointerX = t.clientX;
                lastPointerY = t.clientY;
                state.yaw   += dx * INITIAL_CAMERA.mouseSensitivity * 1.8;
                state.pitch  = clamp(state.pitch - dy * INITIAL_CAMERA.mouseSensitivity * 1.8, -89.0, 89.0);
                break;
            }
        }
    }, { passive: true });

    const endTouch = (e) => {
        for (const t of e.changedTouches) {
            if (t.identifier === activeTouchId) activeTouchId = null;
        }
    };
    canvas.addEventListener('touchend',   endTouch, { passive: true });
    canvas.addEventListener('touchcancel', endTouch, { passive: true });

    // -----------------------------------------------------------------------
    // On-screen D-pad + action buttons
    // -----------------------------------------------------------------------
    const bindHoldButton = (id, onDown, onUp) => {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.addEventListener('pointerdown',  (e) => { e.preventDefault(); onDown(); });
        const release = (e) => { e.preventDefault(); onUp(); };
        btn.addEventListener('pointerup',     release);
        btn.addEventListener('pointerleave',  release);
        btn.addEventListener('pointercancel', release);
    };

    bindHoldButton('btn-fwd',    () => { touchMove.fwd    =  1; }, () => { touchMove.fwd    = 0; });
    bindHoldButton('btn-back',   () => { touchMove.fwd    = -1; }, () => { touchMove.fwd    = 0; });
    bindHoldButton('btn-left',   () => { touchMove.right  = -1; }, () => { touchMove.right  = 0; });
    bindHoldButton('btn-right',  () => { touchMove.right  =  1; }, () => { touchMove.right  = 0; });
    bindHoldButton('btn-up',     () => { touchMove.up     =  1; }, () => { touchMove.up     = 0; });
    bindHoldButton('btn-down',   () => { touchMove.up     = -1; }, () => { touchMove.up     = 0; });
    bindHoldButton('btn-sprint', () => { touchMove.sprint = true; }, () => { touchMove.sprint = false; });

    document.getElementById('btn-rolcar')?.addEventListener('click', resetCamera);
    document.getElementById('btn-primer-anillo')?.addEventListener('click', teleportPrimerAnillo);
    document.getElementById('btn-tercer-anillo')?.addEventListener('click', teleportTercerAnillo);
    document.getElementById('btn-pause')?.addEventListener('click', () => togglePause());
    document.getElementById('pause-resume')?.addEventListener('click', () => togglePause(false));

    // -----------------------------------------------------------------------
    // Pause-menu action buttons
    // -----------------------------------------------------------------------
    document.getElementById('pause-wasm-test')?.addEventListener('click', () => {
        try {
            const v    = wasm.get_version();
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
        const activeCount = callbacks.getActiveCarCount ? callbacks.getActiveCarCount() : state.carCount;
        if (elCars) {
            elCars.textContent = state.carsEnabled ? `${activeCount} activos` : 'Pausado';
            elCars.className   = state.carsEnabled ? 'metric-good' : 'metric-warn';
        }
        logPause(`🚗 Simulación de tráfico: ${state.carsEnabled ? 'ACTIVADA' : 'DESACTIVADA'}`);
        showToast(state.carsEnabled ? 'Tráfico: ON' : 'Tráfico: OFF');
    });

    document.getElementById('pause-toggle-time')?.addEventListener('click', () => {
        state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
        state.simHour   = TIME_PRESETS[state.presetIdx].hour;
        logPause(`☀️ Hora establecida: ${TIME_PRESETS[state.presetIdx].label}`);
        showToast(`Hora: ${TIME_PRESETS[state.presetIdx].label}`);
    });

    document.getElementById('pause-force-traffic')?.addEventListener('click', () => {
        const simTimeFloat = MEM_SIM_TIME_PTR >> 2;
        const currentPhase = wasm.traffic_tick(MEM_SIM_TIME_PTR, 0.0);
        const nextPhase    = (currentPhase + 1) % 4;
        const phaseTimes   = [0.0, 9.5, 12.5, 21.5];
        f32Mem[simTimeFloat] = phaseTimes[nextPhase];
        state.trafficPhase   = wasm.traffic_tick(MEM_SIM_TIME_PTR, 0.0);
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

    document.getElementById('pause-teleport-primer-anillo')?.addEventListener('click', () => {
        teleportPrimerAnillo();
        logPause('🏛️ Teleport a Primer Anillo (Av. Convención)');
        togglePause(false);
    });

    document.getElementById('pause-teleport-tercer-anillo')?.addEventListener('click', () => {
        teleportTercerAnillo();
        logPause('🛣️ Teleport a Tercer Anillo (Av. Siglo XXI)');
        togglePause(false);
    });

    document.getElementById('pause-switch-backend')?.addEventListener('click', () => {
        const isWebGPU = document.getElementById('hud-backend')?.classList.contains('badge-vulkan');
        const next = isWebGPU ? 'webgl2' : 'webgpu';
        const url  = new URL(window.location.href);
        url.searchParams.set('backend', next);
        window.location.href = url.toString();
    });

    document.getElementById('pause-toggle-buildings')?.addEventListener('click', () => {
        state.renderMode = (state.renderMode === 'buildings') ? 'all' : 'buildings';
        logPause(`🏢 Modo Render: ${state.renderMode === 'buildings' ? 'Solo Edificios (WebGPU Pipeline)' : 'Escena Completa'}`);
    });

    // Toolbar buttons
    document.getElementById('btn-time')?.addEventListener('click', () => {
        state.presetIdx = (state.presetIdx + 1) % TIME_PRESETS.length;
        state.simHour   = TIME_PRESETS[state.presetIdx].hour;
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

    return { keysDown, touchMove };
}
