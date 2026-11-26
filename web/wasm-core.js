// ============================================================================
// wasm-core.js — Constantes de memoria WASM, helpers matemáticos y loader
// ============================================================================

// Posición inicial de cámara frente a Rolcar Paseo de la Cruz
export const INITIAL_CAMERA = {
    pos: [954.4, 8.8, 793.1],
    yaw: -45.7,
    pitch: 4.9,
    moveSpeed: 35.0,
    sprintMultiplier: 4.0,
    mouseSensitivity: 0.12,
};

// Offsets de memoria lineal WASM (coinciden con street_vulkan_core.wat)
// 0x0000..0x0003 reservado como NULL guard (paridad C/Emscripten ABI)
export const MEM_POS_PTR       = 0x0004;
export const MEM_SIM_TIME_PTR  = 0x0010;
export const MEM_FWD_PTR       = 0x0014;
export const MEM_RIGHT_PTR     = 0x0020;
export const MEM_UP_PTR        = 0x002C;
export const MEM_VIEW_PTR      = 0x0040;
export const MEM_PROJ_WGPU_PTR = 0x0080;
export const MEM_MVP_WGPU_PTR  = 0x00C0;
export const MEM_PLANES_PTR    = 0x0100;
export const MEM_PROJ_WGL_PTR  = 0x0160;
export const MEM_MVP_WGL_PTR   = 0x01A0;
export const MEM_AABBS_PTR     = 0x0200;
export const MEM_FLAGS_PTR     = 0x8000;
export const MEM_CARS_PTR      = 0x9000;
export const MAX_CULL_BATCH    = 1024;

export const TIME_PRESETS = [
    { hour: 14.0, label: '14:00 Día' },
    { hour: 17.5, label: '17:30 Atardecer' },
    { hour: 22.5, label: '22:30 Noche' },
    { hour: 6.5,  label: '06:30 Amanecer' },
];

export const TRAFFIC_PHASE_LABELS = [
    'F0: N-S Verde',
    'F1: N-S Ámbar',
    'F2: E-O Verde',
    'F3: E-O Ámbar',
];

// ----------------------------------------------------------------------------
// Helpers matemáticos puros
// ----------------------------------------------------------------------------
export function degToRad(d) {
    return d * 0.017453292519943295;
}

export function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
}

export function linearToSrgbChannel(c) {
    return Math.pow(clamp(c, 0.0, 1.0), 1.0 / 2.2);
}

// ----------------------------------------------------------------------------
// Loader del kernel WebAssembly (.wat → .wasm)
// Intenta instantiateStreaming primero; cae a arrayBuffer si falla.
// ----------------------------------------------------------------------------
export async function loadStreetVulkanWasm() {
    const wasmUrl = new URL('./street_vulkan_core.wasm', import.meta.url).href;
    let instance;

    if (typeof WebAssembly.instantiateStreaming === 'function') {
        try {
            const resp = await fetch(wasmUrl);
            if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${wasmUrl}`);
            const result = await WebAssembly.instantiateStreaming(resp, {});
            instance = result.instance;
        } catch (streamErr) {
            console.warn('[WASM] instantiateStreaming fallback a arrayBuffer:', streamErr.message);
            const resp = await fetch(wasmUrl);
            if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${wasmUrl}`);
            const bytes = await resp.arrayBuffer();
            const result = await WebAssembly.instantiate(bytes, {});
            instance = result.instance;
        }
    } else {
        const resp = await fetch(wasmUrl);
        if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${wasmUrl}`);
        const bytes = await resp.arrayBuffer();
        const result = await WebAssembly.instantiate(bytes, {});
        instance = result.instance;
    }

    const exports = instance.exports;
    const version = exports.get_version();
    if (version !== 1) {
        throw new Error(`Versión inesperada de street_vulkan_core.wasm: ${version}`);
    }
    return exports;
}
