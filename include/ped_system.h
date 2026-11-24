#ifndef PED_SYSTEM_H
#define PED_SYSTEM_H

#include <stdint.h>
#include <stddef.h>
#include "traffic_system.h"

typedef enum {
    PED_WALKING = 0,
    PED_WAITING_RED = 1,
    PED_CROSSING = 2
} PedestrianState;

typedef struct {
    float pos[3];
    float heading;
    float speed;
    uint32_t current_sidewalk_idx;
    PedestrianState state;
    float tint[4];
} Pedestrian;

typedef struct {
    Pedestrian* peds;
    size_t count;
    size_t capacity;
} PedestrianSystem;

void ped_system_init(PedestrianSystem* sys, size_t initial_capacity);
void ped_system_free(PedestrianSystem* sys);

/* Registra un peatón en el sistema; devuelve 1 si tuvo éxito, 0 si falla memoria. */
int ped_system_spawn(PedestrianSystem* sys, const Pedestrian* ped);

/* Actualiza cinemática y estado semafórico de los peatones a paso deltaTime. */
void ped_system_update(PedestrianSystem* sys, const TrafficSystem* traffic, float deltaTime);

#endif /* PED_SYSTEM_H */
