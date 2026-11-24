#!/usr/bin/env python3
"""
procedural_props.py FASE 2b - Árboles visibles a 700m
- 12m alto, copa 5m, color neón debug + beacon emisivo
"""
import math, random
from topography_math import triangulate_2d
from rolcar_vector import build_rolcar_storefront_geometry, build_rolcar_elevated_sign

def make_cylinder(base_x, base_y, base_z, radius, height, segments=6, color=(0.2,0.2,0.2,1.0), uv_tile=None):
    verts=[]; top_y=base_y+height
    for s in range(segments):
        a0=s*2.0*math.pi/segments; a1=(s+1)*2.0*math.pi/segments
        c0,s0=math.cos(a0),math.sin(a0); c1,s1=math.cos(a1),math.sin(a1)
        p0=(base_x+radius*c0,base_y,base_z+radius*s0)
        p1=(base_x+radius*c1,base_y,base_z+radius*s1)
        p2=(base_x+radius*c1,top_y,base_z+radius*s1)
        p3=(base_x+radius*c0,top_y,base_z+radius*s0)
        avg_n=((c0+c1)*0.5,0.0,(s0+s1)*0.5)
        if uv_tile:
            col, row = uv_tile
            u0 = (col + s / float(segments)) * 0.125
            u1 = (col + (s + 1) / float(segments)) * 0.125
            v0 = row * 0.125
            v1 = (row + 1) * 0.125
            uv0, uv1, uv2, uv3 = (u0, v1), (u1, v1), (u1, v0), (u0, v0)
        else:
            uv0, uv1, uv2, uv3 = (0,0), (0,0), (0,0), (0,0)
        verts.append((p0,avg_n,uv0,color,0.0)); verts.append((p1,avg_n,uv1,color,0.0)); verts.append((p2,avg_n,uv2,color,0.0))
        verts.append((p0,avg_n,uv0,color,0.0)); verts.append((p2,avg_n,uv2,color,0.0)); verts.append((p3,avg_n,uv3,color,0.0))
    return verts

def make_box(cx,cy,cz,wx,wy,wz,color=(0.18,0.18,0.2,1.0),emission=0.0):
    verts=[]; hx,hy,hz=wx*0.5,wy*0.5,wz*0.5
    faces=[([(cx-hx,cy-hy,cz+hz),(cx+hx,cy-hy,cz+hz),(cx+hx,cy+hy,cz+hz),(cx-hx,cy+hy,cz+hz)],(0,0,1)),
           ([(cx+hx,cy-hy,cz-hz),(cx-hx,cy-hy,cz-hz),(cx-hx,cy+hy,cz-hz),(cx+hx,cy+hy,cz-hz)],(0,0,-1)),
           ([(cx-hx,cy+hy,cz+hz),(cx+hx,cy+hy,cz+hz),(cx+hx,cy+hy,cz-hz),(cx-hx,cy+hy,cz-hz)],(0,1,0)),
           ([(cx-hx,cy-hy,cz-hz),(cx+hx,cy-hy,cz-hz),(cx+hx,cy-hy,cz+hz),(cx-hx,cy-hy,cz+hz)],(0,-1,0)),
           ([(cx+hx,cy-hy,cz+hz),(cx+hx,cy-hy,cz-hz),(cx+hx,cy+hy,cz-hz),(cx+hx,cy+hy,cz+hz)],(1,0,0)),
           ([(cx-hx,cy-hy,cz-hz),(cx-hx,cy-hy,cz+hz),(cx-hx,cy+hy,cz+hz),(cx-hx,cy+hy,cz-hz)],(-1,0,0))]
    for quad,norm in faces:
        verts.append((quad[0],norm,(0,0),color,emission)); verts.append((quad[1],norm,(0,0),color,emission)); verts.append((quad[2],norm,(0,0),color,emission))
        verts.append((quad[0],norm,(0,0),color,emission)); verts.append((quad[2],norm,(0,0),color,emission)); verts.append((quad[3],norm,(0,0),color,emission))
    return verts

# ==============================================================================
# Atlas Slot Definitions (8x8 Texture Atlas Grid)
# ==============================================================================
SLOT_METAL_SHUTTER = 15      # Slot 15: (4, 1) - Cortina metálica comercial arrollable
SLOT_BRICK = 16              # Slot 16: (5, 1) - Ladrillo / Tabique rojo recocido mexicano
SLOT_WINDOW_GRILLE = 18      # Slot 18: (7, 1) - Protecciones / Rejas de ventana de herrería

ATLAS_SLOT_TILES = {
    SLOT_METAL_SHUTTER: (4, 1),
    SLOT_BRICK: (5, 1),
    SLOT_WINDOW_GRILLE: (7, 1),
    "cortina_metal": (4, 1),
    "metal_shutter": (4, 1),
    "ladrillo": (5, 1),
    "brick": (5, 1),
    "proteccion_ventana": (7, 1),
    "window_grille": (7, 1),
}

CATEGORY_TILES = {
    "residencial": (0, 0),
    "vivienda": (0, 0),
    "casa": (0, 0),
    "residence_1f": (0, 0),
    "residence_2f": (0, 0),
    "comercial": (1, 0),
    "oxxo": (1, 0),
    "rolcar": (1, 0),
    "retail": (1, 0),
    "tienda": (1, 0),
    "commercial_local": (1, 0),
    "pharmacy": (1, 0),
    "supermarket": (1, 0),
    "escuela": (2, 0),
    "educacion": (2, 0),
    "school": (2, 0),
    "templo": (3, 0),
    "iglesia": (3, 0),
    "catedral": (3, 0),
    "church": (3, 0),
    "hospital": (4, 0),
    "salud": (4, 0),
    "oficina": (5, 0),
    "gobierno": (5, 0),
    "government": (5, 0),
    "industrial": (6, 0),
    "almacen": (6, 0),
    "bodega": (6, 0),
    "asfalto": (7, 0),
    "banqueta": (0, 1),
    "curb_red": (1, 1),
    "curb_yellow": (2, 1),
    "pasto": (3, 1),
    "cortina_metal": (4, 1),
    "metal_shutter": (4, 1),
    SLOT_METAL_SHUTTER: (4, 1),
    "ladrillo": (5, 1),
    "brick": (5, 1),
    SLOT_BRICK: (5, 1),
    "madera_arbol": (6, 1),
    "proteccion_ventana": (7, 1),
    "window_grille": (7, 1),
    "reja": (7, 1),
    SLOT_WINDOW_GRILLE: (7, 1),
    "malla_ciclonica": (0, 2),
    "barandal": (1, 2),
    "stop_sign": (2, 2),
    "alto": (2, 2),
    "hidrante": (3, 2),
    "cauce_arroyo": (4, 2),
    "falla_geologica": (5, 2),
    "fachada_cochera": (6, 2),
    "cantera_rosa": (7, 2),
}

def get_atlas_uvs(slot_or_cat):
    """
    Retorna las coordenadas UV (uv0, uv1, uv2, uv3) en el atlas 8x8 para
    el slot entero (15, 16, 18), tupla (col, row) o string de categoría.
    uv0: inferior-izq (u0, v1)
    uv1: inferior-der (u1, v1)
    uv2: superior-der (u1, v0)
    uv3: superior-izq (u0, v0)
    """
    if isinstance(slot_or_cat, tuple):
        col, row = slot_or_cat
    elif isinstance(slot_or_cat, int):
        col, row = ATLAS_SLOT_TILES.get(slot_or_cat, CATEGORY_TILES.get(slot_or_cat, (0, 0)))
    else:
        col, row = CATEGORY_TILES.get(str(slot_or_cat).lower(), (0, 0))
    u0 = col * 0.125
    u1 = u0 + 0.125
    v0 = row * 0.125
    v1 = v0 + 0.125
    return (u0, v1), (u1, v1), (u1, v0), (u0, v0)

def make_facade_uvs(p0, p1, height, category="residencial"):
    dx = p1[0] - p0[0]; dz = p1[1] - p0[1]; length = math.hypot(dx, dz)
    u1 = max(0.5, length / 4.0); v1 = max(0.5, height / 3.0)
    if isinstance(category, int):
        col, row = ATLAS_SLOT_TILES.get(category, (0, 0))
    else:
        col, row = CATEGORY_TILES.get(str(category).lower(), (0, 0))
    u0_tile = col * 0.125
    v0_tile = row * 0.125
    uv0 = (u0_tile, v0_tile)
    uv1 = (u0_tile + (u1 % 1.0) * 0.125, v0_tile)
    uv2 = (u0_tile + (u1 % 1.0) * 0.125, v0_tile + (v1 % 1.0) * 0.125)
    uv3 = (u0_tile, v0_tile + (v1 % 1.0) * 0.125)
    return uv0, uv1, uv2, uv3

def make_icosahedron(cx, cy, cz, radius, color=(0.15, 0.55, 0.20, 1.0)):
    # 12 vértices de un icosaedro regular
    t = (1.0 + math.sqrt(5.0)) / 2.0
    v_raw = [
        (-1,  t,  0), ( 1,  t,  0), (-1, -t,  0), ( 1, -t,  0),
        ( 0, -1,  t), ( 0,  1,  t), ( 0, -1, -t), ( 0,  1, -t),
        ( t,  0, -1), ( t,  0,  1), (-t,  0, -1), (-t,  0,  1)
    ]
    # Normalizar y escalar por radius
    verts_pos = []
    for x, y, z in v_raw:
        length = math.hypot(x, math.hypot(y, z))
        verts_pos.append((cx + (x/length)*radius, cy + (y/length)*radius, cz + (z/length)*radius))
    
    # 20 caras triangulares del icosaedro
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)
    ]
    
    result = []
    for i0, i1, i2 in faces:
        p0, p1, p2 = verts_pos[i0], verts_pos[i1], verts_pos[i2]
        # Calcular normal de la cara
        v0 = (p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2])
        v1 = (p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2])
        nx = v0[1]*v1[2] - v0[2]*v1[1]
        ny = v0[2]*v1[0] - v0[0]*v1[2]
        nz = v0[0]*v1[1] - v0[1]*v1[0]
        nlen = math.hypot(nx, math.hypot(ny, nz)) or 1.0
        norm = (nx/nlen, ny/nlen, nz/nlen)
        
        result.append((p0, norm, (0,0), color, 0.0))
        result.append((p1, norm, (0,0), color, 0.0))
        result.append((p2, norm, (0,0), color, 0.0))
    return result

def make_shadow_disc(cx, gy, cz, radius, opacity=0.45):
    # Disco de sombra proyectada en el suelo bajo el árbol
    verts = []
    norm = (0.0, 1.0, 0.0)
    shadow_col = (0.05, 0.08, 0.05, 0.6)  # matID 0.6
    y = gy + 0.02
    segments = 8
    for s in range(segments):
        a0 = s * 2.0 * math.pi / segments
        a1 = (s + 1) * 2.0 * math.pi / segments
        p0 = (cx, y, cz)
        p1 = (cx + radius * math.cos(a0), y, cz + radius * math.sin(a0))
        p2 = (cx + radius * math.cos(a1), y, cz + radius * math.sin(a1))
        verts.append((p0, norm, (0,0), shadow_col, 0.0))
        verts.append((p1, norm, (0,0), shadow_col, 0.0))
        verts.append((p2, norm, (0,0), shadow_col, 0.0))
    return verts

def make_tree_3d(cx, gy, cz, radius=2.2, species=0, debug_beacon=False):
    verts = []
    # 1. Sombra proyectada en el suelo bajo el árbol
    verts.extend(make_shadow_disc(cx, gy, cz, radius=radius * 1.25))

    # 2. Tronco cilíndrico
    trunk_h = 3.5 + random.random() * 1.2
    trunk_r = 0.28 + random.random() * 0.06
    trunk_col = (0.28 + random.uniform(-0.04, 0.04), 0.18 + random.uniform(-0.03, 0.03), 0.11, 0.7) # matID 0.7
    verts.extend(make_cylinder(cx, gy, cz, trunk_r, trunk_h, segments=6, color=trunk_col, uv_tile=(6, 1)))
    
    crown_center_y = gy + trunk_h + radius * 0.75

    # 3. Variación de Especies (Fresno, Jacaranda verde/púrpura, Encino, Pirul, Olivo)
    # Paletas de color con ligera variación aleatoria por cada árbol
    var_r = random.uniform(-0.03, 0.03)
    var_g = random.uniform(-0.04, 0.04)
    var_b = random.uniform(-0.03, 0.03)
    
    sp_type = species % 4
    if sp_type == 0:  # Fresno / Árbol templado (verde brillante natural)
        base_leaf = (0.16 + var_r, 0.54 + var_g, 0.18 + var_b, 0.8) # matID 0.8
    elif sp_type == 1:  # Encino / Árbol frondoso oscuro (verde bosque)
        base_leaf = (0.10 + var_r, 0.42 + var_g, 0.15 + var_b, 0.8)
    elif sp_type == 2:  # Pirul / Olivo (verde oliva/calidez mexicana)
        base_leaf = (0.28 + var_r, 0.48 + var_g, 0.16 + var_b, 0.8)
    else:  # Jacaranda florecida (púrpura/violeta característico de región)
        base_leaf = (0.42 + var_r, 0.22 + var_g, 0.58 + var_b, 0.8)

    # 4. Copa Icosaedro Low-Poly con sombreado de follaje (capas superior e inferior)
    top_leaf = (base_leaf[0] * 1.15, base_leaf[1] * 1.12, base_leaf[2] * 1.10, 0.8)
    bottom_leaf = (base_leaf[0] * 0.75, base_leaf[1] * 0.75, base_leaf[2] * 0.75, 0.8)

    # Copa base
    verts.extend(make_icosahedron(cx, crown_center_y, cz, radius=radius, color=base_leaf))
    # Copa superior soleada
    verts.extend(make_icosahedron(cx, crown_center_y + radius * 0.45, cz, radius=radius * 0.72, color=top_leaf))
    # Base inferior en sombra propia del follaje
    verts.extend(make_icosahedron(cx, crown_center_y - radius * 0.35, cz, radius=radius * 0.65, color=bottom_leaf))

    return verts

def make_grass_patch(cx,gy,cz,size=2.0):
    norm=(0.0,1.0,0.0)
    col=(0.24,0.55,0.24,0.8) # matID 0.8
    h=size*0.5
    q0=(cx-h,gy+0.01,cz-h); q1=(cx+h,gy+0.01,cz-h); q2=(cx+h,gy+0.01,cz+h); q3=(cx-h,gy+0.01,cz+h)
    return [(q0,norm,(0,0),col,0.0),(q1,norm,(0,0),col,0.0),(q2,norm,(0,0),col,0.0),(q0,norm,(0,0),col,0.0),(q2,norm,(0,0),col,0.0),(q3,norm,(0,0),col,0.0)]

def make_traffic_signal_3d(sig_id,inter_id,phase_group,x,ground_y,z,dir_angle=0.0,street_name=""):
    verts=[]; metal_color=(0.2,0.22,0.24,0.95); housing_color=(0.12,0.12,0.13,0.95) # matID 0.95
    post_height=5.2; verts.extend(make_cylinder(x,ground_y,z,0.09,post_height,segments=6,color=metal_color))
    arm_length=3.2; ca=math.cos(dir_angle); sa=math.sin(dir_angle)
    head_x=x+arm_length*ca; head_z=z+arm_length*sa; head_y=ground_y+post_height-0.2
    
    # Cabeza del semáforo (luces)
    verts.extend(make_box(head_x,head_y,head_z,0.35,0.95,0.28,color=housing_color))
    lens_info={}; lens_configs=[("red",head_y+0.30,(1.0,0.1,0.1,0.95)),("amber",head_y,(1.0,0.75,0.0,0.95)),("green",head_y-0.30,(0.0,1.0,0.4,0.95))]
    for name,ly,col in lens_configs:
        start_idx=len(verts); rad=0.10; norm=(ca,0.0,sa)
        p_front_x=head_x+0.15*ca; p_front_z=head_z+0.15*sa; p_perp_x=-sa*rad; p_perp_z=ca*rad
        q0=(p_front_x-p_perp_x,ly-rad,p_front_z-p_perp_z); q1=(p_front_x+p_perp_x,ly-rad,p_front_z+p_perp_z); q2=(p_front_x+p_perp_x,ly+rad,p_front_z+p_perp_z); q3=(p_front_x-p_perp_x,ly+rad,p_front_z+p_perp_z)
        verts.append((q0,norm,(0,0),col,0.0)); verts.append((q1,norm,(0,0),col,0.0)); verts.append((q2,norm,(0,0),col,0.0))
        verts.append((q0,norm,(0,0),col,0.0)); verts.append((q2,norm,(0,0),col,0.0)); verts.append((q3,norm,(0,0),col,0.0))
        lens_info[name]={"start":start_idx,"count":6}

    # Letrero Verde Vía Superior en el brazo del semáforo
    sign_green = (0.05, 0.48, 0.22, 0.95)
    sign_border = (0.95, 0.95, 0.95, 0.95)
    sign_x = x + (arm_length * 0.55) * ca
    sign_z = z + (arm_length * 0.55) * sa
    sign_y = head_y + 0.45
    # Placa verde
    verts.extend(make_box(sign_x, sign_y, sign_z, 1.4, 0.45, 0.08, color=sign_green))
    # Borde blanco
    verts.extend(make_box(sign_x, sign_y, sign_z, 1.44, 0.49, 0.06, color=sign_border))

    metadata={"id":sig_id,"intersection":inter_id,"phase":phase_group,"x":head_x,"y":head_y,"z":head_z,"dir_angle":round(float(dir_angle),4),"lenses":lens_info,"street_name":street_name}
    return verts,metadata

def make_oriented_box(cx, cy, cz, length, height, thickness, dir_w, norm_n, color=(0.85, 0.78, 0.10, 0.95), emission=0.0):
    """
    Crea una caja 3D orientada a lo largo del vector de dirección de la pared (dir_w)
    y con su cara exterior orientada según la normal de la fachada (norm_n).
    """
    wx, wz = dir_w
    nx, nz = norm_n
    hl = length * 0.5
    hh = height * 0.5
    ht = thickness * 0.5

    corners_2d = [
        (-hl * wx + ht * nx, -hl * wz + ht * nz),
        ( hl * wx + ht * nx,  hl * wz + ht * nz),
        ( hl * wx - ht * nx,  hl * wz - ht * nz),
        (-hl * wx - ht * nx, -hl * wz - ht * nz)
    ]
    y_bot = cy - hh
    y_top = cy + hh

    p0_bot = (cx + corners_2d[0][0], y_bot, cz + corners_2d[0][1])
    p1_bot = (cx + corners_2d[1][0], y_bot, cz + corners_2d[1][1])
    p2_bot = (cx + corners_2d[2][0], y_bot, cz + corners_2d[2][1])
    p3_bot = (cx + corners_2d[3][0], y_bot, cz + corners_2d[3][1])

    p0_top = (cx + corners_2d[0][0], y_top, cz + corners_2d[0][1])
    p1_top = (cx + corners_2d[1][0], y_top, cz + corners_2d[1][1])
    p2_top = (cx + corners_2d[2][0], y_top, cz + corners_2d[2][1])
    p3_top = (cx + corners_2d[3][0], y_top, cz + corners_2d[3][1])

    faces = [
        # Frontal (hacia la calle): normal = norm_n
        ([p0_bot, p1_bot, p1_top, p0_top], (nx, 0.0, nz)),
        # Trasero (hacia el interior de la pared): normal = -norm_n
        ([p2_bot, p3_bot, p3_top, p2_top], (-nx, 0.0, -nz)),
        # Lateral derecho (+w): normal = dir_w
        ([p1_bot, p2_bot, p2_top, p1_top], (wx, 0.0, wz)),
        # Lateral izquierdo (-w): normal = -dir_w
        ([p3_bot, p0_bot, p0_top, p3_top], (-wx, 0.0, -wz)),
        # Arriba: normal = (0, 1, 0)
        ([p0_top, p1_top, p2_top, p3_top], (0.0, 1.0, 0.0)),
        # Abajo: normal = (0, -1, 0)
        ([p3_bot, p2_bot, p1_bot, p0_bot], (0.0, -1.0, 0.0))
    ]

    verts = []
    for quad, norm in faces:
        verts.append((quad[0], norm, (0, 0), color, emission))
        verts.append((quad[1], norm, (0, 0), color, emission))
        verts.append((quad[2], norm, (0, 0), color, emission))
        verts.append((quad[0], norm, (0, 0), color, emission))
        verts.append((quad[2], norm, (0, 0), color, emission))
        verts.append((quad[3], norm, (0, 0), color, emission))
    return verts

# --- DICCIONARIO DE TRAZOS VECTORIALES 3D PARA NOMENCLATURA VIAL URBANA ---
STREET_FONT = {
    'A': [(0.05, 0.0, 0.23, 0.85), (0.77, 0.0, 0.95, 0.85), (0.05, 0.82, 0.95, 1.0), (0.05, 0.42, 0.95, 0.58)],
    'B': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.82, 0.80, 1.0), (0.05, 0.42, 0.80, 0.58), (0.05, 0.0, 0.80, 0.18), (0.77, 0.50, 0.95, 0.90), (0.77, 0.10, 0.95, 0.50)],
    'C': [(0.05, 0.10, 0.23, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18)],
    'D': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.82, 0.77, 1.0), (0.05, 0.0, 0.77, 0.18), (0.77, 0.15, 0.95, 0.85)],
    'E': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.82, 0.95, 1.0), (0.05, 0.42, 0.75, 0.58), (0.05, 0.0, 0.95, 0.18)],
    'F': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.82, 0.95, 1.0), (0.05, 0.42, 0.75, 0.58)],
    'G': [(0.05, 0.10, 0.23, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18), (0.77, 0.0, 0.95, 0.50), (0.45, 0.35, 0.95, 0.50)],
    'H': [(0.05, 0.0, 0.23, 1.0), (0.77, 0.0, 0.95, 1.0), (0.05, 0.42, 0.95, 0.58)],
    'I': [(0.41, 0.0, 0.59, 1.0), (0.15, 0.82, 0.85, 1.0), (0.15, 0.0, 0.85, 0.18)],
    'J': [(0.70, 0.15, 0.88, 1.0), (0.30, 0.82, 0.95, 1.0), (0.10, 0.0, 0.80, 0.18), (0.05, 0.10, 0.23, 0.45)],
    'K': [(0.05, 0.0, 0.23, 1.0), (0.23, 0.40, 0.85, 0.95), (0.35, 0.05, 0.95, 0.55)],
    'L': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.0, 0.95, 0.18)],
    'M': [(0.05, 0.0, 0.23, 1.0), (0.77, 0.0, 0.95, 1.0), (0.20, 0.45, 0.45, 0.95), (0.55, 0.45, 0.80, 0.95), (0.41, 0.25, 0.59, 0.60)],
    'N': [(0.05, 0.0, 0.23, 1.0), (0.77, 0.0, 0.95, 1.0), (0.23, 0.30, 0.77, 0.70)],
    'O': [(0.05, 0.10, 0.23, 0.90), (0.77, 0.10, 0.95, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18)],
    'P': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.82, 0.85, 1.0), (0.05, 0.45, 0.85, 0.62), (0.77, 0.52, 0.95, 0.90)],
    'Q': [(0.05, 0.10, 0.23, 0.90), (0.77, 0.10, 0.95, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18), (0.55, 0.0, 0.95, 0.30)],
    'R': [(0.05, 0.0, 0.23, 1.0), (0.05, 0.82, 0.85, 1.0), (0.05, 0.48, 0.85, 0.65), (0.77, 0.55, 0.95, 0.90), (0.48, 0.0, 0.88, 0.50)],
    'S': [(0.05, 0.82, 0.95, 1.0), (0.05, 0.50, 0.23, 0.90), (0.05, 0.42, 0.95, 0.58), (0.77, 0.10, 0.95, 0.50), (0.05, 0.0, 0.95, 0.18)],
    'T': [(0.41, 0.0, 0.59, 1.0), (0.05, 0.82, 0.95, 1.0)],
    'U': [(0.05, 0.10, 0.23, 1.0), (0.77, 0.10, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18)],
    'V': [(0.05, 0.30, 0.25, 1.0), (0.75, 0.30, 0.95, 1.0), (0.25, 0.0, 0.75, 0.35)],
    'W': [(0.05, 0.0, 0.23, 1.0), (0.77, 0.0, 0.95, 1.0), (0.41, 0.0, 0.59, 0.70), (0.15, 0.0, 0.85, 0.20)],
    'X': [(0.05, 0.55, 0.45, 0.95), (0.55, 0.05, 0.95, 0.45), (0.55, 0.55, 0.95, 0.95), (0.05, 0.05, 0.45, 0.45), (0.35, 0.35, 0.65, 0.65)],
    'Y': [(0.41, 0.0, 0.59, 0.55), (0.05, 0.55, 0.45, 1.0), (0.55, 0.55, 0.95, 1.0)],
    'Z': [(0.05, 0.82, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18), (0.20, 0.18, 0.80, 0.82)],
    '0': [(0.05, 0.10, 0.23, 0.90), (0.77, 0.10, 0.95, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.0, 0.95, 0.18), (0.30, 0.30, 0.70, 0.70)],
    '1': [(0.41, 0.0, 0.65, 1.0), (0.18, 0.65, 0.48, 0.90), (0.15, 0.0, 0.85, 0.18)],
    '2': [(0.05, 0.82, 0.95, 1.0), (0.77, 0.50, 0.95, 0.90), (0.05, 0.42, 0.95, 0.58), (0.05, 0.10, 0.23, 0.50), (0.05, 0.0, 0.95, 0.18)],
    '3': [(0.05, 0.82, 0.95, 1.0), (0.77, 0.50, 0.95, 0.90), (0.20, 0.42, 0.80, 0.58), (0.77, 0.10, 0.95, 0.50), (0.05, 0.0, 0.95, 0.18)],
    '4': [(0.05, 0.40, 0.23, 1.0), (0.05, 0.35, 0.95, 0.52), (0.62, 0.0, 0.80, 1.0)],
    '5': [(0.05, 0.82, 0.95, 1.0), (0.05, 0.48, 0.23, 0.90), (0.05, 0.42, 0.95, 0.58), (0.77, 0.10, 0.95, 0.50), (0.05, 0.0, 0.95, 0.18)],
    '6': [(0.05, 0.10, 0.23, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.42, 0.95, 0.58), (0.77, 0.10, 0.95, 0.50), (0.05, 0.0, 0.95, 0.18)],
    '7': [(0.05, 0.82, 0.95, 1.0), (0.55, 0.0, 0.85, 0.85)],
    '8': [(0.05, 0.10, 0.23, 0.90), (0.77, 0.10, 0.95, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.42, 0.95, 0.58), (0.05, 0.0, 0.95, 0.18)],
    '9': [(0.05, 0.50, 0.23, 0.90), (0.77, 0.10, 0.95, 0.90), (0.05, 0.82, 0.95, 1.0), (0.05, 0.42, 0.95, 0.58), (0.05, 0.0, 0.95, 0.18)],
    '.': [(0.35, 0.0, 0.65, 0.25)],
    ',': [(0.35, -0.15, 0.65, 0.20)],
    '-': [(0.15, 0.42, 0.85, 0.58)],
    '/': [(0.15, 0.0, 0.45, 0.50), (0.45, 0.50, 0.85, 1.0)],
    '>': [(0.05, 0.42, 0.95, 0.58), (0.55, 0.58, 0.85, 0.85), (0.55, 0.15, 0.85, 0.42)],
    '<': [(0.05, 0.42, 0.95, 0.58), (0.15, 0.58, 0.45, 0.85), (0.15, 0.15, 0.45, 0.42)],
    ' ': []
}

def format_street_name_for_sign(name):
    if not name:
        return "CALLE"
    s = str(name).strip().strip('"').strip("'")
    s = s.replace("Avenida ", "AV. ").replace("avenida ", "AV. ")
    s = s.replace("Calle ", "C. ").replace("calle ", "C. ")
    s = s.replace("Boulevard ", "BLVD. ").replace("boulevard ", "BLVD. ")
    s = s.replace("Andador ", "AND. ").replace("andador ", "AND. ")
    s = s.replace("Calzada ", "CALZ. ").replace("calzada ", "CALZ. ")
    s = s.replace("Privada ", "PRIV. ").replace("privada ", "PRIV. ")
    s = s.replace("Prolongación ", "PROL. ").replace("prolongacion ", "PROL. ")
    s = s.replace("Oriente", "OTE.").replace("oriente", "OTE.")
    s = s.replace("Poniente", "PTE.").replace("poniente", "PTE.")
    s = s.replace("Norte", "NTE.").replace("norte", "NTE.")
    s = s.replace("Sur", "SUR").replace("sur", "SUR")
    s = s.upper()
    accents = {'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U', 'Ñ': 'N', '"': '', "'": ''}
    for a, b in accents.items():
        s = s.replace(a, b)
    s = " ".join(s.split())
    if len(s) > 26:
        s = s[:26]
    return s

def render_text_quads_3d(text, center_pos, dir_w, norm_n, max_w, base_w, base_h, base_sp, color=(0.04, 0.04, 0.04, 0.95)):
    verts = []
    text = text.upper().strip()
    n = len(text)
    if n == 0: return verts

    total_w = n * base_w + (n - 1) * base_sp
    scale = 1.0
    if total_w > max_w:
        scale = max_w / total_w
    char_w = base_w * scale
    char_h = base_h * scale
    sp = base_sp * scale
    actual_total_w = n * char_w + (n - 1) * sp

    wx, wz = dir_w
    nx, nz = norm_n
    norm_3d = (nx, 0.0, nz)
    start_u = -actual_total_w * 0.5

    def get_pos(u, v):
        px = center_pos[0] + u * wx + 0.003 * nx
        py = center_pos[1] + v
        pz = center_pos[2] + u * wz + 0.003 * nz
        return (px, py, pz)

    curr_u = start_u
    for ch in text:
        strokes = STREET_FONT.get(ch, STREET_FONT.get(' ', []))
        for x0, y0, x1, y1 in strokes:
            u0 = curr_u + x0 * char_w
            u1 = curr_u + x1 * char_w
            v0 = (y0 - 0.5) * char_h
            v1 = (y1 - 0.5) * char_h
            q0 = get_pos(u0, v0); q1 = get_pos(u1, v0); q2 = get_pos(u1, v1); q3 = get_pos(u0, v1)
            verts.append((q0, norm_3d, (0, 0), color, 0.0))
            verts.append((q1, norm_3d, (0, 0), color, 0.0))
            verts.append((q2, norm_3d, (0, 0), color, 0.0))
            verts.append((q0, norm_3d, (0, 0), color, 0.0))
            verts.append((q2, norm_3d, (0, 0), color, 0.0))
            verts.append((q3, norm_3d, (0, 0), color, 0.0))
        curr_u += char_w + sp
    return verts

def make_facade_street_plate_3d(px, py, pz, length, dir_w, norm_n,
                                street_name="CALLE", cp="20000",
                                delegacion="DEL. CENTRO", colonia="COL. CENTRO",
                                arrow_dir=">"):
    """
    Placa de nomenclatura estilo Aguascalientes con información urbana real:
    - Marco y borde perimetral negro (0.04, 0.04, 0.04) pegado a la pared
    - Placa amarilla frontal (0.92, 0.82, 0.10)
    - Marco interior decorativo negro
    - Encabezado: Delegación Municipal + Colonia
    - Centro: Nombre real de la calle + flecha vial de sentido
    - Pie: Código Postal (C.P.) + Estado
    """
    sign_yellow = (0.92, 0.82, 0.10, 0.95)
    sign_border = (0.04, 0.04, 0.04, 0.95)
    plate_h = 0.28
    plate_th = 0.02

    verts = []
    # 1. Marco negro posterior pegado a la fachada
    verts.extend(make_oriented_box(px, py, pz, length + 0.04, plate_h + 0.04, 0.015, dir_w, norm_n, color=sign_border))

    # 2. Cara amarilla frontal ligeramente salida
    fx = px + 0.012 * norm_n[0]
    fz = pz + 0.012 * norm_n[1]
    verts.extend(make_oriented_box(fx, py, fz, length, plate_h, plate_th, dir_w, norm_n, color=sign_yellow))

    # Posición frontal de superficie para textos y ribetes
    front_pos = (fx + 0.011 * norm_n[0], py, fz + 0.011 * norm_n[1])
    wx, wz = dir_w
    nx, nz = norm_n
    norm_3d = (nx, 0.0, nz)

    # 3. Ribete interior negro perimetral
    in_w = length - 0.035
    in_h = plate_h - 0.035
    line_t = 0.003
    hw_in = in_w * 0.5
    hh_in = in_h * 0.5

    def get_quad_pts(u0, v0, u1, v1):
        def p(u, v):
            return (front_pos[0] + u * wx + 0.002 * nx, front_pos[1] + v, front_pos[2] + u * wz + 0.002 * nz)
        return p(u0, v0), p(u1, v0), p(u1, v1), p(u0, v1)

    for bar in [
        (-hw_in, hh_in - line_t, hw_in, hh_in),       # Barra superior
        (-hw_in, -hh_in, hw_in, -hh_in + line_t),      # Barra inferior
        (-hw_in, -hh_in, -hw_in + line_t, hh_in),      # Barra izquierda
        (hw_in - line_t, -hh_in, hw_in, hh_in)        # Barra derecha
    ]:
        q0, q1, q2, q3 = get_quad_pts(bar[0], bar[1], bar[2], bar[3])
        verts.append((q0, norm_3d, (0, 0), sign_border, 0.0))
        verts.append((q1, norm_3d, (0, 0), sign_border, 0.0))
        verts.append((q2, norm_3d, (0, 0), sign_border, 0.0))
        verts.append((q0, norm_3d, (0, 0), sign_border, 0.0))
        verts.append((q2, norm_3d, (0, 0), sign_border, 0.0))
        verts.append((q3, norm_3d, (0, 0), sign_border, 0.0))

    # 4. Línea Superior: Delegación Municipal y Colonia
    clean_del = delegacion.upper()
    clean_col = colonia.upper() if colonia else ""
    hdr_str = f"{clean_del} - {clean_col}" if clean_col else clean_del
    v_hdr = render_text_quads_3d(hdr_str, (front_pos[0], py + 0.078, front_pos[2]),
                                 dir_w, norm_n, max_w=length - 0.06,
                                 base_w=0.015, base_h=0.024, base_sp=0.005, color=sign_border)
    verts.extend(v_hdr)

    # 5. Línea Central: Flecha de sentido vial + Nombre de la calle
    clean_st = format_street_name_for_sign(street_name)
    main_str = f"{arrow_dir}  {clean_st}"
    v_main = render_text_quads_3d(main_str, (front_pos[0], py - 0.008, front_pos[2]),
                                  dir_w, norm_n, max_w=length - 0.06,
                                  base_w=0.032, base_h=0.054, base_sp=0.009, color=sign_border)
    verts.extend(v_main)

    # 6. Línea Inferior: Código Postal y Estado
    cp_str = f"C.P. {cp} - AGS."
    v_cp = render_text_quads_3d(cp_str, (front_pos[0], py - 0.086, front_pos[2]),
                                dir_w, norm_n, max_w=length - 0.06,
                                base_w=0.015, base_h=0.022, base_sp=0.005, color=sign_border)
    verts.extend(v_cp)

    return verts

def make_corner_street_signs_on_facade(corner_x, corner_z, ground_y,
                                       w1, n1, w2, n2,
                                       name1="CALLE", name2="",
                                       bldg_height=5.0,
                                       cp="20000", delegacion="DEL. CENTRO", colonia="COL. CENTRO"):
    """
    Placas de nomenclatura de esquina estilo Aguascalientes montadas directamente
    sobre las paredes de la esquina de la casa/edificio con textos reales completos.
    w1, n1: dirección y normal exterior de la pared 1
    w2, n2: dirección y normal exterior de la pared 2
    """
    verts = []
    mount_h = min(2.40, max(1.80, bldg_height - 0.40))
    top_y = ground_y + mount_h

    # 1. Placa en pared 1
    clean1 = format_street_name_for_sign(name1)
    name1_len = len(clean1)
    sign_w1 = max(0.85, min(1.45, 0.055 * name1_len + 0.35))
    offset1 = 0.50 + sign_w1 * 0.5
    p1x = corner_x + offset1 * w1[0] + 0.025 * n1[0]
    p1z = corner_z + offset1 * w1[1] + 0.025 * n1[1]
    verts.extend(make_facade_street_plate_3d(p1x, top_y, p1z, sign_w1, w1, n1,
                                            street_name=name1, cp=cp,
                                            delegacion=delegacion, colonia=colonia, arrow_dir=">"))

    # 2. Placa en pared 2 (si la pared 2 es válida y tiene longitud)
    if w2 and n2 and (abs(w2[0]) > 0.01 or abs(w2[1]) > 0.01):
        actual_name2 = name2 if name2 else name1
        clean2 = format_street_name_for_sign(actual_name2)
        name2_len = len(clean2)
        sign_w2 = max(0.85, min(1.45, 0.055 * name2_len + 0.35))
        offset2 = 0.50 + sign_w2 * 0.5
        p2x = corner_x + offset2 * w2[0] + 0.025 * n2[0]
        p2z = corner_z + offset2 * w2[1] + 0.025 * n2[1]
        verts.extend(make_facade_street_plate_3d(p2x, top_y, p2z, sign_w2, w2, n2,
                                                street_name=actual_name2, cp=cp,
                                                delegacion=delegacion, colonia=colonia, arrow_dir="<"))

    return verts

def make_street_corner_sign_3d(cx, ground_y, cz, street_name="CALLE", dir_angle=0.0,
                               cp="20000", delegacion="DEL. CENTRO", colonia="COL. CENTRO"):
    """Fallback compatible: coloca placas orientadas según ángulo."""
    ca = math.cos(dir_angle); sa = math.sin(dir_angle)
    w1 = (ca, sa); n1 = (-sa, ca)
    w2 = (-sa, ca); n2 = (-ca, -sa)
    return make_corner_street_signs_on_facade(cx, cz, ground_y, w1, n1, w2, n2,
                                              name1=street_name, bldg_height=4.0,
                                              cp=cp, delegacion=delegacion, colonia=colonia)

def make_sidewalk_3d(sp0_x, sp0_z, sp1_x, sp1_z, y0, y1, half_w,
                     norm0, norm1=None,
                     sidewalk_w=1.60, curb_h=0.15,
                     curb_type="auto",
                     gen_right=True, gen_left=True,
                     cap_start_r=False, cap_end_r=False,
                     cap_start_l=False, cap_end_l=False,
                     fwd_dir=None,
                     is_corner_r=False, is_corner_l=False):
    """
    Banqueta peatonal continua 3D elevada 0.15m con guarnición vertical,
    muros de cierre en extremos (end caps) y normales continuas con bisectriz (miter).
    curb_type: 'red' (No estacionarse / Esquinas), 'yellow' (Carga/Comercial), 'gray' (Estándar), 'auto'
    """
    verts = []
    norm_up = (0.0, 1.0, 0.0)
    sidewalk_col = (0.58, 0.56, 0.54, 0.95) # Concreto natural peatonal (tono realista, no sobreexpuesto)
    col_red = (0.85, 0.14, 0.12, 0.95)      # Rojo: Prohibido estacionar / esquinas
    col_yellow = (0.90, 0.80, 0.10, 0.95)   # Amarillo: Carga y descarga
    col_gray = (0.52, 0.50, 0.48, 0.95)     # Gris: Guarnición de concreto natural

    # Soporte compatible para llamadas heredadas con escalares px_norm, pz_norm
    if isinstance(norm0, (int, float)):
        nx0 = float(norm0)
        nz0 = float(norm1) if (norm1 is not None and isinstance(norm1, (int, float))) else 0.0
        nx1, nz1 = nx0, nz0
    else:
        nx0, nz0 = norm0
        if norm1 is not None and not isinstance(norm1, (int, float)):
            nx1, nz1 = norm1
        else:
            nx1, nz1 = nx0, nz0

    # Vector unitario hacia adelante a lo largo de la calzada
    if fwd_dir is not None:
        fdx, fdz = fwd_dir
    else:
        dfx = sp1_x - sp0_x
        dfz = sp1_z - sp0_z
        lf = math.hypot(dfx, dfz)
        if lf > 1e-4:
            fdx, fdz = dfx / lf, dfz / lf
        else:
            fdx, fdz = 1.0, 0.0

    def get_curb_color(is_corner):
        if curb_type == "red":
            return col_red
        elif curb_type == "yellow":
            return col_yellow
        elif curb_type == "gray":
            return col_gray
        else:
            return col_red if is_corner else col_gray

    curb_col_r = get_curb_color(is_corner_r or cap_start_r or cap_end_r)
    curb_col_l = get_curb_color(is_corner_l or cap_start_l or cap_end_l)

    if gen_right:
        # Vértices lado derecho
        sw_r0_street = (sp0_x + half_w * nx0, y0, sp0_z + half_w * nz0)
        sw_r0_inner  = (sp0_x + half_w * nx0, y0 + curb_h, sp0_z + half_w * nz0)
        sw_r0_outer  = (sp0_x + (half_w + sidewalk_w) * nx0, y0 + curb_h, sp0_z + (half_w + sidewalk_w) * nz0)
        sw_r0_bottom = (sp0_x + (half_w + sidewalk_w) * nx0, y0, sp0_z + (half_w + sidewalk_w) * nz0)

        sw_r1_street = (sp1_x + half_w * nx1, y1, sp1_z + half_w * nz1)
        sw_r1_inner  = (sp1_x + half_w * nx1, y1 + curb_h, sp1_z + half_w * nz1)
        sw_r1_outer  = (sp1_x + (half_w + sidewalk_w) * nx1, y1 + curb_h, sp1_z + (half_w + sidewalk_w) * nz1)
        sw_r1_bottom = (sp1_x + (half_w + sidewalk_w) * nx1, y1, sp1_z + (half_w + sidewalk_w) * nz1)

        # 1. Superficie plana de banqueta derecha (walkable top)
        verts.append((sw_r0_inner, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r0_outer, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r1_outer, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r0_inner, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r1_outer, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r1_inner, norm_up, (0,0), sidewalk_col, 0.0))

        # 2. Cara vertical de guarnición derecha (hacia la calle, dirección -norm)
        avg_nx_r = -0.5 * (nx0 + nx1)
        avg_nz_r = -0.5 * (nz0 + nz1)
        len_nr = math.hypot(avg_nx_r, avg_nz_r)
        if len_nr > 1e-4:
            norm_curb_r = (avg_nx_r / len_nr, 0.0, avg_nz_r / len_nr)
        else:
            norm_curb_r = (-nx0, 0.0, -nz0)

        verts.append((sw_r0_street, norm_curb_r, (0,0), curb_col_r, 0.0))
        verts.append((sw_r0_inner,  norm_curb_r, (0,0), curb_col_r, 0.0))
        verts.append((sw_r1_inner,  norm_curb_r, (0,0), curb_col_r, 0.0))
        verts.append((sw_r0_street, norm_curb_r, (0,0), curb_col_r, 0.0))
        verts.append((sw_r1_inner,  norm_curb_r, (0,0), curb_col_r, 0.0))
        verts.append((sw_r1_street, norm_curb_r, (0,0), curb_col_r, 0.0))

        # 3. Muro posterior exterior (hacia predios/fachadas, dirección +norm)
        norm_back_r = (-norm_curb_r[0], 0.0, -norm_curb_r[2])
        verts.append((sw_r0_outer,  norm_back_r, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r0_bottom, norm_back_r, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r1_bottom, norm_back_r, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r0_outer,  norm_back_r, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r1_bottom, norm_back_r, (0,0), sidewalk_col, 0.0))
        verts.append((sw_r1_outer,  norm_back_r, (0,0), sidewalk_col, 0.0))

        # 4. Tapa vertical inicial si inicia banqueta (facing -fwd)
        if cap_start_r:
            norm_cap_start = (-fdx, 0.0, -fdz)
            verts.append((sw_r0_street, norm_cap_start, (0,0), curb_col_r, 0.0))
            verts.append((sw_r0_bottom, norm_cap_start, (0,0), curb_col_r, 0.0))
            verts.append((sw_r0_outer,  norm_cap_start, (0,0), curb_col_r, 0.0))
            verts.append((sw_r0_street, norm_cap_start, (0,0), curb_col_r, 0.0))
            verts.append((sw_r0_outer,  norm_cap_start, (0,0), curb_col_r, 0.0))
            verts.append((sw_r0_inner,  norm_cap_start, (0,0), curb_col_r, 0.0))

        # 5. Tapa vertical final si termina banqueta (facing +fwd)
        if cap_end_r:
            norm_cap_end = (fdx, 0.0, fdz)
            verts.append((sw_r1_street, norm_cap_end, (0,0), curb_col_r, 0.0))
            verts.append((sw_r1_inner,  norm_cap_end, (0,0), curb_col_r, 0.0))
            verts.append((sw_r1_outer,  norm_cap_end, (0,0), curb_col_r, 0.0))
            verts.append((sw_r1_street, norm_cap_end, (0,0), curb_col_r, 0.0))
            verts.append((sw_r1_outer,  norm_cap_end, (0,0), curb_col_r, 0.0))
            verts.append((sw_r1_bottom, norm_cap_end, (0,0), curb_col_r, 0.0))

    if gen_left:
        # Vértices lado izquierdo
        sw_l0_street = (sp0_x - half_w * nx0, y0, sp0_z - half_w * nz0)
        sw_l0_inner  = (sp0_x - half_w * nx0, y0 + curb_h, sp0_z - half_w * nz0)
        sw_l0_outer  = (sp0_x - (half_w + sidewalk_w) * nx0, y0 + curb_h, sp0_z - (half_w + sidewalk_w) * nz0)
        sw_l0_bottom = (sp0_x - (half_w + sidewalk_w) * nx0, y0, sp0_z - (half_w + sidewalk_w) * nz0)

        sw_l1_street = (sp1_x - half_w * nx1, y1, sp1_z - half_w * nz1)
        sw_l1_inner  = (sp1_x - half_w * nx1, y1 + curb_h, sp1_z - half_w * nz1)
        sw_l1_outer  = (sp1_x - (half_w + sidewalk_w) * nx1, y1 + curb_h, sp1_z - (half_w + sidewalk_w) * nz1)
        sw_l1_bottom = (sp1_x - (half_w + sidewalk_w) * nx1, y1, sp1_z - (half_w + sidewalk_w) * nz1)

        # 1. Superficie plana de banqueta izquierda
        verts.append((sw_l0_outer, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l0_inner, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l1_inner, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l0_outer, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l1_inner, norm_up, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l1_outer, norm_up, (0,0), sidewalk_col, 0.0))

        # 2. Cara vertical de guarnición izquierda (hacia la calle, dirección +norm)
        avg_nx_l = 0.5 * (nx0 + nx1)
        avg_nz_l = 0.5 * (nz0 + nz1)
        len_nl = math.hypot(avg_nx_l, avg_nz_l)
        if len_nl > 1e-4:
            norm_curb_l = (avg_nx_l / len_nl, 0.0, avg_nz_l / len_nl)
        else:
            norm_curb_l = (nx0, 0.0, nz0)

        verts.append((sw_l0_inner,  norm_curb_l, (0,0), curb_col_l, 0.0))
        verts.append((sw_l0_street, norm_curb_l, (0,0), curb_col_l, 0.0))
        verts.append((sw_l1_street, norm_curb_l, (0,0), curb_col_l, 0.0))
        verts.append((sw_l0_inner,  norm_curb_l, (0,0), curb_col_l, 0.0))
        verts.append((sw_l1_street, norm_curb_l, (0,0), curb_col_l, 0.0))
        verts.append((sw_l1_inner,  norm_curb_l, (0,0), curb_col_l, 0.0))

        # 3. Muro posterior exterior (hacia predios/fachadas, dirección -norm)
        norm_back_l = (-norm_curb_l[0], 0.0, -norm_curb_l[2])
        verts.append((sw_l0_bottom, norm_back_l, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l0_outer,  norm_back_l, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l1_outer,  norm_back_l, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l0_bottom, norm_back_l, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l1_outer,  norm_back_l, (0,0), sidewalk_col, 0.0))
        verts.append((sw_l1_bottom, norm_back_l, (0,0), sidewalk_col, 0.0))

        # 4. Tapa vertical inicial si inicia banqueta (facing -fwd)
        if cap_start_l:
            norm_cap_start = (-fdx, 0.0, -fdz)
            verts.append((sw_l0_bottom, norm_cap_start, (0,0), curb_col_l, 0.0))
            verts.append((sw_l0_street, norm_cap_start, (0,0), curb_col_l, 0.0))
            verts.append((sw_l0_inner,  norm_cap_start, (0,0), curb_col_l, 0.0))
            verts.append((sw_l0_bottom, norm_cap_start, (0,0), curb_col_l, 0.0))
            verts.append((sw_l0_inner,  norm_cap_start, (0,0), curb_col_l, 0.0))
            verts.append((sw_l0_outer,  norm_cap_start, (0,0), curb_col_l, 0.0))

        # 5. Tapa vertical final si termina banqueta (facing +fwd)
        if cap_end_l:
            norm_cap_end = (fdx, 0.0, fdz)
            verts.append((sw_l1_inner,  norm_cap_end, (0,0), curb_col_l, 0.0))
            verts.append((sw_l1_street, norm_cap_end, (0,0), curb_col_l, 0.0))
            verts.append((sw_l1_bottom, norm_cap_end, (0,0), curb_col_l, 0.0))
            verts.append((sw_l1_inner,  norm_cap_end, (0,0), curb_col_l, 0.0))
            verts.append((sw_l1_bottom, norm_cap_end, (0,0), curb_col_l, 0.0))
            verts.append((sw_l1_outer,  norm_cap_end, (0,0), curb_col_l, 0.0))
    
    return verts

def make_zebra_crossing_3d(cx,ground_y,cz,road_dir_angle,road_width=8.0):
    verts=[]; stripe_w=0.50; stripe_len=3.60; gap=0.50; num_stripes=int(max(3,(road_width-1.0)/(stripe_w+gap)))
    ca=math.cos(road_dir_angle); sa=math.sin(road_dir_angle); px=-sa; pz=ca; y=ground_y+0.02; white_col=(0.95,0.95,0.95,0.95); norm=(0.0,1.0,0.0) # matID 0.95
    total_span=(num_stripes-1)*(stripe_w+gap); start_offset=-total_span*0.5
    for i in range(num_stripes):
        off=start_offset+i*(stripe_w+gap); scx=cx+off*px; scz=cz+off*pz; hw=stripe_w*0.5; hl=stripe_len*0.5
        q0=(scx-hl*ca-hw*px,y,scz-hl*sa-hw*pz); q1=(scx+hl*ca-hw*px,y,scz+hl*sa-hw*pz); q2=(scx+hl*ca+hw*px,y,scz+hl*sa+hw*pz); q3=(scx-hl*ca+hw*px,y,scz-hl*sa+hw*pz)
        verts.append((q0,norm,(0.0,0.0),white_col,0.0)); verts.append((q1,norm,(1.0,0.0),white_col,0.0)); verts.append((q2,norm,(1.0,1.0),white_col,0.0))
        verts.append((q0,norm,(0.0,0.0),white_col,0.0)); verts.append((q2,norm,(1.0,1.0),white_col,0.0)); verts.append((q3,norm,(0.0,1.0),white_col,0.0))
    return verts

def make_building_3d(polygon,height,get_elevation_func,roof_color=(0.85,0.82,0.78),wall_color_override=None,category="residencial",x0_map=0,z0_map=0,x1_map=1,z1_map=1):
    verts=[]; n=len(polygon)
    if n<3: return verts
    ground_heights=[get_elevation_func(p[0],p[1]) for p in polygon]
    base_y=min(ground_heights); roof_y=base_y+height
    roof_indices=triangulate_2d(polygon); norm_up=(0.0,1.0,0.0)
    roof_col_rgba=(roof_color[0]*0.9,roof_color[1]*0.9,roof_color[2]*0.9,0.35)
    for i0,i1,i2 in roof_indices:
        for idx in (i0,i1,i2):
            px,pz=polygon[idx]; u=(px-x0_map)/max(1.0,(x1_map-x0_map)); v=(pz-z0_map)/max(1.0,(z1_map-z0_map))
            verts.append(((px,roof_y,pz),norm_up,(u,v),roof_col_rgba,0.0))

    # Identificación de tipología arquitectónica mexicana
    c_lower = str(category).lower()
    is_rolcar = ("rolcar" in c_lower)
    is_res = any(w in c_lower for w in ("residence", "residencial", "vivienda", "casa"))
    is_com = is_rolcar or any(w in c_lower for w in ("commercial", "comercial", "retail", "tienda", "oxxo", "pharmacy", "supermarket", "local"))
    is_ind = any(w in c_lower for w in ("industrial", "almacen", "bodega"))
    is_sch = any(w in c_lower for w in ("school", "escuela", "educacion"))
    is_chu = any(w in c_lower for w in ("church", "templo", "iglesia", "catedral"))
    if not is_com and not is_ind and not is_sch and not is_chu:
        is_res = True

    if is_rolcar:
        build_rolcar_storefront_geometry(verts, polygon, ground_heights, height, make_cylinder)
        return verts

    is_multi_story = (height > 4.0)
    ground_h = min(3.4, height * 0.45) if is_multi_story else height

    for i in range(n):
        p0=polygon[i]; p1=polygon[(i+1)%n]
        dx=p1[0]-p0[0]; dz=p1[1]-p0[1]; edge_len=math.hypot(dx,dz)
        if edge_len<0.01: continue
        wall_norm=(-dz/edge_len,0.0,dx/edge_len)
        gy0=ground_heights[i]; gy1=ground_heights[(i+1)%n]
        var=(i*37+int(p0[0]))%15/100.0

        bldg_seed = (int(abs(p0[0]) * 13) + int(abs(p0[1]) * 29) + i * 37) % 100

        # Modular bays arquitectónicas: módulos de ~3.5m a 5.0m
        n_bays = max(1, min(4, int(round(edge_len / 4.2))))

        for bi in range(n_bays):
            bay_seed = (bldg_seed + bi * 31) % 100
            bt0 = bi / float(n_bays)
            bt1 = (bi + 1) / float(n_bays)
            b_p0_x = p0[0] + bt0 * dx
            b_p0_z = p0[1] + bt0 * dz
            b_p0_y = gy0 + bt0 * (gy1 - gy0)

            b_p1_x = p0[0] + bt1 * dx
            b_p1_z = p0[1] + bt1 * dz
            b_p1_y = gy0 + bt1 * (gy1 - gy0)

            # Selección de materiales según categoría arquitectónica mexicana
            if is_com:
                # 1. Edificios comerciales: cortinas de metal arrollables en planta baja (SLOT_METAL_SHUTTER)
                if bay_seed < 72:
                    gf_cat = SLOT_METAL_SHUTTER       # Cortina de metal arrollable comercial (Slot 15)
                else:
                    gf_cat = "comercial"             # Vitrina y marquesina comercial
                
                # Plantas superiores comerciales: oficinas, marquesinas o ladrillo
                if bay_seed < 45:
                    uf_cat = "comercial"
                elif bay_seed < 70:
                    uf_cat = "oficina"
                else:
                    uf_cat = SLOT_BRICK              # Variación de ladrillo en planta alta (Slot 16)

            elif is_res:
                # 2. Residencial: protecciones de ventanas en planta baja (SLOT_WINDOW_GRILLE),
                # cocheras, variación de ladrillo (SLOT_BRICK) y cantera rosa.
                if bay_seed < 45:
                    gf_cat = SLOT_WINDOW_GRILLE      # Ventana con protecciones de herrería en planta baja (Slot 18)
                elif bay_seed < 65:
                    gf_cat = "fachada_cochera"       # Portón de cochera moderno
                elif bay_seed < 85:
                    gf_cat = SLOT_BRICK              # Muro de tabique rojo aparente mexicano (Slot 16)
                elif bay_seed < 93:
                    gf_cat = "cantera_rosa"          # Cantera rosa colonial
                else:
                    gf_cat = "residencial"           # Estuco tradicional

                # Plantas superiores residenciales: estuco tradicional sin reja, ladrillo aparente o cantera
                if bay_seed < 55:
                    uf_cat = "residencial"           # Ventanas residenciales superiores sin rejas
                elif bay_seed < 85:
                    uf_cat = SLOT_BRICK              # Variación de tabique rojo en planta alta (Slot 16)
                else:
                    uf_cat = "cantera_rosa"

            elif is_sch:
                # Escuelas mexicanas: tabique rojo recocido predominante
                if bay_seed < 60:
                    gf_cat = SLOT_BRICK
                    uf_cat = SLOT_BRICK
                else:
                    gf_cat = "escuela"
                    uf_cat = "escuela"

            elif is_ind:
                # Industrial: cortinas metálicas de carga pesada, lámina y ladrillo
                if bay_seed < 45:
                    gf_cat = SLOT_METAL_SHUTTER
                    uf_cat = "industrial"
                elif bay_seed < 75:
                    gf_cat = SLOT_BRICK
                    uf_cat = "industrial"
                else:
                    gf_cat = "industrial"
                    uf_cat = "industrial"

            elif is_chu:
                gf_cat = "cantera_rosa" if bay_seed < 55 else "templo"
                uf_cat = gf_cat
            else:
                gf_cat = "residencial"
                uf_cat = "residencial"

            # Coloración base con tintes apropiados según material
            if wall_color_override:
                gf_color = (max(0.1, min(1.0, wall_color_override[0] + var*0.5)),
                            max(0.1, min(1.0, wall_color_override[1] + var*0.5)),
                            max(0.1, min(1.0, wall_color_override[2] + var*0.5)),
                            1.0)
                uf_color = gf_color
            else:
                if gf_cat == SLOT_METAL_SHUTTER:
                    gf_color = (0.90 + var*0.1, 0.92 + var*0.1, 0.95 + var*0.1, 1.0)
                elif gf_cat in (SLOT_BRICK, SLOT_WINDOW_GRILLE):
                    gf_color = (1.0, 1.0, 1.0, 1.0)
                else:
                    gf_color = (0.82 + var, 0.78 + var, 0.70 + var, 1.0)

                if uf_cat in (SLOT_BRICK, SLOT_WINDOW_GRILLE):
                    uf_color = (1.0, 1.0, 1.0, 1.0)
                else:
                    uf_color = (0.82 + var, 0.78 + var, 0.70 + var, 1.0)

            # Geometría de Planta Baja (Ground Floor)
            gf_top_y0 = b_p0_y + ground_h if is_multi_story else roof_y
            gf_top_y1 = b_p1_y + ground_h if is_multi_story else roof_y

            q0 = (b_p0_x, b_p0_y, b_p0_z)
            q1 = (b_p1_x, b_p1_y, b_p1_z)
            q2 = (b_p1_x, gf_top_y1, b_p1_z)
            q3 = (b_p0_x, gf_top_y0, b_p0_z)

            uv0, uv1, uv2, uv3 = get_atlas_uvs(gf_cat)
            verts.append((q0, wall_norm, uv0, gf_color, 0.0))
            verts.append((q1, wall_norm, uv1, gf_color, 0.0))
            verts.append((q2, wall_norm, uv2, gf_color, 0.0))
            verts.append((q0, wall_norm, uv0, gf_color, 0.0))
            verts.append((q2, wall_norm, uv2, gf_color, 0.0))
            verts.append((q3, wall_norm, uv3, gf_color, 0.0))

            # Geometría de Plantas Superiores (Upper Floor) si es multi-piso
            if is_multi_story:
                uq0 = (b_p0_x, gf_top_y0, b_p0_z)
                uq1 = (b_p1_x, gf_top_y1, b_p1_z)
                uq2 = (b_p1_x, roof_y, b_p1_z)
                uq3 = (b_p0_x, roof_y, b_p0_z)

                uuv0, uuv1, uuv2, uuv3 = get_atlas_uvs(uf_cat)
                verts.append((uq0, wall_norm, uuv0, uf_color, 0.0))
                verts.append((uq1, wall_norm, uuv1, uf_color, 0.0))
                verts.append((uq2, wall_norm, uuv2, uf_color, 0.0))
                verts.append((uq0, wall_norm, uuv0, uf_color, 0.0))
                verts.append((uq2, wall_norm, uuv2, uf_color, 0.0))
                verts.append((uq3, wall_norm, uuv3, uf_color, 0.0))

        # Ventanas adicionales nocturnas emisivas y protecciones de ventana inferiores
        if is_res and edge_len > 4.5 and (int(p0[0]*0.7) + i) % 6 == 0:
            # Ventana inferior residencial con protecciones de herrería (SLOT_WINDOW_GRILLE)
            win_w = min(1.3, edge_len * 0.22)
            win_h = 1.1
            win_y = gy0 + 1.45
            off = 0.035
            tan_x = dx / edge_len; tan_z = dz / edge_len
            hw = win_w * 0.5; hh = win_h * 0.5
            mid_x = (p0[0] + p1[0]) * 0.5; mid_z = (p0[1] + p1[1]) * 0.5

            gwq0 = (mid_x - tan_x*hw + wall_norm[0]*off, win_y - hh, mid_z - tan_z*hw + wall_norm[2]*off)
            gwq1 = (mid_x + tan_x*hw + wall_norm[0]*off, win_y - hh, mid_z + tan_z*hw + wall_norm[2]*off)
            gwq2 = (mid_x + tan_x*hw + wall_norm[0]*off, win_y + hh, mid_z + tan_z*hw + wall_norm[2]*off)
            gwq3 = (mid_x - tan_x*hw + wall_norm[0]*off, win_y + hh, mid_z - tan_z*hw + wall_norm[2]*off)
            guv0, guv1, guv2, guv3 = get_atlas_uvs(SLOT_WINDOW_GRILLE)
            grille_col = (1.0, 1.0, 1.0, 1.0)
            verts.append((gwq0, wall_norm, guv0, grille_col, 0.0))
            verts.append((gwq1, wall_norm, guv1, grille_col, 0.0))
            verts.append((gwq2, wall_norm, guv2, grille_col, 0.0))
            verts.append((gwq0, wall_norm, guv0, grille_col, 0.0))
            verts.append((gwq2, wall_norm, guv2, grille_col, 0.0))
            verts.append((gwq3, wall_norm, guv3, grille_col, 0.0))

        if edge_len > 6.0 and (int(p0[0]*0.7) + i) % 9 == 0:
            win_y = gy0 + height * 0.55
            win_w = min(1.2, edge_len * 0.22); win_h = 1.0
            mid_x = (p0[0] + p1[0]) * 0.5; mid_z = (p0[1] + p1[1]) * 0.5
            off = 0.05
            wq0 = (mid_x - win_w*0.5 + wall_norm[0]*off, win_y - win_h*0.5, mid_z + wall_norm[2]*off)
            wq1 = (mid_x + win_w*0.5 + wall_norm[0]*off, win_y - win_h*0.5, mid_z + wall_norm[2]*off)
            wq2 = (mid_x + win_w*0.5 + wall_norm[0]*off, win_y + win_h*0.5, mid_z + wall_norm[2]*off)
            wq3 = (mid_x - win_w*0.5 + wall_norm[0]*off, win_y + win_h*0.5, mid_z + wall_norm[2]*off)
            win_col = (1.0, 0.92, 0.6, 1.0)
            verts.append((wq0, wall_norm, (0, 0), win_col, 0.9))
            verts.append((wq1, wall_norm, (0, 0), win_col, 0.9))
            verts.append((wq2, wall_norm, (0, 0), win_col, 0.9))
            verts.append((wq0, wall_norm, (0, 0), win_col, 0.9))
            verts.append((wq2, wall_norm, (0, 0), win_col, 0.9))
            verts.append((wq3, wall_norm, (0, 0), win_col, 0.9))

    return verts

def make_stop_sign_3d(x, ground_y, z, dir_angle=0.0):
    """
    Señal de ALTO octogonal mexicana oficial (NOM SCT).
    Montada sobre poste tubular de acero galvanizado.
    """
    verts = []
    post_h = 2.20
    post_r = 0.038
    post_col = (0.72, 0.74, 0.78, 0.95)
    verts.extend(make_cylinder(x, ground_y, z, post_r, post_h, segments=6, color=post_col))
    
    sign_w = 0.65
    sign_h = 0.65
    sign_cy = ground_y + post_h - 0.10
    
    ca = math.cos(dir_angle); sa = math.sin(dir_angle)
    norm_fwd = (ca, 0.0, sa)
    norm_back = (-ca, 0.0, -sa)
    side_x = -sa; side_z = ca
    
    hw = sign_w * 0.5; hh = sign_h * 0.5
    u0 = 2.0 * 0.125; u1 = 3.0 * 0.125
    v0 = 2.0 * 0.125; v1 = 3.0 * 0.125
    
    p0 = (x - side_x * hw, sign_cy - hh, z - side_z * hw)
    p1 = (x + side_x * hw, sign_cy - hh, z + side_z * hw)
    p2 = (x + side_x * hw, sign_cy + hh, z + side_z * hw)
    p3 = (x - side_x * hw, sign_cy + hh, z - side_z * hw)
    
    sign_col = (1.0, 1.0, 1.0, 1.0)
    verts.append((p0, norm_fwd, (u0, v1), sign_col, 0.0))
    verts.append((p1, norm_fwd, (u1, v1), sign_col, 0.0))
    verts.append((p2, norm_fwd, (u1, v0), sign_col, 0.0))
    verts.append((p0, norm_fwd, (u0, v1), sign_col, 0.0))
    verts.append((p2, norm_fwd, (u1, v0), sign_col, 0.0))
    verts.append((p3, norm_fwd, (u0, v0), sign_col, 0.0))
    
    back_col = (0.65, 0.67, 0.70, 0.95)
    verts.append((p1, norm_back, (0, 0), back_col, 0.0))
    verts.append((p0, norm_back, (0, 0), back_col, 0.0))
    verts.append((p3, norm_back, (0, 0), back_col, 0.0))
    verts.append((p1, norm_back, (0, 0), back_col, 0.0))
    verts.append((p3, norm_back, (0, 0), back_col, 0.0))
    verts.append((p2, norm_back, (0, 0), back_col, 0.0))
    
    return verts

def make_fire_hydrant_3d(x, ground_y, z):
    """
    Hidrante urbano cilíndrico en fundición de hierro rojo y tapas de latón amarillo.
    """
    verts = []
    base_col = (0.35, 0.36, 0.38, 0.95)
    verts.extend(make_cylinder(x, ground_y, z, radius=0.18, height=0.08, segments=8, color=base_col))
    
    red_col = (0.85, 0.12, 0.12, 0.95)
    barrel_h = 0.58
    verts.extend(make_cylinder(x, ground_y + 0.08, z, radius=0.12, height=barrel_h, segments=8, color=red_col))
    
    ring_col = (0.75, 0.10, 0.10, 0.95)
    verts.extend(make_cylinder(x, ground_y + 0.38, z, radius=0.135, height=0.04, segments=8, color=ring_col))
    
    brass_col = (0.92, 0.75, 0.16, 0.95)
    nozzle_y = ground_y + 0.44
    verts.extend(make_cylinder(x + 0.11, nozzle_y, z, radius=0.045, height=0.08, segments=6, color=brass_col))
    verts.extend(make_cylinder(x - 0.19, nozzle_y, z, radius=0.045, height=0.08, segments=6, color=brass_col))
    verts.extend(make_cylinder(x, nozzle_y, z + 0.11, radius=0.055, height=0.07, segments=6, color=brass_col))
    
    dome_y = ground_y + 0.08 + barrel_h
    verts.extend(make_cylinder(x, dome_y, z, radius=0.10, height=0.06, segments=8, color=red_col))
    verts.extend(make_cylinder(x, dome_y + 0.06, z, radius=0.035, height=0.04, segments=5, color=brass_col))
    
    return verts

def make_chainlink_fence_3d(p0, p1, y0, y1, height=1.80):
    """
    Malla ciclónica perimetral con postes de acero y alambre galvanizado entrelazado.
    Usa el slot (0, 2) del Atlas con recorte alpha en fragment shader.
    """
    verts = []
    dx = p1[0] - p0[0]; dz = p1[1] - p0[1]
    length = math.hypot(dx, dz)
    if length < 0.2: return verts
    
    nx = -dz / length; nz = dx / length
    norm_fwd = (nx, 0.0, nz)
    norm_back = (-nx, 0.0, -nz)
    
    pipe_col = (0.70, 0.72, 0.76, 0.95)
    panel_w = 2.0
    num_panels = max(1, int(math.ceil(length / panel_w)))
    
    u_base = 0.0 * 0.125
    u_span = 0.125
    v_base = 2.0 * 0.125
    v_span = 0.125
    
    # 1. Postes tubulares verticales en cada unión
    for pi in range(num_panels + 1):
        t_post = pi / float(num_panels)
        post_x = p0[0] + t_post * dx
        post_z = p0[1] + t_post * dz
        post_y = y0 + t_post * (y1 - y0)
        verts.extend(make_cylinder(post_x, post_y, post_z, radius=0.038, height=height, segments=6, color=pipe_col))
    
    # 2. Paneles de malla romboidal con alpha cutout
    mesh_col = (1.0, 1.0, 1.0, 1.0)
    for pi in range(num_panels):
        t0 = pi / float(num_panels)
        t1 = (pi + 1) / float(num_panels)
        pan_len = (t1 - t0) * length
        u_frac = min(1.0, max(0.2, pan_len / panel_w))
        
        px0 = p0[0] + t0 * dx; pz0 = p0[1] + t0 * dz
        px1 = p0[0] + t1 * dx; pz1 = p0[1] + t1 * dz
        py0 = y0 + t0 * (y1 - y0); py1 = y0 + t1 * (y1 - y0)
        
        q0 = (px0, py0, pz0)
        q1 = (px1, py1, pz1)
        q2 = (px1, py1 + height, pz1)
        q3 = (px0, py0 + height, pz0)
        
        uv0 = (u_base, v_base + v_span)
        uv1 = (u_base + u_frac * u_span, v_base + v_span)
        uv2 = (u_base + u_frac * u_span, v_base)
        uv3 = (u_base, v_base)
        
        # Cara frontal
        verts.append((q0, norm_fwd, uv0, mesh_col, 0.0))
        verts.append((q1, norm_fwd, uv1, mesh_col, 0.0))
        verts.append((q2, norm_fwd, uv2, mesh_col, 0.0))
        verts.append((q0, norm_fwd, uv0, mesh_col, 0.0))
        verts.append((q2, norm_fwd, uv2, mesh_col, 0.0))
        verts.append((q3, norm_fwd, uv3, mesh_col, 0.0))
        
        # Cara posterior
        verts.append((q1, norm_back, uv1, mesh_col, 0.0))
        verts.append((q0, norm_back, uv0, mesh_col, 0.0))
        verts.append((q3, norm_back, uv3, mesh_col, 0.0))
        verts.append((q1, norm_back, uv1, mesh_col, 0.0))
        verts.append((q3, norm_back, uv3, mesh_col, 0.0))
        verts.append((q2, norm_back, uv2, mesh_col, 0.0))
    
    return verts

def make_railing_3d(p0, p1, y0, y1, height=1.05):
    """
    Barandal de herrería metálico con pasamanos tubular y barrotes verticales.
    Usa el slot (1, 2) del Atlas con recorte alpha en fragment shader.
    """
    verts = []
    dx = p1[0] - p0[0]; dz = p1[1] - p0[1]
    length = math.hypot(dx, dz)
    if length < 0.2: return verts
    
    nx = -dz / length; nz = dx / length
    norm_fwd = (nx, 0.0, nz)
    norm_back = (-nx, 0.0, -nz)
    
    panel_w = 1.5
    num_panels = max(1, int(math.ceil(length / panel_w)))
    
    u_base = 1.0 * 0.125
    u_span = 0.125
    v_base = 2.0 * 0.125
    v_span = 0.125
    
    railing_col = (1.0, 1.0, 1.0, 1.0)
    for pi in range(num_panels):
        t0 = pi / float(num_panels)
        t1 = (pi + 1) / float(num_panels)
        pan_len = (t1 - t0) * length
        u_frac = min(1.0, max(0.2, pan_len / panel_w))
        
        px0 = p0[0] + t0 * dx; pz0 = p0[1] + t0 * dz
        px1 = p0[0] + t1 * dx; pz1 = p0[1] + t1 * dz
        py0 = y0 + t0 * (y1 - y0); py1 = y0 + t1 * (y1 - y0)
        
        q0 = (px0, py0, pz0)
        q1 = (px1, py1, pz1)
        q2 = (px1, py1 + height, pz1)
        q3 = (px0, py0 + height, pz0)
        
        uv0 = (u_base, v_base + v_span)
        uv1 = (u_base + u_frac * u_span, v_base + v_span)
        uv2 = (u_base + u_frac * u_span, v_base)
        uv3 = (u_base, v_base)
        
        verts.append((q0, norm_fwd, uv0, railing_col, 0.0))
        verts.append((q1, norm_fwd, uv1, railing_col, 0.0))
        verts.append((q2, norm_fwd, uv2, railing_col, 0.0))
        verts.append((q0, norm_fwd, uv0, railing_col, 0.0))
        verts.append((q2, norm_fwd, uv2, railing_col, 0.0))
        verts.append((q3, norm_fwd, uv3, railing_col, 0.0))
        
        verts.append((q1, norm_back, uv1, railing_col, 0.0))
        verts.append((q0, norm_back, uv0, railing_col, 0.0))
        verts.append((q3, norm_back, uv3, railing_col, 0.0))
        verts.append((q1, norm_back, uv1, railing_col, 0.0))
        verts.append((q3, norm_back, uv3, railing_col, 0.0))
        verts.append((q2, norm_back, uv2, railing_col, 0.0))
        
    return verts


def make_rolcar_elevated_sign_3d(cx, ground_y, cz, dir_angle=0.0, pole_h=11.0):
    """
    Anuncio elevado / tótem espectacular corporativo de ROLCAR (100% código vectorial, sin PNGs).
    """
    return build_rolcar_elevated_sign(cx, ground_y, cz, dir_angle, pole_h, make_box, make_cylinder)
