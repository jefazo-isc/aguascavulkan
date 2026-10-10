#include "traffic_system.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void traffic_system_init(TrafficSystem* sys) {
    memset(sys, 0, sizeof(TrafficSystem));
    sys->intersectionCapacity = 64;
    sys->signalCapacity = 256;
    sys->intersections = calloc(sys->intersectionCapacity, sizeof(TrafficIntersection));
    sys->signals = calloc(sys->signalCapacity, sizeof(TrafficSignal));
}

void traffic_system_free(TrafficSystem* sys) {
    free(sys->intersections);
    free(sys->signals);
    memset(sys, 0, sizeof(TrafficSystem));
}

TrafficIntersection* traffic_system_get_or_create_intersection(TrafficSystem* sys, int intersectionId) {
    for (size_t i = 0; i < sys->intersectionCount; ++i) {
        if (sys->intersections[i].id == intersectionId) {
            return &sys->intersections[i];
        }
    }

    if (sys->intersectionCount >= sys->intersectionCapacity) {
        sys->intersectionCapacity *= 2;
        sys->intersections = realloc(sys->intersections, sys->intersectionCapacity * sizeof(TrafficIntersection));
    }

    TrafficIntersection* inter = &sys->intersections[sys->intersectionCount++];
    memset(inter, 0, sizeof(TrafficIntersection));
    inter->id = intersectionId;
    inter->timer = 0.0f;
    inter->currentPhase = 0;
    inter->greenDuration = 10.0f;
    inter->amberDuration = 3.0f;
    inter->allRedDuration = 1.0f;

    return inter;
}

void traffic_system_add_signal(TrafficSystem* sys, TrafficSignal signal) {
    if (sys->signalCount >= sys->signalCapacity) {
        sys->signalCapacity *= 2;
        sys->signals = realloc(sys->signals, sys->signalCapacity * sizeof(TrafficSignal));
    }
    sys->signals[sys->signalCount++] = signal;
}

static void set_lens_visual(TrafficLens* lens, int isActive, float r, float g, float b, Vertex* vertices, size_t maxVertices) {
    if (!lens || lens->vertexCount == 0 || !vertices) return;
    for (size_t i = 0; i < lens->vertexCount; ++i) {
        size_t idx = lens->vertexStartIndex + i;
        if (maxVertices > 0 && idx >= maxVertices) continue; // Validación de límites del buffer
        if (isActive) {
            vertices[idx].r = r;
            vertices[idx].g = g;
            vertices[idx].b = b;
            vertices[idx].emission = 6.0f;
        } else {
            // Lente inactivo: Cristal ahumado oscuro completamente apagado
            vertices[idx].r = 0.03f;
            vertices[idx].g = 0.03f;
            vertices[idx].b = 0.04f;
            vertices[idx].emission = 0.0f;
        }
    }
}

// Función auxiliar para buscar y extraer el start/count de un color en el JSON de una línea
static int parse_lens_data(const char* line, const char* color, size_t* outStart, size_t* outCount) {
    char key[32];
    snprintf(key, sizeof(key), "\"%s\"", color);
    
    const char* p = strstr(line, key);
    if (!p) return 0;
    
    const char* s = strstr(p, "\"start\"");
    if (!s) return 0;
    
    const char* c = strstr(s, "\"count\"");
    if (!c) return 0;
    
    int start = 0, count = 0;
    // Tolerar variaciones de espaciado en la serialización JSON
    if (sscanf(s, "\"start\": %d", &start) != 1) {
        if (sscanf(s, "\"start\":%d", &start) != 1) return 0;
    }
    if (sscanf(c, "\"count\": %d", &count) != 1) {
        if (sscanf(c, "\"count\":%d", &count) != 1) return 0;
    }
    
    *outStart = (size_t)start;
    *outCount = (size_t)count;
    return 1;
}

int traffic_system_load_json(TrafficSystem* sys, const char* jsonPath) {
    FILE* f = fopen(jsonPath, "r");
    if (!f) {
        fprintf(stderr, "[Tráfico] No se pudo abrir %s\n", jsonPath);
        return 0;
    }

    char line[4096];
    size_t loaded = 0;

    while (fgets(line, sizeof(line), f)) {
        // Solo procesar líneas que abran un objeto JSON
        if (line[0] != '{') continue;

        int id = 0, interId = 0, phase = 0;
        float x = 0.0f, y = 0.0f, z = 0.0f;
        
        // Parsear base del semáforo
        if (sscanf(line, "{\"id\": %d, \"intersection\": %d, \"phase\": %d, \"x\": %f, \"y\": %f, \"z\": %f",
                   &id, &interId, &phase, &x, &y, &z) < 6) {
            // Intento secundario sin espacios
            if (sscanf(line, "{\"id\":%d,\"intersection\":%d,\"phase\":%d,\"x\":%f,\"y\":%f,\"z\":%f",
                       &id, &interId, &phase, &x, &y, &z) < 6) {
                continue;
            }
        }

        traffic_system_get_or_create_intersection(sys, interId);
        
        TrafficSignal sig;
        memset(&sig, 0, sizeof(TrafficSignal));
        sig.id = id;
        sig.intersectionId = interId;
        sig.phaseGroup = phase;
        sig.x = x;
        sig.y = y;
        sig.z = z;

        // Extraer los índices globales de los vértices
        size_t rs = 0, rc = 0, as_ = 0, ac = 0, gs = 0, gc = 0;
        
        if (parse_lens_data(line, "red", &rs, &rc)) {
            sig.redLens.vertexStartIndex = rs;
            sig.redLens.vertexCount = rc;
            sig.redLens.type = TRAFFIC_LIGHT_RED;
        }
        if (parse_lens_data(line, "amber", &as_, &ac)) {
            sig.amberLens.vertexStartIndex = as_;
            sig.amberLens.vertexCount = ac;
            sig.amberLens.type = TRAFFIC_LIGHT_AMBER;
        }
        if (parse_lens_data(line, "green", &gs, &gc)) {
            sig.greenLens.vertexStartIndex = gs;
            sig.greenLens.vertexCount = gc;
            sig.greenLens.type = TRAFFIC_LIGHT_GREEN;
        }

        traffic_system_add_signal(sys, sig);
        loaded++;
    }

    fclose(f);
    printf("[Tráfico] Cargados %zu semáforos (%zu intersecciones) con lentes globales\n", loaded, sys->intersectionCount);
    return 1;
}

void traffic_system_update(TrafficSystem* sys, float deltaTime, Vertex* vertexBufferMapped, size_t maxVertices) {
    if (!sys || sys->intersectionCount == 0 || !vertexBufferMapped) return;

    // 1. Actualizar temporizadores y fases de intersecciones (Lógica original de 6 fases)
    for (size_t i = 0; i < sys->intersectionCount; ++i) {
        TrafficIntersection* in = &sys->intersections[i];
        in->timer += deltaTime;

        switch (in->currentPhase) {
            case 0: // NS Verde, EO Rojo
                if (in->timer >= in->greenDuration) {
                    in->currentPhase = 1;
                    in->timer = 0.0f;
                }
                break;
            case 1: // NS Ámbar, EO Rojo
                if (in->timer >= in->amberDuration) {
                    in->currentPhase = 2;
                    in->timer = 0.0f;
                }
                break;
            case 2: // Todo Rojo (Seguridad)
                if (in->timer >= in->allRedDuration) {
                    in->currentPhase = 3;
                    in->timer = 0.0f;
                }
                break;
            case 3: // EO Verde, NS Rojo
                if (in->timer >= in->greenDuration) {
                    in->currentPhase = 4;
                    in->timer = 0.0f;
                }
                break;
            case 4: // EO Ámbar, NS Rojo
                if (in->timer >= in->amberDuration) {
                    in->currentPhase = 5;
                    in->timer = 0.0f;
                }
                break;
            case 5: // Todo Rojo (Seguridad)
                if (in->timer >= in->allRedDuration) {
                    in->currentPhase = 0;
                    in->timer = 0.0f;
                }
                break;
            default:
                in->currentPhase = 0;
                in->timer = 0.0f;
                break;
        }
    }

    // 2. Aplicar estados de emisión lumínica a los vértices mapeados
    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        TrafficIntersection* in = NULL;

        for (size_t i = 0; i < sys->intersectionCount; ++i) {
            if (sys->intersections[i].id == sig->intersectionId) {
                in = &sys->intersections[i];
                break;
            }
        }
        if (!in) continue;

        TrafficLightState currentLight = TRAFFIC_LIGHT_RED;

        if (sig->phaseGroup == 0) { // Eje Norte-Sur
            if (in->currentPhase == 0) currentLight = TRAFFIC_LIGHT_GREEN;
            else if (in->currentPhase == 1) currentLight = TRAFFIC_LIGHT_AMBER;
            else currentLight = TRAFFIC_LIGHT_RED;
        } else { // Eje Este-Oeste
            if (in->currentPhase == 3) currentLight = TRAFFIC_LIGHT_GREEN;
            else if (in->currentPhase == 4) currentLight = TRAFFIC_LIGHT_AMBER;
            else currentLight = TRAFFIC_LIGHT_RED;
        }

        sig->currentState = currentLight;

        set_lens_visual(&sig->redLens, currentLight == TRAFFIC_LIGHT_RED,
                        1.0f, 0.04f, 0.04f, vertexBufferMapped, maxVertices);
        set_lens_visual(&sig->amberLens, currentLight == TRAFFIC_LIGHT_AMBER,
                        1.0f, 0.65f, 0.0f, vertexBufferMapped, maxVertices);
        set_lens_visual(&sig->greenLens, currentLight == TRAFFIC_LIGHT_GREEN,
                        0.0f, 1.0f, 0.35f, vertexBufferMapped, maxVertices);
    }
}

void traffic_system_force_mode(TrafficSystem* sys, int mode, Vertex* vertexBufferMapped, size_t maxVertices) {
    if (!sys || !vertexBufferMapped) return;
    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        if (mode == 1) { // Todos VERDE
            sig->currentState = TRAFFIC_LIGHT_GREEN;
            set_lens_visual(&sig->redLens, 0, 1.0f, 0.04f, 0.04f, vertexBufferMapped, maxVertices);
            set_lens_visual(&sig->amberLens, 0, 1.0f, 0.65f, 0.0f, vertexBufferMapped, maxVertices);
            set_lens_visual(&sig->greenLens, 1, 0.0f, 1.0f, 0.35f, vertexBufferMapped, maxVertices);
        } else if (mode == 2) { // Todos ROJO
            sig->currentState = TRAFFIC_LIGHT_RED;
            set_lens_visual(&sig->redLens, 1, 1.0f, 0.04f, 0.04f, vertexBufferMapped, maxVertices);
            set_lens_visual(&sig->amberLens, 0, 1.0f, 0.65f, 0.0f, vertexBufferMapped, maxVertices);
            set_lens_visual(&sig->greenLens, 0, 0.0f, 1.0f, 0.35f, vertexBufferMapped, maxVertices);
        }
    }
}
