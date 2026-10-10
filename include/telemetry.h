/* telemetry.h - Telemetría y Métricas ISO/IEC 25010:2023 para StreetVulkan
 *
 * Mide en microsegundos (µs) y milisegundos (ms) la Eficiencia de Desempeño:
 * - Comportamiento Temporal (CPU vs GPU breakdown, FPS, Frame Time).
 * - Utilización de Recursos (VRAM estimada, RAM de vértices, Draw Calls).
 * - Capacidad y Culling (Triángulos visibles vs totales, porcentaje de descarte).
 */
#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <SDL2/SDL.h>
#include <stdint.h>
#include <stdio.h>

#define TELEMETRY_HISTORY_SIZE 60

typedef struct {
    /* --- ISO 25010: Comportamiento Temporal (Time Behaviour) --- */
    float fps;                  /* Frames por segundo (promedio móvil) */
    float frameTimeMs;          /* Tiempo total por cuadro (ms) */
    float cpuTimeMs;            /* Tiempo consumido por la CPU (lógica, culling, entrada) (ms) */
    float gpuTimeMs;            /* Tiempo de envío y renderizado en Vulkan GPU (ms) */
    float frameBudgetPct;       /* Presupuesto de tiempo consumido vs objetivo 60 FPS (16.66ms) */

    /* Breakdown de CPU (µs) */
    uint64_t cpuInputUs;        /* Procesamiento de eventos e insumos */
    uint64_t cpuTrafficUs;      /* Simulación de vehículos y semáforos */
    uint64_t cpuCullUs;         /* Frustum culling de chunks */

    /* Breakdown de GPU (µs) */
    uint64_t gpuCmdUs;          /* Grabación de command buffers y draws */
    uint64_t gpuPresentUs;      /* Espera de fence y presentación en swapchain */

    /* --- ISO 25010: Utilización de Recursos (Resource Utilization) --- */
    size_t vramEstimatedBytes;  /* Memoria asignada en GPU (Buffers Vértices + Texturas) */
    size_t ramVertexBytes;      /* Memoria RAM usada por la geometría activa */
    uint32_t drawCalls;         /* Número de llamadas de dibujo en el frame */

    /* --- Información de Hardware y Sistema --- */
    char gpuName[256];          /* Nombre de la GPU detectada por Vulkan */
    uint32_t screenWidth;       /* Ancho del Viewport en píxeles */
    uint32_t screenHeight;      /* Alto del Viewport en píxeles */

    /* --- Sistema de Tráfico Dinámico & Tiempo --- */
    float simHour;                    /* Hora simulada (0.0 - 24.0 h) en ciclo de 72 min */
    uint32_t trafficSignalsCount;     /* Número de semáforos 3D cargados */
    uint32_t trafficIntersectionsCount;/* Número de cruces/intersecciones activas */

    /* --- ISO 25010: Capacidad y Culling (Capacity) --- */
    uint32_t totalChunks;       /* Chunks totales en la escena */
    uint32_t visibleChunks;     /* Chunks pasando el test de visión */
    uint32_t totalVerts;        /* Vértices totales */
    uint32_t visibleVerts;      /* Vértices dibujados */
    float cullingEfficiencyPct; /* Porcentaje de vértices descartados por culling */

    /* Medición interna */
    Uint64 timerFreq;
    Uint64 frameStartCounter;
    Uint64 cpuStartCounter;
    Uint64 gpuStartCounter;

    /* Acumuladores para promedio móvil de 60 frames */
    float frameTimeHistory[TELEMETRY_HISTORY_SIZE];
    float cpuTimeHistory[TELEMETRY_HISTORY_SIZE];
    float gpuTimeHistory[TELEMETRY_HISTORY_SIZE];
    int historyIdx;
} TelemetrySystem;

static inline void telemetry_init(TelemetrySystem *t) {
    memset(t, 0, sizeof(TelemetrySystem));
    t->timerFreq = SDL_GetPerformanceFrequency();
}

static inline void telemetry_frame_start(TelemetrySystem *t) {
    t->frameStartCounter = SDL_GetPerformanceCounter();
}

static inline void telemetry_cpu_begin(TelemetrySystem *t) {
    t->cpuStartCounter = SDL_GetPerformanceCounter();
}

static inline void telemetry_cpu_end(TelemetrySystem *t) {
    Uint64 now = SDL_GetPerformanceCounter();
    double elapsedUs = (double)(now - t->cpuStartCounter) * 1000000.0 / (double)t->timerFreq;
    float elapsedMs = (float)(elapsedUs / 1000.0);

    t->cpuTimeHistory[t->historyIdx] = elapsedMs;
}

static inline void telemetry_gpu_begin(TelemetrySystem *t) {
    t->gpuStartCounter = SDL_GetPerformanceCounter();
}

static inline void telemetry_gpu_end(TelemetrySystem *t) {
    Uint64 now = SDL_GetPerformanceCounter();
    double elapsedUs = (double)(now - t->gpuStartCounter) * 1000000.0 / (double)t->timerFreq;
    float elapsedMs = (float)(elapsedUs / 1000.0);

    t->gpuTimeHistory[t->historyIdx] = elapsedMs;
}

static inline void telemetry_frame_end(TelemetrySystem *t) {
    Uint64 now = SDL_GetPerformanceCounter();
    double totalUs = (double)(now - t->frameStartCounter) * 1000000.0 / (double)t->timerFreq;
    float totalMs = (float)(totalUs / 1000.0);

    t->frameTimeHistory[t->historyIdx] = totalMs;
    t->historyIdx = (t->historyIdx + 1) % TELEMETRY_HISTORY_SIZE;

    /* Promedios móviles */
    float avgFrameMs = 0.0f, avgCpuMs = 0.0f, avgGpuMs = 0.0f;
    for (int i = 0; i < TELEMETRY_HISTORY_SIZE; i++) {
        avgFrameMs += t->frameTimeHistory[i];
        avgCpuMs += t->cpuTimeHistory[i];
        avgGpuMs += t->gpuTimeHistory[i];
    }
    avgFrameMs /= TELEMETRY_HISTORY_SIZE;
    avgCpuMs /= TELEMETRY_HISTORY_SIZE;
    avgGpuMs /= TELEMETRY_HISTORY_SIZE;

    t->frameTimeMs = avgFrameMs;
    t->cpuTimeMs = avgCpuMs;
    t->gpuTimeMs = avgGpuMs;
    t->fps = (avgFrameMs > 0.0001f) ? (1000.0f / avgFrameMs) : 0.0f;

    /* Presupuesto respecto a 16.66 ms (60 FPS) */
    t->frameBudgetPct = (avgFrameMs / 16.6667f) * 100.0f;

    /* Culling Efficiency ISO 25010 */
    if (t->totalVerts > 0) {
        t->cullingEfficiencyPct = (1.0f - ((float)t->visibleVerts / (float)t->totalVerts)) * 100.0f;
    } else {
        t->cullingEfficiencyPct = 0.0f;
    }
}

#endif /* TELEMETRY_H */
