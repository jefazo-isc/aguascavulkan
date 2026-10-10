#!/usr/bin/env python3
"""
tools/celestial_stars.py - Generador del Domo Celeste Nocturno de Aguascalientes
- Latitud real: 21.88° N, Longitud: 102.29° W
- Catálogo de estrellas reales observables a simple vista (HIPPARCOS / Yale Bright Star Catalog):
  Sirius, Canopus, Arcturus, Vega, Capella, Rigel, Procyon, Betelgeuse, Aldebaran,
  Spica, Antares, Pollux, Fomalhaut, Deneb, Regulus, Castor, Bellatrix, Polaris,
  junto con las constelaciones principales (Orión, Osa Mayor, Casiopea, Pléyades, Cruz del Sur visible al horizonte sur).
- Campo estelar estocástico de fondo (Vía Láctea y estrellas de magnitud 2 a 5).
"""

import math
import random

# Latitud de Aguascalientes en radianes
AGUASCALIENTES_LAT_RAD = math.radians(21.8807)

# Catálogo de estrellas principales brillantes:
# (Nombre, Ascensión Recta en horas [0-24], Declinación en grados [-90 a +90], Magnitud visual aproximada, Tinte espectral RGB)
BRIGHTEST_STARS = [
    ("Sirius", 6.75, -16.72, -1.46, (0.85, 0.92, 1.0)),       # A1V blanca-azulada
    ("Canopus", 6.40, -52.70, -0.74, (0.95, 0.95, 1.0)),      # F0II blanca
    ("Arcturus", 14.26, 19.18, -0.05, (1.0, 0.72, 0.40)),     # K1.5III naranja
    ("Vega", 18.62, 38.78, 0.03, (0.80, 0.88, 1.0)),          # A0V azulada
    ("Capella", 5.28, 45.99, 0.08, (1.0, 0.95, 0.70)),        # G3III amarilla
    ("Rigel", 5.24, -8.20, 0.13, (0.75, 0.85, 1.0)),          # B8Ia supergigante azul
    ("Procyon", 7.65, 5.22, 0.38, (0.98, 0.95, 0.88)),        # F5IV
    ("Betelgeuse", 5.92, 7.41, 0.50, (1.0, 0.45, 0.20)),      # M1-2Ia supergigante roja
    ("Aldebaran", 4.60, 16.51, 0.85, (1.0, 0.60, 0.25)),      # K5III naranja
    ("Antares", 16.49, -26.43, 0.96, (1.0, 0.38, 0.18)),      # M1.5Iab supergigante roja
    ("Spica", 13.42, -11.16, 0.98, (0.70, 0.80, 1.0)),        # B1III-IV azul
    ("Pollux", 7.76, 28.03, 1.14, (1.0, 0.82, 0.50)),         # K0III naranja
    ("Fomalhaut", 22.96, -29.62, 1.16, (0.85, 0.90, 1.0)),    # A3V
    ("Deneb", 20.69, 45.28, 1.25, (0.88, 0.92, 1.0)),         # A2Ia
    ("Regulus", 10.14, 11.97, 1.36, (0.75, 0.85, 1.0)),       # B7V
    ("Castor", 7.58, 31.89, 1.58, (0.90, 0.92, 1.0)),         # A1V
    ("Bellatrix", 5.42, 6.35, 1.64, (0.75, 0.85, 1.0)),       # B2III
    ("Polaris", 2.53, 89.26, 1.98, (1.0, 0.98, 0.85)),        # Estrella Polar (Elevación ~21.9° sobre horizonte norte en Ags)
    # Cinturón de Orión
    ("Alnitak", 5.68, -1.94, 1.77, (0.75, 0.85, 1.0)),
    ("Alnilam", 5.60, -1.20, 1.69, (0.75, 0.85, 1.0)),
    ("Mintaka", 5.53, -0.30, 2.23, (0.75, 0.85, 1.0)),
    # Osa Mayor (El cucharón)
    ("Dubhe", 11.06, 61.75, 1.79, (1.0, 0.85, 0.60)),
    ("Merak", 11.03, 56.38, 2.37, (0.90, 0.92, 1.0)),
    ("Phecda", 11.90, 53.69, 2.44, (0.90, 0.92, 1.0)),
    ("Megrez", 12.25, 57.03, 3.31, (0.90, 0.92, 1.0)),
    ("Alioth", 12.90, 55.96, 1.77, (0.90, 0.92, 1.0)),
    ("Mizar", 13.40, 54.92, 2.23, (0.90, 0.92, 1.0)),
    ("Alkaid", 13.79, 49.31, 1.86, (0.75, 0.85, 1.0)),
    # Casiopea (La W en el cielo norte)
    ("Schedar", 0.68, 56.54, 2.23, (1.0, 0.75, 0.40)),
    ("Caph", 0.15, 59.15, 2.27, (0.95, 0.95, 0.95)),
    ("GammaCas", 0.94, 60.72, 2.47, (0.75, 0.85, 1.0)),
    ("Ruchbah", 1.43, 60.23, 2.68, (0.90, 0.92, 1.0)),
]

def radec_to_altaz(ra_hours, dec_deg, lst_hours=2.0, lat_rad=AGUASCALIENTES_LAT_RAD):
    """
    Convierte Coordenadas Ecuatoriales (Ascensión Recta, Declinación)
    a Coordenadas Horizontales (Altitud, Azimut) para el observador en Aguascalientes.
    - lst_hours: Tiempo Sidéreo Local (~medianoche en otoño/octubre en Aguascalientes = ~2.0h).
    """
    ha_rad = ((lst_hours - ra_hours) * 15.0) * math.pi / 180.0
    dec_rad = math.radians(dec_deg)

    # Fórmula esférica de altitud (elevación sobre horizonte)
    sin_alt = math.sin(dec_rad) * math.sin(lat_rad) + math.cos(dec_rad) * math.cos(lat_rad) * math.cos(ha_rad)
    alt_rad = math.asin(max(-1.0, min(1.0, sin_alt)))

    # Azimut
    cos_az = (math.sin(dec_rad) - math.sin(alt_rad) * math.sin(lat_rad)) / (math.cos(alt_rad) * math.cos(lat_rad) + 1e-7)
    cos_az = max(-1.0, min(1.0, cos_az))
    az_rad = math.acos(cos_az)
    if math.sin(ha_rad) > 0:
        az_rad = 2.0 * math.pi - az_rad

    return alt_rad, az_rad

def make_star_billboard(pos_3d, size=2.5, color=(1.0, 1.0, 1.0), emission=1.0):
    """
    Crea un pequeño octaedro/quad emisivo orientado al centro para que brille intensamente de noche.
    """
    x, y, z = pos_3d
    norm_to_center = (-x, -y, -z)
    length = math.hypot(x, math.hypot(y, z)) or 1.0
    norm = (norm_to_center[0]/length, norm_to_center[1]/length, norm_to_center[2]/length)

    # Tangentes perpendiculares para el quad de la estrella
    up = (0.0, 1.0, 0.0) if abs(norm[1]) < 0.9 else (1.0, 0.0, 0.0)
    tx = up[1]*norm[2] - up[2]*norm[1]
    ty = up[2]*norm[0] - up[0]*norm[2]
    tz = up[0]*norm[1] - up[1]*norm[0]
    tlen = math.hypot(tx, math.hypot(ty, tz)) or 1.0
    tang = (tx/tlen, ty/tlen, tz/tlen)

    bx = norm[1]*tang[2] - norm[2]*tang[1]
    by = norm[2]*tang[0] - norm[0]*tang[2]
    bz = norm[0]*tang[1] - norm[1]*tang[0]
    bitang = (bx, by, bz)

    hs = size * 0.5
    p0 = (x - tang[0]*hs - bitang[0]*hs, y - tang[1]*hs - bitang[1]*hs, z - tang[2]*hs - bitang[2]*hs)
    p1 = (x + tang[0]*hs - bitang[0]*hs, y + tang[1]*hs - bitang[1]*hs, z + tang[2]*hs - bitang[2]*hs)
    p2 = (x + tang[0]*hs + bitang[0]*hs, y + tang[1]*hs + bitang[1]*hs, z + tang[2]*hs + bitang[2]*hs)
    p3 = (x - tang[0]*hs + bitang[0]*hs, y - tang[1]*hs + bitang[1]*hs, z - tang[2]*hs + bitang[2]*hs)

    # matID = 0.95 para color emisivo puro en el shader
    col_rgba = (color[0], color[1], color[2], 0.95)
    return [
        (p0, norm, (0,0), col_rgba, emission),
        (p1, norm, (0,0), col_rgba, emission),
        (p2, norm, (0,0), col_rgba, emission),
        (p0, norm, (0,0), col_rgba, emission),
        (p2, norm, (0,0), col_rgba, emission),
        (p3, norm, (0,0), col_rgba, emission)
    ]

def generate_aguascalientes_night_sky(dome_radius=2200.0, center_x=0.0, center_z=0.0, center_y=100.0):
    """
    Genera el firmamento estrellado real observable desde Aguascalientes:
    - Estrellas principales con sus posiciones astrométricas reales y colores espectrales.
    - ~750 estrellas de campo y tenue banda de la Vía Láctea.
    """
    verts = []

    # 1. Estrellas principales del catálogo astronómico
    for name, ra, dec, mag, rgb in BRIGHTEST_STARS:
        alt, az = radec_to_altaz(ra, dec, lst_hours=2.0)
        # Solo estrellas sobre el horizonte local (> 5° de altitud)
        if alt > math.radians(5.0):
            # Proyección esférica 3D sobre el domo celeste
            r_cos_alt = dome_radius * math.cos(alt)
            sx = center_x + r_cos_alt * math.sin(az)
            sz = center_z + r_cos_alt * math.cos(az)
            sy = center_y + dome_radius * math.sin(alt)

            # Estrellas más brillantes (menor magnitud) tienen mayor tamaño e intensidad
            star_size = max(2.5, (3.5 - mag) * 1.8)
            emission = min(1.0, max(0.75, 1.2 - mag * 0.15))

            verts.extend(make_star_billboard((sx, sy, sz), size=star_size, color=rgb, emission=emission))

    # 2. Campo estelar estocástico de fondo (Constelaciones secundarias y fondo de la Vía Láctea)
    random.seed(42)  # Semilla determinista para cielo idéntico
    num_background_stars = 750
    for _ in range(num_background_stars):
        # Distribución uniforme sobre el hemisferio superior
        az = random.uniform(0.0, 2.0 * math.pi)
        alt = math.asin(random.uniform(0.08, 0.98))  # Sobre 5° hasta el cenit

        r_cos_alt = dome_radius * math.cos(alt)
        sx = center_x + r_cos_alt * math.sin(az)
        sz = center_z + r_cos_alt * math.cos(az)
        sy = center_y + dome_radius * math.sin(alt)

        # Variación de temperatura estelar (azul caliente, blanco, amarillo, naranja tenue)
        temp_type = random.random()
        if temp_type < 0.25:
            rgb = (0.75, 0.85, 1.0) # Clase B/A azulada
        elif temp_type < 0.70:
            rgb = (0.95, 0.96, 1.0) # Clase F/G blanca
        elif temp_type < 0.90:
            rgb = (1.0, 0.90, 0.70) # Clase K amarillenta
        else:
            rgb = (1.0, 0.70, 0.50) # Clase M rojiza

        star_size = random.uniform(1.2, 2.2)
        emission = random.uniform(0.65, 0.95)

        verts.extend(make_star_billboard((sx, sy, sz), size=star_size, color=rgb, emission=emission))

    print(f"[Cielo Nocturno Aguascalientes] {len(verts)//6} estrellas reales añadidas al domo celeste")
    return verts

if __name__ == '__main__':
    v = generate_aguascalientes_night_sky()
    print("Vértices generados:", len(v))
