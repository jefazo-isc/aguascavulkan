#include <SDL2/SDL.h>
#include <stdio.h>
#include "math_camera.h"
#include "vulkan.h"
#include "pause_menu.h"

int main(void) {
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "Error al iniciar SDL: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window *window = SDL_CreateWindow(
        "StreetView Vulkan - Cámara Libre",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        1024, 768, SDL_WINDOW_VULKAN | SDL_WINDOW_RESIZABLE);

    if (!window) {
        fprintf(stderr, "Error al crear la ventana: %s\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }

    VulkanEngine eng = {0};
    if (!vulkan_init(&eng, window)) {
        fprintf(stderr, "Error inicializando Vulkan\n");
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }

    SDL_SetRelativeMouseMode(SDL_TRUE);

    int running = 1;
    SDL_Event event;
    Uint64 lastTime = SDL_GetPerformanceCounter();
    Uint64 timerFreq = SDL_GetPerformanceFrequency();
    float titleTimer = 0.0f;

    while (running) {
        Uint64 currentTime = SDL_GetPerformanceCounter();
        float deltaTime = (float)(currentTime - lastTime) / (float)timerFreq;
        lastTime = currentTime;
        if (deltaTime > 0.1f) deltaTime = 0.1f;

        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                running = 0;
            } else if (event.type == SDL_KEYDOWN) {
                SDL_Keycode sym = event.key.keysym.sym;
                if (sym == SDLK_ESCAPE || sym == SDLK_p) {
                    eng.isPaused = !eng.isPaused;
                    if (eng.isPaused) {
                        g_camera.mouseCaptured = 0;
                        SDL_SetRelativeMouseMode(SDL_FALSE);
                        pause_menu_notify(&eng, "Pausa Activada - Menu de Testing");
                    } else {
                        g_camera.mouseCaptured = 1;
                        SDL_SetRelativeMouseMode(SDL_TRUE);
                        pause_menu_notify(&eng, "Simulacion Reanudada");
                    }
                } else if (eng.isPaused) {
                    pause_menu_handle_key(&eng, sym, &running);
                } else {
                    if (sym == SDLK_TAB) {
                        g_camera.mouseCaptured = !g_camera.mouseCaptured;
                        SDL_SetRelativeMouseMode(g_camera.mouseCaptured ? SDL_TRUE : SDL_FALSE);
                    } else {
                        pause_menu_handle_hotkeys(&eng, sym);
                    }
                }
            } else if (event.type == SDL_MOUSEBUTTONDOWN) {
                if (!eng.isPaused && !g_camera.mouseCaptured) {
                    g_camera.mouseCaptured = 1;
                    SDL_SetRelativeMouseMode(SDL_TRUE);
                }
            } else if (event.type == SDL_WINDOWEVENT) {
                if (event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED ||
                    event.window.event == SDL_WINDOWEVENT_RESIZED) {
                    eng.framebufferResized = 1;
                }
            } else if (event.type == SDL_MOUSEMOTION) {
                if (!eng.isPaused && g_camera.mouseCaptured) {
                    g_camera.yaw += (float)event.motion.xrel * g_camera.mouseSensitivity;
                    g_camera.pitch -= (float)event.motion.yrel * g_camera.mouseSensitivity;
                    if (g_camera.pitch > 89.0f) g_camera.pitch = 89.0f;
                    if (g_camera.pitch < -89.0f) g_camera.pitch = -89.0f;
                }
            }
        }

        if (!eng.isPaused && g_camera.mouseCaptured) {
            const Uint8 *keys = SDL_GetKeyboardState(NULL);
            float speed = g_camera.moveSpeed * deltaTime;
            if (keys[SDL_SCANCODE_LSHIFT] || keys[SDL_SCANCODE_RSHIFT]) {
                speed *= g_camera.sprintMultiplier;
            }

            Vec3 forward, right, up;
            camera_get_vectors(&g_camera, &forward, &right, &up);

            if (keys[SDL_SCANCODE_W]) {
                g_camera.pos.x += forward.x * speed;
                g_camera.pos.y += forward.y * speed;
                g_camera.pos.z += forward.z * speed;
            }
            if (keys[SDL_SCANCODE_S]) {
                g_camera.pos.x -= forward.x * speed;
                g_camera.pos.y -= forward.y * speed;
                g_camera.pos.z -= forward.z * speed;
            }
            if (keys[SDL_SCANCODE_D]) {
                g_camera.pos.x += right.x * speed;
                g_camera.pos.y += right.y * speed;
                g_camera.pos.z += right.z * speed;
            }
            if (keys[SDL_SCANCODE_A]) {
                g_camera.pos.x -= right.x * speed;
                g_camera.pos.y -= right.y * speed;
                g_camera.pos.z -= right.z * speed;
            }
            if (keys[SDL_SCANCODE_SPACE]) {
                g_camera.pos.y += speed;
            }
            if (keys[SDL_SCANCODE_LCTRL] || keys[SDL_SCANCODE_C]) {
                g_camera.pos.y -= speed;
            }
        }

        titleTimer += deltaTime;
        if (titleTimer >= 0.15f) {
            titleTimer = 0.0f;
            char title[384];
            int simH = (int)eng.simHour;
            int simM = (int)((eng.simHour - (float)simH) * 60.0f);
            if (eng.isPaused) {
                snprintf(title, sizeof(title),
                    "StreetView Vulkan [EN PAUSA] | Hora: %02d:%02d (%s) | Escala: %.1fx | [P/ESC: Reanudar]",
                    simH, simM, eng.timeFrozen ? "Congelada" : "En Marcha",
                    eng.timeScale);
            } else {
                snprintf(title, sizeof(title),
                    "StreetView Vulkan | %02d:%02d (%.1fx) | Pos: (%.1f, %.1f, %.1f) | Yaw: %.0f°%s",
                    simH, simM, eng.timeScale,
                    g_camera.pos.x, g_camera.pos.y, g_camera.pos.z,
                    g_camera.yaw,
                    g_camera.mouseCaptured ? " [WASD+Ratón]" : " [TAB/Clic: Capturar]");
            }
            SDL_SetWindowTitle(window, title);
        }

        vulkan_draw(&eng, deltaTime);
    }

    vulkan_destroy(&eng);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
