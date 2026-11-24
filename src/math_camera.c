/* math_camera.c - Estado inicial de la cámara libre en StreetVulkan
 *
 * Define la instancia global `g_camera` utilizada por el bucle principal
 * y los renderizadores Vulkan para posicionar la vista inicial del usuario
 * frente a la sucursal de referencia en el macro-sector (0, 0).
 */
#include "math_camera.h"

/* Cámara global inicial: posición en mundo (X, Y, Z), orientación (yaw/pitch)
 * en grados, velocidades de desplazamiento y captura inicial del puntero. */
Camera g_camera = {
    .pos = { 954.4f, 8.8f, 793.1f }, /* Posición inicial frente a sucursal */
    .yaw = -45.7f,                   /* Orientación horizontal hacia el local */
    .pitch = 4.9f,                   /* Ligera inclinación hacia anuncio elevado */
    .moveSpeed = 35.0f,              /* Velocidad base de cámara libre (m/s) */
    .sprintMultiplier = 4.0f,        /* Multiplicador al mantener Shift */
    .mouseSensitivity = 0.12f,       /* Sensibilidad de rotación con ratón */
    .mouseCaptured = 1               /* Cursor capturado al iniciar */
};
