#!/usr/bin/env python3
"""
generate_texture_atlas.py
=========================
Genera un Atlas de Texturas Pixel-Art (128x128 px formado por cuadros 16x16 px)
para StreetVulkan.

Cada casilla de 16x16 contiene la textura pixel-art nítida para:
- Residencial, Comercial, Escuela, Templo, Hospital, Oficina, Industrial.
- Asfalto, Banqueta, Guarnición Roja, Guarnición Amarilla, Pasto.
"""
import os
import random
from PIL import Image, ImageDraw

TILE_SIZE = 16
GRID_COLS = 8
GRID_ROWS = 8
ATLAS_W = TILE_SIZE * GRID_COLS
ATLAS_H = TILE_SIZE * GRID_ROWS

def create_16x16_tile(style_type):
    img = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    if style_type == "residencial":
        # Estuco cálido con ladrillo claro y ventanas tradicionales
        base_col = (210, 195, 175)
        for y in range(16):
            for x in range(16):
                var = random.randint(-8, 8)
                img.putpixel((x, y), (base_col[0]+var, base_col[1]+var, base_col[2]+var, 255))
        # Ventana 4x4 en el centro
        draw.rectangle([5, 4, 10, 9], fill=(60, 90, 120, 255), outline=(240, 240, 240, 255))

    elif style_type == "comercial":
        # Fachada tipo OXXO / Comercial (rojo/blanco corporativo)
        for y in range(16):
            for x in range(16):
                if y < 4:
                    img.putpixel((x, y), (210, 30, 25, 255)) # Marquesina roja
                elif y < 6:
                    img.putpixel((x, y), (240, 240, 240, 255)) # Franja blanca
                else:
                    var = random.randint(-5, 5)
                    img.putpixel((x, y), (220+var, 215+var, 205+var, 255))
        # Vitrina comercial
        draw.rectangle([3, 7, 12, 13], fill=(40, 70, 100, 255), outline=(230, 230, 230, 255))

    elif style_type == "escuela":
        # Ladrillo rojo académico con ventanas ordenadas
        for y in range(16):
            for x in range(16):
                mortar = (y % 4 == 0) or (x % 4 == 0 and (y // 4) % 2 == 0)
                if mortar:
                    img.putpixel((x, y), (180, 175, 165, 255))
                else:
                    var = random.randint(-12, 12)
                    img.putpixel((x, y), (160+var, 70+var, 50+var, 255))
        # Ventanas pequeñas
        draw.rectangle([2, 2, 5, 5], fill=(80, 120, 160, 255))
        draw.rectangle([10, 2, 13, 5], fill=(80, 120, 160, 255))

    elif style_type == "templo":
        # Cantera beige pulida / Piedra labrada colonial
        base_col = (195, 180, 155)
        for y in range(16):
            for x in range(16):
                joint = (y % 8 == 0) or (x % 8 == 0)
                var = random.randint(-10, 10)
                if joint:
                    img.putpixel((x, y), (130, 120, 100, 255))
                else:
                    img.putpixel((x, y), (base_col[0]+var, base_col[1]+var, base_col[2]+var, 255))

    elif style_type == "hospital":
        # Azulejo clínico blanco/verde pastel + cruz médica
        for y in range(16):
            for x in range(16):
                joint = (y % 4 == 0) or (x % 4 == 0)
                if joint:
                    img.putpixel((x, y), (180, 205, 195, 255))
                else:
                    var = random.randint(-4, 4)
                    img.putpixel((x, y), (235+var, 245+var, 240+var, 255))
        # Cruz médica
        draw.rectangle([7, 5, 8, 10], fill=(210, 40, 40, 255))
        draw.rectangle([5, 7, 10, 8], fill=(210, 40, 40, 255))

    elif style_type == "oficina":
        # Cristalería y marcos de aluminio de rascacielos/oficinas
        for y in range(16):
            for x in range(16):
                frame = (y % 4 == 0) or (x % 4 == 0)
                if frame:
                    img.putpixel((x, y), (140, 150, 160, 255)) # Aluminio
                else:
                    var = random.randint(-8, 8)
                    img.putpixel((x, y), (50+var, 90+var, 130+var, 255)) # Cristal azul

    elif style_type == "industrial":
        # Concreto gris industrial / Lámina
        for y in range(16):
            for x in range(16):
                var = random.randint(-12, 12)
                img.putpixel((x, y), (130+var, 135+var, 140+var, 255))

    elif style_type == "asfalto":
        # Asfalto gris oscuro con motas de grava 16x16
        for y in range(16):
            for x in range(16):
                var = random.randint(-15, 15)
                img.putpixel((x, y), (55+var, 55+var, 60+var, 255))

    elif style_type == "banqueta":
        # Concreto claro de acera peatonal con juntas cuadradas
        for y in range(16):
            for x in range(16):
                joint = (y == 0 or y == 15 or x == 0 or x == 15)
                if joint:
                    img.putpixel((x, y), (130, 130, 130, 255))
                else:
                    var = random.randint(-8, 8)
                    img.putpixel((x, y), (185+var, 182+var, 178+var, 255))

    elif style_type == "curb_red":
        # Guarnición Roja Preventiva de esquina
        for y in range(16):
            for x in range(16):
                var = random.randint(-10, 10)
                img.putpixel((x, y), (215+var, 30+var, 25+var, 255))

    elif style_type == "curb_yellow":
        # Guarnición Amarilla de Carga
        for y in range(16):
            for x in range(16):
                var = random.randint(-10, 10)
                img.putpixel((x, y), (230+var, 200+var, 20+var, 255))

    elif style_type == "pasto":
        # Hierba/Pasto verde pixel-art
        for y in range(16):
            for x in range(16):
                var = random.randint(-18, 18)
                img.putpixel((x, y), (55+var, 140+var, 50+var, 255))

    return img

def generate_atlas():
    atlas = Image.new("RGBA", (ATLAS_W, ATLAS_H), (0, 0, 0, 255))

    # Mapeo de Tiles 16x16 en el Atlas
    tiles_map = {
        (0, 0): "residencial",
        (1, 0): "comercial",
        (2, 0): "escuela",
        (3, 0): "templo",
        (4, 0): "hospital",
        (5, 0): "oficina",
        (6, 0): "industrial",
        (7, 0): "asfalto",
        (0, 1): "banqueta",
        (1, 1): "curb_red",
        (2, 1): "curb_yellow",
        (3, 1): "pasto",
    }

    for (col, row), style_name in tiles_map.items():
        tile = create_16x16_tile(style_name)
        atlas.paste(tile, (col * TILE_SIZE, row * TILE_SIZE))

    os.makedirs("models", exist_ok=True)
    os.makedirs("assets", exist_ok=True)
    out_png = "models/texture_atlas_16x16.png"
    atlas.save(out_png)
    print(f"[Atlas 16x16] ✅ Creado exitosamente en {out_png} (128x128 px)")

if __name__ == "__main__":
    generate_atlas()
