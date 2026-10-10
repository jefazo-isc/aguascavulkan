#!/usr/bin/env python3
"""
Generador de Modelos 3D (OBJ) desde Imágenes Satelitales via Gemini AI
=======================================================================
Pipeline:
  1. Recibe un recuadro (bounding box) de la imagen satelital + metadatos JSON
  2. Recorta el parche (patch) de la ortofoto
  3. Envía imagen + contexto JSON a Gemini (modelo multimodal)
  4. Gemini devuelve JSON estructurado con la geometría 3D del objeto
  5. Se convierte a formato Wavefront OBJ compatible con StreetVulkan

Uso:
  python3 gemini_obj_generator.py --image assets/satellite.png \
    --bbox '{"x0": -500, "z0": -300, "x1": -450, "z1": -260}' \
    --metadata '{"type": "building", "area_m2": 180, "stories_hint": 3}' \
    --output models/generated_building.obj

  python3 gemini_obj_generator.py --config patch_request.json
"""

import os
import sys
import json
import math
import base64
import argparse
import time
import hashlib
import threading
import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

# PIL para recortar la imagen
try:
    from PIL import Image
except ImportError:
    print("[ERROR] Necesitas Pillow: pip3 install --break-system-packages Pillow")
    sys.exit(1)

# SDK de Google Gemini
try:
    from google import genai
    from pydantic import BaseModel, Field
    from typing import List, Optional
except ImportError:
    print("[ERROR] Necesitas google-genai: pip3 install --break-system-packages google-genai")
    sys.exit(1)

# Cargar .env (misma convención del Oráculo)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # Sin dotenv, usa variables del sistema


# ===========================================================================
# RateLimiter — copiado del Oráculo (ultimate_oraculus/agente/rate_limiter.py)
# ===========================================================================

class RateLimiter:
    """
    Controlador de peticiones estricto para evitar errores 429 (Too Many Requests).
    Maneja la concurrencia de múltiples hilos utilizando threading.Lock().
    """
    def __init__(self, max_calls: int = 14, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period]

            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    logger.info(f"Semáforo API en rojo. Límite de {self.max_calls} RPM alcanzado. Esperando {round(sleep_time, 2)}s...")
                    print(f"[RateLimit] ⏳ Esperando {sleep_time:.1f}s (límite {self.max_calls} RPM)")
                    time.sleep(sleep_time)

                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.period]

            self.calls.append(now)


# Instancia global del rate limiter (configurable vía .env)
_rpm = int(os.environ.get("GEMINI_RPM", "14"))
gemini_rate_limiter = RateLimiter(max_calls=_rpm, period=60.0)


# ===========================================================================
# DiskCache — Cache en disco para no desperdiciar peticiones de Gemini
# ===========================================================================

class DiskCache:
    """
    Caché persistente en disco para respuestas de Gemini.
    Clave = hash(bbox + metadata). Valor = JSON de GeneratedObject3D.
    Directorio por defecto: models/gemini_cache/
    """
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            # Siempre relativo al proyecto vulkan, no al cwd
            cache_dir = Path(__file__).parent.parent / "models" / "gemini_cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, bbox: dict, metadata: dict) -> str:
        """Genera un hash determinista del bbox + metadatos."""
        payload = json.dumps({"bbox": bbox, "meta": metadata}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get(self, bbox: dict, metadata: dict) -> Optional[str]:
        """Busca en caché. Devuelve el JSON crudo si existe, None si no."""
        key = self._make_key(bbox, metadata)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            print(f"[Cache] ✅ HIT — Usando resultado guardado ({key})")
            return cache_file.read_text()
        return None

    def put(self, bbox: dict, metadata: dict, response_json: str):
        """Guarda la respuesta de Gemini en disco."""
        key = self._make_key(bbox, metadata)
        cache_file = self.cache_dir / f"{key}.json"
        cache_file.write_text(response_json)
        print(f"[Cache] 💾 Guardado en disco ({key})")

    def has(self, bbox: dict, metadata: dict) -> bool:
        key = self._make_key(bbox, metadata)
        return (self.cache_dir / f"{key}.json").exists()


# Instancia global de caché
gemini_cache = DiskCache()


# Modelo configurable (misma convención del Oráculo config.py)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")


# ===========================================================================
# Esquema de datos 3D (Pydantic → JSON Schema para Structured Output)
# ===========================================================================

class Vertex3D(BaseModel):
    """Un vértice en espacio 3D local (metros)."""
    x: float = Field(description="Coordenada X en metros (este-oeste)")
    y: float = Field(description="Coordenada Y en metros (altura sobre el suelo)")
    z: float = Field(description="Coordenada Z en metros (norte-sur)")

class Face3D(BaseModel):
    """Una cara poligonal definida por índices de vértices (1-indexed como OBJ)."""
    vertex_indices: List[int] = Field(
        description="Índices de vértices que forman esta cara (1-indexed). "
                    "Mínimo 3 para un triángulo. Orden counter-clockwise visto desde afuera."
    )

class MaterialInfo(BaseModel):
    """Información de material/color del objeto."""
    name: str = Field(description="Nombre del material (ej: 'concreto', 'ladrillo', 'vidrio', 'metal')")
    r: float = Field(description="Componente rojo del color (0.0-1.0)")
    g: float = Field(description="Componente verde del color (0.0-1.0)")
    b: float = Field(description="Componente azul del color (0.0-1.0)")

class ObjectComponent(BaseModel):
    """Un componente/parte del objeto 3D (ej: techo, paredes, base)."""
    name: str = Field(description="Nombre descriptivo del componente (ej: 'roof', 'walls', 'base', 'tower')")
    vertices: List[Vertex3D] = Field(description="Lista de vértices de este componente")
    faces: List[Face3D] = Field(description="Lista de caras poligonales de este componente")
    material: MaterialInfo = Field(description="Material/color de este componente")

class GeneratedObject3D(BaseModel):
    """Objeto 3D completo generado a partir de una vista aérea satelital."""
    object_type: str = Field(description="Tipo de objeto identificado (ej: 'edificio_residencial', 'bodega', 'iglesia', 'estacionamiento')")
    description: str = Field(description="Descripción breve del objeto y sus características arquitectónicas")
    estimated_height_m: float = Field(description="Altura estimada en metros")
    estimated_width_m: float = Field(description="Ancho estimado en metros (eje X)")
    estimated_depth_m: float = Field(description="Profundidad estimada en metros (eje Z)")
    components: List[ObjectComponent] = Field(description="Componentes geométricos del objeto 3D")
    confidence: float = Field(description="Confianza en la identificación (0.0-1.0)")


# ===========================================================================
# Funciones de recorte y preparación
# ===========================================================================

def crop_satellite_patch(image_path, x0, z0, x1, z1, map_x0, map_z0, map_x1, map_z1):
    """
    Recorta un parche rectangular de la ortofoto satelital.
    Las coordenadas (x0,z0)-(x1,z1) están en metros del espacio mundo.
    (map_x0, map_z0)-(map_x1, map_z1) son los límites totales del mapa en metros.
    
    Devuelve: (imagen PIL recortada, bytes PNG en base64)
    """
    img = Image.open(image_path)
    w, h = img.size

    # Convertir metros a píxeles
    u0 = (x0 - map_x0) / (map_x1 - map_x0)
    v0 = (z0 - map_z0) / (map_z1 - map_z0)
    u1 = (x1 - map_x0) / (map_x1 - map_x0)
    v1 = (z1 - map_z0) / (map_z1 - map_z0)

    px_left = max(0, int(u0 * w))
    px_top = max(0, int(v0 * h))
    px_right = min(w, int(u1 * w))
    px_bottom = min(h, int(v1 * h))

    patch = img.crop((px_left, px_top, px_right, px_bottom))

    # Escalar a 512x512 para enviar a Gemini (buen balance calidad/tokens)
    patch_resized = patch.resize((512, 512), Image.Resampling.LANCZOS)

    # Convertir a base64
    buf = BytesIO()
    patch_resized.save(buf, format="PNG")
    b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

    return patch_resized, b64_data


def build_prompt(metadata, bbox):
    """Construye el prompt del sistema y del usuario para Gemini."""

    system_prompt = """Eres un experto en fotogrametría, modelado 3D urbano y generación procedural de assets.
Tu tarea es analizar imágenes satelitales/aéreas de vista superior (top-down) y generar
la geometría 3D del objeto principal con ALTA DENSIDAD DE POLÍGONOS.

REGLAS DE GEOMETRÍA:
1. El origen (0,0,0) es el centro del bounding box del objeto al nivel del suelo.
2. Y positivo = hacia arriba (altura).
3. X positivo = este, Z positivo = sur (convención StreetVulkan).
4. Las caras usan índices 1-indexed (como formato OBJ).
5. Las caras deben estar en orden counter-clockwise vistas desde afuera.
6. Genera geometría con DENSIDAD MEDIA-ALTA: 50-800 vértices por componente.
7. Separa el objeto en componentes lógicos con materiales diferentes.
8. TODOS los triángulos deben ser de 3 vértices (no quads).

GUÍA DE DENSIDAD POR TIPO DE OBJETO:
- Árbol: tronco cilíndrico (12-16 segmentos) + copa esférica/irregular (40-80 vértices). 
  La copa NO es una esfera perfecta, debe tener irregularidades naturales.
  Genera al menos 3 niveles de ramas si es un árbol grande.
- Roca: forma irregular con 30-60 vértices, superficie rugosa con variaciones.
- Vegetación/arbusto: masa orgánica irregular, 20-50 vértices, forma esférica achatada.
- Edificio: extrusión con detalles (cornisas, escalones, voladizos). 40-200 vértices.
- Puente: arcos estructurales + superficie de rodamiento + barandillas. 100-400 vértices.
- Estatua/monumento: silueta reconocible, base + cuerpo + detalles. 80-300 vértices.
- Campo deportivo: superficie plana + marcas + porterías/postes. 60-150 vértices.
- Iglesia/templo: nave + campanario/torre + techo a dos aguas. 100-300 vértices.
- Fuente: base circular + tazones + columna central. 60-200 vértices.
- Banca/mobiliario: forma reconocible compacta. 20-40 vértices.

REGLAS DE COLOR:
- Los colores RGB deben reflejar lo observado en la imagen satelital.
- Árboles: tronco marrón oscuro (0.35, 0.22, 0.10), copa verde variado.
- Rocas: tonos grises/marrones irregulares.
- Concreto: beige/gris claro.
- Metal: gris oscuro con reflectividad.
- Pasto: verde (0.25, 0.55, 0.15)."""

    user_prompt = f"""Analiza esta vista aérea/satelital y genera el modelo 3D del objeto principal.
Genera geometría DETALLADA con alta densidad de polígonos.

CONTEXTO (metadatos del recuadro):
- Bounding box en metros: x=[{bbox['x0']:.1f}, {bbox['x1']:.1f}], z=[{bbox['z0']:.1f}, {bbox['z1']:.1f}]
- Tamaño del recuadro: {abs(bbox['x1'] - bbox['x0']):.1f}m x {abs(bbox['z1'] - bbox['z0']):.1f}m
"""

    if metadata:
        if 'type' in metadata:
            user_prompt += f"- Tipo sugerido: {metadata['type']}\n"
        if 'area_m2' in metadata:
            user_prompt += f"- Área estimada: {metadata['area_m2']:.1f} m²\n"
        if 'stories_hint' in metadata:
            user_prompt += f"- Pisos estimados: {metadata['stories_hint']}\n"
        if 'roof_color' in metadata:
            rc = metadata['roof_color']
            user_prompt += f"- Color de azotea detectado (RGB): ({rc[0]:.2f}, {rc[1]:.2f}, {rc[2]:.2f})\n"
        if 'neighborhood' in metadata:
            user_prompt += f"- Colonia/barrio: {metadata['neighborhood']}\n"
        if 'osm_tags' in metadata:
            user_prompt += f"- Tags OSM: {json.dumps(metadata['osm_tags'])}\n"
        if 'poly_hint' in metadata:
            user_prompt += f"- Densidad de polígonos deseada: {metadata['poly_hint']}\n"

    user_prompt += """
Genera la geometría 3D completa del objeto con MUCHOS polígonos. Incluye:
1. Forma detallada del objeto con subdivisiones suficientes para que se vea suave
2. Componentes separados con materiales y colores distintos
3. Si es vegetación: formas orgánicas irregulares, NO esferas perfectas
4. Si es edificio: cornisas, relieves, detalles arquitectónicos
5. Usa SOLO triángulos (3 vértices por cara)

Responde ÚNICAMENTE con el JSON estructurado."""

    return system_prompt, user_prompt


# ===========================================================================
# Llamada a Gemini
# ===========================================================================

def call_gemini(image_b64, system_prompt, user_prompt, api_key=None, bbox=None, metadata=None):
    """
    Envía el parche de imagen + prompt a Gemini y obtiene geometría 3D estructurada.
    Incluye: caché en disco + rate limiter (patrón Oráculo).
    """
    # 1. Verificar caché en disco ANTES de gastar una petición
    if bbox and metadata:
        cached = gemini_cache.get(bbox, metadata)
        if cached:
            return GeneratedObject3D.model_validate_json(cached)

    # 2. Rate limiter — esperar si estamos en el límite de RPM
    gemini_rate_limiter.wait()

    # 3. Conectar con Gemini
    _api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if _api_key:
        client = genai.Client(api_key=_api_key)
    else:
        client = genai.Client()

    model = GEMINI_MODEL
    print(f"[Gemini] Enviando imagen al modelo {model}...")
    start_time = time.time()

    interaction = client.interactions.create(
        model=model,
        system_instruction=system_prompt,
        input=[
            {
                "type": "image",
                "data": image_b64,
                "mime_type": "image/png"
            },
            {
                "type": "text",
                "text": user_prompt
            }
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": GeneratedObject3D.model_json_schema()
        },
    )

    elapsed = time.time() - start_time
    print(f"[Gemini] Respuesta recibida en {elapsed:.1f}s")

    # Parsear respuesta estructurada
    raw_json = interaction.output_text
    result = GeneratedObject3D.model_validate_json(raw_json)

    # 4. Guardar en caché para no desperdiciar esta petición
    if bbox and metadata:
        gemini_cache.put(bbox, metadata, raw_json)

    return result


# ===========================================================================
# Generación de Textura con Gemini Image
# ===========================================================================

# Caché separada para texturas (mismo patrón)
texture_cache = DiskCache(
    cache_dir=Path(__file__).parent.parent / "models" / "gemini_texture_cache"
)

def synthesize_bitmap_texture(generated: GeneratedObject3D, tex_path: str, width=512, height=512):
    """
    Sintetizador procedural de texturas bitmap de alta resolución para props urbanos,
    vegetación, campos deportivos, rocas, puentes y monumentos.
    Genera un archivo PNG de 512x512 de calidad fotorealista sin requerir descargas.
    """
    import random
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np

    ot = (generated.object_type or "").lower()
    desc = (generated.description or "").lower()

    if any(k in ot or k in desc for k in ["futbol", "soccer", "estadio", "cancha", "campo"]):
        # ── Campo de Fútbol / Cancha Deportiva ──
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        stripe_w = 32
        for i in range(0, width, stripe_w):
            col = (46, 155, 46) if (i // stripe_w) % 2 == 0 else (36, 132, 36)
            draw.rectangle([i, 0, i + stripe_w, height], fill=col)
        pad = 28
        draw.rectangle([pad, pad, width - pad, height - pad], outline=(245, 245, 245), width=3)
        mid_x = width // 2
        draw.line([(mid_x, pad), (mid_x, height - pad)], fill=(245, 245, 245), width=3)
        cr = 54
        draw.ellipse([mid_x - cr, height // 2 - cr, mid_x + cr, height // 2 + cr], outline=(245, 245, 245), width=3)
        draw.ellipse([mid_x - 4, height // 2 - 4, mid_x + 4, height // 2 + 4], fill=(245, 245, 245))
        box_w, box_h = 75, 150
        draw.rectangle([pad, height // 2 - box_h // 2, pad + box_w, height // 2 + box_h // 2], outline=(245, 245, 245), width=3)
        draw.rectangle([width - pad - box_w, height // 2 - box_h // 2, width - pad, height // 2 + box_h // 2], outline=(245, 245, 245), width=3)
        goal_w, goal_h = 35, 70
        draw.rectangle([pad, height // 2 - goal_h // 2, pad + goal_w, height // 2 + goal_h // 2], outline=(245, 245, 245), width=3)
        draw.rectangle([width - pad - goal_w, height // 2 - goal_h // 2, width - pad, height // 2 + goal_h // 2], outline=(245, 245, 245), width=3)
        draw.ellipse([pad + 55 - 3, height // 2 - 3, pad + 55 + 3, height // 2 + 3], fill=(245, 245, 245))
        draw.ellipse([width - pad - 55 - 3, height // 2 - 3, width - pad - 55 + 3, height // 2 + 3], fill=(245, 245, 245))
        c_arc = 12
        draw.arc([pad - c_arc, pad - c_arc, pad + c_arc, pad + c_arc], 0, 90, fill=(245, 245, 245), width=2)
        draw.arc([width - pad - c_arc, pad - c_arc, width - pad + c_arc, pad + c_arc], 90, 180, fill=(245, 245, 245), width=2)
        draw.arc([width - pad - c_arc, height - pad - c_arc, width - pad + c_arc, height - pad + c_arc], 180, 270, fill=(245, 245, 245), width=2)
        draw.arc([pad - c_arc, height - pad - c_arc, pad + c_arc, height - pad + c_arc], 270, 360, fill=(245, 245, 245), width=2)
        img.save(tex_path, format="PNG")

    elif any(k in ot or k in desc for k in ["arbol", "tree", "vegetacion", "planta", "arbusto", "palmera"]):
        # ── Árbol / Vegetación: Atlas compuesto (Corteza + Follaje) ──
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        # Mitad izquierda: Corteza
        for y in range(height):
            for x in range(width // 2):
                grain = int(22 * np.sin(x * 0.18) + 12 * np.sin(y * 0.04) + random.randint(-12, 12))
                r = np.clip(82 + grain, 35, 135)
                g = np.clip(52 + int(grain * 0.65), 22, 95)
                b = np.clip(32 + int(grain * 0.35), 12, 55)
                arr[y, x] = [r, g, b]
        # Mitad derecha: Follaje denso
        for y in range(height):
            for x in range(width // 2, width):
                leaf = random.randint(-40, 40)
                depth = int(18 * np.sin(x * 0.08) * np.cos(y * 0.08))
                r = np.clip(32 + leaf // 2 + depth, 15, 80)
                g = np.clip(125 + leaf + depth, 55, 195)
                b = np.clip(28 + leaf // 3 + depth, 10, 65)
                arr[y, x] = [r, g, b]
        img = Image.fromarray(arr).filter(ImageFilter.SMOOTH_MORE)
        img.save(tex_path, format="PNG")

    elif any(k in ot or k in desc for k in ["roca", "rock", "piedra", "peña", "pedregal"]):
        # ── Roca / Piedra Estratificada ──
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                strata = int(25 * np.sin((y + x * 0.3) * 0.05) + random.randint(-20, 20))
                r = np.clip(130 + strata, 60, 190)
                g = np.clip(125 + strata, 58, 185)
                b = np.clip(120 + strata, 55, 180)
                arr[y, x] = [r, g, b]
        img = Image.fromarray(arr).filter(ImageFilter.SMOOTH)
        img.save(tex_path, format="PNG")

    elif any(k in ot or k in desc for k in ["puente", "bridge", "viaducto", "paso_desnivel"]):
        # ── Puente: Concreto estructural con calzada ──
        img = Image.new("RGB", (width, height), (130, 130, 135))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 0, width - 40, height], fill=(55, 55, 58))
        draw.line([(width // 2, 0), (width // 2, height)], fill=(240, 190, 30), width=4)
        draw.line([(60, 0), (60, height)], fill=(240, 240, 240), width=3)
        draw.line([(width - 60, 0), (width - 60, height)], fill=(240, 240, 240), width=3)
        img.save(tex_path, format="PNG")

    elif any(k in ot or k in desc for k in ["estatua", "statue", "monumento", "escultura"]):
        # ── Estatua / Monumento: Bronce con pátina ──
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                patina = random.random() < 0.22
                if patina:
                    r, g, b = random.randint(40, 80), random.randint(140, 180), random.randint(140, 175)
                else:
                    noise = random.randint(-15, 15)
                    r = np.clip(125 + noise, 70, 160)
                    g = np.clip(95 + noise, 55, 130)
                    b = np.clip(60 + noise, 35, 90)
                arr[y, x] = [r, g, b]
        img = Image.fromarray(arr).filter(ImageFilter.SMOOTH)
        img.save(tex_path, format="PNG")

    else:
        # ── Edificio Urbano / Fachadas y Techo ──
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                noise = random.randint(-10, 10)
                arr[y, x] = [np.clip(190 + noise, 120, 230),
                             np.clip(185 + noise, 115, 225),
                             np.clip(175 + noise, 110, 215)]
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        win_w, win_h = 24, 36
        for gy in range(40, height - 40, 60):
            for gx in range(40, width - 40, 48):
                draw.rectangle([gx, gy, gx + win_w, gy + win_h], fill=(45, 75, 110), outline=(220, 220, 220), width=2)
        img.save(tex_path, format="PNG")

    print(f"[Textura] 🎨 Bitmap sintetizado proceduralmente ({width}x{height}): {tex_path}")
    return tex_path

def generate_texture(generated: GeneratedObject3D, output_path: str, api_key=None, bbox=None, metadata=None):
    """
    Genera una textura bitmap para el objeto 3D usando Gemini Image con fallback a síntesis procedural.
    La guarda como PNG junto al OBJ y la referencia en el MTL.
    
    Returns: ruta al PNG generado.
    """
    tex_path = output_path.replace(".obj", "_tex.png")

    # 1. Verificar si ya existe en disco
    if os.path.exists(tex_path) and os.path.getsize(tex_path) > 100:
        print(f"[Textura] ✅ Ya existe en disco: {tex_path}")
        return tex_path

    # 2. Verificar caché
    cache_key_meta = {**(metadata or {}), "_tex": True}
    cached_b64 = texture_cache.get(bbox or {}, cache_key_meta) if bbox else None
    if cached_b64:
        img_data = base64.b64decode(cached_b64)
        with open(tex_path, "wb") as f:
            f.write(img_data)
        print(f"[Textura] ✅ Cargada desde caché: {tex_path}")
        return tex_path

    # 3. Intentar generar con Gemini Image si hay key
    _api_key = api_key or os.environ.get("GEMINI_API_KEY")
    tex_model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-lite-image")

    if _api_key:
        try:
            gemini_rate_limiter.wait()
            client = genai.Client(api_key=_api_key)
            materials = ", ".join(set(c.material.name for c in generated.components))
            tex_prompt = (
                f"Seamless tileable texture atlas of a {generated.object_type}. "
                f"Details: {generated.description}. Materials: {materials}. "
                f"Photorealistic 512x512, top down perspective. No text or labels."
            )
            print(f"[Textura] Intentando generar bitmap con {tex_model}...")
            resp = client.models.generate_content(
                model=tex_model,
                contents=[tex_prompt]
            )
            for part in resp.parts:
                if part.inline_data is not None:
                    raw_bytes = part.inline_data.data
                    with open(tex_path, "wb") as f:
                        f.write(raw_bytes)
                    print(f"[Textura] 💾 Bitmap IA generado: {tex_path}")
                    if bbox and metadata:
                        texture_cache.put(bbox, cache_key_meta, base64.b64encode(raw_bytes).decode())
                    return tex_path
        except Exception as e:
            print(f"[Textura] Nota: Generación por API no disponible ({e}), usando sintetizador procedural.")

    # 4. Fallback garantizado: Síntesis procedural de bitmap fotorealista
    synthesize_bitmap_texture(generated, tex_path)
    return tex_path

def export_obj(generated: GeneratedObject3D, output_path: str, offset_x=0.0, offset_y=0.0, offset_z=0.0, texture_path=None):
    """
    Convierte el objeto 3D generado por Gemini a formato Wavefront OBJ.
    offset_x, offset_y, offset_z: para posicionar el objeto en el espacio mundo de StreetVulkan sobre el terreno.
    texture_path: ruta al PNG de textura generada (opcional).
    """
    lines = []
    lines.append(f"# Generado por gemini_obj_generator.py (StreetVulkan)")
    lines.append(f"# Tipo: {generated.object_type}")
    lines.append(f"# Descripción: {generated.description}")
    lines.append(f"# Dimensiones estimadas: {generated.estimated_width_m:.1f}m x {generated.estimated_height_m:.1f}m x {generated.estimated_depth_m:.1f}m")
    lines.append(f"# Confianza: {generated.confidence:.2f}")
    lines.append("")

    # Generar archivo MTL inline (para colores + textura)
    mtl_name = os.path.splitext(os.path.basename(output_path))[0] + ".mtl"
    mtl_path = os.path.join(os.path.dirname(output_path) or ".", mtl_name)
    lines.append(f"mtllib {mtl_name}")
    lines.append("")

    # Nombre relativo de la textura para el MTL
    tex_rel = os.path.basename(texture_path) if texture_path else None

    mtl_lines = []
    mtl_lines.append(f"# Material generado por Gemini AI para: {generated.object_type}")
    if tex_rel:
        mtl_lines.append(f"# Textura: {tex_rel}")

    vertex_offset = 0  # Acumulador de offset de vértices entre componentes

    for comp in generated.components:
        lines.append(f"o {comp.name}")
        lines.append(f"usemtl {comp.material.name}_{comp.name}")

        # Material
        mtl_lines.append(f"\nnewmtl {comp.material.name}_{comp.name}")
        mtl_lines.append(f"Kd {comp.material.r:.4f} {comp.material.g:.4f} {comp.material.b:.4f}")
        mtl_lines.append(f"Ka {comp.material.r * 0.3:.4f} {comp.material.g * 0.3:.4f} {comp.material.b * 0.3:.4f}")
        mtl_lines.append("Ks 0.1000 0.1000 0.1000")
        mtl_lines.append("Ns 10.0")
        mtl_lines.append("d 1.0")
        # Textura generada por IA
        if tex_rel:
            mtl_lines.append(f"map_Kd {tex_rel}")

        # Calcular UVs por componente
        xs = [v.x for v in comp.vertices] if comp.vertices else [0.0]
        ys = [v.y for v in comp.vertices] if comp.vertices else [0.0]
        zs = [v.z for v in comp.vertices] if comp.vertices else [0.0]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        dx = max(0.01, max_x - min_x)
        dy = max(0.01, max_y - min_y)
        dz = max(0.01, max_z - min_z)

        is_tree = any(k in comp.name.lower() or k in generated.object_type.lower()
                      for k in ["arbol", "tree", "vegetacion", "tronco", "hoja", "canopy", "rama"])
        is_trunk = any(k in comp.name.lower() for k in ["tronco", "trunk", "rama", "base", "tallo"])

        # Vértices con coordenadas UV (x y z u v)
        for v in comp.vertices:
            if is_tree:
                if is_trunk:
                    angle = (math.atan2(v.z, v.x) + math.pi) / (2.0 * math.pi)
                    u = 0.02 + angle * 0.46  # Mitad izquierda: corteza
                    vt = (v.y - min_y) / dy
                else:
                    u = 0.52 + ((v.x - min_x) / dx) * 0.46  # Mitad derecha: follaje
                    vt = (v.z - min_z) / dz
            elif dy < 0.8:  # Superficies horizontales (campo fútbol, techos, terreno)
                u = (v.x - min_x) / dx
                vt = (v.z - min_z) / dz
            else:  # Superficies verticales / 3D (rocas, puentes, edificios)
                u = (v.x - min_x) / dx
                vt = (v.y - min_y) / dy

            lines.append(f"v {v.x + offset_x:.6f} {v.y + offset_y:.6f} {v.z + offset_z:.6f} {u:.4f} {vt:.4f}")

        lines.append("")

        # Caras (ajustar índices con el offset acumulado)
        for face in comp.faces:
            idx_str = " ".join(str(i + vertex_offset) for i in face.vertex_indices)
            lines.append(f"f {idx_str}")

        lines.append("")
        vertex_offset += len(comp.vertices)

    # Escribir OBJ
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[OBJ] Modelo exportado: {output_path} ({vertex_offset} vértices)")

    # Escribir MTL
    with open(mtl_path, "w") as f:
        f.write("\n".join(mtl_lines))
    print(f"[MTL] Material exportado: {mtl_path}")

    return output_path


# ===========================================================================
# Funciones de integración con StreetVulkan
# ===========================================================================

def get_ground_elevation(x, z):
    """
    Obtiene la cota topográfica real del terreno en metros desde el DEM satelital.
    Garantiza que cualquier objeto generado se pose SOBRE el terreno y nunca en el subsuelo.
    """
    try:
        from geo_dem import TerrainElevation, DEFAULT_ORIGIN_LAT, DEFAULT_ORIGIN_LON
        terrain = TerrainElevation(21.8690, 21.8940, -102.3110, -102.2815,
                                   nx=40, ny=40,
                                   origin_lat=DEFAULT_ORIGIN_LAT, origin_lon=DEFAULT_ORIGIN_LON)
        return terrain.get_ground_elevation(x, z)
    except Exception as e:
        print(f"[DEM] Aviso de elevación: {e}")
        return 0.0


def generate_from_patch(image_path, bbox, metadata=None,
                        map_bounds=None, output_path=None, api_key=None):
    """
    Función principal: genera un OBJ a partir de un parche satelital.
    
    Args:
        image_path: Ruta a la ortofoto satelital completa
        bbox: dict con {x0, z0, x1, z1} en metros (espacio mundo)
        metadata: dict opcional con pistas (type, area_m2, stories_hint, roof_color, etc.)
        map_bounds: dict con {x0, z0, x1, z1} de los límites totales del mapa en metros
        output_path: ruta del archivo OBJ de salida
        api_key: API key de Gemini (o usar env GEMINI_API_KEY)
    
    Returns:
        GeneratedObject3D con la geometría parseada, o None si falla
    """
    if map_bounds is None:
        map_bounds = {"x0": -1700, "z0": -1600, "x1": 1700, "z1": 1600}

    if metadata is None:
        metadata = {}

    if output_path is None:
        output_path = f"models/gemini_object_{int(time.time())}.obj"

    # 1. Recortar parche
    print(f"[Patch] Recortando parche: ({bbox['x0']:.0f},{bbox['z0']:.0f}) -> ({bbox['x1']:.0f},{bbox['z1']:.0f})")
    patch_img, b64_data = crop_satellite_patch(
        image_path,
        bbox["x0"], bbox["z0"], bbox["x1"], bbox["z1"],
        map_bounds["x0"], map_bounds["z0"], map_bounds["x1"], map_bounds["z1"]
    )

    # 2. Construir prompt
    system_prompt, user_prompt = build_prompt(metadata, bbox)

    # 3. Llamar a Gemini (con caché + rate limiter integrados)
    generated = call_gemini(b64_data, system_prompt, user_prompt, api_key,
                            bbox=bbox, metadata=metadata)

    print(f"[Gemini] Objeto identificado: {generated.object_type}")
    print(f"[Gemini] Descripción: {generated.description}")
    print(f"[Gemini] Dimensiones: {generated.estimated_width_m:.1f}m x {generated.estimated_height_m:.1f}m x {generated.estimated_depth_m:.1f}m")
    print(f"[Gemini] Confianza: {generated.confidence:.0%}")
    print(f"[Gemini] Componentes: {len(generated.components)}")
    total_verts = 0
    for comp in generated.components:
        total_verts += len(comp.vertices)
        print(f"  - {comp.name}: {len(comp.vertices)} vértices, {len(comp.faces)} caras ({comp.material.name})")
    print(f"[Gemini] Total vértices: {total_verts}")

    # 4. Generar textura con Gemini Image (con fallback procedural)
    tex_path = generate_texture(generated, output_path, api_key=api_key,
                                 bbox=bbox, metadata=metadata)

    # 5. Exportar OBJ posicionado SOBRE el terreno topográfico (cero subsuelo)
    center_x = (bbox["x0"] + bbox["x1"]) / 2.0
    center_z = (bbox["z0"] + bbox["z1"]) / 2.0
    ground_y = get_ground_elevation(center_x, center_z)
    offset_y = ground_y + 0.05  # +5cm para apoyarse limpiamente sobre el suelo sin z-fighting
    print(f"[Elevación] Cota topográfica en ({center_x:.1f}, {center_z:.1f}): {ground_y:.2f}m -> Base a {offset_y:.2f}m")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    export_obj(generated, output_path, offset_x=center_x, offset_y=offset_y, offset_z=center_z,
               texture_path=tex_path)

    # 6. Guardar parche recortado como referencia
    patch_path = output_path.replace(".obj", "_patch.png")
    patch_img.save(patch_path)
    print(f"[Patch] Imagen de referencia guardada: {patch_path}")

    return generated


def batch_generate(image_path, patches_json_path, map_bounds=None, output_dir="models/generated", api_key=None):
    """
    Genera múltiples objetos 3D a partir de una lista de parches en un JSON.
    
    El JSON debe tener la estructura:
    [
        {
            "bbox": {"x0": ..., "z0": ..., "x1": ..., "z1": ...},
            "metadata": {"type": "building", "area_m2": 180, ...}
        },
        ...
    ]
    """
    with open(patches_json_path, "r") as f:
        patches = json.load(f)

    os.makedirs(output_dir, exist_ok=True)
    results = []

    for i, patch_def in enumerate(patches):
        print(f"\n{'='*60}")
        print(f"  Procesando parche {i+1}/{len(patches)}")
        print(f"{'='*60}")

        bbox = patch_def["bbox"]
        metadata = patch_def.get("metadata", {})
        out_path = os.path.join(output_dir, f"object_{i:04d}.obj")

        try:
            result = generate_from_patch(
                image_path, bbox, metadata,
                map_bounds=map_bounds,
                output_path=out_path,
                api_key=api_key
            )
            results.append({"index": i, "path": out_path, "type": result.object_type, "ok": True})
        except Exception as e:
            print(f"[ERROR] Fallo en parche {i}: {e}")
            results.append({"index": i, "path": out_path, "error": str(e), "ok": False})

        # Rate limiting suave
        if i < len(patches) - 1:
            time.sleep(1.0)

    # Resumen
    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETADO: {ok_count}/{len(patches)} objetos generados")
    print(f"{'='*60}")

    summary_path = os.path.join(output_dir, "batch_summary.json")
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)

    return results


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Genera modelos 3D (OBJ) desde imágenes satelitales usando Gemini AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Generar un solo objeto:
  python3 gemini_obj_generator.py \\
    --image assets/satellite.png \\
    --bbox '{"x0": -500, "z0": -300, "x1": -450, "z1": -260}' \\
    --metadata '{"type": "building", "area_m2": 180, "stories_hint": 3}' \\
    --output models/building_test.obj

  # Generar desde archivo de configuración:
  python3 gemini_obj_generator.py --config patch_request.json

  # Generar múltiples objetos en batch:
  python3 gemini_obj_generator.py \\
    --image assets/satellite.png \\
    --batch patches_list.json \\
    --output-dir models/generated
        """
    )

    parser.add_argument("--image", "-i", help="Ruta a la ortofoto satelital completa")
    parser.add_argument("--bbox", "-b", help="Bounding box en JSON: {x0, z0, x1, z1} (metros)")
    parser.add_argument("--metadata", "-m", help="Metadatos extra en JSON", default="{}")
    parser.add_argument("--output", "-o", help="Ruta del archivo OBJ de salida", default=None)
    parser.add_argument("--config", "-c", help="Archivo JSON con toda la configuración del request")
    parser.add_argument("--batch", help="Archivo JSON con lista de parches para procesamiento batch")
    parser.add_argument("--output-dir", help="Directorio de salida para batch", default="models/generated")
    parser.add_argument("--api-key", help="API key de Gemini (o usar env GEMINI_API_KEY)", default=None)
    parser.add_argument("--map-bounds", help="Límites del mapa en JSON: {x0, z0, x1, z1}", default=None)

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")

    map_bounds = None
    if args.map_bounds:
        map_bounds = json.loads(args.map_bounds)

    # Modo: archivo de configuración
    if args.config:
        with open(args.config, "r") as f:
            config = json.load(f)
        generate_from_patch(
            config["image"],
            config["bbox"],
            config.get("metadata", {}),
            map_bounds=config.get("map_bounds", map_bounds),
            output_path=config.get("output", args.output),
            api_key=api_key
        )
        return

    # Modo: batch
    if args.batch:
        if not args.image:
            print("[ERROR] --image es requerido para modo batch")
            sys.exit(1)
        batch_generate(args.image, args.batch, map_bounds=map_bounds,
                       output_dir=args.output_dir, api_key=api_key)
        return

    # Modo: individual
    if not args.image or not args.bbox:
        parser.print_help()
        print("\n[ERROR] Se requiere --image y --bbox (o --config)")
        sys.exit(1)

    bbox = json.loads(args.bbox)
    metadata = json.loads(args.metadata)

    generate_from_patch(
        args.image, bbox, metadata,
        map_bounds=map_bounds,
        output_path=args.output,
        api_key=api_key
    )


if __name__ == "__main__":
    main()
