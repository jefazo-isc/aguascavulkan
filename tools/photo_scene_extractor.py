#!/usr/bin/env python3
"""
photo_scene_extractor.py
========================
Analiza una fotografía georeferenciada con Gemini Vision y extrae
elementos urbanos estáticos (vialidades, árboles, vegetación, postes,
macetas, bancas, guarniciones...) como modelos 3D OBJ listos para
cargar en StreetVulkan.

REGLAS ESTRICTAS:
  ✅ Modela: árboles, arbustos, macetas, postes de luz, bancas,
             guarniciones, machuelos, señales de tráfico, pavimento,
             banquetas, bardas, muros, columnas
  ❌ IGNORA: personas, peatones, ciclistas, autos, camiones,
             motos, animales, cualquier ser vivo en movimiento

Flujo:
  1. Toma la foto + su JSON de metadatos (lat/lon/heading/pitch/FOV)
  2. Pide a Gemini que identifique y localice los elementos estáticos
  3. Por cada elemento, genera un OBJ procedural calibrado en escala real
  4. Los coloca en el espacio mundo usando la geometría perspectiva de la foto
  5. Guarda en models/generated/ para carga automática del motor

Uso:
  python3 tools/photo_scene_extractor.py \\
      --photo assets/streetview/gsv_xxx.jpg \\
      --meta  assets/streetview/gsv_xxx.json \\
      --dist 30.0

  O con metadatos inline:
  python3 tools/photo_scene_extractor.py \\
      --photo mi_foto.jpg \\
      --lat 21.8807 --lon -102.2965 --heading 90.0 --pitch 0.0 --fov 73.0
"""

import argparse
import base64
import json
import math
import os
import sys
import time
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
except ImportError:
    print("[ERROR] Necesitas: pip3 install --break-system-packages Pillow numpy")
    sys.exit(1)

try:
    from google import genai
    from pydantic import BaseModel, Field
    from typing import List, Optional
except ImportError:
    print("[ERROR] Necesitas: pip3 install --break-system-packages google-genai pydantic")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# ── Coordenadas del motor ────────────────────────────────────────────────────
ORIGIN_LAT = 21.8807
ORIGIN_LON = -102.2965
M_PER_LAT  = 111320.0


def get_m_per_lon(lat=ORIGIN_LAT):
    return M_PER_LAT * math.cos(math.radians(lat))


def geo_to_world(lat, lon, alt=0.0):
    m_per_lon = get_m_per_lon(ORIGIN_LAT)
    x = (lon - ORIGIN_LON) * m_per_lon
    z = -(lat - ORIGIN_LAT) * M_PER_LAT
    y = alt - 1871.0 if alt > 100.0 else alt
    return x, y, z


def heading_pitch_to_dir(heading_deg, pitch_deg):
    """Azimut → vector dirección en espacio del motor (X=Este, Y=Arriba, Z=Sur)."""
    h = math.radians(heading_deg)
    p = math.radians(pitch_deg)
    dx =  math.sin(h) * math.cos(p)
    dy =  math.sin(p)
    dz = -math.cos(h) * math.cos(p)
    return dx, dy, dz


# ── Esquema de respuesta estructurada de Gemini ──────────────────────────────

class PixelBBox(BaseModel):
    """Bounding box normalizado (0–1) del elemento en la imagen."""
    x_min: float = Field(description="Borde izquierdo normalizado (0.0–1.0)")
    y_min: float = Field(description="Borde superior normalizado (0.0–1.0)")
    x_max: float = Field(description="Borde derecho normalizado (0.0–1.0)")
    y_max: float = Field(description="Borde inferior normalizado (0.0–1.0)")

class SceneElement(BaseModel):
    """Un elemento urbano estático identificado en la foto."""
    element_type: str = Field(
        description="Tipo del elemento. Valores permitidos: "
                    "'tree' (árbol alto), 'shrub' (arbusto bajo), 'palm' (palmera), "
                    "'planter' (maceta/jardinera), 'bench' (banca), "
                    "'streetlight' (farol/poste de luz), 'trafficlight' (semáforo), "
                    "'trafficsign' (señal de tránsito), 'pole' (poste genérico), "
                    "'wall' (barda/muro), 'column' (columna/pilar), "
                    "'curb' (guarnición/machuelo), 'pavement' (pavimento/asfalto), "
                    "'sidewalk' (banqueta/acera), 'fence' (reja/cerca), "
                    "'staircase' (escaleras), 'fountain' (fuente), 'other_static' (otro elemento estático)"
    )
    confidence: float = Field(description="Confianza 0.0–1.0")
    bbox: PixelBBox = Field(description="Bounding box del elemento en la imagen (coordenadas normalizadas)")
    estimated_height_m: float = Field(description="Altura estimada del objeto en metros (ej: árbol=5.0, banca=0.9, poste=8.0)")
    estimated_width_m:  float = Field(description="Ancho estimado del objeto en metros")
    color_r: float = Field(description="Color dominante R (0.0–1.0)")
    color_g: float = Field(description="Color dominante G (0.0–1.0)")
    color_b: float = Field(description="Color dominante B (0.0–1.0)")
    secondary_color_r: float = Field(default=0.3, description="Color secundario R (tronco, marco, base)")
    secondary_color_g: float = Field(default=0.2, description="Color secundario G")
    secondary_color_b: float = Field(default=0.1, description="Color secundario B")
    distance_hint_m:   float = Field(default=15.0, description="Distancia estimada al objeto en metros (basándose en perspectiva y tamaño aparente)")

class SceneAnalysis(BaseModel):
    """Análisis completo de la escena urbana."""
    scene_description: str = Field(description="Descripción breve de la escena")
    time_of_day: str = Field(description="Hora aproximada: 'day', 'dusk', 'night'")
    weather: str = Field(description="Condición: 'clear', 'cloudy', 'rainy'")
    elements: List[SceneElement] = Field(
        description="Lista de elementos ESTÁTICOS identificados. "
                    "NUNCA incluyas: personas, peatones, ciclistas, conductores, "
                    "automóviles, camionetas, autobuses, motocicletas, bicicletas, "
                    "ni ningún ser vivo o vehículo en movimiento. "
                    "SOLO elementos fijos del entorno urbano."
    )


# ── Generadores procedurales OBJ por tipo ───────────────────────────────────

def _v(lines, x, y, z, u=0.0, v_=0.0):
    lines.append(f"v {x:.4f} {y:.4f} {z:.4f} {u:.4f} {v_:.4f}")

def _f(lines, *idxs):
    lines.append("f " + " ".join(str(i) for i in idxs))

def make_cylinder(cx, cy, cz, radius, height, segments, color_r, color_g, color_b,
                  base_idx=1, uv_u_range=(0.0, 1.0)):
    """Genera un cilindro vertical como geometría OBJ."""
    lines = []
    verts = []
    # Anillo inferior
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = cx + radius * math.cos(angle)
        z_ = cz + radius * math.sin(angle)
        u = uv_u_range[0] + (uv_u_range[1] - uv_u_range[0]) * i / segments
        _v(lines, x, cy, z_, u, 0.0)
        verts.append((x, cy, z_))
    # Anillo superior
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = cx + radius * math.cos(angle)
        z_ = cz + radius * math.sin(angle)
        u = uv_u_range[0] + (uv_u_range[1] - uv_u_range[0]) * i / segments
        _v(lines, x, cy + height, z_, u, 1.0)
        verts.append((x, cy + height, z_))
    # Caras laterales
    for i in range(segments):
        ni = (i + 1) % segments
        b0 = base_idx + i
        b1 = base_idx + ni
        t0 = base_idx + segments + i
        t1 = base_idx + segments + ni
        lines.append(f"f {b0} {b1} {t1}")
        lines.append(f"f {b0} {t1} {t0}")
    return lines, 2 * segments


def make_tree_obj(world_x, world_y, world_z, height_m, color_r, color_g, color_b,
                  sec_r, sec_g, sec_b, base_idx=1):
    """Árbol: tronco cilíndrico + copa esférica aproximada."""
    lines = []
    trunk_r = max(0.08, height_m * 0.04)
    trunk_h = height_m * 0.42
    crown_r = height_m * 0.35
    crown_cx = world_x
    crown_cy = world_y + trunk_h
    crown_cz = world_z
    seg = 10

    # Tronco
    lines.append(f"usemtl trunk")
    trunk_lines, trunk_verts = make_cylinder(world_x, world_y, world_z,
                                              trunk_r, trunk_h, seg, sec_r, sec_g, sec_b,
                                              base_idx=base_idx, uv_u_range=(0.0, 0.48))
    lines.extend(trunk_lines)
    vidx = base_idx + trunk_verts

    # Copa: icosfera aproximada con 3 bandas
    lines.append(f"usemtl crown")
    crown_verts_list = []
    bands = 4
    for band in range(bands + 1):
        phi = math.pi * band / bands
        ring_r = crown_r * math.sin(phi)
        ring_y = crown_cy + crown_r * math.cos(phi)
        ring_segs = max(4, int(seg * math.sin(phi) + 2))
        for i in range(ring_segs):
            theta = 2 * math.pi * i / ring_segs
            # irregularidad orgánica
            ir = 1.0 + 0.12 * math.sin(theta * 3 + phi * 5)
            vx = crown_cx + ring_r * ir * math.cos(theta)
            vz = crown_cz + ring_r * ir * math.sin(theta)
            u_ = (i / ring_segs) * 0.46 + 0.52
            v__ = band / bands
            _v(lines, vx, ring_y, vz, u_, v__)
            crown_verts_list.append((vx, ring_y, vz, ring_segs))

    # Cara superior (polo norte)
    lines.append(f"v {crown_cx:.4f} {crown_cy + crown_r:.4f} {crown_cz:.4f} 0.75 1.0")
    top_idx = vidx + len(crown_verts_list) + 1

    # Caras de la copa (aproximación por banda)
    # Indexado lineal simplificado: para cada banda construimos quads entre bandas consecutivas
    band_starts = []
    cur = vidx
    for band in range(bands + 1):
        phi = math.pi * band / bands
        rs = max(4, int(seg * math.sin(phi) + 2))
        band_starts.append((cur, rs))
        cur += rs

    for bi in range(bands):
        s0, n0 = band_starts[bi]
        s1, n1 = band_starts[bi + 1]
        for i in range(min(n0, n1)):
            a0 = s0 + i
            a1 = s0 + (i + 1) % n0
            b0 = s1 + i % n1
            b1 = s1 + (i + 1) % n1
            lines.append(f"f {a0} {a1} {b1}")
            lines.append(f"f {a0} {b1} {b0}")

    total_verts = trunk_verts + len(crown_verts_list) + 1
    return lines, total_verts


def make_shrub_obj(world_x, world_y, world_z, height_m, width_m,
                   color_r, color_g, color_b, base_idx=1):
    """Arbusto: esfera achatada con irregularidades."""
    lines = []
    lines.append("usemtl shrub")
    rh = height_m / 2.0
    rw = width_m / 2.0
    segs_u, segs_v = 8, 5
    vcount = 0
    grid = []
    for vi in range(segs_v + 1):
        phi = math.pi * vi / segs_v
        row = []
        for ui in range(segs_u):
            theta = 2 * math.pi * ui / segs_u
            ir = 1.0 + 0.15 * math.sin(theta * 4 + phi * 3)
            vx = world_x + rw * ir * math.sin(phi) * math.cos(theta)
            vy = world_y + rh * (1.0 - math.cos(phi))
            vz = world_z + rw * ir * math.sin(phi) * math.sin(theta)
            u_ = ui / segs_u
            v__ = vi / segs_v
            _v(lines, vx, vy, vz, u_, v__)
            row.append(base_idx + vcount)
            vcount += 1
        grid.append(row)
    for vi in range(segs_v):
        for ui in range(segs_u):
            a = grid[vi][ui]
            b = grid[vi][(ui + 1) % segs_u]
            c = grid[vi + 1][(ui + 1) % segs_u]
            d = grid[vi + 1][ui]
            lines.append(f"f {a} {b} {c}")
            lines.append(f"f {a} {c} {d}")
    return lines, vcount


def make_pole_obj(world_x, world_y, world_z, height_m, radius_m, color_r, color_g, color_b, base_idx=1):
    """Poste/farol: cilindro delgado."""
    lines = []
    lines.append("usemtl pole")
    seg = 8
    cyl_lines, cyl_verts = make_cylinder(world_x, world_y, world_z,
                                          radius_m, height_m, seg, color_r, color_g, color_b,
                                          base_idx=base_idx)
    lines.extend(cyl_lines)
    return lines, cyl_verts


def make_bench_obj(world_x, world_y, world_z, heading_deg,
                   width_m, color_r, color_g, color_b, base_idx=1):
    """Banca: caja plana + dos soportes."""
    lines = []
    lines.append("usemtl bench")
    h = math.radians(heading_deg)
    rx = math.cos(h); rz = -math.sin(h)  # eje derecho
    seat_h = 0.45; seat_t = 0.07; seat_d = 0.42
    w2 = width_m / 2.0
    d2 = seat_d / 2.0
    # 8 vértices del asiento
    corners = [(-w2, 0, -d2), (w2, 0, -d2), (w2, 0, d2), (-w2, 0, d2),
               (-w2, seat_t, -d2), (w2, seat_t, -d2), (w2, seat_t, d2), (-w2, seat_t, d2)]
    for (lx, ly, lz) in corners:
        gx = world_x + lx * rx + lz * rz
        gy = world_y + seat_h + ly
        gz = world_z + lx * (-rz) + lz * rx
        _v(lines, gx, gy, gz, (lx + w2) / width_m, (lz + d2) / seat_d)
    # 6 caras de la caja
    b = base_idx
    for face in [(b,b+1,b+5,b+4),(b+1,b+2,b+6,b+5),(b+2,b+3,b+7,b+6),
                 (b+3,b,b+4,b+7),(b+4,b+5,b+6,b+7),(b,b+3,b+2,b+1)]:
        lines.append(f"f {face[0]} {face[1]} {face[2]}")
        lines.append(f"f {face[0]} {face[2]} {face[3]}")
    return lines, 8


def make_curb_obj(world_x, world_y, world_z, heading_deg,
                  length_m, color_r, color_g, color_b, base_idx=1):
    """Guarnición/machuelo: prisma bajo."""
    lines = []
    lines.append("usemtl curb")
    h = math.radians(heading_deg)
    rx = math.cos(h); rz = -math.sin(h)
    w = 0.15; ht = 0.15; l2 = length_m / 2.0
    corners = [(-l2, 0, 0), (l2, 0, 0), (l2, 0, w), (-l2, 0, w),
               (-l2, ht, 0), (l2, ht, 0), (l2, ht, w), (-l2, ht, w)]
    for (lx, ly, lz) in corners:
        gx = world_x + lx * rx + lz * rz
        gy = world_y + ly
        gz = world_z + lx * (-rz) + lz * rx
        _v(lines, gx, gy, gz, (lx + l2) / length_m, lz / w)
    b = base_idx
    for face in [(b,b+1,b+5,b+4),(b+1,b+2,b+6,b+5),(b+2,b+3,b+7,b+6),
                 (b+3,b,b+4,b+7),(b+4,b+5,b+6,b+7),(b,b+3,b+2,b+1)]:
        lines.append(f"f {face[0]} {face[1]} {face[2]}")
        lines.append(f"f {face[0]} {face[2]} {face[3]}")
    return lines, 8


def make_wall_obj(world_x, world_y, world_z, heading_deg,
                  length_m, height_m, color_r, color_g, color_b, base_idx=1):
    """Barda/muro: quad vertical."""
    lines = []
    lines.append("usemtl wall")
    h = math.radians(heading_deg)
    rx = math.cos(h); rz = -math.sin(h)
    l2 = length_m / 2.0
    pts = [(-l2, 0), (l2, 0), (l2, height_m), (-l2, height_m)]
    for (lx, ly) in pts:
        gx = world_x + lx * rx
        gz = world_z + lx * (-rz)
        _v(lines, gx, world_y + ly, gz, (lx + l2) / length_m, ly / height_m)
    b = base_idx
    lines.append(f"f {b} {b+1} {b+2}")
    lines.append(f"f {b} {b+2} {b+3}")
    lines.append(f"f {b} {b+2} {b+1}")
    lines.append(f"f {b} {b+3} {b+2}")
    return lines, 4


def write_mtl_for_element(el: SceneElement):
    """Genera el contenido MTL para un elemento."""
    r, g, b = el.color_r, el.color_g, el.color_b
    sr, sg, sb = el.secondary_color_r, el.secondary_color_g, el.secondary_color_b
    etype = el.element_type
    if etype in ("tree", "palm"):
        return (
            f"newmtl trunk\nKd {sr:.4f} {sg:.4f} {sb:.4f}\nKa 0.1 0.08 0.05\nKs 0 0 0\nd 1.0\n\n"
            f"newmtl crown\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0.05 0.12 0.04\nKs 0 0 0\nd 1.0\n"
        )
    elif etype == "shrub":
        return f"newmtl shrub\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0.04 0.10 0.03\nKs 0 0 0\nd 1.0\n"
    elif etype in ("streetlight", "trafficlight", "pole"):
        return f"newmtl pole\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0.1 0.1 0.1\nKs 0.4 0.4 0.4\nNs 30\nd 1.0\n"
    elif etype == "bench":
        return f"newmtl bench\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0.08 0.08 0.08\nKs 0.1 0.1 0.1\nd 1.0\n"
    elif etype == "curb":
        return f"newmtl curb\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0.1 0.1 0.1\nKs 0 0 0\nd 1.0\n"
    else:
        return f"newmtl wall\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0.06 0.06 0.06\nKs 0 0 0\nd 1.0\n"


# ── Cálculo de posición mundial desde perspectiva ────────────────────────────

def pixel_to_world(
    bbox: PixelBBox, distance_m: float,
    cam_x, cam_y, cam_z,
    heading_deg, pitch_deg, fov_h_deg,
    img_w, img_h,
    element_height_m: float
):
    """
    Convierte el bounding box en imagen a coordenadas mundiales.
    Usa el centro inferior del bbox (base del objeto) para anclar al suelo.
    """
    fwd_x, fwd_y, fwd_z = heading_pitch_to_dir(heading_deg, pitch_deg)

    # Vector Right
    world_up = (0.0, 1.0, 0.0)
    rx = fwd_y * world_up[2] - fwd_z * world_up[1]
    ry = fwd_z * world_up[0] - fwd_x * world_up[2]
    rz = fwd_x * world_up[1] - fwd_y * world_up[0]
    rlen = math.sqrt(rx*rx + ry*ry + rz*rz)
    if rlen < 1e-6: rx, ry, rz = 1.0, 0.0, 0.0
    else: rx, ry, rz = rx/rlen, ry/rlen, rz/rlen

    # Vector Up real
    ux = ry * fwd_z - rz * fwd_y
    uy = rz * fwd_x - rx * fwd_z
    uz = rx * fwd_y - ry * fwd_x

    # Centro inferior del bbox en NDC (-1..1)
    cx_ndc = (bbox.x_min + bbox.x_max) / 2.0 * 2.0 - 1.0
    cy_ndc = -(bbox.y_max * 2.0 - 1.0)  # Invertir Y: imagen top-left, NDC bottom-left

    aspect = img_w / img_h
    fov_h_rad = math.radians(fov_h_deg)
    tan_half_h = math.tan(fov_h_rad / 2.0)
    tan_half_v = tan_half_h / aspect

    # Dirección al centro del objeto
    dir_x = fwd_x + cx_ndc * tan_half_h * rx + cy_ndc * tan_half_v * ux
    dir_y = fwd_y + cx_ndc * tan_half_h * ry + cy_ndc * tan_half_v * uy
    dir_z = fwd_z + cx_ndc * tan_half_h * rz + cy_ndc * tan_half_v * uz
    dlen = math.sqrt(dir_x**2 + dir_y**2 + dir_z**2)
    if dlen > 1e-6: dir_x, dir_y, dir_z = dir_x/dlen, dir_y/dlen, dir_z/dlen

    # Posición del objeto a la distancia estimada (proyectada al plano Y=0)
    obj_x = cam_x + dir_x * distance_m
    obj_z = cam_z + dir_z * distance_m
    obj_y = cam_y  # Anclar al nivel del suelo de la cámara

    return obj_x, obj_y, obj_z


# ── Pipeline principal ───────────────────────────────────────────────────────

def analyze_photo_with_gemini(photo_path: str, api_key: str = None) -> SceneAnalysis:
    """Envía la foto a Gemini y obtiene la lista de elementos estáticos."""
    _api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not _api_key:
        raise RuntimeError("Se requiere GEMINI_API_KEY en el entorno o --api-key")

    img = Image.open(photo_path)
    img_w, img_h = img.size

    # Redimensionar para no gastar tokens innecesarios
    max_side = 1024
    if max(img_w, img_h) > max_side:
        scale = max_side / max(img_w, img_h)
        img = img.resize((int(img_w * scale), int(img_h * scale)), Image.Resampling.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()

    client = genai.Client(api_key=_api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    system = """Eres un experto en visión artificial, fotogrametría y modelado de entornos urbanos.
Tu tarea es analizar fotografías de calles y detectar ÚNICAMENTE elementos urbanos ESTÁTICOS:
árboles, arbustos, macetas, postes, bancas, semáforos, señales, bardas, guarniciones, pavimento.

REGLAS ABSOLUTAS — NUNCA incluyas:
  ❌ Personas (peatones, ciclistas, conductores)
  ❌ Vehículos (autos, camiones, motocicletas, bicicletas)
  ❌ Cualquier ser vivo en movimiento
  ❌ Elementos que no sean parte fija del entorno urbano

Para cada elemento ESTÁTICO identificado proporciona:
  - Tipo exacto según el enum definido
  - Bounding box normalizado (0–1) en la imagen
  - Altura y ancho estimados en metros (basarte en contexto urbano real)
  - Color dominante en RGB (0–1) observado en la foto
  - Distancia estimada a la cámara en metros (perspectiva)

Sé preciso en las estimaciones de distancia: un árbol que ocupa 1/4 de la imagen
vertical probablemente está a 8–15m. Un poste de luz que se ve pequeño puede estar a 20–40m."""

    user = """Analiza esta fotografía de calle urbana.
Identifica y lista TODOS los elementos estáticos visibles (árboles, vegetación, postes, bancas, etc).
EXCLUYE absolutamente cualquier persona, vehículo o ser vivo.
Para cada elemento proporciona su bounding box normalizado y estimaciones de tamaño y distancia.
Responde ÚNICAMENTE con el JSON estructurado."""

    print(f"[Gemini] Analizando foto con {model}...")
    t0 = time.time()
    interaction = client.interactions.create(
        model=model,
        system_instruction=system,
        input=[
            {"type": "image", "data": b64, "mime_type": "image/jpeg"},
            {"type": "text",  "text": user}
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": SceneAnalysis.model_json_schema()
        }
    )
    print(f"[Gemini] Respuesta en {time.time() - t0:.1f}s")

    return SceneAnalysis.model_validate_json(interaction.output_text)


def extract_scene(
    photo_path: str,
    lat: float, lon: float, alt: float = 1871.0,
    heading: float = 0.0, pitch: float = 0.0, fov_h: float = 73.0,
    max_depth: float = 50.0,
    output_dir: str = "models/generated",
    api_key: str = None,
    min_confidence: float = 0.40,
):
    """
    Pipeline completo: analiza la foto, genera OBJ por elemento, los guarda.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Dimensiones de la imagen original
    orig_img = Image.open(photo_path)
    img_w, img_h = orig_img.size

    # Posición de la cámara en espacio mundo
    cam_x, cam_y, cam_z = geo_to_world(lat, lon, alt)
    print(f"[Scene] Cámara mundo: ({cam_x:.2f}, {cam_y:.2f}, {cam_z:.2f})")
    print(f"[Scene] heading={heading}° pitch={pitch}° fov={fov_h}°")

    # 1. Análisis de la escena
    analysis = analyze_photo_with_gemini(photo_path, api_key=api_key)
    print(f"\n[Scene] '{analysis.scene_description}'")
    print(f"[Scene] Hora: {analysis.time_of_day} | Clima: {analysis.weather}")
    print(f"[Scene] Elementos detectados: {len(analysis.elements)}")

    # Guardar análisis JSON de referencia
    analysis_path = os.path.join(output_dir, "scene_analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis.model_dump(), f, indent=2, ensure_ascii=False)
    print(f"[Scene] Análisis guardado: {analysis_path}")

    # 2. Generar OBJ por elemento
    generated_count = 0
    skipped = []
    for i, el in enumerate(analysis.elements):
        if el.confidence < min_confidence:
            skipped.append(f"{el.element_type} (conf={el.confidence:.0%})")
            continue

        print(f"\n[{i+1}/{len(analysis.elements)}] {el.element_type.upper()} "
              f"| h={el.estimated_height_m:.1f}m w={el.estimated_width_m:.1f}m "
              f"| dist≈{el.distance_hint_m:.0f}m | conf={el.confidence:.0%}")

        # Clamp distancia
        dist = min(el.distance_hint_m, max_depth)

        # Calcular posición en espacio mundo
        obj_x, obj_y, obj_z = pixel_to_world(
            el.bbox, dist,
            cam_x, cam_y, cam_z,
            heading, pitch, fov_h,
            img_w, img_h,
            el.estimated_height_m
        )
        print(f"  → Mundo: ({obj_x:.2f}, {obj_y:.2f}, {obj_z:.2f})")

        # Nombre de archivo
        base_name = f"scene_elem_{i:03d}_{el.element_type}"
        obj_path = os.path.join(output_dir, base_name + ".obj")
        mtl_path = os.path.join(output_dir, base_name + ".mtl")

        lines = [
            f"# Elemento urbano: {el.element_type}",
            f"# Confianza: {el.confidence:.0%}",
            f"# Altura estimada: {el.estimated_height_m:.2f}m",
            f"# Posición mundo: ({obj_x:.2f}, {obj_y:.2f}, {obj_z:.2f})",
            f"mtllib {base_name}.mtl",
            "",
        ]

        geo_lines = []
        total_verts = 0

        if el.element_type in ("tree", "palm"):
            geo_lines, total_verts = make_tree_obj(
                obj_x, obj_y, obj_z,
                el.estimated_height_m,
                el.color_r, el.color_g, el.color_b,
                el.secondary_color_r, el.secondary_color_g, el.secondary_color_b,
                base_idx=1
            )
        elif el.element_type == "shrub":
            geo_lines, total_verts = make_shrub_obj(
                obj_x, obj_y, obj_z,
                el.estimated_height_m, el.estimated_width_m,
                el.color_r, el.color_g, el.color_b,
                base_idx=1
            )
        elif el.element_type in ("streetlight", "trafficlight", "pole"):
            geo_lines, total_verts = make_pole_obj(
                obj_x, obj_y, obj_z,
                el.estimated_height_m,
                max(0.05, el.estimated_width_m * 0.08),
                el.color_r, el.color_g, el.color_b,
                base_idx=1
            )
        elif el.element_type == "bench":
            geo_lines, total_verts = make_bench_obj(
                obj_x, obj_y, obj_z, heading,
                el.estimated_width_m,
                el.color_r, el.color_g, el.color_b,
                base_idx=1
            )
        elif el.element_type == "curb":
            geo_lines, total_verts = make_curb_obj(
                obj_x, obj_y, obj_z, heading,
                el.estimated_width_m,
                el.color_r, el.color_g, el.color_b,
                base_idx=1
            )
        elif el.element_type in ("wall", "fence"):
            geo_lines, total_verts = make_wall_obj(
                obj_x, obj_y, obj_z, heading,
                el.estimated_width_m, el.estimated_height_m,
                el.color_r, el.color_g, el.color_b,
                base_idx=1
            )
        else:
            # Fallback: cubo genérico
            geo_lines, total_verts = make_shrub_obj(
                obj_x, obj_y, obj_z,
                el.estimated_height_m, el.estimated_width_m,
                el.color_r, el.color_g, el.color_b,
                base_idx=1
            )

        lines.extend(geo_lines)

        with open(obj_path, "w") as f:
            f.write("\n".join(lines))
        with open(mtl_path, "w") as f:
            f.write(f"# Material para {el.element_type}\n")
            f.write(write_mtl_for_element(el))

        print(f"  ✅ {obj_path} ({total_verts} vértices)")
        generated_count += 1

    print(f"\n[Scene] ✅ Completado: {generated_count} objetos generados en '{output_dir}'")
    if skipped:
        print(f"[Scene] ⏩ Omitidos (baja confianza): {', '.join(skipped)}")
    print("[Scene] Reinicia el motor (./street_vulkan) para ver los objetos en la ciudad.")
    return generated_count


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extrae elementos urbanos estáticos de una foto con Gemini y genera OBJ 3D."
    )
    parser.add_argument("--photo",      required=False, help="Ruta a la imagen (JPG/PNG).")
    parser.add_argument("--meta",       required=False, help="JSON de metadatos (lat/lon/heading/pitch).")
    parser.add_argument("--lat",        type=float, default=None)
    parser.add_argument("--lon",        type=float, default=None)
    parser.add_argument("--alt",        type=float, default=1871.0)
    parser.add_argument("--heading",    type=float, default=0.0)
    parser.add_argument("--pitch",      type=float, default=0.0)
    parser.add_argument("--fov",        type=float, default=73.0)
    parser.add_argument("--dist",       type=float, default=50.0, help="Profundidad máxima de escena (metros)")
    parser.add_argument("--confidence", type=float, default=0.40, help="Confianza mínima para incluir un elemento")
    parser.add_argument("--outdir",     type=str,   default="models/generated")
    parser.add_argument("--api-key",    type=str,   default=None)
    args = parser.parse_args()

    photo_path = args.photo
    lat, lon, alt = args.lat, args.lon, args.alt
    heading, pitch, fov = args.heading, args.pitch, args.fov

    if args.meta:
        with open(args.meta) as f:
            meta = json.load(f)
        lat     = meta.get("lat",     lat)
        lon     = meta.get("lon",     lon)
        heading = meta.get("heading", heading)
        pitch   = meta.get("pitch",   pitch)
        alt     = meta.get("alt",     alt)
        fov     = meta.get("fov_h",   fov)
        if not photo_path:
            photo_path = meta.get("file_path") or meta.get("photo")

    if not photo_path:
        parser.error("Se requiere --photo con la ruta a la imagen.")
    if lat is None or lon is None:
        parser.error("Se requieren --lat y --lon (o usa --meta).")

    extract_scene(
        photo_path=photo_path,
        lat=lat, lon=lon, alt=alt,
        heading=heading, pitch=pitch, fov_h=fov,
        max_depth=args.dist,
        output_dir=args.outdir,
        api_key=args.api_key,
        min_confidence=args.confidence,
    )


if __name__ == "__main__":
    main()
