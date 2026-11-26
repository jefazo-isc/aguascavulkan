/*
 * pause_menu.c - Implementación del menú de pausa y toasts de StreetVulkan.
 * Extraído de include/pause_menu.h para evitar implementaciones en headers.
 */
#include "pause_menu.h"
#include "lighting_system.h"
#include "debug_overlay.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <math.h>

/* -------------------------------------------------------------------------
 * Tablas de datos estáticos (antes eran static const en el header)
 * ---------------------------------------------------------------------- */

const TimePreset g_timePresets[NUM_TIME_PRESETS] = {
    {"12:00 Mediodia",   12.0f, "Cenit solar (Dia pleno)"},
    {"17:30 Atardecer",  17.5f, "Luz dorada rasante (Golden Hour)"},
    {"23:00 Medianoche", 23.0f, "Noche oscura y domo estelar"},
    {"06:30 Amanecer",    6.5f, "Primeros rayos matutinos"},
    {"09:00 Manana",      9.0f, "Luz diurna fresca"},
    {"20:00 Anochecer",  20.0f, "Crepusculo y farolas encendidas"},
};

const TimeSpeed g_timeSpeeds[NUM_TIME_SPEEDS] = {
    {"1.0x (Normal)",        1.0f,  "72 min reales = 24h sim"},
    {"5.0x (Rapido)",        5.0f,  "14.4 min reales = 24h sim"},
    {"15.0x (Acelerado)",   15.0f,  "4.8 min reales = 24h sim"},
    {"60.0x (Timelapse)",   60.0f,  "1 dia sim en 72s"},
    {"120.0x (Hiperlapso)", 120.0f, "1 dia sim en 36s"},
    {"300.0x (Ultra Rapido)", 300.0f, "1 dia sim en 14.4s"},
};

const TeleportTarget g_teleportTargets[NUM_TELEPORT_TARGETS] = {
    {"Plaza de la Patria (Centro)",  {0.0f,    15.0f,  25.0f},  180.0f, -10.0f, "Catedral y Teatro Morelos"},
    {"Viaducto / Puente Poniente",   {-450.0f, 22.0f, 120.0f},   90.0f,  -8.0f, "Paso vehicular elevado"},
    {"Cruce Principal Semaforos",    {-345.0f,  4.0f, 350.0f},  163.0f, -12.0f, "Interseccion activa"},
    {"Vista Aerea Panoramica",       {0.0f,   450.0f, 250.0f},  180.0f, -55.0f, "Sector urbano completo (450m)"},
    {"Modelos Gemini AI (Beacons)",  {25.0f,   12.0f,  35.0f},  215.0f, -15.0f, "Props IA con haz vertical"},
};

const CamSpeed g_camSpeeds[NUM_CAM_SPEEDS] = {
    {"15 m/s (Lenta / Inspeccion)", 15.0f},
    {"35 m/s (Normal)",             35.0f},
    {"85 m/s (Rapida / Vuelo)",     85.0f},
};

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* =========================================================================
 * ACCIONES Y TESTING
 * ========================================================================= */

void pause_menu_notify(VulkanEngine *eng, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vsnprintf(eng->notificationText, sizeof(eng->notificationText), fmt, args);
    va_end(args);
    eng->notificationTimer = 2.8f;
}

void pause_menu_toggle_flashlight(VulkanEngine *eng) {
    lighting_system_toggle_flashlight(&eng->lightingSystem);
    pause_menu_notify(eng, "[LINTERNA] Linterna frontal: %s",
        eng->lightingSystem.flashlightEnabled ? "ACTIVADA (Cono 75m)" : "DESACTIVADA");
}

void pause_menu_cycle_time_scale(VulkanEngine *eng, int direction) {
    eng->timeScaleIndex = (eng->timeScaleIndex + direction + NUM_TIME_SPEEDS) % NUM_TIME_SPEEDS;
    eng->timeScale = g_timeSpeeds[eng->timeScaleIndex].scale;
    pause_menu_notify(eng, "[TIEMPO] Velocidad: %s (%s)",
        g_timeSpeeds[eng->timeScaleIndex].label,
        g_timeSpeeds[eng->timeScaleIndex].desc);
}

void pause_menu_apply_time_preset(VulkanEngine *eng, int presetIdx) {
    presetIdx = (presetIdx + NUM_TIME_PRESETS) % NUM_TIME_PRESETS;
    eng->timePresetIndex = presetIdx;
    eng->simHour = g_timePresets[presetIdx].hour;
    pause_menu_notify(eng, "[HORA] %s - %s",
        g_timePresets[presetIdx].name,
        g_timePresets[presetIdx].desc);
}

void pause_menu_adjust_hour(VulkanEngine *eng, float deltaHours) {
    eng->simHour += deltaHours;
    if (eng->simHour >= 24.0f) eng->simHour = fmodf(eng->simHour, 24.0f);
    if (eng->simHour < 0.0f) eng->simHour += 24.0f;
    int h = (int)eng->simHour;
    int m = (int)((eng->simHour - (float)h) * 60.0f);
    const char *ph = (h >= 6 && h < 18) ? ((h < 8) ? "Amanecer" : (h > 16) ? "Atardecer" : "Dia") : "Noche";
    pause_menu_notify(eng, "[HORA] %02d:%02d (%s)", h, m, ph);
}

void pause_menu_toggle_time_freeze(VulkanEngine *eng) {
    eng->timeFrozen = !eng->timeFrozen;
    pause_menu_notify(eng, "[TIEMPO] Avance solar: %s",
        eng->timeFrozen ? "CONGELADO" : "EN TIEMPO REAL");
}

void pause_menu_apply_teleport(VulkanEngine *eng, int targetIdx) {
    targetIdx = (targetIdx + NUM_TELEPORT_TARGETS) % NUM_TELEPORT_TARGETS;
    const TeleportTarget *tgt = &g_teleportTargets[targetIdx];
    g_camera.pos = tgt->pos;
    g_camera.yaw = tgt->yaw;
    g_camera.pitch = tgt->pitch;
    pause_menu_notify(eng, "[TELEPORT] %s", tgt->name);
}

void pause_menu_toggle_culling(VulkanEngine *eng) {
    eng->cullingEnabled = !eng->cullingEnabled;
    pause_menu_notify(eng, "[RENDER] Frustum Culling: %s",
        eng->cullingEnabled ? "ACTIVADO (Chunks)" : "DESACTIVADO (Malla Completa)");
}

void pause_menu_toggle_telemetry(VulkanEngine *eng) {
    eng->showTelemetry = !eng->showTelemetry;
    pause_menu_notify(eng, "[HUD] Telemetria ISO 25010: %s",
        eng->showTelemetry ? "VISIBLE" : "OCULTA");
}

void pause_menu_cycle_cam_speed(VulkanEngine *eng, int direction) {
    eng->camSpeedIndex = (eng->camSpeedIndex + direction + NUM_CAM_SPEEDS) % NUM_CAM_SPEEDS;
    g_camera.moveSpeed = g_camSpeeds[eng->camSpeedIndex].speed;
    pause_menu_notify(eng, "[CAMARA] Velocidad: %s", g_camSpeeds[eng->camSpeedIndex].name);
}

void pause_menu_cycle_traffic_mode(VulkanEngine *eng, int direction) {
    eng->trafficSignalMode = (eng->trafficSignalMode + direction + 3) % 3;
    const char *mNames[] = {"Ciclo Automatico (6 Fases)", "Forzar Todos VERDE", "Forzar Todos ROJO"};
    pause_menu_notify(eng, "[TRAFICO] Modo: %s", mNames[eng->trafficSignalMode]);
}

/* =========================================================================
 * CONTROL DE ENTRADA (TECLADO)
 * ========================================================================= */

void pause_menu_toggle_fullscreen(VulkanEngine *eng) {
    if (!eng || !eng->window) return;
    Uint32 flags = SDL_GetWindowFlags(eng->window);
    int isFullscreen = (flags & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP)) != 0;
    if (isFullscreen) {
        SDL_SetWindowFullscreen(eng->window, 0);
        pause_menu_notify(eng, "[PANTALLA] Modo Ventana");
    } else {
        SDL_SetWindowFullscreen(eng->window, SDL_WINDOW_FULLSCREEN_DESKTOP);
        pause_menu_notify(eng, "[PANTALLA] Pantalla Completa (F11)");
    }
    eng->framebufferResized = 1;
}

int pause_menu_handle_hotkeys(VulkanEngine *eng, SDL_Keycode key) {
    switch (key) {
        case SDLK_F11: pause_menu_toggle_fullscreen(eng); return 1;
        case SDLK_LEFTBRACKET:  pause_menu_adjust_hour(eng, -1.0f); return 1;
        case SDLK_RIGHTBRACKET: pause_menu_adjust_hour(eng, +1.0f); return 1;
        case SDLK_t: pause_menu_cycle_time_scale(eng, +1); return 1;
        case SDLK_y: pause_menu_toggle_time_freeze(eng); return 1;
        case SDLK_F1: pause_menu_apply_teleport(eng, 0); return 1;
        case SDLK_F2: pause_menu_apply_teleport(eng, 1); return 1;
        case SDLK_F3: pause_menu_apply_teleport(eng, 2); return 1;
        case SDLK_F4: pause_menu_apply_teleport(eng, 3); return 1;
        case SDLK_F6: pause_menu_apply_teleport(eng, 4); return 1;
        case SDLK_F5: pause_menu_toggle_culling(eng); return 1;
        case SDLK_F8: pause_menu_toggle_telemetry(eng); return 1;
        case SDLK_f:
        case SDLK_l:  pause_menu_toggle_flashlight(eng); return 1;
        default:      return 0;
    }
}

void pause_menu_handle_key(VulkanEngine *eng, SDL_Keycode key, int *outRunning) {
    static int s_tp = 0;
    if (!eng->isPaused) return;

    if (pause_menu_handle_hotkeys(eng, key)) return;

    switch (key) {
        case SDLK_UP:
        case SDLK_w:
            eng->pauseMenuIndex = (eng->pauseMenuIndex - 1 + MENU_COUNT) % MENU_COUNT;
            break;
        case SDLK_DOWN:
        case SDLK_s:
            eng->pauseMenuIndex = (eng->pauseMenuIndex + 1) % MENU_COUNT;
            break;

        case SDLK_LEFT:
        case SDLK_a:
            switch (eng->pauseMenuIndex) {
                case MENU_TIME_SCALE:   pause_menu_cycle_time_scale(eng, -1); break;
                case MENU_TIME_PRESET:
                    eng->timePresetIndex = (eng->timePresetIndex - 1 + NUM_TIME_PRESETS) % NUM_TIME_PRESETS;
                    pause_menu_apply_time_preset(eng, eng->timePresetIndex);
                    break;
                case MENU_HOUR_STEP:    pause_menu_adjust_hour(eng, -0.5f); break;
                case MENU_TIME_FREEZE:  pause_menu_toggle_time_freeze(eng); break;
                case MENU_TELEPORT:
                    s_tp = (s_tp - 1 + NUM_TELEPORT_TARGETS) % NUM_TELEPORT_TARGETS;
                    pause_menu_apply_teleport(eng, s_tp);
                    break;
                case MENU_CULLING:      pause_menu_toggle_culling(eng); break;
                case MENU_TELEMETRY:    pause_menu_toggle_telemetry(eng); break;
                case MENU_CAM_SPEED:    pause_menu_cycle_cam_speed(eng, -1); break;
                case MENU_TRAFFIC_MODE: pause_menu_cycle_traffic_mode(eng, -1); break;
                case MENU_FLASHLIGHT:   pause_menu_toggle_flashlight(eng); break;
                default: break;
            }
            break;

        case SDLK_RIGHT:
        case SDLK_d:
            switch (eng->pauseMenuIndex) {
                case MENU_TIME_SCALE:   pause_menu_cycle_time_scale(eng, +1); break;
                case MENU_TIME_PRESET:
                    eng->timePresetIndex = (eng->timePresetIndex + 1) % NUM_TIME_PRESETS;
                    pause_menu_apply_time_preset(eng, eng->timePresetIndex);
                    break;
                case MENU_HOUR_STEP:    pause_menu_adjust_hour(eng, +0.5f); break;
                case MENU_TIME_FREEZE:  pause_menu_toggle_time_freeze(eng); break;
                case MENU_TELEPORT:
                    s_tp = (s_tp + 1) % NUM_TELEPORT_TARGETS;
                    pause_menu_apply_teleport(eng, s_tp);
                    break;
                case MENU_CULLING:      pause_menu_toggle_culling(eng); break;
                case MENU_TELEMETRY:    pause_menu_toggle_telemetry(eng); break;
                case MENU_CAM_SPEED:    pause_menu_cycle_cam_speed(eng, +1); break;
                case MENU_TRAFFIC_MODE: pause_menu_cycle_traffic_mode(eng, +1); break;
                case MENU_FLASHLIGHT:   pause_menu_toggle_flashlight(eng); break;
                default: break;
            }
            break;

        case SDLK_RETURN:
        case SDLK_KP_ENTER:
        case SDLK_SPACE:
            switch (eng->pauseMenuIndex) {
                case MENU_RESUME:
                    eng->isPaused = 0;
                    g_camera.mouseCaptured = 1;
                    SDL_SetRelativeMouseMode(SDL_TRUE);
                    pause_menu_notify(eng, "Simulacion Reanudada");
                    break;
                case MENU_TIME_SCALE:   pause_menu_cycle_time_scale(eng, +1); break;
                case MENU_TIME_PRESET:
                    eng->timePresetIndex = (eng->timePresetIndex + 1) % NUM_TIME_PRESETS;
                    pause_menu_apply_time_preset(eng, eng->timePresetIndex);
                    break;
                case MENU_HOUR_STEP:    pause_menu_adjust_hour(eng, +1.0f); break;
                case MENU_TIME_FREEZE:  pause_menu_toggle_time_freeze(eng); break;
                case MENU_TELEPORT:
                    s_tp = (s_tp + 1) % NUM_TELEPORT_TARGETS;
                    pause_menu_apply_teleport(eng, s_tp);
                    break;
                case MENU_CULLING:      pause_menu_toggle_culling(eng); break;
                case MENU_TELEMETRY:    pause_menu_toggle_telemetry(eng); break;
                case MENU_CAM_SPEED:    pause_menu_cycle_cam_speed(eng, +1); break;
                case MENU_TRAFFIC_MODE: pause_menu_cycle_traffic_mode(eng, +1); break;
                case MENU_FLASHLIGHT:   pause_menu_toggle_flashlight(eng); break;
                case MENU_QUIT:
                    if (outRunning) *outRunning = 0;
                    break;
                default: break;
            }
            break;

        case SDLK_q:
            if (outRunning) *outRunning = 0;
            break;

        default: break;
    }
}

/* =========================================================================
 * RENDERIZADO VISUAL DEL MENÚ DE PAUSA Y TOASTS
 * ========================================================================= */

void pause_menu_render_notification(DebugOverlay *ov, VulkanEngine *eng) {
    if (eng->notificationTimer <= 0.0f || eng->notificationText[0] == '\0') return;

    float screenW = ov->screenW;
    float notifW = 500.0f;
    float notifH = 34.0f;
    float nx = (screenW - notifW) * 0.5f;
    float ny = 14.0f;

    /* Evitar colisión con el HUD de telemetría ISO 25010 en resoluciones compactas (<= 1280px) */
    if (eng->showTelemetry && nx < 420.0f) {
        if (screenW >= (notifW + 420.0f)) {
            nx = screenW - notifW - 20.0f;
        } else {
            ny = 240.0f;
        }
    }

    /* Fondo oscuro con borde neón ámbar/cyan */
    debug_overlay_add_rect_z(ov, nx, ny, notifW, notifH, 0.04f, 0.07f, 0.12f, 0.0015f);
    debug_overlay_add_rect_z(ov, nx, ny, notifW, 2.0f, 1.0f, 0.85f, 0.20f, 0.0010f);
    debug_overlay_add_rect_z(ov, nx, ny + notifH - 2.0f, notifW, 2.0f, 0.0f, 0.85f, 1.0f, 0.0010f);

    /* Texto centrado en amarillo brillante */
    debug_overlay_add_text(ov, nx + 16.0f, ny + 9.0f, eng->notificationText, 2.0f, 1.0f, 0.95f, 0.35f);
}

void pause_menu_render(DebugOverlay *ov, VulkanEngine *eng) {
    if (!eng->isPaused) return;

    float screenW = ov->screenW;
    float screenH = ov->screenH;

    /* 1. Telón de fondo oscuro translúcido */
    debug_overlay_add_rect_z(ov, 0, 0, screenW, screenH, 0.015f, 0.025f, 0.045f, 0.0035f);

    /* 2. Dimensiones y centrado de la ventana del menú */
    float panelW = 580.0f;
    float panelH = 480.0f;
    float px = (screenW - panelW) * 0.5f;
    float py = (screenH - panelH) * 0.5f;

    if (eng->showTelemetry && px < 410.0f && screenW >= (panelW + 410.0f)) {
        px = screenW - panelW - 15.0f;
    }
    if (px < 10.0f) px = 10.0f;
    if (py < 10.0f) py = 10.0f;

    /* Fondo del panel */
    debug_overlay_add_rect_z(ov, px, py, panelW, panelH, 0.05f, 0.08f, 0.14f, 0.0025f);

    /* Marco perimetral */
    debug_overlay_add_rect_z(ov, px, py, panelW, 3.0f, 0.0f, 0.85f, 1.0f, 0.0018f);
    debug_overlay_add_rect_z(ov, px, py + panelH - 3.0f, panelW, 3.0f, 0.0f, 0.55f, 0.85f, 0.0018f);
    debug_overlay_add_rect_z(ov, px, py, 3.0f, panelH, 0.0f, 0.85f, 1.0f, 0.0018f);
    debug_overlay_add_rect_z(ov, px + panelW - 3.0f, py, 3.0f, panelH, 0.0f, 0.85f, 1.0f, 0.0018f);

    /* 3. Encabezado */
    float scaleTitle = 2.2f;
    debug_overlay_add_text(ov, px + 22.0f, py + 14.0f, "=== STREETVULKAN: PAUSA & TESTING ===", scaleTitle, 0.0f, 0.90f, 1.0f);

    int hours = (int)eng->simHour;
    int mins  = (int)((eng->simHour - (float)hours) * 60.0f);
    const char *phase = (hours >= 6 && hours < 18) ? ((hours < 8) ? "Amanecer" : (hours > 16) ? "Atardecer" : "Dia") : "Noche";

    char statusBuf[128];
    snprintf(statusBuf, sizeof(statusBuf), "Hora: %02d:%02d (%s) | Vel: %.1fx | FPS: %.0f | %s",
             hours, mins, phase, eng->timeScale, eng->currentFps,
             eng->timeFrozen ? "SOL CONGELADO" : "TIEMPO ACTIVO");
    debug_overlay_add_text(ov, px + 22.0f, py + 38.0f, statusBuf, 1.8f, 1.0f, 0.85f, 0.35f);

    debug_overlay_add_rect_z(ov, px + 18.0f, py + 56.0f, panelW - 36.0f, 2.0f, 0.18f, 0.32f, 0.48f, 0.0020f);

    /* 4. Lista de opciones */
    float itemStartY = py + 66.0f;
    float itemH = 29.0f;
    float textScale = 1.9f;

    for (int i = 0; i < MENU_COUNT; i++) {
        float iy = itemStartY + (float)i * itemH;
        int isSelected = (i == eng->pauseMenuIndex);

        if (isSelected) {
            debug_overlay_add_rect_z(ov, px + 14.0f, iy - 2.0f, panelW - 28.0f, itemH - 2.0f,
                                     0.12f, 0.24f, 0.42f, 0.0016f);
            debug_overlay_add_text(ov, px + 22.0f, iy + 4.0f, ">>", textScale, 1.0f, 0.92f, 0.20f);
        } else {
            debug_overlay_add_text(ov, px + 22.0f, iy + 4.0f, "  ", textScale, 0.5f, 0.5f, 0.5f);
        }

        float colTextR = isSelected ? 1.0f : 0.78f;
        float colTextG = isSelected ? 1.0f : 0.84f;
        float colTextB = isSelected ? 1.0f : 0.90f;
        float valR = isSelected ? 1.0f : 0.35f;
        float valG = isSelected ? 0.92f : 0.85f;
        float valB = isSelected ? 0.30f : 0.95f;

        char lineLabel[64] = {0};
        char lineValue[64] = {0};

        switch (i) {
            case MENU_RESUME:
                snprintf(lineLabel, sizeof(lineLabel), "1. Reanudar Simulacion");
                snprintf(lineValue, sizeof(lineValue), "[ESC / P]");
                break;
            case MENU_TIME_SCALE:
                snprintf(lineLabel, sizeof(lineLabel), "2. Velocidad de Tiempo");
                snprintf(lineValue, sizeof(lineValue), "< %s >", g_timeSpeeds[eng->timeScaleIndex].label);
                break;
            case MENU_TIME_PRESET:
                snprintf(lineLabel, sizeof(lineLabel), "3. Fijar Hora del Dia");
                snprintf(lineValue, sizeof(lineValue), "< %s >", g_timePresets[eng->timePresetIndex].name);
                break;
            case MENU_HOUR_STEP:
                snprintf(lineLabel, sizeof(lineLabel), "4. Ajustar Hora (+/-)");
                snprintf(lineValue, sizeof(lineValue), "< %02d:%02d hrs >  [[ / ]]", hours, mins);
                break;
            case MENU_TIME_FREEZE:
                snprintf(lineLabel, sizeof(lineLabel), "5. Congelar Avance Solar");
                snprintf(lineValue, sizeof(lineValue), "[ %s ]  [Y]", eng->timeFrozen ? "SI (FIJO)" : "NO (AVANZA)");
                break;
            case MENU_TELEPORT:
                snprintf(lineLabel, sizeof(lineLabel), "6. Teletransporte Rapido");
                snprintf(lineValue, sizeof(lineValue), "< Puntos POI [F1-F6] >");
                break;
            case MENU_CULLING:
                snprintf(lineLabel, sizeof(lineLabel), "7. Frustum Culling");
                snprintf(lineValue, sizeof(lineValue), "[ %s ]  [F5]", eng->cullingEnabled ? "ACTIVADO" : "DESACTIVADO");
                break;
            case MENU_TELEMETRY:
                snprintf(lineLabel, sizeof(lineLabel), "8. Telemetria ISO 25010");
                snprintf(lineValue, sizeof(lineValue), "[ %s ]  [F8]", eng->showTelemetry ? "VISIBLE" : "OCULTO");
                break;
            case MENU_CAM_SPEED:
                snprintf(lineLabel, sizeof(lineLabel), "9. Velocidad de Camara");
                snprintf(lineValue, sizeof(lineValue), "< %s >", g_camSpeeds[eng->camSpeedIndex].name);
                break;
            case MENU_TRAFFIC_MODE: {
                const char *sModes[] = {"Automatico", "Todos Verde", "Todos Rojo"};
                snprintf(lineLabel, sizeof(lineLabel), "10. Modo Semaforos");
                snprintf(lineValue, sizeof(lineValue), "< %s >", sModes[eng->trafficSignalMode]);
                break;
            }
            case MENU_FLASHLIGHT:
                snprintf(lineLabel, sizeof(lineLabel), "11. Linterna Frontal");
                snprintf(lineValue, sizeof(lineValue), "[ %s ]  [F / L]",
                         eng->lightingSystem.flashlightEnabled ? "ACTIVADA" : "DESACTIVADA");
                break;
            case MENU_QUIT:
                snprintf(lineLabel, sizeof(lineLabel), "12. Salir del Motor");
                snprintf(lineValue, sizeof(lineValue), "[Q / Salir]");
                break;
            default: break;
        }

        debug_overlay_add_text(ov, px + 44.0f,  iy + 4.0f, lineLabel, textScale, colTextR, colTextG, colTextB);
        debug_overlay_add_text(ov, px + 310.0f, iy + 4.0f, lineValue, textScale, valR, valG, valB);
    }

    /* 5. Footer */
    debug_overlay_add_rect_z(ov, px + 18.0f, py + panelH - 46.0f, panelW - 36.0f, 1.5f, 0.18f, 0.32f, 0.48f, 0.0020f);

    float footerScale = 1.45f;
    debug_overlay_add_text(ov, px + 22.0f, py + panelH - 36.0f,
                           "[ARRIBA/ABAJO]: Seleccionar  [IZQ/DER]: Ajustar  [ENTER/ESPACIO]: Aplicar",
                           footerScale, 0.70f, 0.82f, 0.95f);
    debug_overlay_add_text(ov, px + 22.0f, py + panelH - 18.0f,
                           "[P / ESC]: Reanudar  [[ / ]]: -/+1h  [T]: Vel. Tiempo  [F1-F6]: Teleport  [Q]: Salir",
                           footerScale, 0.55f, 0.75f, 0.88f);
}
