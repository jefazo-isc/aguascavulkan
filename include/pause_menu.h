#ifndef PAUSE_MENU_H
#define PAUSE_MENU_H

#include <SDL2/SDL.h>
#include "vulkan_types.h"
#include "math_camera.h"
#include "debug_overlay.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* =========================================================================
 * PRESETS Y DATOS DE CONFIGURACIÓN
 * ========================================================================= */

typedef struct {
    const char *name;
    float hour;
    const char *desc;
} TimePreset;

typedef struct {
    const char *label;
    float scale;
    const char *desc;
} TimeSpeed;

typedef struct {
    const char *name;
    Vec3 pos;
    float yaw;
    float pitch;
    const char *info;
} TeleportTarget;

typedef struct {
    const char *name;
    float speed;
} CamSpeed;

#define NUM_TIME_PRESETS    6
#define NUM_TIME_SPEEDS     6
#define NUM_TELEPORT_TARGETS 5
#define NUM_CAM_SPEEDS      3

/* Tablas de datos (definidas en src/pause_menu.c) */
extern const TimePreset    g_timePresets[NUM_TIME_PRESETS];
extern const TimeSpeed     g_timeSpeeds[NUM_TIME_SPEEDS];
extern const TeleportTarget g_teleportTargets[NUM_TELEPORT_TARGETS];
extern const CamSpeed      g_camSpeeds[NUM_CAM_SPEEDS];

/* =========================================================================
 * ÍNDICES DEL MENÚ
 * ========================================================================= */

enum {
    MENU_RESUME = 0,
    MENU_TIME_SCALE,
    MENU_TIME_PRESET,
    MENU_HOUR_STEP,
    MENU_TIME_FREEZE,
    MENU_TELEPORT,
    MENU_CULLING,
    MENU_TELEMETRY,
    MENU_CAM_SPEED,
    MENU_TRAFFIC_MODE,
    MENU_FLASHLIGHT,
    MENU_QUIT,
    MENU_COUNT
};

/* =========================================================================
 * API PÚBLICA (implementación en src/pause_menu.c)
 * ========================================================================= */

void pause_menu_notify(VulkanEngine *eng, const char *fmt, ...);
void pause_menu_toggle_flashlight(VulkanEngine *eng);
void pause_menu_cycle_time_scale(VulkanEngine *eng, int direction);
void pause_menu_apply_time_preset(VulkanEngine *eng, int presetIdx);
void pause_menu_adjust_hour(VulkanEngine *eng, float deltaHours);
void pause_menu_toggle_time_freeze(VulkanEngine *eng);
void pause_menu_apply_teleport(VulkanEngine *eng, int targetIdx);
void pause_menu_toggle_culling(VulkanEngine *eng);
void pause_menu_toggle_telemetry(VulkanEngine *eng);
void pause_menu_cycle_cam_speed(VulkanEngine *eng, int direction);
void pause_menu_cycle_traffic_mode(VulkanEngine *eng, int direction);
void pause_menu_toggle_fullscreen(VulkanEngine *eng);
int  pause_menu_handle_hotkeys(VulkanEngine *eng, SDL_Keycode key);
void pause_menu_handle_key(VulkanEngine *eng, SDL_Keycode key, int *outRunning);
void pause_menu_render_notification(DebugOverlay *ov, VulkanEngine *eng);
void pause_menu_render(DebugOverlay *ov, VulkanEngine *eng);

#endif /* PAUSE_MENU_H */
