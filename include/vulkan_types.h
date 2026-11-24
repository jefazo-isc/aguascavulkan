#ifndef VULKAN_TYPES_H
#define VULKAN_TYPES_H

typedef struct SDL_Window SDL_Window;
#include <vulkan/vulkan.h>
#include "vertex_format.h"
#include "obj_loader.h"
#define MAX_FRAMES_IN_FLIGHT 2

#include "traffic_system.h"
#include "lighting_system.h"
#include "chunk_system.h"
#include "sector_system.h"
#include "debug_overlay.h"
#include "road_graph.h"
#include "car_system.h"
#include "vulkan_memory_pool.h"

typedef struct {
    float mvp[16];        // 64 bytes
    float model[16];      // 64 bytes
} PushConstants;
_Static_assert(sizeof(PushConstants) <= 128, "PushConstants must not exceed Vulkan 1.2 128-byte minimum");

typedef struct VulkanEngine {
    // --- Window Reference ---
    SDL_Window *window;
    int framebufferResized;
    float totalTimeSeconds; // Temporizador global para ciclo día/noche (72 min)

    // --- Core Vulkan Instance & Device ---
    VkInstance instance;
    VkDebugUtilsMessengerEXT debugMessenger;
    VkSurfaceKHR surface;
    VkPhysicalDevice physicalDevice;
    char gpuName[256];
    uint32_t graphicsQueueFamily;
    VkDevice device;
    VkQueue graphicsQueue;

    // --- Subasignadores Centrales de Memoria Vulkan (Tier S) ---
    VulkanMemoryPool vramBufferPool;  // DEVICE_LOCAL exclusivo para VkBuffer (geometría estática VBOs e IBOs)
    VulkanMemoryPool vramImagePool;   // DEVICE_LOCAL exclusivo para VkImage (Texturas en Tiling Optimal)
    VulkanMemoryPool hostVisiblePool; // HOST_VISIBLE | HOST_COHERENT para UBOs, staging y HUDs dynamic

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
    VulkanSuballocation depthImageSub;
    VkDeviceSize depthImageAllocSize;
    VkImageView depthImageView;

    // --- Pipeline & Renderpass ---
    VkRenderPass renderPass;
    VkFramebuffer *framebuffers;
    VkPipelineLayout pipelineLayout;
    VkPipeline graphicsPipeline;

    // --- Commands & Sync (Doble Buffer Frames in Flight) ---
    VkCommandPool commandPool;
    VkCommandBuffer commandBuffers[MAX_FRAMES_IN_FLIGHT];
    VkSemaphore imageAvailableSemaphores[MAX_FRAMES_IN_FLIGHT];
    VkSemaphore *renderFinishedSemaphores;
    uint32_t renderFinishedSemaphoreCount;
    VkFence inFlightFences[MAX_FRAMES_IN_FLIGHT];
    uint32_t currentFrame;

    // --- Vertex Buffer Principal (DEVICE_LOCAL VRAM pura) ---
    VkBuffer vertexBuffer;
    VkDeviceMemory vertexBufferMemory;
    Vertex* vertexData;
    size_t vertexCount;

    // --- Index Buffer Principal (DEVICE_LOCAL VRAM pura) ---
    VkBuffer indexBuffer;
    VkDeviceMemory indexBufferMemory;
    uint32_t* indexData;
    size_t indexCount;

    // --- Geometría Auxiliar (Gemini AI OBJs, Photo Planes, Debug RoadGraph) ---
    VkBuffer auxVertexBuffer;
    Vertex *auxVertexData;
    size_t auxVertexCount;

    // --- Recursos de Texturas ---
    uint32_t textureWidth;
    uint32_t textureHeight;
    VkImage textureImage;
    VkDeviceMemory textureImageMemory;
    VkImageView textureImageView;
    VkImage facadeImage;
    VkDeviceMemory facadeMemory;
    VkImageView facadeImageView;
    VkImage photoImage;          // Textura de foto georeferenciada (binding 3)
    VkImageView photoImageView;  // View de la textura de foto
    VkBuffer textureStagingBuffer;
    VkDeviceMemory textureStagingMemory;
    VkSampler textureSampler;

    // --- Descriptores (uno por frame in flight para evitar Data Races) ---
    VkDescriptorSetLayout descriptorSetLayout;
    VkDescriptorPool descriptorPool;
    VkDescriptorSet descriptorSets[MAX_FRAMES_IN_FLIGHT];

    // --- Sistema de Iluminación Dinámica (Semáforos, Farolas, Beacons, Linterna) ---
    VkBuffer lightingBuffers[MAX_FRAMES_IN_FLIGHT];
    LightingUBO *lightingUboMapped[MAX_FRAMES_IN_FLIGHT];
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
    size_t baseVertexCount; // Vértices pertenecientes a la malla base GLTF (cubiertos por chunks)

    // --- Sistema Modular de Macro-Sectores (<99MB) ---
    SectorSystem sectorSystem;
    int useSectorSystem; // 1 si se usan macro-sectores modulares en vez del monolítico

    // --- HUD Debug Overlay (Per-Frame Dynamic Buffers) ---
    VkBuffer hudVertexBuffers[MAX_FRAMES_IN_FLIGHT];
    VkDeviceMemory hudVertexBufferMemories[MAX_FRAMES_IN_FLIGHT];
    Vertex* hudMappedDatas[MAX_FRAMES_IN_FLIGHT];
    DebugOverlay debugOverlay;
    float fpsAccum;
    int fpsFrameCount;
    float currentFps;
    uint32_t lastDrawCalls;
    uint32_t lastVisibleVerts;
    float lastCpuTimeMs;
    float lastGpuTimeMs;
    float simCpuAccumMs;
    VkQueryPool timestampQueryPool;
    float timestampPeriodNs;
    int timestampValid[MAX_FRAMES_IN_FLIGHT];

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
