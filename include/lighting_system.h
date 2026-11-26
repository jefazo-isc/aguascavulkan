#ifndef LIGHTING_SYSTEM_H
#define LIGHTING_SYSTEM_H

#include "math_camera.h"
#include "traffic_system.h"
#include <stdint.h>
#include <stddef.h>
#include <math.h>

#define MAX_GPU_LIGHTS   64
#define MAX_STREETLIGHTS 256

/* -------------------------------------------------------------------------
 * Tipos de datos GPU / CPU
 * ---------------------------------------------------------------------- */

/* Estructura GPU para cada luz puntual (alineación vec4 std140) */
typedef struct {
    float posRadius[4];      /* xyz: posición mundo (m), w: radio de alcance (m) */
    float colorIntensity[4]; /* rgb: color normalizado (0..1), w: intensidad     */
} GpuLight;

/* Bloque UBO transferido al Fragment Shader */
typedef struct {
    GpuLight lights[MAX_GPU_LIGHTS];
    int   lightCount;
    float flashlightOn;
    float pad0;
    float pad1;
    float flashPos[4];   /* xyz: posición linterna, w: alcance (m)         */
    float flashDir[4];   /* xyz: dirección frontal, w: cos(spot angle)     */
    float sunDir[4];     /* xyz: dirección del sol, w: intensidad ambiental */
    float skyColor[4];   /* rgb: color del cielo, a: factor nocturno        */
    float timeParams[4]; /* x: simHour (0-24), yzw: camPos (x, y, z)       */
} LightingUBO;

/* Representación interna de una farola */
typedef struct {
    float x, y, z;
    float r, g, b;
    float radius;
    float baseIntensity;
} SceneLight;

/* Sistema integral de iluminación */
typedef struct {
    SceneLight streetlights[MAX_STREETLIGHTS];
    int streetlightCount;
    int flashlightEnabled; /* 1 = Linterna activa, 0 = inactiva */
} LightingSystem;

/* Estructura auxiliar (interna a lighting_system.c) expuesta para tests */
typedef struct {
    float distSq;
    GpuLight light;
} CandidateLight;

/* -------------------------------------------------------------------------
 * Tabla de beacons Gemini AI (antes eran floats hardcodeados en la función)
 * Modifica este array para reubicar las balizas sin tocar la lógica.
 * ---------------------------------------------------------------------- */
typedef struct {
    float x, y, z;
    float radius;
    float r, g, b;
    float intensity;
    const char *label;
} LightingBeacon;

#define LIGHTING_NUM_BEACONS 2
extern const LightingBeacon g_lighting_beacons[LIGHTING_NUM_BEACONS];

/* -------------------------------------------------------------------------
 * API pública (implementación en src/lighting_system.c)
 * ---------------------------------------------------------------------- */

void lighting_system_init(LightingSystem *sys, const TrafficSystem *trafficSys);
void lighting_system_toggle_flashlight(LightingSystem *sys);
void lighting_system_update(LightingSystem *sys,
                            const TrafficSystem *trafficSys,
                            float simHour,
                            const Vec3 *camPos,
                            const Vec3 *camForward,
                            LightingUBO *outUbo);

#endif /* LIGHTING_SYSTEM_H */
