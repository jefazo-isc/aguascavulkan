#!/usr/bin/env python3
"""
generate_texture_atlas.py
=========================
Genera un Atlas de Texturas de Alta Definición (512x512 px formado por casillas de 64x64 px)
para StreetVulkan.

Proporciona texturas ricas y detalladas para elementos urbanos reales de Aguascalientes:
Fila 0:
  (0, 0): residencial (estuco cálido, ventana con marco de madera y repisa)
  (1, 0): comercial (fachada tipo OXXO / tienda de abarrotes con marquesina roja y vitrina)
  (2, 0): escuela (muro institucional de tabique y ventanales)
  (3, 0): templo (cantera labrada colonial beige)
  (4, 0): hospital (azulejo clínico y cruz médica de emergencias)
  (5, 0): oficina (muro cortina de cristal azul y perfiles de aluminio)
  (6, 0): industrial (lámina acanalada y concreto gris)
  (7, 0): asfalto (asfalto vehicular micro-texturado con grava)

Fila 1:
  (0, 1): banqueta (concreto peinado con juntas de dilatación)
  (1, 1): curb_red (guarnición roja preventiva reglamentaria)
  (2, 1): curb_yellow (guarnición amarilla de carga)
  (3, 1): pasto (césped verde con textura de briznas)
  (4, 1): cortina_metal (cortina metálica arrollable comercial mexicana)
  (5, 1): ladrillo (tabique rojo recocido mexicano con juntas de mortero)
  (6, 1): madera_arbol (corteza de madera natural con vetas longitudinales)
  (7, 1): proteccion_ventana (rejas de herrería artesanal mexicana para ventanas)

Fila 2:
  (0, 2): malla_ciclonica (malla de alambre galvanizado con patrón romboidal)
  (1, 2): barandal (barandales de herrería y pasamanos tubulares)
  (2, 2): stop_sign (señal octogonal reglamentaria de ALTO NOM SCT)
  (3, 2): hidrante (hidrante urbano rojo con boquillas de bronce amarillo)
  (4, 2): cauce_arroyo (lecho de arroyo con cantos rodados y arena fluvial)
  (5, 2): falla_geologica (escarpe y fractura geológica de suelo/asfalto)
  (6, 2): fachada_cochera (portón de cochera moderno y fachada residencial)
  (7, 2): cantera_rosa (cantera rosa tradicional de Aguascalientes)
"""
import os
import math
import random
from PIL import Image, ImageDraw, ImageFont

TILE_SIZE = 64
GRID_COLS = 8
GRID_ROWS = 8
ATLAS_W = TILE_SIZE * GRID_COLS  # 512 px
ATLAS_H = TILE_SIZE * GRID_ROWS  # 512 px

def create_tile(style_type, s=64):
    img = Image.new("RGBA", (s, s), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    random.seed(hash(style_type) & 0xFFFFFFFF)

    # ----------------------------------------------------
    # FILA 0: Fachadas Base y Superficies
    # ----------------------------------------------------
    if style_type == "residencial":
        # Estuco cálido mexicano con ventana de madera, marco y herrería sutil
        base = (225, 215, 195)
        for y in range(s):
            for x in range(s):
                var = random.randint(-6, 6)
                img.putpixel((x, y), (base[0]+var, base[1]+var, base[2]+var, 255))
        # Zoclo inferior
        draw.rectangle([0, s-8, s-1, s-1], fill=(160, 145, 130, 255))
        # Ventana central con moldura
        wx0, wy0, wx1, wy1 = 18, 14, 46, 44
        draw.rectangle([wx0-3, wy0-3, wx1+3, wy1+3], fill=(245, 240, 230, 255)) # Marco exterior
        draw.rectangle([wx0, wy0, wx1, wy1], fill=(45, 75, 105, 255))           # Cristal
        # Parteluces / división de ventana
        draw.line([(wx0+wx1)//2, wy0, (wx0+wx1)//2, wy1], fill=(230, 225, 215, 255), width=2)
        draw.line([wx0, (wy0+wy1)//2, wx1, (wy0+wy1)//2], fill=(230, 225, 215, 255), width=2)
        # Repisa de piedra bajo la ventana
        draw.rectangle([wx0-5, wy1+1, wx1+5, wy1+4], fill=(180, 168, 150, 255))

    elif style_type == "comercial":
        # Fachada comercial mexicana / OXXO
        for y in range(s):
            for x in range(s):
                if y < 16:
                    # Marquesina roja corporativa con relieve
                    shade = int(25 * (y / 16.0))
                    img.putpixel((x, y), (210 - shade, 28, 25, 255))
                elif y < 22:
                    # Franja blanca / amarilla
                    img.putpixel((x, y), (245, 235, 70, 255) if y < 19 else (245, 245, 245, 255))
                else:
                    var = random.randint(-4, 4)
                    img.putpixel((x, y), (230+var, 228+var, 222+var, 255))
        # Vitrina comercial de cristal templado
        draw.rectangle([8, 26, s-9, s-5], fill=(35, 65, 95, 255), outline=(210, 210, 210, 255), width=2)
        # Marco de puerta
        draw.line([s//2, 26, s//2, s-5], fill=(210, 210, 210, 255), width=2)
        # Manija cromada
        draw.rectangle([s//2-3, 40, s//2-1, 46], fill=(230, 230, 235, 255))

    elif style_type == "escuela":
        # Muro institucional de tabique y ventanales
        for y in range(s):
            for x in range(s):
                mortar = (y % 8 == 0) or (x % 16 == 0 and (y // 8) % 2 == 0) or ((x + 8) % 16 == 0 and (y // 8) % 2 == 1)
                if mortar:
                    img.putpixel((x, y), (195, 190, 180, 255))
                else:
                    var = random.randint(-12, 12)
                    img.putpixel((x, y), (170+var, 65+var, 45+var, 255))
        # Ventanas dobles
        draw.rectangle([8, 12, 26, 30], fill=(60, 95, 135, 255), outline=(235, 235, 235, 255), width=2)
        draw.rectangle([38, 12, 56, 30], fill=(60, 95, 135, 255), outline=(235, 235, 235, 255), width=2)

    elif style_type == "templo":
        # Cantera beige labrada / sillares coloniales
        base = (205, 190, 160)
        for y in range(s):
            for x in range(s):
                joint = (y % 16 == 0) or (x % 32 == 0 and (y // 16) % 2 == 0) or ((x + 16) % 32 == 0 and (y // 16) % 2 == 1)
                var = random.randint(-8, 8)
                if joint:
                    img.putpixel((x, y), (135, 122, 100, 255))
                else:
                    # Textura porosa de cantera
                    porous = 12 if random.random() < 0.08 else 0
                    img.putpixel((x, y), (base[0]+var-porous, base[1]+var-porous, base[2]+var-porous, 255))
        # Arco colonial decorativo
        draw.arc([16, 12, 48, 54], start=180, end=0, fill=(140, 125, 105, 255), width=3)

    elif style_type == "hospital":
        # Muro clínico y cruz roja
        for y in range(s):
            for x in range(s):
                tile_joint = (y % 8 == 0) or (x % 8 == 0)
                if tile_joint:
                    img.putpixel((x, y), (205, 220, 215, 255))
                else:
                    var = random.randint(-3, 3)
                    img.putpixel((x, y), (242+var, 250+var, 246+var, 255))
        # Cruz médica de emergencias
        draw.rectangle([28, 18, 36, 46], fill=(220, 30, 30, 255))
        draw.rectangle([18, 28, 46, 36], fill=(220, 30, 30, 255))

    elif style_type == "oficina":
        # Muro cortina de cristal azul reflectante
        for y in range(s):
            for x in range(s):
                mullion = (y % 16 == 0) or (x % 16 == 0)
                if mullion:
                    img.putpixel((x, y), (165, 175, 185, 255)) # Perfil aluminio anodizado
                else:
                    # Degradado de cielo reflejado en cristal
                    glass_r = int(35 + 25 * (y / float(s)))
                    glass_g = int(75 + 35 * (y / float(s)))
                    glass_b = int(125 + 45 * (y / float(s)))
                    img.putpixel((x, y), (glass_r, glass_g, glass_b, 255))

    elif style_type == "industrial":
        # Lámina acanalada galvanizada
        for y in range(s):
            for x in range(s):
                wave = math.sin(x * 0.45) * 25
                base_c = int(140 + wave)
                base_c = max(0, min(255, base_c + random.randint(-4, 4)))
                img.putpixel((x, y), (base_c, base_c+2, base_c+5, 255))
        # Tornillos de fijación
        for r in range(4, s, 20):
            for c in range(8, s, 16):
                draw.rectangle([c-1, r-1, c+1, r+1], fill=(80, 85, 90, 255))

    elif style_type == "asfalto":
        # Asfalto vehicular con árido fino y grava
        for y in range(s):
            for x in range(s):
                grain = random.randint(-18, 18)
                c = max(0, min(255, 54 + grain))
                # Puntos blancos/grises ocasionales de piedra triturada
                if random.random() < 0.05:
                    c = min(255, c + 45)
                img.putpixel((x, y), (c, c, int(c * 1.05), 255))

    # ----------------------------------------------------
    # FILA 1: Vialidad, Elementos Mexicanos y Materiales
    # ----------------------------------------------------
    elif style_type == "banqueta":
        # Banqueta de concreto peinado con junta dilatación
        for y in range(s):
            for x in range(s):
                joint = (y == 0 or y == s-1 or x == 0 or x == s-1)
                if joint:
                    img.putpixel((x, y), (125, 125, 120, 255))
                else:
                    broom = int(math.sin(y * 1.8) * 4) # Estriado antideslizante
                    var = random.randint(-5, 5)
                    c = 195 + broom + var
                    img.putpixel((x, y), (c, c-2, c-6, 255))

    elif style_type == "curb_red":
        # Guarnición roja preventiva
        for y in range(s):
            for x in range(s):
                var = random.randint(-10, 10)
                # Borde superior con desgaste
                wear = 20 if (y < 4 or y > s-5) and random.random() < 0.2 else 0
                img.putpixel((x, y), (215+var-wear, 32+var+wear, 28+var+wear, 255))

    elif style_type == "curb_yellow":
        # Guarnición amarilla de carga/descarga
        for y in range(s):
            for x in range(s):
                var = random.randint(-12, 12)
                img.putpixel((x, y), (235+var, 205+var, 25+var, 255))

    elif style_type == "pasto":
        # Césped y briznas de pasto
        for y in range(s):
            for x in range(s):
                var = random.randint(-22, 22)
                img.putpixel((x, y), (50+var, 142+var, 45+var, 255))
        # Briznas individuales
        for _ in range(80):
            bx = random.randint(2, s-3)
            by = random.randint(4, s-2)
            draw.line([bx, by, bx+random.choice([-1, 0, 1]), by-random.randint(3, 6)],
                      fill=(85, 190, 70, 255), width=1)

    elif style_type == "cortina_metal":
        # CORTINA DE METAL ARROLLABLE MEXICANA (Roll-up Shutter)
        # Rieles laterales guía
        for y in range(s):
            for x in range(s):
                if x < 4 or x >= s-4:
                    # Guías laterales de acero grueso
                    img.putpixel((x, y), (85, 90, 95, 255))
                elif y >= s-8:
                    # Viga/zócalo inferior reforzado
                    img.putpixel((x, y), (70, 75, 80, 255))
                else:
                    # Lamas horizontales acanaladas (ribs cada 4 px)
                    rib_phase = y % 4
                    if rib_phase == 0:
                        shade = 45   # Brillo superior de la lama
                    elif rib_phase == 1:
                        shade = 20
                    elif rib_phase == 2:
                        shade = -10
                    else:
                        shade = -35  # Sombra de hendidura entre lamas
                    base_m = 160 + shade + random.randint(-3, 3)
                    img.putpixel((x, y), (base_m, base_m+2, base_m+5, 255))
        # Portacandado central y manijas de jalón
        draw.rectangle([s//2-5, s-12, s//2+5, s-4], fill=(50, 52, 55, 255), outline=(130, 135, 140, 255))
        draw.ellipse([s//2-2, s-10, s//2+2, s-6], fill=(210, 180, 60, 255)) # Ojo de candado de latón
        # Manijas laterales de elevación
        draw.rectangle([14, s-11, 22, s-9], fill=(50, 50, 55, 255))
        draw.rectangle([s-22, s-11, s-14, s-9], fill=(50, 50, 55, 255))

    elif style_type == "ladrillo":
        # TABIQUE ROJO RECOCIDO MEXICANO (Red Brick)
        # Dimensiones de tabique: 16 px ancho x 8 px alto
        brick_h = 8
        brick_w = 16
        mortar_color = (205, 200, 192, 255)
        for y in range(s):
            row = y // brick_h
            y_in_b = y % brick_h
            is_h_mortar = (y_in_b == 0)
            x_shift = (brick_w // 2) if (row % 2 == 1) else 0

            for x in range(s):
                x_adj = (x + x_shift) % s
                col = x_adj // brick_w
                x_in_b = x_adj % brick_w
                is_v_mortar = (x_in_b == 0)

                if is_h_mortar or is_v_mortar:
                    # Junta de mortero
                    m_grain = random.randint(-6, 6)
                    img.putpixel((x, y), (mortar_color[0]+m_grain, mortar_color[1]+m_grain, mortar_color[2]+m_grain, 255))
                else:
                    # Color natural de tabique recocido con variabilidad por ladrillo
                    brick_seed = (row * 37 + col * 101) & 0xFF
                    r_bias = (brick_seed % 25) - 12
                    b_grain = random.randint(-10, 10)
                    r = max(0, min(255, 185 + r_bias + b_grain))
                    g = max(0, min(255, 68 + int(r_bias*0.6) + b_grain))
                    b = max(0, min(255, 45 + int(r_bias*0.4) + b_grain))
                    # Bisel de sombra en orilla del ladrillo
                    if y_in_b == 1 or x_in_b == 1:
                        r, g, b = int(r * 1.15), int(g * 1.15), int(b * 1.15)
                    elif y_in_b == brick_h - 1 or x_in_b == brick_w - 1:
                        r, g, b = int(r * 0.75), int(g * 0.75), int(b * 0.75)
                    img.putpixel((x, y), (min(255, r), min(255, g), min(255, b), 255))

    elif style_type == "madera_arbol":
        # CORTEZA DE MADERA NATURAL PARA ÁRBOLES (Tree Bark)
        for y in range(s):
            for x in range(s):
                # Vetas verticales sinuosas
                furrow = math.sin(x * 0.6 + math.sin(y * 0.15) * 1.8) * 28
                fissure = 40 if abs(furrow) < 5 else 0 # Grieta profunda
                var = random.randint(-12, 12)
                r = max(0, min(255, int(92 + furrow - fissure + var)))
                g = max(0, min(255, int(66 + furrow*0.8 - fissure + var)))
                b = max(0, min(255, int(46 + furrow*0.5 - fissure + var)))
                # Musgo sutil en la corteza
                if (x + y * 3) % 47 == 0:
                    r, g, b = int(r*0.7), int(g*1.2), int(b*0.7)
                img.putpixel((x, y), (r, g, b, 255))

    elif style_type == "proteccion_ventana":
        # PROTECCIONES DE VENTANA (Herrería tradicional mexicana)
        # Fondo de ventana
        for y in range(s):
            for x in range(s):
                glass_b = int(70 + 40 * (y / float(s)))
                img.putpixel((x, y), (35, 55, glass_b, 255))
        # Marco de ventana blanco
        draw.rectangle([0, 0, s-1, s-1], outline=(235, 235, 240, 255), width=3)
        # Barrotes verticales de herrería negra (cada 8 px)
        bar_color = (25, 28, 30, 255)
        bar_hi = (75, 80, 85, 255)
        for bx in range(8, s-4, 8):
            draw.line([bx, 3, bx, s-4], fill=bar_color, width=3)
            draw.line([bx-1, 3, bx-1, s-4], fill=bar_hi, width=1) # Brillo metálico
            # Puntas de lanza / peinazo decorativo superior
            draw.polygon([(bx-3, 9), (bx, 3), (bx+3, 9)], fill=bar_color)
            # Nudo decorativo en el tercio medio
            draw.rectangle([bx-3, 30, bx+3, 33], fill=bar_hi)
        # Travesaños horizontales
        for ty in [14, s//2, s-14]:
            draw.line([3, ty, s-4, ty], fill=bar_color, width=3)
            draw.line([3, ty-1, s-4, ty-1], fill=bar_hi, width=1)

    # ----------------------------------------------------
    # FILA 2: Props, Señalización y Accidentes Geológicos
    # ----------------------------------------------------
    elif style_type == "malla_ciclonica":
        # MALLA CICLÓNICA DE ALAMBRE GALVANIZADO (Chain Link)
        # Fondo transparente
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Tubo superior de tensión
        draw.rectangle([0, 0, s-1, 6], fill=(160, 165, 170, 255), outline=(110, 115, 120, 255))
        # Poste vertical en el borde izquierdo
        draw.rectangle([0, 0, 5, s-1], fill=(150, 155, 160, 255), outline=(95, 100, 105, 255))
        # Alambre romboidal entrelazado
        wire_col = (175, 180, 185, 255)
        wire_shadow = (90, 95, 100, 255)
        step = 8
        for offset in range(-s, s * 2, step):
            # Líneas diagonales a 45 grados
            draw.line([offset, 7, offset + s, s], fill=wire_shadow, width=2)
            draw.line([offset, 7, offset + s, s], fill=wire_col, width=1)
            # Líneas diagonales a -45 grados
            draw.line([offset + s, 7, offset, s], fill=wire_shadow, width=2)
            draw.line([offset + s, 7, offset, s], fill=wire_col, width=1)

    elif style_type == "barandal":
        # BARANDAL DE HERRERÍA Y BALCÓN
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        iron_c = (30, 32, 36, 255)
        iron_hi = (95, 100, 105, 255)
        # Pasamanos superior
        draw.rectangle([0, 2, s-1, 8], fill=iron_c)
        draw.line([0, 2, s-1, 2], fill=iron_hi, width=1)
        # Riel inferior
        draw.rectangle([0, s-8, s-1, s-4], fill=iron_c)
        # Barrotes con nudillos decorativos
        for bx in range(6, s, 10):
            draw.line([bx, 8, bx, s-8], fill=iron_c, width=3)
            draw.line([bx-1, 8, bx-1, s-8], fill=iron_hi, width=1)
            # Macolla / nudo central
            draw.ellipse([bx-3, s//2-3, bx+3, s//2+3], fill=iron_c, outline=iron_hi)

    elif style_type == "stop_sign":
        # SEÑAL DE ALTO MEXICANA (NOM SCT)
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Poste galvanizado de fondo
        draw.rectangle([s//2-2, 0, s//2+2, s-1], fill=(160, 165, 170, 255))
        # Octágono rojo oficial NOM
        # Vértices del octágono regular
        pad = 4
        d = s - pad * 2
        corner = int(d * 0.2929) # d * (1 - 1/sqrt(2))
        x0, y0 = pad, pad
        x1, y1 = s - pad, s - pad
        oct_pts = [
            (x0 + corner, y0), (x1 - corner, y0),
            (x1, y0 + corner), (x1, y1 - corner),
            (x1 - corner, y1), (x0 + corner, y1),
            (x0, y1 - corner), (x0, y0 + corner)
        ]
        # Fondo rojo brillante oficial #C8102E
        draw.polygon(oct_pts, fill=(200, 16, 46, 255))
        # Borde blanco interior
        pad_in = pad + 3
        d_in = s - pad_in * 2
        corner_in = int(d_in * 0.2929)
        oct_in = [
            (pad_in + corner_in, pad_in), (s - pad_in - corner_in, pad_in),
            (s - pad_in, pad_in + corner_in), (s - pad_in, s - pad_in - corner_in),
            (s - pad_in - corner_in, s - pad_in), (pad_in + corner_in, s - pad_in),
            (pad_in, s - pad_in - corner_in), (pad_in, pad_in + corner_in)
        ]
        draw.polygon(oct_in, outline=(255, 255, 255, 255), width=2)
        # Letras "ALTO" centradas y nítidas
        # Tipografía stencil geométrica de alta legibilidad
        cy = s // 2
        # 'A'
        draw.polygon([(15, cy+7), (19, cy-7), (23, cy+7)], outline=(255, 255, 255, 255), width=2)
        draw.line([16, cy+2, 22, cy+2], fill=(255, 255, 255, 255), width=2)
        # 'L'
        draw.line([26, cy-7, 26, cy+7], fill=(255, 255, 255, 255), width=2)
        draw.line([26, cy+7, 32, cy+7], fill=(255, 255, 255, 255), width=2)
        # 'T'
        draw.line([34, cy-7, 42, cy-7], fill=(255, 255, 255, 255), width=2)
        draw.line([38, cy-7, 38, cy+7], fill=(255, 255, 255, 255), width=2)
        # 'O'
        draw.ellipse([44, cy-7, 52, cy+7], outline=(255, 255, 255, 255), width=2)

    elif style_type == "hidrante":
        # HIDRANTE URBANO (Fire Hydrant)
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        red_body = (215, 30, 30, 255)
        red_hi   = (255, 80, 80, 255)
        red_sh   = (140, 18, 18, 255)
        brass    = (225, 190, 45, 255) # Latón de boquillas y tuerca
        # Brida base con pernos
        draw.rectangle([16, s-8, 48, s-2], fill=(90, 92, 95, 255), outline=(50, 50, 50, 255))
        for px in [20, 26, 32, 38, 44]:
            draw.rectangle([px-1, s-9, px+1, s-7], fill=(180, 185, 190, 255))
        # Barril cilíndrico central
        draw.rectangle([22, 18, 42, s-8], fill=red_body)
        draw.line([25, 18, 25, s-8], fill=red_hi, width=2)  # Brillo cilíndrico
        draw.line([39, 18, 39, s-8], fill=red_sh, width=2)  # Sombra cilíndrica
        # Anillo / brida intermedia
        draw.rectangle([20, 34, 44, 38], fill=red_sh)
        # Boquillas laterales de 2.5 pulgadas
        draw.rectangle([12, 24, 22, 32], fill=brass, outline=(140, 110, 25, 255)) # Izquierda
        draw.rectangle([42, 24, 52, 32], fill=brass, outline=(140, 110, 25, 255)) # Derecha
        # Cadenas de retención de tapones
        draw.line([14, 33, 20, 42], fill=(180, 180, 185, 255), width=1)
        draw.line([50, 33, 44, 42], fill=(180, 180, 185, 255), width=1)
        # Boquilla frontal principal (steamer port de 4.5 pulgadas)
        draw.ellipse([27, 24, 37, 34], fill=brass, outline=(140, 110, 25, 255))
        # Cúpula superior (bonete)
        draw.chord([20, 10, 44, 24], start=180, end=0, fill=red_body, outline=red_sh)
        # Tuerca pentagonal de apertura en la punta
        draw.rectangle([30, 6, 34, 11], fill=brass, outline=(130, 100, 20, 255))

    elif style_type == "cauce_arroyo":
        # LECHO Y CAUCE DE ARROYO (Río San Pedro / El Cedazo)
        # Gravas, cantos rodados y arena fluvial húmeda
        for y in range(s):
            for x in range(s):
                var = random.randint(-15, 15)
                # Tono arena arcillosa fluvial típica de Aguascalientes
                c_r = max(0, min(255, 155 + var))
                c_g = max(0, min(255, 140 + var))
                c_b = max(0, min(255, 118 + var))
                img.putpixel((x, y), (c_r, c_g, c_b, 255))
        # Cantos rodados y piedras redondeadas por el agua
        for _ in range(45):
            px = random.randint(4, s-6)
            py = random.randint(4, s-6)
            prx = random.randint(3, 7)
            pry = random.randint(2, 5)
            stone_col = random.choice([
                (175, 170, 160, 255), # Piedra caliza clara
                (120, 115, 110, 255), # Basalto gris oscuro
                (185, 140, 115, 255), # Canto rodado rojizo
                (140, 130, 110, 255)  # Canto rodado beige
            ])
            draw.ellipse([px-prx, py-pry, px+prx, py+pry], fill=stone_col)
            # Sombra y brillo de la piedra
            draw.arc([px-prx, py-pry, px+prx, py+pry], start=0, end=180, fill=(70, 65, 60, 255))
            draw.arc([px-prx, py-pry, px+prx, py+pry], start=180, end=360, fill=(230, 225, 215, 255))

    elif style_type == "falla_geologica":
        # ESCARPE Y FRACTURA DE FALLA GEOLÓGICA (Falla Oriente/Poniente)
        for y in range(s):
            # Escarpe vertical: lado izquierdo bloque levantado (+claro), lado derecho bloque hundido (+oscuro)
            base_l = 150
            for x in range(s):
                displ = -25 if x > 32 else 15
                var = random.randint(-8, 8)
                c = max(0, min(255, base_l + displ + var))
                img.putpixel((x, y), (c, c-3, c-8, 255))
        # Grieta/fractura central sinuosa del terreno
        crack_x = 32
        for y in range(s):
            crack_x += random.choice([-1, 0, 0, 1])
            crack_x = max(24, min(40, crack_x))
            draw.line([crack_x-1, y, crack_x+1, y], fill=(35, 30, 25, 255), width=2)
            # Fisuras secundarias ramificadas
            if random.random() < 0.12:
                fork_dir = random.choice([-5, 5])
                draw.line([crack_x, y, crack_x+fork_dir, y+random.randint(2, 5)], fill=(45, 40, 35, 255), width=1)

    elif style_type == "fachada_cochera":
        # PORTÓN DE COCHERA MEXICANO MODERNO
        for y in range(s):
            for x in range(s):
                if y < 14:
                    # Cornisa superior de cantera
                    img.putpixel((x, y), (210, 195, 175, 255))
                elif x < 6 or x >= s-6:
                    # Muro lateral de fachada
                    img.putpixel((x, y), (225, 218, 205, 255))
                else:
                    # Portón de perfiles horizontales chocolate / café tabaco
                    slat = (y - 14) % 6
                    c_base = 65 if slat == 0 else (90 if slat == 1 else 75)
                    img.putpixel((x, y), (c_base+15, c_base+5, c_base-5, 255))
        # Chapetón / cerradura de portón
        draw.rectangle([s-14, 36, s-10, 42], fill=(210, 190, 70, 255))

    elif style_type == "cantera_rosa":
        # CANTERA ROSA TRADICIONAL DE AGUASCALIENTES (Templo de San Antonio / Jesús María)
        base = (215, 165, 155)
        for y in range(s):
            for x in range(s):
                joint = (y % 16 == 0) or (x % 32 == 0 and (y // 16) % 2 == 0) or ((x + 16) % 32 == 0 and (y // 16) % 2 == 1)
                var = random.randint(-9, 9)
                if joint:
                    img.putpixel((x, y), (155, 110, 100, 255))
                else:
                    grain = 10 if random.random() < 0.12 else 0
                    img.putpixel((x, y), (base[0]+var-grain, base[1]+var-grain, base[2]+var-grain, 255))

    return img

def generate_atlas():
    atlas = Image.new("RGBA", (ATLAS_W, ATLAS_H), (0, 0, 0, 0))

    # Mapeo de Tiles en el Atlas (Grid de 8x8, cada tile de 64x64 px)
    tiles_map = {
        # Fila 0: Fachadas Base
        (0, 0): "residencial",
        (1, 0): "comercial",
        (2, 0): "escuela",
        (3, 0): "templo",
        (4, 0): "hospital",
        (5, 0): "oficina",
        (6, 0): "industrial",
        (7, 0): "asfalto",

        # Fila 1: Vialidad y Materiales Mexicanos
        (0, 1): "banqueta",
        (1, 1): "curb_red",
        (2, 1): "curb_yellow",
        (3, 1): "pasto",
        (4, 1): "cortina_metal",
        (5, 1): "ladrillo",
        (6, 1): "madera_arbol",
        (7, 1): "proteccion_ventana",

        # Fila 2: Props, Señalización y Relieve
        (0, 2): "malla_ciclonica",
        (1, 2): "barandal",
        (2, 2): "stop_sign",
        (3, 2): "hidrante",
        (4, 2): "cauce_arroyo",
        (5, 2): "falla_geologica",
        (6, 2): "fachada_cochera",
        (7, 2): "cantera_rosa",
    }

    print(f"[Atlas HD] Generando atlas de texturas ligero ({ATLAS_W}x{ATLAS_H} px)...")
    for (col, row), style_name in tiles_map.items():
        tile = create_tile(style_name, TILE_SIZE)
        atlas.paste(tile, (col * TILE_SIZE, row * TILE_SIZE))
        print(f"  ✓ Slot ({col}, {row}) -> '{style_name}'")

    os.makedirs("models", exist_ok=True)
    os.makedirs("assets", exist_ok=True)
    out_models = "models/texture_atlas_16x16.png"
    out_assets = "assets/texture_atlas_16x16.png"
    atlas.save(out_models)
    atlas.save(out_assets)
    print(f"[Atlas HD] ✅ Creado exitosamente en {out_models} y {out_assets} ({ATLAS_W}x{ATLAS_H} px, {len(tiles_map)} texturas activas)")

if __name__ == "__main__":
    generate_atlas()
