#ifndef LIGHTING_SYSTEM_H
#define LIGHTING_SYSTEM_H

#include "math_camera.h"
#include "traffic_system.h"
#include <stdint.h>
#include <stddef.h>
#include <math.h>

#define MAX_GPU_LIGHTS 64
#define MAX_STREETLIGHTS 256

/* Estructura GPU para cada luz puntual (alineación vec4 std140) */
typedef struct {
    float posRadius[4];      // xyz: posición mundo (m), w: radio de alcance (m)
    float colorIntensity[4]; // rgb: color normalizado (0..1), w: intensidad luminosa
} GpuLight;

/* Bloque Uniform Buffer Object (UBO) transferido al Fragment Shader */
typedef struct {
    GpuLight lights[MAX_GPU_LIGHTS];
    int lightCount;
    float flashlightOn;
    float pad0;
    float pad1;
    float flashPos[4];   // xyz: posición linterna, w: alcance (m)
    float flashDir[4];   // xyz: dirección frontal, w: cos(spot angle)
    float sunDir[4];     // xyz: dirección del sol, w: intensidad ambiental
    float skyColor[4];   // rgb: color del cielo, a: factor nocturno (0.0=día, 1.0=noche)
    float timeParams[4]; // x: simHour (0-24), yzw: camPos (x, y, z)
} LightingUBO;

/* Representación interna de una fuente de luz en el mundo */
typedef struct {
    float x, y, z;
    float r, g, b;
    float radius;
    float baseIntensity;
} SceneLight;

/* Sistema integral de iluminación de la ciudad */
typedef struct {
    SceneLight streetlights[MAX_STREETLIGHTS];
    int streetlightCount;
    int flashlightEnabled; // 1 = Linterna activa, 0 = inactiva
} LightingSystem;

/* Inicializa las farolas de alumbrado público a lo largo de las intersecciones y avenidas */
static inline void lighting_system_init(LightingSystem *sys, const TrafficSystem *trafficSys) {
    sys->streetlightCount = 0;
    sys->flashlightEnabled = 1; // Linterna lista por defecto

    if (!trafficSys || trafficSys->signalCount == 0) return;

    /* Colocar farolas elevadas en cada intersección única */
    for (size_t i = 0; i < trafficSys->signalCount && sys->streetlightCount < MAX_STREETLIGHTS; ++i) {
        const TrafficSignal *sig = &trafficSys->signals[i];

        /* Verificar si ya hay una farola cercana a esta intersección para no duplicar */
        int alreadyExists = 0;
        for (int j = 0; j < sys->streetlightCount; ++j) {
            float dx = sys->streetlights[j].x - sig->x;
            float dz = sys->streetlights[j].z - sig->z;
            if (dx * dx + dz * dz < 25.0f * 25.0f) {
                alreadyExists = 1;
                break;
            }
        }
        if (alreadyExists) continue;

        SceneLight *sl = &sys->streetlights[sys->streetlightCount++];
        sl->x = sig->x + 2.0f;
        sl->y = sig->y + 1.5f; /* Altura estándar de luminaria urbana (~6.5m sobre suelo; sig->y ya incluye +5.0m) */
        sl->z = sig->z + 2.0f;
        /* Luz de vapor de sodio cálida / LED vial moderno (2800K - 3200K) */
        sl->r = 1.0f;
        sl->g = 0.76f;
        sl->b = 0.42f;
        sl->radius = 35.0f;
        sl->baseIntensity = 3.6f;
    }
}

static inline void lighting_system_toggle_flashlight(LightingSystem *sys) {
    sys->flashlightEnabled = !sys->flashlightEnabled;
}

/* Estructura auxiliar para ordenar luces candidatas por distancia a la cámara */
typedef struct {
    float distSq;
    GpuLight light;
} CandidateLight;

/* Actualiza las 64 luces más influyentes alrededor de la cámara para el fotograma actual */
static inline void lighting_system_update(LightingSystem *sys,
                                          const TrafficSystem *trafficSys,
                                          float simHour,
                                          const Vec3 *camPos,
                                          const Vec3 *camForward,
                                          LightingUBO *outUbo) {
    if (!outUbo) return;

    /* 1. Factor de intensidad del alumbrado público según la hora solar */
    float streetFactor = 0.0f;
    if (simHour >= 19.0f || simHour <= 5.5f) {
        streetFactor = 1.0f; /* Noche cerrada: Farolas al 100% */
    } else if (simHour > 17.5f && simHour < 19.0f) {
        streetFactor = (simHour - 17.5f) / 1.5f; /* Atardecer: Encendido gradual */
    } else if (simHour > 5.5f && simHour < 7.0f) {
        streetFactor = 1.0f - (simHour - 5.5f) / 1.5f; /* Amanecer: Apagado gradual */
    }

    CandidateLight candidates[512];
    int candidateCount = 0;

    /* 2. Luces dinámicas de Semáforos activos (Rojo, Ámbar o Verde) */
    if (trafficSys) {
        for (size_t i = 0; i < trafficSys->signalCount && candidateCount < 500; ++i) {
            const TrafficSignal *sig = &trafficSys->signals[i];
            float dx = sig->x - camPos->x;
            float dy = sig->y - camPos->y;
            float dz = sig->z - camPos->z;
            float d2 = dx * dx + dy * dy + dz * dz;

            /* Rango amplio de selección (650m) para que las luces no se apaguen a la distancia */
            if (d2 < 650.0f * 650.0f) {
                CandidateLight *c = &candidates[candidateCount++];
                c->distSq = d2;
                c->light.posRadius[0] = sig->x;
                c->light.posRadius[1] = sig->y; /* Altura real del cabezal */
                c->light.posRadius[2] = sig->z;
                c->light.posRadius[3] = 22.0f; /* Radio de luz proyectada sobre el cruce */

                if (sig->currentState == TRAFFIC_LIGHT_RED) {
                    c->light.colorIntensity[0] = 1.0f;
                    c->light.colorIntensity[1] = 0.04f;
                    c->light.colorIntensity[2] = 0.04f;
                    c->light.colorIntensity[3] = 4.2f;
                } else if (sig->currentState == TRAFFIC_LIGHT_AMBER) {
                    c->light.colorIntensity[0] = 1.0f;
                    c->light.colorIntensity[1] = 0.65f;
                    c->light.colorIntensity[2] = 0.0f;
                    c->light.colorIntensity[3] = 4.2f;
                } else { // GREEN
                    c->light.colorIntensity[0] = 0.0f;
                    c->light.colorIntensity[1] = 1.0f;
                    c->light.colorIntensity[2] = 0.35f;
                    c->light.colorIntensity[3] = 4.2f;
                }
            }
        }
    }

    /* 3. Farolas de Alumbrado Público (cuando cae la tarde o es de noche) */
    if (streetFactor > 0.02f) {
        for (int i = 0; i < sys->streetlightCount && candidateCount < 500; ++i) {
            const SceneLight *sl = &sys->streetlights[i];
            float dx = sl->x - camPos->x;
            float dy = sl->y - camPos->y;
            float dz = sl->z - camPos->z;
            float d2 = dx * dx + dy * dy + dz * dz;

            /* Rango amplio de cobertura (700m) para alumbrado vial continuo a larga distancia */
            if (d2 < 700.0f * 700.0f) {
                CandidateLight *c = &candidates[candidateCount++];
                c->distSq = d2;
                c->light.posRadius[0] = sl->x;
                c->light.posRadius[1] = sl->y;
                c->light.posRadius[2] = sl->z;
                c->light.posRadius[3] = sl->radius;
                c->light.colorIntensity[0] = sl->r;
                c->light.colorIntensity[1] = sl->g;
                c->light.colorIntensity[2] = sl->b;
                c->light.colorIntensity[3] = sl->baseIntensity * streetFactor;
            }
        }
    }

    /* 4. Balizas de Modelos Gemini AI (Beacons con luz vertical cyan) */
    {
        /* Beacon 1: Plaza / Centro */
        float bx1 = 0.0f, by1 = 12.0f, bz1 = 0.0f;
        float d2_1 = (bx1 - camPos->x)*(bx1 - camPos->x) + (by1 - camPos->y)*(by1 - camPos->y) + (bz1 - camPos->z)*(bz1 - camPos->z);
        if (d2_1 < 850.0f * 850.0f && candidateCount < 500) {
            CandidateLight *c = &candidates[candidateCount++];
            c->distSq = d2_1;
            c->light.posRadius[0] = bx1; c->light.posRadius[1] = by1; c->light.posRadius[2] = bz1;
            c->light.posRadius[3] = 42.0f;
            c->light.colorIntensity[0] = 0.0f; c->light.colorIntensity[1] = 0.88f; c->light.colorIntensity[2] = 1.0f;
            c->light.colorIntensity[3] = 4.5f;
        }

        /* Beacon 2: Props AI este */
        float bx2 = 25.0f, by2 = 14.0f, bz2 = 35.0f;
        float d2_2 = (bx2 - camPos->x)*(bx2 - camPos->x) + (by2 - camPos->y)*(by2 - camPos->y) + (bz2 - camPos->z)*(bz2 - camPos->z);
        if (d2_2 < 850.0f * 850.0f && candidateCount < 500) {
            CandidateLight *c = &candidates[candidateCount++];
            c->distSq = d2_2;
            c->light.posRadius[0] = bx2; c->light.posRadius[1] = by2; c->light.posRadius[2] = bz2;
            c->light.posRadius[3] = 36.0f;
            c->light.colorIntensity[0] = 0.1f; c->light.colorIntensity[1] = 0.95f; c->light.colorIntensity[2] = 0.85f;
            c->light.colorIntensity[3] = 4.2f;
        }
    }

    /* 5. Selección rápida de las 64 luces más cercanas por Insertion Sort parcial */
    int selectCount = candidateCount < MAX_GPU_LIGHTS ? candidateCount : MAX_GPU_LIGHTS;
    for (int i = 0; i < selectCount; ++i) {
        int bestIdx = i;
        for (int j = i + 1; j < candidateCount; ++j) {
            if (candidates[j].distSq < candidates[bestIdx].distSq) {
                bestIdx = j;
            }
        }
        if (bestIdx != i) {
            CandidateLight tmp = candidates[i];
            candidates[i] = candidates[bestIdx];
            candidates[bestIdx] = tmp;
        }
        outUbo->lights[i] = candidates[i].light;
    }
    outUbo->lightCount = selectCount;

    /* 6. Configurar Linterna de Inspección del Jugador */
    outUbo->flashlightOn = sys->flashlightEnabled ? 1.0f : 0.0f;
    outUbo->flashPos[0] = camPos->x;
    outUbo->flashPos[1] = camPos->y;
    outUbo->flashPos[2] = camPos->z;
    outUbo->flashPos[3] = 75.0f; /* 75 metros de alcance */

    outUbo->flashDir[0] = camForward->x;
    outUbo->flashDir[1] = camForward->y;
    outUbo->flashDir[2] = camForward->z;
    outUbo->flashDir[3] = 0.866f; /* Cono de apertura ~30° */
}

#endif /* LIGHTING_SYSTEM_H */
