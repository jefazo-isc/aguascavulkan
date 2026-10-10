/* debug_overlay.h - Debug text overlay para StreetVulkan
 *
 * Genera vértices en espacio NDC para texto de debug usando un bitmap font 5x7
 * embebido. Cada carácter se renderiza como micro-quads (píxeles del glifo).
 * Usa emission=2.0 para que el fragment shader lo trate como HUD sin iluminación.
 */
#ifndef DEBUG_OVERLAY_H
#define DEBUG_OVERLAY_H

#include "vertex_format.h"
#include <string.h>
#include <stdio.h>

/* Capacidad máxima de vértices HUD/Menú por frame */
#define DEBUG_MAX_VERTS 65536

/* Fuente bitmap 5x7 para ASCII 32-127 (95 caracteres imprimibles).
 * Cada glifo es 5 columnas × 7 filas, empaquetado en 5 bytes (1 byte por columna).
 * Bit 0 = fila superior, Bit 6 = fila inferior. */
static const unsigned char debug_font_5x7[96][5] = {
    /* 32 ' ' */ {0x00,0x00,0x00,0x00,0x00},
    /* 33 '!' */ {0x00,0x00,0x5F,0x00,0x00},
    /* 34 '"' */ {0x00,0x07,0x00,0x07,0x00},
    /* 35 '#' */ {0x14,0x7F,0x14,0x7F,0x14},
    /* 36 '$' */ {0x24,0x2A,0x7F,0x2A,0x12},
    /* 37 '%' */ {0x23,0x13,0x08,0x64,0x62},
    /* 38 '&' */ {0x36,0x49,0x55,0x22,0x50},
    /* 39 ''' */ {0x00,0x05,0x03,0x00,0x00},
    /* 40 '(' */ {0x00,0x1C,0x22,0x41,0x00},
    /* 41 ')' */ {0x00,0x41,0x22,0x1C,0x00},
    /* 42 '*' */ {0x14,0x08,0x3E,0x08,0x14},
    /* 43 '+' */ {0x08,0x08,0x3E,0x08,0x08},
    /* 44 ',' */ {0x00,0x50,0x30,0x00,0x00},
    /* 45 '-' */ {0x08,0x08,0x08,0x08,0x08},
    /* 46 '.' */ {0x00,0x60,0x60,0x00,0x00},
    /* 47 '/' */ {0x20,0x10,0x08,0x04,0x02},
    /* 48 '0' */ {0x3E,0x51,0x49,0x45,0x3E},
    /* 49 '1' */ {0x00,0x42,0x7F,0x40,0x00},
    /* 50 '2' */ {0x42,0x61,0x51,0x49,0x46},
    /* 51 '3' */ {0x21,0x41,0x45,0x4B,0x31},
    /* 52 '4' */ {0x18,0x14,0x12,0x7F,0x10},
    /* 53 '5' */ {0x27,0x45,0x45,0x45,0x39},
    /* 54 '6' */ {0x3C,0x4A,0x49,0x49,0x30},
    /* 55 '7' */ {0x01,0x71,0x09,0x05,0x03},
    /* 56 '8' */ {0x36,0x49,0x49,0x49,0x36},
    /* 57 '9' */ {0x06,0x49,0x49,0x29,0x1E},
    /* 58 ':' */ {0x00,0x36,0x36,0x00,0x00},
    /* 59 ';' */ {0x00,0x56,0x36,0x00,0x00},
    /* 60 '<' */ {0x08,0x14,0x22,0x41,0x00},
    /* 61 '=' */ {0x14,0x14,0x14,0x14,0x14},
    /* 62 '>' */ {0x00,0x41,0x22,0x14,0x08},
    /* 63 '?' */ {0x02,0x01,0x51,0x09,0x06},
    /* 64 '@' */ {0x32,0x49,0x79,0x41,0x3E},
    /* 65 'A' */ {0x7E,0x11,0x11,0x11,0x7E},
    /* 66 'B' */ {0x7F,0x49,0x49,0x49,0x36},
    /* 67 'C' */ {0x3E,0x41,0x41,0x41,0x22},
    /* 68 'D' */ {0x7F,0x41,0x41,0x22,0x1C},
    /* 69 'E' */ {0x7F,0x49,0x49,0x49,0x41},
    /* 70 'F' */ {0x7F,0x09,0x09,0x09,0x01},
    /* 71 'G' */ {0x3E,0x41,0x49,0x49,0x7A},
    /* 72 'H' */ {0x7F,0x08,0x08,0x08,0x7F},
    /* 73 'I' */ {0x00,0x41,0x7F,0x41,0x00},
    /* 74 'J' */ {0x20,0x40,0x41,0x3F,0x01},
    /* 75 'K' */ {0x7F,0x08,0x14,0x22,0x41},
    /* 76 'L' */ {0x7F,0x40,0x40,0x40,0x40},
    /* 77 'M' */ {0x7F,0x02,0x0C,0x02,0x7F},
    /* 78 'N' */ {0x7F,0x04,0x08,0x10,0x7F},
    /* 79 'O' */ {0x3E,0x41,0x41,0x41,0x3E},
    /* 80 'P' */ {0x7F,0x09,0x09,0x09,0x06},
    /* 81 'Q' */ {0x3E,0x41,0x51,0x21,0x5E},
    /* 82 'R' */ {0x7F,0x09,0x19,0x29,0x46},
    /* 83 'S' */ {0x46,0x49,0x49,0x49,0x31},
    /* 84 'T' */ {0x01,0x01,0x7F,0x01,0x01},
    /* 85 'U' */ {0x3F,0x40,0x40,0x40,0x3F},
    /* 86 'V' */ {0x1F,0x20,0x40,0x20,0x1F},
    /* 87 'W' */ {0x3F,0x40,0x38,0x40,0x3F},
    /* 88 'X' */ {0x63,0x14,0x08,0x14,0x63},
    /* 89 'Y' */ {0x07,0x08,0x70,0x08,0x07},
    /* 90 'Z' */ {0x61,0x51,0x49,0x45,0x43},
    /* 91 '[' */ {0x00,0x7F,0x41,0x41,0x00},
    /* 92 '\' */ {0x02,0x04,0x08,0x10,0x20},
    /* 93 ']' */ {0x00,0x41,0x41,0x7F,0x00},
    /* 94 '^' */ {0x04,0x02,0x01,0x02,0x04},
    /* 95 '_' */ {0x40,0x40,0x40,0x40,0x40},
    /* 96 '`' */ {0x00,0x01,0x02,0x04,0x00},
    /* 97 'a' */ {0x20,0x54,0x54,0x54,0x78},
    /* 98 'b' */ {0x7F,0x48,0x44,0x44,0x38},
    /* 99 'c' */ {0x38,0x44,0x44,0x44,0x20},
    /*100 'd' */ {0x38,0x44,0x44,0x48,0x7F},
    /*101 'e' */ {0x38,0x54,0x54,0x54,0x18},
    /*102 'f' */ {0x08,0x7E,0x09,0x01,0x02},
    /*103 'g' */ {0x0C,0x52,0x52,0x52,0x3E},
    /*104 'h' */ {0x7F,0x08,0x04,0x04,0x78},
    /*105 'i' */ {0x00,0x44,0x7D,0x40,0x00},
    /*106 'j' */ {0x20,0x40,0x44,0x3D,0x00},
    /*107 'k' */ {0x7F,0x10,0x28,0x44,0x00},
    /*108 'l' */ {0x00,0x41,0x7F,0x40,0x00},
    /*109 'm' */ {0x7C,0x04,0x18,0x04,0x78},
    /*110 'n' */ {0x7C,0x08,0x04,0x04,0x78},
    /*111 'o' */ {0x38,0x44,0x44,0x44,0x38},
    /*112 'p' */ {0x7C,0x14,0x14,0x14,0x08},
    /*113 'q' */ {0x08,0x14,0x14,0x18,0x7C},
    /*114 'r' */ {0x7C,0x08,0x04,0x04,0x08},
    /*115 's' */ {0x48,0x54,0x54,0x54,0x20},
    /*116 't' */ {0x04,0x3F,0x44,0x40,0x20},
    /*117 'u' */ {0x3C,0x40,0x40,0x20,0x7C},
    /*118 'v' */ {0x1C,0x20,0x40,0x20,0x1C},
    /*119 'w' */ {0x3C,0x40,0x30,0x40,0x3C},
    /*120 'x' */ {0x44,0x28,0x10,0x28,0x44},
    /*121 'y' */ {0x0C,0x50,0x50,0x50,0x3C},
    /*122 'z' */ {0x44,0x64,0x54,0x4C,0x44},
    /*123 '{' */ {0x00,0x08,0x36,0x41,0x00},
    /*124 '|' */ {0x00,0x00,0x7F,0x00,0x00},
    /*125 '}' */ {0x00,0x41,0x36,0x08,0x00},
    /*126 '~' */ {0x10,0x08,0x08,0x10,0x08},
    /*127 DEL */ {0x00,0x00,0x00,0x00,0x00},
};

typedef struct {
    Vertex verts[DEBUG_MAX_VERTS];
    int vertCount;
    float screenW, screenH; /* Dimensiones del swapchain para normalización */
} DebugOverlay;

/* Limpiar el overlay al inicio del frame */
static inline void debug_overlay_begin(DebugOverlay *ov, float screenW, float screenH) {
    ov->vertCount = 0;
    ov->screenW = screenW;
    ov->screenH = screenH;
}

/* Agregar un rectángulo sólido en coordenadas de píxel (origen arriba-izquierda).
 * Se convierte a NDC: x_ndc = (x/W)*2-1, y_ndc = (y/H)*2-1 (Vulkan: Y down). */
static inline void debug_overlay_add_rect(DebugOverlay *ov,
    float px, float py, float pw, float ph,
    float r, float g, float b)
{
    if (ov->vertCount + 6 > DEBUG_MAX_VERTS) return;

    /* Convertir píxeles a NDC [-1, 1] */
    float x0 = (px / ov->screenW) * 2.0f - 1.0f;
    float y0 = (py / ov->screenH) * 2.0f - 1.0f;
    float x1 = ((px + pw) / ov->screenW) * 2.0f - 1.0f;
    float y1 = ((py + ph) / ov->screenH) * 2.0f - 1.0f;

    /* Z = 0.002 para fondo HUD (texto usará 0.0005, más cerca → gana depth test) */
    float hz = 0.002f;

    Vertex v = {0};
    v.r = r; v.g = g; v.b = b; v.a = 0.95f;
    v.emission = 10.0f; /* Marca HUD: sin iluminación ni fog */
    v.ny = 1.0f;

    /* Triángulo 1 */
    v.x = x0; v.y = y0; v.z = hz; ov->verts[ov->vertCount++] = v;
    v.x = x1; v.y = y0; v.z = hz; ov->verts[ov->vertCount++] = v;
    v.x = x1; v.y = y1; v.z = hz; ov->verts[ov->vertCount++] = v;
    /* Triángulo 2 */
    v.x = x0; v.y = y0; v.z = hz; ov->verts[ov->vertCount++] = v;
    v.x = x1; v.y = y1; v.z = hz; ov->verts[ov->vertCount++] = v;
    v.x = x0; v.y = y1; v.z = hz; ov->verts[ov->vertCount++] = v;
}

/* Versión interna de add_rect con z explícito */
static inline void debug_overlay_add_rect_z(DebugOverlay *ov,
    float px, float py, float pw, float ph,
    float r, float g, float b, float hz)
{
    if (ov->vertCount + 6 > DEBUG_MAX_VERTS) return;
    float x0 = (px / ov->screenW) * 2.0f - 1.0f;
    float y0 = (py / ov->screenH) * 2.0f - 1.0f;
    float x1 = ((px + pw) / ov->screenW) * 2.0f - 1.0f;
    float y1 = ((py + ph) / ov->screenH) * 2.0f - 1.0f;
    Vertex v = {0};
    v.r = r; v.g = g; v.b = b; v.a = 1.0f;
    v.emission = 10.0f;
    v.ny = 1.0f;
    v.x = x0; v.y = y0; v.z = hz; ov->verts[ov->vertCount++] = v;
    v.x = x1; v.y = y0;           ov->verts[ov->vertCount++] = v;
    v.x = x1; v.y = y1;           ov->verts[ov->vertCount++] = v;
    v.x = x0; v.y = y0;           ov->verts[ov->vertCount++] = v;
    v.x = x1; v.y = y1;           ov->verts[ov->vertCount++] = v;
    v.x = x0; v.y = y1;           ov->verts[ov->vertCount++] = v;
}

/* Dibujar un carácter del bitmap font en coordenadas de píxel.
 * scale: tamaño de cada "píxel" del glifo en píxeles reales de pantalla. */
static inline void debug_overlay_add_char(DebugOverlay *ov,
    float px, float py, char ch, float scale,
    float r, float g, float b)
{
    int idx = (int)ch - 32;
    if (idx < 0 || idx > 95) idx = 0;
    const unsigned char *glyph = debug_font_5x7[idx];

    for (int col = 0; col < 5; col++) {
        unsigned char colBits = glyph[col];
        for (int row = 0; row < 7; row++) {
            if (colBits & (1 << row)) {
                /* Z=0.0005: más cerca que el fondo (0.002) → gana depth test */
                debug_overlay_add_rect_z(ov,
                    px + col * scale,
                    py + row * scale,
                    scale, scale,
                    r, g, b, 0.0005f);
            }
        }
    }
}

/* Dibujar una cadena de texto completa.
 * Devuelve el ancho total en píxeles. */
static inline float debug_overlay_add_text(DebugOverlay *ov,
    float px, float py, const char *text, float scale,
    float r, float g, float b)
{
    float startX = px;
    while (*text) {
        debug_overlay_add_char(ov, px, py, *text, scale, r, g, b);
        px += 6.0f * scale; /* 5 columnas + 1 espacio */
        text++;
    }
    return px - startX;
}

#include "telemetry.h"

/* Construir el panel completo ISO 25010:2023 Performance & Telemetry */
static inline void debug_overlay_build_telemetry(DebugOverlay *ov,
    const TelemetrySystem *t,
    float camX, float camY, float camZ)
{
    float scale = 2.5f;
    float margin = 10.0f;
    float lineH = 9.0f * scale;
    float panelW = 380.0f;
    float panelH = lineH * 10 + 16.0f;
    float y = margin + 4.0f;

    /* Fondo HUD semitransparente con borde */
    debug_overlay_add_rect(ov, margin - 4, margin - 4, panelW, panelH, 0.05f, 0.07f, 0.10f);

    /* Encabezado ISO 25010:2023 */
    debug_overlay_add_text(ov, margin, y, "[ISO 25010:2023 TELEMETRIA]", scale, 0.0f, 0.9f, 1.0f);
    y += lineH + 2.0f;

    char buf[128];
    /* GPU Hardware y Resolución */
    if (t->gpuName[0] != '\0') {
        snprintf(buf, sizeof(buf), "GPU: %.28s...", t->gpuName);
        debug_overlay_add_text(ov, margin, y, buf, scale, 0.7f, 0.85f, 1.0f);
        y += lineH;
    }
    if (t->screenWidth > 0 && t->screenHeight > 0) {
        snprintf(buf, sizeof(buf), "Res: %ux%u px", t->screenWidth, t->screenHeight);
        debug_overlay_add_text(ov, margin, y, buf, scale, 0.7f, 0.85f, 1.0f);
        y += lineH;
    }

    /* Hora simulada (Ciclo de 72 min) */
    int hours = (int)t->simHour;
    int mins = (int)((t->simHour - (float)hours) * 60.0f);
    const char* phase = (hours >= 6 && hours < 18) ? ((hours < 8) ? "Amanecer" : (hours > 16) ? "Atardecer" : "Dia") : "Noche";
    snprintf(buf, sizeof(buf), "Hora Sim: %02d:%02d (%s)", hours, mins, phase);
    debug_overlay_add_text(ov, margin, y, buf, scale, 1.0f, 0.9f, 0.4f);
    y += lineH;

    /* Color FPS: verde >50, amarillo 30-50, rojo <30 */
    float fr = (t->fps < 30.0f) ? 1.0f : (t->fps < 50.0f) ? 1.0f : 0.2f;
    float fg = (t->fps < 30.0f) ? 0.2f : (t->fps < 50.0f) ? 0.9f : 1.0f;
    float fb = (t->fps < 30.0f) ? 0.2f : (t->fps < 50.0f) ? 0.2f : 0.4f;

    snprintf(buf, sizeof(buf), "FPS: %.0f (Frame: %.2f ms)", t->fps, t->frameTimeMs);
    debug_overlay_add_text(ov, margin, y, buf, scale, fr, fg, fb);
    y += lineH;

    snprintf(buf, sizeof(buf), "CPU Update: %.2f ms", t->cpuTimeMs);
    debug_overlay_add_text(ov, margin, y, buf, scale, 0.9f, 0.8f, 0.3f);
    y += lineH;

    snprintf(buf, sizeof(buf), "GPU Render: %.2f ms", t->gpuTimeMs);
    debug_overlay_add_text(ov, margin, y, buf, scale, 0.4f, 0.9f, 0.5f);
    y += lineH;

    snprintf(buf, sizeof(buf), "Traffic: %u Semaf | %u Cruces",
             t->trafficSignalsCount, t->trafficIntersectionsCount);
    debug_overlay_add_text(ov, margin, y, buf, scale, 1.0f, 0.75f, 0.3f);
    y += lineH;

    snprintf(buf, sizeof(buf), "Chunks: %u/%u | Draw: %u",
             t->visibleChunks, t->totalChunks, t->drawCalls);
    debug_overlay_add_text(ov, margin, y, buf, scale, 0.8f, 0.9f, 1.0f);
    y += lineH;

    snprintf(buf, sizeof(buf), "Verts: %uk/%uk (Cull: %.0f%%)",
             t->visibleVerts / 1000, t->totalVerts / 1000, t->cullingEfficiencyPct);
    debug_overlay_add_text(ov, margin, y, buf, scale, 0.8f, 0.9f, 1.0f);
    y += lineH;

    snprintf(buf, sizeof(buf), "Pos: %.0f %.0f %.0f", camX, camY, camZ);
    debug_overlay_add_text(ov, margin, y, buf, scale, 0.6f, 0.8f, 0.6f);
}

/* Construir la información de debug estándar del frame (retrocompatibilidad) */
static inline void debug_overlay_build_stats(DebugOverlay *ov,
    float fps, int visibleChunks, int totalChunks,
    uint32_t visibleVerts, uint32_t totalVerts,
    float camX, float camY, float camZ)
{
    TelemetrySystem t = {0};
    t.fps = fps;
    t.frameTimeMs = (fps > 0.1f) ? (1000.0f / fps) : 0.0f;
    t.visibleChunks = (uint32_t)visibleChunks;
    t.totalChunks = (uint32_t)totalChunks;
    t.visibleVerts = visibleVerts;
    t.totalVerts = totalVerts;
    t.drawCalls = (uint32_t)visibleChunks;
    if (totalVerts > 0) {
        t.cullingEfficiencyPct = (1.0f - ((float)visibleVerts / (float)totalVerts)) * 100.0f;
    }
    t.frameBudgetPct = (t.frameTimeMs / 16.6667f) * 100.0f;
    debug_overlay_build_telemetry(ov, &t, camX, camY, camZ);
}

#endif /* DEBUG_OVERLAY_H */

