/*
 * lighting_system.c - Implementación del sistema de iluminación dinámica de StreetVulkan.
 * Extraído de include/lighting_system.h para evitar implementaciones en headers.
 */
#include "lighting_system.h"
#include <math.h>
#include <stddef.h>

/* -------------------------------------------------------------------------
 * Tabla de beacons Gemini AI.
 * Antes eran floats hardcodeados dentro de lighting_system_update().
 * Modifica este array para reubicar las balizas sin tocar la lógica.
 * ---------------------------------------------------------------------- */
const LightingBeacon g_lighting_beacons[LIGHTING_NUM_BEACONS] = {
    /* Beacon 1: Plaza / Centro (luz cyan vertical) */
    { 0.0f, 12.0f,  0.0f, 42.0f, 0.0f, 0.88f, 1.00f, 4.5f, "Plaza / Centro" },
    /* Beacon 2: Props AI este */
    { 25.0f, 14.0f, 35.0f, 36.0f, 0.1f, 0.95f, 0.85f, 4.2f, "Props AI Este"  },
};

void lighting_system_init(LightingSystem *sys, const TrafficSystem *trafficSys) {
    sys->streetlightCount = 0;
    sys->flashlightEnabled = 1; /* Linterna lista por defecto */

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
        sl->y = sig->y + 1.5f; /* Altura estándar de luminaria urbana (~6.5m sobre suelo) */
        sl->z = sig->z + 2.0f;
        /* Luz de vapor de sodio cálida / LED vial moderno (2800K - 3200K) */
        sl->r = 1.0f;
        sl->g = 0.76f;
        sl->b = 0.42f;
        sl->radius = 35.0f;
        sl->baseIntensity = 3.6f;
    }
}

void lighting_system_toggle_flashlight(LightingSystem *sys) {
    sys->flashlightEnabled = !sys->flashlightEnabled;
}

/* Recolecta luces dinámicas de semáforos dentro de 650m de la cámara. */
static void gather_traffic_lights(const TrafficSystem *trafficSys, const Vec3 *camPos,
                                  CandidateLight *candidates, int *candidateCount) {
    if (!trafficSys) return;
    for (size_t i = 0; i < trafficSys->signalCount && *candidateCount < 500; ++i) {
        const TrafficSignal *sig = &trafficSys->signals[i];
        float dx = sig->x - camPos->x;
        float dy = sig->y - camPos->y;
        float dz = sig->z - camPos->z;
        float d2 = dx * dx + dy * dy + dz * dz;
        if (d2 >= 650.0f * 650.0f) continue;

        CandidateLight *c = &candidates[(*candidateCount)++];
        c->distSq = d2;
        c->light.posRadius[0] = sig->x;
        c->light.posRadius[1] = sig->y;
        c->light.posRadius[2] = sig->z;
        c->light.posRadius[3] = 22.0f;

        if (sig->currentState == TRAFFIC_LIGHT_RED) {
            c->light.colorIntensity[0] = 1.0f; c->light.colorIntensity[1] = 0.04f; c->light.colorIntensity[2] = 0.04f;
        } else if (sig->currentState == TRAFFIC_LIGHT_AMBER) {
            c->light.colorIntensity[0] = 1.0f; c->light.colorIntensity[1] = 0.65f; c->light.colorIntensity[2] = 0.0f;
        } else {
            c->light.colorIntensity[0] = 0.0f; c->light.colorIntensity[1] = 1.0f;  c->light.colorIntensity[2] = 0.35f;
        }
        c->light.colorIntensity[3] = 4.2f;
    }
}

/* Recolecta luminarias viales activas durante atardecer/noche dentro de 700m. */
static void gather_streetlights(const LightingSystem *sys, const Vec3 *camPos, float streetFactor,
                                CandidateLight *candidates, int *candidateCount) {
    if (streetFactor <= 0.02f) return;
    for (int i = 0; i < sys->streetlightCount && *candidateCount < 500; ++i) {
        const SceneLight *sl = &sys->streetlights[i];
        float dx = sl->x - camPos->x;
        float dy = sl->y - camPos->y;
        float dz = sl->z - camPos->z;
        float d2 = dx * dx + dy * dy + dz * dz;
        if (d2 >= 700.0f * 700.0f) continue;

        CandidateLight *c = &candidates[(*candidateCount)++];
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

/* Recolecta balizas Gemini AI dentro de 850m de la cámara. */
static void gather_beacons(const Vec3 *camPos, CandidateLight *candidates, int *candidateCount) {
    for (int b = 0; b < LIGHTING_NUM_BEACONS && *candidateCount < 500; ++b) {
        const LightingBeacon *bk = &g_lighting_beacons[b];
        float dx = bk->x - camPos->x;
        float dy = bk->y - camPos->y;
        float dz = bk->z - camPos->z;
        float d2 = dx * dx + dy * dy + dz * dz;
        if (d2 >= 850.0f * 850.0f) continue;

        CandidateLight *c = &candidates[(*candidateCount)++];
        c->distSq = d2;
        c->light.posRadius[0] = bk->x;
        c->light.posRadius[1] = bk->y;
        c->light.posRadius[2] = bk->z;
        c->light.posRadius[3] = bk->radius;
        c->light.colorIntensity[0] = bk->r;
        c->light.colorIntensity[1] = bk->g;
        c->light.colorIntensity[2] = bk->b;
        c->light.colorIntensity[3] = bk->intensity;
    }
}

/* Selecciona las MAX_GPU_LIGHTS más cercanas mediante ordenamiento parcial. */
static void select_nearest_lights(CandidateLight *candidates, int candidateCount,
                                  LightingUBO *outUbo) {
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
}

void lighting_system_update(LightingSystem *sys,
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

    gather_traffic_lights(trafficSys, camPos, candidates, &candidateCount);
    gather_streetlights(sys, camPos, streetFactor, candidates, &candidateCount);
    gather_beacons(camPos, candidates, &candidateCount);
    select_nearest_lights(candidates, candidateCount, outUbo);

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
