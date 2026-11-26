/**
 * hud.js — DOM telemetry HUD, toast notifications, loader overlay, canvas resize.
 *
 * No internal project imports (zero deps). All DOM refs are injected via initHUD().
 */

// ---------------------------------------------------------------------------
// Module-level DOM state (populated by initHUD)
// ---------------------------------------------------------------------------
let _elBackend  = null;
let _elGpu      = null;
let _elRes      = null;
let _elTime     = null;
let _elTraffic  = null;
let _elFps      = null;
let _elCpuDraw  = null;
let _elChunks   = null;
let _elVerts    = null;
let _elPos      = null;
let _elLoader   = null;
let _elLoaderText = null;
let _elLoaderBar  = null;
let _elHud      = null;
let _elToast    = null;

let _toastTimer = 0;

// ---------------------------------------------------------------------------
// initHUD(elements) — call once from main()
// ---------------------------------------------------------------------------
export function initHUD(elements) {
    _elBackend    = elements.elBackend;
    _elGpu        = elements.elGpu;
    _elRes        = elements.elRes;
    _elTime       = elements.elTime;
    _elTraffic    = elements.elTraffic;
    _elFps        = elements.elFps;
    _elCpuDraw    = elements.elCpuDraw;
    _elChunks     = elements.elChunks;
    _elVerts      = elements.elVerts;
    _elPos        = elements.elPos;
    _elLoader     = elements.elLoader;
    _elLoaderText = elements.elLoaderText;
    _elLoaderBar  = elements.elLoaderBar;
    _elHud        = elements.elHud;
    _elToast      = elements.elToast;
}

// ---------------------------------------------------------------------------
// Loader overlay
// ---------------------------------------------------------------------------
export function getLoaderTextEl()  { return _elLoaderText; }
export function getLoaderBarEl()   { return _elLoaderBar; }

export function setLoaderText(msg) {
    if (_elLoaderText) _elLoaderText.textContent = msg;
}

export function hideLoader() {
    if (_elLoader) _elLoader.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Backend badge
// ---------------------------------------------------------------------------
export function setBackendBadge(backendName, isWebGPU, gpuName) {
    if (_elBackend) {
        _elBackend.textContent = backendName;
        _elBackend.className = isWebGPU ? 'badge badge-vulkan' : 'badge badge-webgl';
    }
    if (_elGpu) {
        _elGpu.textContent = gpuName;
    }
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
export function showToast(msg) {
    if (!_elToast) return;
    _elToast.textContent = msg;
    _elToast.classList.add('visible');
    _toastTimer = 2.6;
}

/** Call every frame with dt (seconds). Automatically hides toast when timer expires. */
export function tickToast(dt) {
    if (_toastTimer > 0) {
        _toastTimer -= dt;
        if (_toastTimer <= 0 && _elToast) {
            _elToast.classList.remove('visible');
        }
    }
}

// ---------------------------------------------------------------------------
// HUD visibility toggle
// ---------------------------------------------------------------------------
export function setHudVisible(visible) {
    if (_elHud) _elHud.classList.toggle('hidden', !visible);
}

// ---------------------------------------------------------------------------
// Canvas DPR-aware resize
// ---------------------------------------------------------------------------
export function updateCanvasSize(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.floor(window.innerWidth * dpr));
    const h = Math.max(1, Math.floor(window.innerHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
    }
    return { w, h };
}

// ---------------------------------------------------------------------------
// Telemetry HUD update (call at ~4 Hz, gated by caller)
// ---------------------------------------------------------------------------
/**
 * @param {object} stats        — renderer stats: { drawCalls, visibleChunks, totalChunks, visibleVerts, totalVerts }
 * @param {object} state        — simulation state
 * @param {HTMLCanvasElement} canvas
 * @param {number} sectorCount
 * @param {number} currentFps
 * @param {number} avgFrameMs
 * @param {number} avgCpuMs
 * @param {string[]} TRAFFIC_PHASE_LABELS
 */
export function updateTelemetry(stats, state, canvas, sectorCount, currentFps, avgFrameMs, avgCpuMs, TRAFFIC_PHASE_LABELS) {
    if (_elRes) _elRes.textContent = `${canvas.width}x${canvas.height} px`;
    if (_elTime) {
        const hrs  = Math.floor(state.simHour);
        const mins = Math.floor((state.simHour - hrs) * 60);
        const phaseLabel = (hrs >= 6 && hrs < 18) ? (hrs < 8 ? 'Amanecer' : hrs > 16 ? 'Atardecer' : 'Día') : 'Noche';
        _elTime.textContent = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')} (${phaseLabel})${state.timeFrozen ? ' [Fijo]' : ''}`;
    }
    if (_elTraffic) {
        _elTraffic.textContent = `${TRAFFIC_PHASE_LABELS[state.trafficPhase] || 'F0'} | ${state.trafficSignals.length} Semaf`;
    }
    if (_elFps) {
        _elFps.textContent = `${currentFps.toFixed(0)} FPS (${avgFrameMs.toFixed(2)} ms)`;
        _elFps.className = currentFps >= 50 ? 'metric-good' : currentFps >= 30 ? 'metric-warn' : 'metric-bad';
    }
    if (_elCpuDraw) {
        _elCpuDraw.textContent = `${avgCpuMs.toFixed(2)} ms | Draw: ${stats.drawCalls}`;
    }
    if (_elChunks) {
        _elChunks.textContent = `${stats.visibleChunks}/${stats.totalChunks} (Sectores: ${sectorCount})`;
    }
    if (_elVerts) {
        const cullPct = stats.totalVerts > 0
            ? (1.0 - stats.visibleVerts / stats.totalVerts) * 100.0
            : 0.0;
        _elVerts.textContent = `${Math.round(stats.visibleVerts / 1000)}k/${Math.round(stats.totalVerts / 1000)}k (Cull: ${cullPct.toFixed(0)}%)`;
    }
    if (_elPos) {
        const { camX, camY, camZ, yaw } = state._camPos;
        _elPos.textContent = `${camX.toFixed(1)}, ${camY.toFixed(1)}, ${camZ.toFixed(1)} | Yaw ${yaw.toFixed(1)}°`;
    }
}
