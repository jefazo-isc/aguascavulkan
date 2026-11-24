#include "traffic_system.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vulkan_types.h"

void traffic_system_init(TrafficSystem* sys) {
    memset(sys, 0, sizeof(TrafficSystem));
    sys->intersectionCapacity = 64;
    sys->signalCapacity = 256;
    sys->intersections = calloc(sys->intersectionCapacity, sizeof(TrafficIntersection));
    sys->signals = calloc(sys->signalCapacity, sizeof(TrafficSignal));
}

void traffic_system_free(TrafficSystem* sys) {
    if (!sys) return;
    if (sys->lensTemplateVertices) {
        free(sys->lensTemplateVertices);
        sys->lensTemplateVertices = NULL;
    }
    if (sys->intersections) {
        free(sys->intersections);
        sys->intersections = NULL;
    }
    if (sys->signals) {
        free(sys->signals);
        sys->signals = NULL;
    }
    memset(sys, 0, sizeof(TrafficSystem));
}

TrafficIntersection* traffic_system_get_or_create_intersection(TrafficSystem* sys, int intersectionId) {
    if (!sys) return NULL;
    for (size_t i = 0; i < sys->intersectionCount; ++i) {
        if (sys->intersections[i].id == intersectionId) {
            return &sys->intersections[i];
        }
    }

    if (sys->intersectionCount >= sys->intersectionCapacity) {
        size_t newCap = sys->intersectionCapacity ? sys->intersectionCapacity * 2 : 64;
        TrafficIntersection* newArr = realloc(sys->intersections, newCap * sizeof(TrafficIntersection));
        if (!newArr) return NULL;
        sys->intersections = newArr;
        sys->intersectionCapacity = newCap;
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

static int find_intersection_index(const TrafficSystem* sys, int intersectionId) {
    for (size_t i = 0; i < sys->intersectionCount; ++i) {
        if (sys->intersections[i].id == intersectionId) {
            return (int)i;
        }
    }
    return -1;
}

static TrafficIntersection* resolve_signal_intersection(const TrafficSystem* sys, TrafficSignal* sig) {
    int idx = sig->intersectionIndex;
    if (idx >= 0 && (size_t)idx < sys->intersectionCount &&
        sys->intersections[idx].id == sig->intersectionId) {
        return &sys->intersections[idx];
    }
    int found = find_intersection_index(sys, sig->intersectionId);
    sig->intersectionIndex = found;
    return (found >= 0) ? &sys->intersections[found] : NULL;
}

void traffic_system_add_signal(TrafficSystem* sys, TrafficSignal signal) {
    if (!sys) return;
    if (sys->signalCount >= sys->signalCapacity) {
        size_t newCap = sys->signalCapacity ? sys->signalCapacity * 2 : 256;
        TrafficSignal* newSignals = realloc(sys->signals, newCap * sizeof(TrafficSignal));
        if (!newSignals) return;
        sys->signals = newSignals;
        sys->signalCapacity = newCap;
    }
    if (signal.intersectionIndex < 0 ||
        (size_t)signal.intersectionIndex >= sys->intersectionCount ||
        sys->intersections[signal.intersectionIndex].id != signal.intersectionId) {
        signal.intersectionIndex = find_intersection_index(sys, signal.intersectionId);
    }
    sys->signals[sys->signalCount++] = signal;
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

static int parse_dir_angle(const char* line, float* outAngle) {
    const char* da = strstr(line, "\"dir_angle\"");
    if (!da) return 0;
    float angle = 0.0f;
    if (sscanf(da, "\"dir_angle\" : %f", &angle) == 1 && isfinite(angle)) {
        *outAngle = angle;
        return 1;
    }
    return 0;
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
        if (line[0] != '{') continue;

        int id = 0, interId = 0, phase = 0;
        float x = 0.0f, y = 0.0f, z = 0.0f;
        
        if (sscanf(line, "{\"id\": %d, \"intersection\": %d, \"phase\": %d, \"x\": %f, \"y\": %f, \"z\": %f",
                   &id, &interId, &phase, &x, &y, &z) < 6) {
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
        sig.intersectionIndex = -1;
        sig.phaseGroup = phase;
        sig.x = x;
        sig.y = y;
        sig.z = z;
        if (parse_dir_angle(line, &sig.dirAngle)) {
            sig.hasDirAngle = 1;
        }

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
    printf("[Tráfico] Cargados %zu semáforos (%zu intersecciones)\n", loaded, sys->intersectionCount);
    return 1;
}

static void build_procedural_lens_quad(Vertex q[6], const TrafficSignal* sig, float hy, const float color[3]) {
    const float rad = 0.10f;
    float ca, sa;
    if (sig->hasDirAngle) {
        ca = cosf(sig->dirAngle);
        sa = sinf(sig->dirAngle);
    } else if (sig->phaseGroup == 0) {
        ca = 1.0f;
        sa = 0.0f;
    } else {
        ca = 0.0f;
        sa = 1.0f;
    }
    float hx = sig->x + 0.155f * ca;
    float hz = sig->z + 0.155f * sa;
    float px = -sa * rad;
    float pz = ca * rad;

    Vertex v = {0};
    v.nx = ca;
    v.ny = 0.0f;
    v.nz = sa;
    v.r = color[0];
    v.g = color[1];
    v.b = color[2];
    v.a = 0.95f;
    v.emission = 0.0f;

    q[0] = v; q[0].x = hx - px; q[0].y = hy - rad; q[0].z = hz - pz;
    q[1] = v; q[1].x = hx + px; q[1].y = hy - rad; q[1].z = hz + pz;
    q[2] = v; q[2].x = hx + px; q[2].y = hy + rad; q[2].z = hz + pz;
    q[3] = v; q[3].x = hx - px; q[3].y = hy - rad; q[3].z = hz - pz;
    q[4] = v; q[4].x = hx + px; q[4].y = hy + rad; q[4].z = hz + pz;
    q[5] = v; q[5].x = hx - px; q[5].y = hy + rad; q[5].z = hz - pz;
}

int traffic_system_init_gpu(TrafficSystem* sys, VulkanEngine* eng, const Vertex* initialVertexData, size_t totalVertices) {
    if (!sys || sys->signalCount == 0 || !eng) return 0;

    // 1. Calcular total de vértices requeridos para los lentes
    size_t totalLensVerts = 0;
    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        sig->redLens.localOffset = totalLensVerts;
        size_t rc = sig->redLens.vertexCount > 0 ? sig->redLens.vertexCount : 6;
        totalLensVerts += rc;

        sig->amberLens.localOffset = totalLensVerts;
        size_t ac = sig->amberLens.vertexCount > 0 ? sig->amberLens.vertexCount : 6;
        totalLensVerts += ac;

        sig->greenLens.localOffset = totalLensVerts;
        size_t gc = sig->greenLens.vertexCount > 0 ? sig->greenLens.vertexCount : 6;
        totalLensVerts += gc;
    }

    sys->totalLensVertices = totalLensVerts;
    sys->lensTemplateVertices = calloc(totalLensVerts, sizeof(Vertex));
    if (!sys->lensTemplateVertices) return 0;

    // 2. Extraer vértices de lentes de la malla estática o generarlos proceduralmente
    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        TrafficLens* lenses[3] = { &sig->redLens, &sig->amberLens, &sig->greenLens };
        float colors[3][3] = {
            { 1.0f, 0.04f, 0.04f },  // Rojo
            { 1.0f, 0.65f, 0.0f },   // Ámbar
            { 0.0f, 1.0f, 0.35f }    // Verde
        };
        float offsetsY[3] = { 0.30f, 0.0f, -0.30f };

        for (int l = 0; l < 3; ++l) {
            TrafficLens* lens = lenses[l];
            size_t count = lens->vertexCount > 0 ? lens->vertexCount : 6;

            if (lens->vertexCount > 0 && initialVertexData && (lens->vertexStartIndex + count <= totalVertices)) {
                for (size_t v = 0; v < count; ++v) {
                    Vertex vert = initialVertexData[lens->vertexStartIndex + v];
                    // Ligero desplazamiento según la normal (+3mm) para eliminar z-fighting con la carcasa estática
                    vert.x += vert.nx * 0.003f;
                    vert.y += vert.ny * 0.003f;
                    vert.z += vert.nz * 0.003f;
                    vert.r = colors[l][0];
                    vert.g = colors[l][1];
                    vert.b = colors[l][2];
                    vert.emission = 0.0f;
                    sys->lensTemplateVertices[lens->localOffset + v] = vert;
                }
            } else {
                // Fallback procedural: generar quad de 2 triángulos orientado según el eje de fase
                Vertex q[6];
                build_procedural_lens_quad(q, sig, sig->y + offsetsY[l], colors[l]);
                for (int k = 0; k < 6; ++k) {
                    sys->lensTemplateVertices[lens->localOffset + k] = q[k];
                }
                lens->vertexCount = 6;
            }
        }
    }

    // 3. Crear los buffers dinámicos en hostVisiblePool (uno por frame in flight)
    VkDeviceSize bufSize = totalLensVerts * sizeof(Vertex);
    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; ++i) {
        VkBufferCreateInfo bi = {
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = bufSize,
            .usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE
        };
        if (vkCreateBuffer(eng->device, &bi, NULL, &sys->lensBuffers[i]) != VK_SUCCESS) {
            fprintf(stderr, "[Tráfico GPU] Error creando buffer de lentes %d\n", i);
            return 0;
        }
        VulkanSuballocation sub;
        if (!vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, sys->lensBuffers[i], &sub)) {
            fprintf(stderr, "[Tráfico GPU] Error vinculando buffer de lentes %d a hostVisiblePool\n", i);
            return 0;
        }
        if (!sub.mappedPtr) {
            fprintf(stderr, "[Tráfico GPU] Error: sub.mappedPtr es nulo para buffer de lentes %d\n", i);
            return 0;
        }
        sys->mappedLensDatas[i] = (Vertex*)sub.mappedPtr;
        memcpy(sys->mappedLensDatas[i], sys->lensTemplateVertices, bufSize);
    }

    printf("[Tráfico GPU] 🚦 Sistema de lentes desacoplado en GPU listo (%zu vértices = %.1f KB por frame)\n",
           totalLensVerts, (double)bufSize / 1024.0);
    return 1;
}

void traffic_system_free_gpu(TrafficSystem* sys, VkDevice device) {
    if (!sys) return;
    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; ++i) {
        sys->mappedLensDatas[i] = NULL;
        if (sys->lensBuffers[i] != VK_NULL_HANDLE) {
            vkDestroyBuffer(device, sys->lensBuffers[i], NULL);
            sys->lensBuffers[i] = VK_NULL_HANDLE;
        }
    }
    if (sys->lensTemplateVertices) {
        free(sys->lensTemplateVertices);
        sys->lensTemplateVertices = NULL;
    }
    sys->totalLensVertices = 0;
}

void traffic_system_update_simulation(TrafficSystem* sys, float deltaTime) {
    if (!sys || sys->intersectionCount == 0) return;

    // 1. Actualizar temporizadores y fases de intersecciones (Lógica determinista de 6 fases)
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

    // 2. Resolver estado lógico de cada semáforo según su intersección (O(1) con índice cacheado)
    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        TrafficIntersection* in = resolve_signal_intersection(sys, sig);
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
    }
}

void traffic_system_force_mode(TrafficSystem* sys, int mode) {
    if (!sys) return;
    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        if (mode == 1) { // Todos VERDE
            sig->currentState = TRAFFIC_LIGHT_GREEN;
        } else if (mode == 2) { // Todos ROJO
            sig->currentState = TRAFFIC_LIGHT_RED;
        }
    }
}

void traffic_system_update_gpu_frame(TrafficSystem* sys, uint32_t frameIdx) {
    if (!sys || sys->totalLensVertices == 0 || frameIdx >= MAX_FRAMES_IN_FLIGHT) return;
    Vertex* mapped = sys->mappedLensDatas[frameIdx];
    if (!mapped) return;

    for (size_t s = 0; s < sys->signalCount; ++s) {
        TrafficSignal* sig = &sys->signals[s];
        TrafficLens* lenses[3] = { &sig->redLens, &sig->amberLens, &sig->greenLens };
        TrafficLightState states[3] = { TRAFFIC_LIGHT_RED, TRAFFIC_LIGHT_AMBER, TRAFFIC_LIGHT_GREEN };
        float colors[3][3] = {
            { 1.0f, 0.04f, 0.04f },
            { 1.0f, 0.65f, 0.0f },
            { 0.0f, 1.0f, 0.35f }
        };

        for (int l = 0; l < 3; ++l) {
            TrafficLens* lens = lenses[l];
            int isActive = (sig->currentState == states[l]);
            size_t off = lens->localOffset;
            size_t cnt = lens->vertexCount > 0 ? lens->vertexCount : 6;

            for (size_t v = 0; v < cnt; ++v) {
                if (off + v < sys->totalLensVertices) {
                    if (isActive) {
                        mapped[off + v].r = colors[l][0];
                        mapped[off + v].g = colors[l][1];
                        mapped[off + v].b = colors[l][2];
                        mapped[off + v].emission = 6.0f;
                    } else {
                        mapped[off + v].r = 0.03f;
                        mapped[off + v].g = 0.03f;
                        mapped[off + v].b = 0.04f;
                        mapped[off + v].emission = 0.0f;
                    }
                }
            }
        }
    }
}

void traffic_system_render(TrafficSystem* sys, VkCommandBuffer cmd, uint32_t frameIdx, VkBuffer staticDummy) {
    if (!sys || sys->totalLensVertices == 0 || frameIdx >= MAX_FRAMES_IN_FLIGHT) return;
    if (sys->lensBuffers[frameIdx] == VK_NULL_HANDLE) return;

    VkBuffer bufs[] = { sys->lensBuffers[frameIdx], staticDummy };
    VkDeviceSize offs[] = { 0, 0 };
    vkCmdBindVertexBuffers(cmd, 0, 2, bufs, offs);
    vkCmdDraw(cmd, (uint32_t)sys->totalLensVertices, 1, 0, 0);
}

void traffic_system_update(TrafficSystem* sys, float deltaTime, Vertex* vertexBufferMapped, size_t maxVertices) {
    (void)vertexBufferMapped; (void)maxVertices;
    traffic_system_update_simulation(sys, deltaTime);
}

void traffic_system_apply_visuals(TrafficSystem* sys, Vertex* vertexBufferMapped, size_t maxVertices) {
    (void)sys; (void)vertexBufferMapped; (void)maxVertices;
}

TrafficLightState traffic_system_get_light_state_at(const TrafficSystem* sys, float x, float z, float maxRadius) {
    if (!sys || sys->signalCount == 0) return TRAFFIC_LIGHT_GREEN;

    float bestDistSq = maxRadius * maxRadius;
    TrafficLightState bestState = TRAFFIC_LIGHT_GREEN;
    int found = 0;

    for (size_t s = 0; s < sys->signalCount; ++s) {
        const TrafficSignal* sig = &sys->signals[s];
        float dx = sig->x - x;
        float dz = sig->z - z;
        float distSq = dx * dx + dz * dz;
        if (distSq < bestDistSq) {
            bestDistSq = distSq;
            bestState = sig->currentState;
            found = 1;
        }
    }

    return found ? bestState : TRAFFIC_LIGHT_GREEN;
}
