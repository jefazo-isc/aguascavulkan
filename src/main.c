#include <SDL2/SDL.h>
#include <stdio.h>
#include "logger.h"
#include "math_camera.h"
#include "vulkan.h"
#include "pause_menu.h"

/* Procesa eventos de teclado (pausa, menú, captura de ratón y hotkeys). */
static void handle_keydown_event(VulkanEngine *eng, SDL_Keycode sym, int *running) {
    if (sym == SDLK_ESCAPE || sym == SDLK_p) {
        eng->isPaused = !eng->isPaused;
        g_camera.mouseCaptured = eng->isPaused ? 0 : 1;
        SDL_SetRelativeMouseMode(eng->isPaused ? SDL_FALSE : SDL_TRUE);
        pause_menu_notify(eng, eng->isPaused ? "Pausa Activada - Menu de Testing" : "Simulacion Reanudada");
        return;
    }
    if (eng->isPaused) {
        pause_menu_handle_key(eng, sym, running);
        return;
    }
    if (sym == SDLK_TAB) {
        g_camera.mouseCaptured = !g_camera.mouseCaptured;
        SDL_SetRelativeMouseMode(g_camera.mouseCaptured ? SDL_TRUE : SDL_FALSE);
        return;
    }
    pause_menu_handle_hotkeys(eng, sym);
}

/* Maneja redimensionado, minimizado y restauración de la ventana SDL. */
static void handle_window_event(VulkanEngine *eng, const SDL_WindowEvent *wev, int *isMinimized) {
    if (wev->event == SDL_WINDOWEVENT_SIZE_CHANGED || wev->event == SDL_WINDOWEVENT_RESIZED) {
        eng->framebufferResized = 1;
    } else if (wev->event == SDL_WINDOWEVENT_MINIMIZED) {
        *isMinimized = 1;
    } else if (wev->event == SDL_WINDOWEVENT_RESTORED || wev->event == SDL_WINDOWEVENT_MAXIMIZED) {
        *isMinimized = 0;
        eng->framebufferResized = 1;
    }
}

/* Drena la cola de eventos SDL y actualiza cámara/estado del motor. */
static void process_sdl_events(VulkanEngine *eng, int *running, int *isMinimized) {
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_QUIT) {
            *running = 0;
        } else if (event.type == SDL_KEYDOWN) {
            handle_keydown_event(eng, event.key.keysym.sym, running);
        } else if (event.type == SDL_MOUSEBUTTONDOWN && !eng->isPaused && !g_camera.mouseCaptured) {
            g_camera.mouseCaptured = 1;
            SDL_SetRelativeMouseMode(SDL_TRUE);
        } else if (event.type == SDL_WINDOWEVENT) {
            handle_window_event(eng, &event.window, isMinimized);
        } else if (event.type == SDL_MOUSEMOTION && !eng->isPaused && g_camera.mouseCaptured) {
            g_camera.yaw += (float)event.motion.xrel * g_camera.mouseSensitivity;
            g_camera.pitch -= (float)event.motion.yrel * g_camera.mouseSensitivity;
            if (g_camera.pitch > 89.0f) g_camera.pitch = 89.0f;
            if (g_camera.pitch < -89.0f) g_camera.pitch = -89.0f;
        }
    }
}

/* Aplica el movimiento WASD + Espacio/Ctrl de la cámara libre. */
static void update_camera_movement(const VulkanEngine *eng, float deltaTime) {
    if (eng->isPaused || !g_camera.mouseCaptured) return;

    const Uint8 *keys = SDL_GetKeyboardState(NULL);
    float speed = g_camera.moveSpeed * deltaTime;
    if (keys[SDL_SCANCODE_LSHIFT] || keys[SDL_SCANCODE_RSHIFT]) {
        speed *= g_camera.sprintMultiplier;
    }

    Vec3 forward, right, up;
    camera_get_vectors(&g_camera, &forward, &right, &up);

    float moveFwd = (keys[SDL_SCANCODE_W] ? 1.0f : 0.0f) - (keys[SDL_SCANCODE_S] ? 1.0f : 0.0f);
    float moveRight = (keys[SDL_SCANCODE_D] ? 1.0f : 0.0f) - (keys[SDL_SCANCODE_A] ? 1.0f : 0.0f);
    float moveUp = (keys[SDL_SCANCODE_SPACE] ? 1.0f : 0.0f) -
                   ((keys[SDL_SCANCODE_LCTRL] || keys[SDL_SCANCODE_C]) ? 1.0f : 0.0f);

    g_camera.pos.x += (forward.x * moveFwd + right.x * moveRight) * speed;
    g_camera.pos.y += (forward.y * moveFwd + right.y * moveRight + moveUp) * speed;
    g_camera.pos.z += (forward.z * moveFwd + right.z * moveRight) * speed;
}

/* Actualiza el título de la ventana cada 0.15s con hora, posición y estado. */
static void update_window_title_periodic(SDL_Window *window, const VulkanEngine *eng,
                                         float deltaTime, float *titleTimer) {
    *titleTimer += deltaTime;
    if (*titleTimer < 0.15f) return;
    *titleTimer = 0.0f;

    char title[384];
    int simH = (int)eng->simHour;
    int simM = (int)((eng->simHour - (float)simH) * 60.0f);
    if (eng->isPaused) {
        snprintf(title, sizeof(title),
            "StreetView Vulkan [EN PAUSA] | Hora: %02d:%02d (%s) | Escala: %.1fx | [P/ESC: Reanudar]",
            simH, simM, eng->timeFrozen ? "Congelada" : "En Marcha", eng->timeScale);
    } else {
        snprintf(title, sizeof(title),
            "StreetView Vulkan | %02d:%02d (%.1fx) | Pos: (%.1f, %.1f, %.1f) | Yaw: %.0f°%s",
            simH, simM, eng->timeScale,
            g_camera.pos.x, g_camera.pos.y, g_camera.pos.z, g_camera.yaw,
            g_camera.mouseCaptured ? " [WASD+Ratón]" : " [TAB/Clic: Capturar]");
    }
    SDL_SetWindowTitle(window, title);
}

int main(void) {
    logger_init("logs", LOG_LEVEL_INFO);
    LOG_INFO("Main", "Iniciando StreetVulkan");

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        LOG_ERROR("SDL", "Error al iniciar SDL: %s", SDL_GetError());
        logger_shutdown();
        return 1;
    }

    SDL_Window *window = SDL_CreateWindow(
        "StreetView Vulkan - Cámara Libre",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        1024, 768, SDL_WINDOW_VULKAN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIDDEN);

    if (!window) {
        LOG_ERROR("SDL", "Error al crear la ventana: %s", SDL_GetError());
        SDL_Quit();
        logger_shutdown();
        return 1;
    }

    static VulkanEngine eng = {0};
    if (!vulkan_init(&eng, window)) {
        LOG_ERROR("Vulkan", "Error inicializando Vulkan");
        SDL_DestroyWindow(window);
        SDL_Quit();
        logger_shutdown();
        return 1;
    }

    vulkan_draw(&eng, 0.016f);
    SDL_ShowWindow(window);
    SDL_RaiseWindow(window);
    SDL_PumpEvents();
    SDL_SetRelativeMouseMode(SDL_TRUE);

    int running = 1;
    int isMinimized = 0;
    Uint64 lastTime = SDL_GetPerformanceCounter();
    Uint64 timerFreq = SDL_GetPerformanceFrequency();
    float titleTimer = 0.0f;

    const float FIXED_DELTA_TIME = 1.0f / 60.0f;
    float simAccumulator = 0.0f;
    const char *testFramesEnv = getenv("TEST_FRAMES");
    int testFrames = testFramesEnv ? atoi(testFramesEnv) : 0;
    int frameCount = 0;
    Uint64 testStartTime = SDL_GetPerformanceCounter();

    if (getenv("TEST_PAUSE")) {
        eng.isPaused = 1;
        pause_menu_notify(&eng, "Pausa Activada - Menu de Testing");
    }

    while (running) {
        if (testFrames > 0 && ++frameCount > testFrames) {
            float testDuration = (float)(SDL_GetPerformanceCounter() - testStartTime) / (float)timerFreq;
            float measuredFps = testDuration > 0.0001f ? ((float)testFrames / testDuration) : eng.currentFps;
            printf("[Test] Renderizados exitosamente %d frames de prueba sin errores.\n", testFrames);
            printf("[Test Telemetria] FPS: %.1f | Draw Calls: %u | Vertices Totales: %zu (Visibles: %u)\n",
                   measuredFps, eng.lastDrawCalls, eng.vertexCount, eng.lastVisibleVerts);
            break;
        }

        Uint64 currentTime = SDL_GetPerformanceCounter();
        float deltaTime = (float)(currentTime - lastTime) / (float)timerFreq;
        lastTime = currentTime;
        if (deltaTime > 0.25f) deltaTime = 0.25f;

        simAccumulator += deltaTime;
        while (simAccumulator >= FIXED_DELTA_TIME) {
            vulkan_update_simulation(&eng, FIXED_DELTA_TIME);
            simAccumulator -= FIXED_DELTA_TIME;
        }

        process_sdl_events(&eng, &running, &isMinimized);
        update_camera_movement(&eng, deltaTime);
        update_window_title_periodic(window, &eng, deltaTime, &titleTimer);

        if (!isMinimized) {
            vulkan_draw(&eng, deltaTime);
        } else {
            SDL_Delay(16);
        }
    }

    LOG_INFO("Main", "Cerrando StreetVulkan");
    vulkan_destroy(&eng);
    SDL_DestroyWindow(window);
    SDL_Quit();
    logger_shutdown();
    return 0;
}
