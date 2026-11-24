#!/usr/bin/env python3
"""
photo_plane_importer.py
=======================
Convierte una fotografía georeferenciada en un plano 3D dentro de StreetVulkan.

Dado:
  - Una imagen (JPG/PNG) tomada en coordenadas GPS conocidas
  - Metadatos: lat, lon, altitud, heading (azimut 0-360°N), pitch (-90..90°), FOV horizontal

Genera:
  - Un quad .obj en models/generated/photo_<nombre>.obj
  - Una copia de la textura en models/generated/photo_<nombre>.jpg
  - Un archivo .mtl asociado
  - Un .json de metadatos para referencia

El motor carga automáticamente todos los .obj en models/generated/ al arrancar.

Uso:
  python3 tools/photo_plane_importer.py --photo assets/streetview/mi_foto.jpg \\
      --lat 21.8807 --lon -102.2965 --heading 90.0 --pitch 0.0 --fov 73.0 \\
      --dist 40.0 --scale 1.0

  O con un JSON de metadatos preexistente (formato StreetView):
  python3 tools/photo_plane_importer.py --meta assets/streetview/gsv_xxx.json

  O con EXIF automático de una foto de smartphone:
  python3 tools/photo_plane_importer.py --photo mi_foto.jpg --exif
"""

import argparse
import json
import math
import os
import shutil
import sys

# ── Constantes del motor StreetVulkan (deben coincidir con vulkan.c) ──────────
ORIGIN_LAT   = 21.8807
ORIGIN_LON   = -102.2965
M_PER_LAT    = 111320.0

def get_m_per_lon(lat=ORIGIN_LAT):
    return M_PER_LAT * math.cos(math.radians(lat))

def geo_to_world(lat, lon, alt=0.0):
    """Convierte GPS (lat, lon, alt_metros) → coordenadas mundo del motor (x, y, z)."""
    m_per_lon = get_m_per_lon(ORIGIN_LAT)
    x = (lon - ORIGIN_LON) * m_per_lon
    z = -(lat - ORIGIN_LAT) * M_PER_LAT
    # La altitud relativa al datum del motor (1871m base Aguascalientes)
    y = alt - 1871.0 if alt > 100.0 else alt
    return x, y, z


def heading_pitch_to_dir(heading_deg, pitch_deg):
    """
    Convierte azimut (0=Norte, 90=Este) y pitch (0=horizontal, +up) al
    vector dirección unitario en el espacio del motor.

    Sistema del motor: X=Este, Y=Arriba, Z=Sur (mano derecha)
    """
    h = math.radians(heading_deg)
    p = math.radians(pitch_deg)

    # Azimut: 0=Norte(−Z), 90=Este(+X)
    dx =  math.sin(h) * math.cos(p)
    dy =  math.sin(p)
    dz = -math.cos(h) * math.cos(p)

    return dx, dy, dz


def make_photo_quad(
    world_x, world_y, world_z,
    heading_deg, pitch_deg,
    fov_h_deg,
    image_width, image_height,
    depth=40.0,
    scale=1.0,
    width_m=None,
    height_m=None,
    output_prefix="photo_plane",
    texture_filename="photo.jpg",
):
    """
    Genera un quad OBJ perspective-correct delante de la posición de la cámara.

    El plano se sitúa a `depth` metros en la dirección de la cámara y se
    dimensiona exactamente para que el ángulo de apertura coincida con el FOV
    de la foto original — lo que significa que si el jugador se para en las
    coordenadas de la foto y mira en la misma dirección, verá el plano
    solapándose perfectamente con la geometría urbana de fondo.
    """
    # ── 1. Vectores de la cámara ─────────────────────────────────────────────
    fwd_x, fwd_y, fwd_z = heading_pitch_to_dir(heading_deg, pitch_deg)

    # Vector "arriba" del mundo
    world_up = (0.0, 1.0, 0.0)

    # Right = Forward × Up (normalizado)
    rx = fwd_y * world_up[2] - fwd_z * world_up[1]
    ry = fwd_z * world_up[0] - fwd_x * world_up[2]
    rz = fwd_x * world_up[1] - fwd_y * world_up[0]
    rlen = math.sqrt(rx*rx + ry*ry + rz*rz)
    if rlen < 1e-6:
        # Cámara mirando exactamente hacia arriba/abajo → usar Z como referencia
        rx, ry, rz = 1.0, 0.0, 0.0
    else:
        rx, ry, rz = rx/rlen, ry/rlen, rz/rlen

    # Up real = Right × Forward
    ux = ry * fwd_z - rz * fwd_y
    uy = rz * fwd_x - rx * fwd_z
    uz = rx * fwd_y - ry * fwd_x

    # ── 2. Dimensiones del quad ──────────────────────────────────────────────
    aspect = image_width / image_height
    if width_m is not None and width_m > 0.0:
        half_w = (width_m / 2.0) * scale
        half_h = (half_w / aspect) if (height_m is None or height_m <= 0.0) else (height_m / 2.0) * scale
    elif height_m is not None and height_m > 0.0:
        half_h = (height_m / 2.0) * scale
        half_w = half_h * aspect * scale
    else:
        # Modo angular por FOV de cámara
        fov_h_rad = math.radians(fov_h_deg)
        half_w = depth * math.tan(fov_h_rad / 2.0) * scale
        half_h = half_w / aspect

    # ── 3. Centro del quad (point in front of camera) ───────────────────────
    cx = world_x + fwd_x * depth
    cy = world_y + fwd_y * depth
    cz = world_z + fwd_z * depth

    # ── 4. Las 4 esquinas del quad ───────────────────────────────────────────
    #        top-left, top-right, bottom-right, bottom-left
    corners = []
    for (sr, su) in [(-1, 1), (1, 1), (1, -1), (-1, -1)]:
        vx = cx + rx * half_w * sr + ux * half_h * su
        vy = cy + ry * half_w * sr + uy * half_h * su
        vz = cz + rz * half_w * sr + uz * half_h * su
        corners.append((vx, vy, vz))

    # ── 5. Normal del quad (apunta hacia la cámara) ──────────────────────────
    nx, ny, nz = -fwd_x, -fwd_y, -fwd_z

    # ── 6. UV coords (con stbi flip=0: Y=0 es arriba, Y=1 es abajo) ───────────
    # corners: top-left (-1,1), top-right (1,1), bottom-right (1,-1), bottom-left (-1,-1)
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

    # ── 7. Generar OBJ ───────────────────────────────────────────────────────
    lines = [
        f"# Generado por photo_plane_importer.py",
        f"# GPS: lat={world_x:.6f} lon={world_y:.6f}  heading={heading_deg}°  pitch={pitch_deg}°",
        f"# Plano a {depth}m de profundidad, FOV={fov_h_deg}° ({image_width}×{image_height}px)",
        f"mtllib {output_prefix}.mtl",
        f"o PhotoPlane",
    ]

    for (vx, vy, vz) in corners:
        lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}")

    for (u, v) in uvs:
        lines.append(f"vt {u:.4f} {v:.4f}")

    lines.append(f"vn {nx:.4f} {ny:.4f} {nz:.4f}")
    lines.append(f"usemtl photo_mat")
    lines.append(f"s off")

    # Dos triángulos (quad = 2 tris, CCW desde fuera)
    # OBJ indexing is 1-based: v/vt/vn
    lines.append("f 1/1/1 2/2/1 3/3/1")
    lines.append("f 1/1/1 3/3/1 4/4/1")

    return "\n".join(lines), corners


def make_mtl(texture_filename):
    return f"""# Material generado por photo_plane_importer.py
newmtl photo_mat
Ka 1.0 1.0 1.0
Kd 1.0 1.0 1.0
Ks 0.0 0.0 0.0
d 1.3
illum 1
map_Kd {texture_filename}
"""


def extract_exif_gps(photo_path):
    """
    Extrae metadatos GPS/orientación del EXIF de una foto de smartphone.
    Requiere: pip install pillow
    Retorna dict con lat, lon, alt, heading, pitch o None si no hay EXIF GPS.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        img = Image.open(photo_path)
        exif_raw = img._getexif()
        if not exif_raw:
            return None

        exif = {TAGS.get(k, k): v for k, v in exif_raw.items()}
        gps_raw = exif.get("GPSInfo", {})
        gps = {GPSTAGS.get(k, k): v for k, v in gps_raw.items()}

        def dms_to_dd(dms, ref):
            d, m, s = [float(x) for x in dms]
            dd = d + m / 60.0 + s / 3600.0
            return -dd if ref in ('S', 'W') else dd

        if "GPSLatitude" not in gps:
            return None

        lat = dms_to_dd(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
        lon = dms_to_dd(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
        alt = float(gps.get("GPSAltitude", 0))
        # Heading: GPSImgDirection (compass bearing of camera)
        heading = float(gps.get("GPSImgDirection", 0))
        # Pitch no está en EXIF estándar (viene del acelerómetro, raramente guardado)
        pitch = 0.0

        return dict(lat=lat, lon=lon, alt=alt, heading=heading, pitch=pitch)

    except Exception as e:
        print(f"[EXIF] No se pudo leer EXIF GPS: {e}")
        return None


def import_photo(
    photo_path,
    lat, lon, alt=1871.0,
    heading=0.0, pitch=0.0,
    fov_h=73.0,
    depth=40.0,
    scale=1.0,
    width_m=None,
    height_m=None,
    output_dir="models/generated",
):
    from PIL import Image

    os.makedirs(output_dir, exist_ok=True)

    # Nombre base del output (sin extensión)
    base = os.path.splitext(os.path.basename(photo_path))[0]
    base = "photo_" + base.replace(" ", "_").replace("-", "_")

    obj_path  = os.path.join(output_dir, base + ".obj")
    mtl_path  = os.path.join(output_dir, base + ".mtl")
    meta_path = os.path.join(output_dir, base + ".json")

    # Determinar la extensión de la textura
    ext = os.path.splitext(photo_path)[1].lower()
    tex_name = base + ext
    tex_path = os.path.join(output_dir, tex_name)

    # Leer dimensiones de la imagen
    img = Image.open(photo_path)
    img_w, img_h = img.size

    # Convertir GPS → coordenadas mundo
    wx, wy, wz = geo_to_world(lat, lon, alt)

    print(f"[import] GPS ({lat:.6f}, {lon:.6f}, alt={alt:.1f}m)")
    print(f"[import] World ({wx:.2f}, {wy:.2f}, {wz:.2f}) — heading={heading}°, pitch={pitch}°, FOV={fov_h}°")
    if width_m or height_m:
        print(f"[import] Dimensiones fijadas: ancho={width_m}m, alto={height_m}m (escala={scale})")
    else:
        print(f"[import] Imagen {img_w}×{img_h} → plano a {depth}m de profundidad (FOV={fov_h}°)")

    # Generar OBJ
    obj_content, corners = make_photo_quad(
        world_x=wx, world_y=wy, world_z=wz,
        heading_deg=heading, pitch_deg=pitch,
        fov_h_deg=fov_h,
        image_width=img_w, image_height=img_h,
        depth=depth, scale=scale,
        width_m=width_m, height_m=height_m,
        output_prefix=base,
        texture_filename=tex_name,
    )

    # Escribir archivos
    with open(obj_path, "w") as f:
        f.write(obj_content)
    with open(mtl_path, "w") as f:
        f.write(make_mtl(tex_name))

    # Copiar/convertir textura al directorio de salida
    if photo_path != tex_path:
        if ext in (".jpg", ".jpeg", ".png", ".bmp"):
            shutil.copy2(photo_path, tex_path)
        else:
            img.convert("RGB").save(tex_path, "JPEG", quality=95)
        print(f"[import] Textura copiada → {tex_path}")

    # Metadatos JSON
    meta = {
        "source_photo": photo_path,
        "gps": {"lat": lat, "lon": lon, "alt": alt},
        "camera": {"heading": heading, "pitch": pitch, "fov_h": fov_h},
        "depth_m": depth,
        "scale": scale,
        "world_origin": {"x": wx, "y": wy, "z": wz},
        "quad_corners_world": [list(c) for c in corners],
        "obj": obj_path,
        "texture": tex_path,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"[import] ✅  Plano generado:")
    print(f"           OBJ:      {obj_path}")
    print(f"           MTL:      {mtl_path}")
    print(f"           Textura:  {tex_path}")
    print(f"           Metadata: {meta_path}")
    print(f"[import] Reinicia el motor (./street_vulkan) para ver el plano en la ciudad.")
    return obj_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Importa una fotografía georeferenciada como plano 3D en StreetVulkan."
    )
    parser.add_argument("--photo",    required=False, help="Ruta a la imagen (JPG/PNG).")
    parser.add_argument("--meta",     required=False, help="JSON de metadatos (formato StreetView o propio).")
    parser.add_argument("--exif",     action="store_true", help="Leer GPS del EXIF de la foto.")
    parser.add_argument("--lat",      type=float, default=None)
    parser.add_argument("--lon",      type=float, default=None)
    parser.add_argument("--alt",      type=float, default=1871.0, help="Altitud en metros (default=1871.0m cota base Aguascalientes)")
    parser.add_argument("--heading",  type=float, default=0.0,    help="Azimut cámara 0=Norte, 90=Este (grados)")
    parser.add_argument("--pitch",    type=float, default=0.0,    help="Inclinación vertical (0=horizontal, +arriba)")
    parser.add_argument("--fov",      type=float, default=73.0,   help="FOV horizontal de la cámara en grados (default=73° iPhone/Android típico)")
    parser.add_argument("--dist",     type=float, default=40.0,   help="Distancia del plano delante de la cámara (metros)")
    parser.add_argument("--width",    type=float, default=None,   help="Ancho explícito del plano en metros (ej: 14.0)")
    parser.add_argument("--height",   type=float, default=None,   help="Alto explícito del plano en metros (ej: 5.0)")
    parser.add_argument("--scale",    type=float, default=1.0,    help="Factor de escala del plano (1.0=perfecto)")
    parser.add_argument("--outdir",   type=str,   default="models/generated")
    args = parser.parse_args()

    # ── Resolver metadatos ───────────────────────────────────────────────────
    photo_path = args.photo
    lat, lon, alt = args.lat, args.lon, args.alt
    heading, pitch, fov = args.heading, args.pitch, args.fov

    if args.meta:
        with open(args.meta) as f:
            meta = json.load(f)
        lat      = meta.get("lat",     lat)
        lon      = meta.get("lon",     lon)
        heading  = meta.get("heading", heading)
        pitch    = meta.get("pitch",   pitch)
        alt      = meta.get("alt",     alt)
        fov      = meta.get("fov_h",   fov)
        if not photo_path:
            photo_path = meta.get("file_path") or meta.get("photo")

    if args.exif and photo_path:
        gps = extract_exif_gps(photo_path)
        if gps:
            lat, lon, alt = gps["lat"], gps["lon"], gps["alt"]
            heading, pitch = gps["heading"], gps["pitch"]
            print(f"[EXIF] GPS extraído: lat={lat:.6f} lon={lon:.6f} heading={heading:.1f}°")
        else:
            print("[EXIF] No se encontró GPS en el EXIF. Usa --lat/--lon manualmente.")
            sys.exit(1)

    if not photo_path:
        parser.error("Se requiere --photo con la ruta a la imagen.")
    if lat is None or lon is None:
        parser.error("Se requieren --lat y --lon (o usa --meta / --exif).")

    import_photo(
        photo_path=photo_path,
        lat=lat, lon=lon, alt=alt,
        heading=heading, pitch=pitch,
        fov_h=fov,
        depth=args.dist,
        scale=args.scale,
        width_m=args.width,
        height_m=args.height,
        output_dir=args.outdir,
    )


if __name__ == "__main__":
    main()
