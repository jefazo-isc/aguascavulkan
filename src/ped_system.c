/* ped_system.c - Sistema de simulación de peatones en StreetVulkan
 *
 * Administra el ciclo de vida de entidades peatonales (inicialización,
 * reserva dinámica, liberación y actualización por frame sincronizada
 * con el estado de los semáforos vehiculares).
 */
#include "ped_system.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Inicializa el arreglo dinámico de peatones con capacidad inicial opcional. */
void ped_system_init(PedestrianSystem* sys, size_t initial_capacity) {
    if (!sys) return;
    memset(sys, 0, sizeof(PedestrianSystem));
    if (initial_capacity > 0) {
        sys->peds = (Pedestrian*)calloc(initial_capacity, sizeof(Pedestrian));
        if (sys->peds) {
            sys->capacity = initial_capacity;
        }
    }
}

/* Libera toda la memoria asignada y reinicia contadores del sistema peatonal. */
void ped_system_free(PedestrianSystem* sys) {
    if (!sys) return;
    free(sys->peds);
    sys->peds = NULL;
    sys->count = 0;
    sys->capacity = 0;
}

/* Inserta un nuevo peatón creciendo el buffer exponencialmente si es necesario. */
int ped_system_spawn(PedestrianSystem* sys, const Pedestrian* ped) {
    if (!sys || !ped) return 0;
    if (sys->count >= sys->capacity) {
        size_t new_cap = (sys->capacity == 0) ? 16 : sys->capacity * 2;
        Pedestrian* grown = (Pedestrian*)realloc(sys->peds, new_cap * sizeof(Pedestrian));
        if (!grown) return 0;
        sys->peds = grown;
        sys->capacity = new_cap;
    }
    sys->peds[sys->count++] = *ped;
    return 1;
}

/* Actualiza estado y desplazamiento peatonal respetando cruces semaforizados. */
void ped_system_update(PedestrianSystem* sys, const TrafficSystem* traffic, float deltaTime) {
    if (!sys || deltaTime <= 0.0f) return;

    const float signal_check_radius = 12.0f;

    for (size_t i = 0; i < sys->count; i++) {
        Pedestrian* p = &sys->peds[i];

        if (traffic && p->state != PED_WALKING) {
            TrafficLightState light = traffic_system_get_light_state_at(
                traffic, p->pos[0], p->pos[2], signal_check_radius);
            /* Si el semáforo vehicular está en verde o ámbar, el peatón espera;
               cuando pasa a rojo vehicular, puede cruzar. */
            if (light == TRAFFIC_LIGHT_GREEN || light == TRAFFIC_LIGHT_AMBER) {
                p->state = PED_WAITING_RED;
                continue;
            } else if (light == TRAFFIC_LIGHT_RED) {
                p->state = PED_CROSSING;
            }
        }

        if (p->state == PED_WAITING_RED) {
            continue;
        }

        float step = p->speed * deltaTime;
        p->pos[0] += cosf(p->heading) * step;
        p->pos[2] += sinf(p->heading) * step;
    }
}
