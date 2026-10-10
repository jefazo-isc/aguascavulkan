#ifndef VULKAN_TYPES_H
#define VULKAN_TYPES_H

#include <SDL2/SDL.h>
#include <vulkan/vulkan.h>
#include "vertex_format.h"
#include "obj_loader.h"
#include "traffic_system.h"
#include "lighting_system.h"
#include "chunk_system.h"
#include "debug_overlay.h"
#include "road_graph.h"
#include "car_system.h"

typedef struct {
    float mvp[16];        // 64 bytes
    float model[16];      // 64 bytes
    float sunDir[4];      // 16 bytes: sunX, sunY, sunZ, ambientIntensity
    float skyColor[4];    // 16 bytes: skyR, skyG, skyB, nightFactor
    float timeParams[4];  // 16 bytes: simHour, 0, 0, 0
} PushConstants;

typedef struct {
    // --- Window Reference ---
    SDL_Window *window;
    int framebufferResized;
    float totalTimeSeconds; // Temporizador global para ciclo día/noche (72 min)

    // --- Core Vulkan Instance & Device ---
    VkInstance instance;
    VkSurfaceKHR surface;
    VkPhysicalDevice physicalDevice;
    char gpuName[256];
    uint32_t graphicsQueueFamily;
    VkDevice device;
    VkQueue graphicsQueue;

    // --- Swapchain ---
    VkSwapchainKHR swapchain;
    VkFormat swapchainImageFormat;
    VkExtent2D swapchainExtent;
    uint32_t imageCount;
    VkImage *swapchainImages;
    VkImageView *swapchainImageViews;

    // --- Depth Buffer ---
    VkFormat depthFormat;
    VkImage depthImage;
    VkDeviceMemory depthImageMemory;
    VkImageView depthImageView;

    // --- Pipeline & Renderpass ---
    VkRenderPass renderPass;
    VkFramebuffer *framebuffers;
    VkPipelineLayout pipelineLayout;
    VkPipeline graphicsPipeline;

    // --- Commands & Sync ---
    VkCommandPool commandPool;
    VkCommandBuffer commandBuffer;
    VkSemaphore imageAvailableSemaphore;
    VkSemaphore renderFinishedSemaphore;
    VkFence inFlightFence;

    // --- Vertex Buffer Principal (Soporta OBJ / GLB) ---
    VkBuffer vertexBuffer;
    VkDeviceMemory vertexBufferMemory;
    Vertex* vertexData;
    Vertex* mappedVertexData; // Puntero mapeado persistente para actualizar semáforos
    size_t vertexCount;

    // --- Recursos de Texturas ---
    uint32_t textureWidth;
    uint32_t textureHeight;
    VkImage textureImage;
    VkDeviceMemory textureImageMemory;
    VkImageView textureImageView;
    VkBuffer textureStagingBuffer;
    VkDeviceMemory textureStagingMemory;
    VkSampler textureSampler;

    // --- Descriptores ---
    VkDescriptorSetLayout descriptorSetLayout;
    VkDescriptorPool descriptorPool;
    VkDescriptorSet descriptorSet;

    // --- Sistema de Iluminación Dinámica (Semáforos, Farolas, Beacons, Linterna) ---
    VkBuffer lightingBuffer;
    VkDeviceMemory lightingBufferMemory;
    LightingUBO *lightingUboMapped;
    LightingSystem lightingSystem;

    // --- Sistema de Grafo Vial ---
    RoadGraph* roadGraph;

    // --- Sistema de Tráfico Cinemático de Coches ---
    CarSystem carSystem;

    // --- Sistema de Tráfico Dinámico ---
    TrafficSystem trafficSystem;

    // --- Sistema de Chunks + Frustum Culling ---
    ChunkSystem chunkSystem;
    int chunksEnabled; // 1 si chunks.json se cargó correctamente

    // --- HUD Debug Overlay ---
    VkBuffer hudVertexBuffer;
    VkDeviceMemory hudVertexBufferMemory;
    Vertex* hudMappedData;
    DebugOverlay debugOverlay;
    float fpsAccum;
    int fpsFrameCount;
    float currentFps;

    // --- Estado de Pausa y Opciones de Testing ---
    int isPaused;              // 1 si el juego está en pausa
    int pauseMenuIndex;        // Índice de opción seleccionada en el menú
    float timeScale;           // Multiplicador de velocidad de tiempo (1.0, 5.0, 15.0, 60.0...)
    float simHour;             // Hora simulada del día (0.0 a 24.0)
    int timeFrozen;            // 1 para congelar el avance solar
    int showTelemetry;         // 1 para mostrar el panel de telemetría ISO
    int cullingEnabled;        // 1 para usar frustum culling, 0 para dibujar todo
    int timePresetIndex;       // Índice de preset de hora (12h, 17.5h, 23h, 6.5h)
    int timeScaleIndex;        // Índice de escala de tiempo (1x, 5x, 15x, 60x, 120x, 300x)
    int camSpeedIndex;         // Índice de velocidad de cámara (15, 35, 85 m/s)
    int trafficSignalMode;     // 0: Normal, 1: Forzar Verde, 2: Forzar Rojo
    char notificationText[128];// Mensaje de estado temporal (toast)
    float notificationTimer;   // Tiempo restante para mostrar la notificación

} VulkanEngine;

#endif // VULKAN_TYPES_H
