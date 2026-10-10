#!/usr/bin/env python3
"""
procedural_props.py FASE 2b - Árboles visibles a 700m
- 12m alto, copa 5m, color neón debug + beacon emisivo
"""
import math, random
from topography_math import triangulate_2d

def make_cylinder(base_x, base_y, base_z, radius, height, segments=6, color=(0.2,0.2,0.2,1.0)):
    verts=[]; top_y=base_y+height
    for s in range(segments):
        a0=s*2.0*math.pi/segments; a1=(s+1)*2.0*math.pi/segments
        c0,s0=math.cos(a0),math.sin(a0); c1,s1=math.cos(a1),math.sin(a1)
        p0=(base_x+radius*c0,base_y,base_z+radius*s0)
        p1=(base_x+radius*c1,base_y,base_z+radius*s1)
        p2=(base_x+radius*c1,top_y,base_z+radius*s1)
        p3=(base_x+radius*c0,top_y,base_z+radius*s0)
        avg_n=((c0+c1)*0.5,0.0,(s0+s1)*0.5)
        verts.append((p0,avg_n,(0,0),color,0.0)); verts.append((p1,avg_n,(0,0),color,0.0)); verts.append((p2,avg_n,(0,0),color,0.0))
        verts.append((p0,avg_n,(0,0),color,0.0)); verts.append((p2,avg_n,(0,0),color,0.0)); verts.append((p3,avg_n,(0,0),color,0.0))
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

CATEGORY_TILES = {
    "residencial": (0, 0),
    "comercial": (1, 0),
    "oxxo": (1, 0),
    "escuela": (2, 0),
    "educacion": (2, 0),
    "templo": (3, 0),
    "iglesia": (3, 0),
    "hospital": (4, 0),
    "salud": (4, 0),
    "oficina": (5, 0),
    "gobierno": (5, 0),
    "industrial": (6, 0),
    "almacen": (6, 0),
    "asfalto": (7, 0),
    "banqueta": (0, 1),
    "curb_red": (1, 1),
    "curb_yellow": (2, 1),
    "pasto": (3, 1),
}

def make_facade_uvs(p0, p1, height, category="residencial"):
    dx = p1[0] - p0[0]; dz = p1[1] - p0[1]; length = math.hypot(dx, dz)
    u1 = max(0.5, length / 4.0); v1 = max(0.5, height / 3.0)
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
    verts.extend(make_cylinder(cx, gy, cz, trunk_r, trunk_h, segments=6, color=trunk_col))
    
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

    metadata={"id":sig_id,"intersection":inter_id,"phase":phase_group,"x":head_x,"y":head_y,"z":head_z,"lenses":lens_info,"street_name":street_name}
    return verts,metadata

def make_street_corner_sign_3d(cx, ground_y, cz, street_name="CALLE", dir_angle=0.0):
    """
    Placa de nomenclatura de esquina estilo Aguascalientes.
    Montada directamente en fachada a ~2.5m de altura, sin poste.
    Fondo amarillo con borde negro (esquema típico de la ciudad).
    Dos placas perpendiculares en la esquina (calle principal + transversal).
    """
    verts = []
    # Typical Aguascalientes street‑name plate: yellow background with black border
    sign_yellow = (0.85, 0.78, 0.10, 0.95)  # approximate yellow
    sign_border = (0.05, 0.05, 0.05, 0.95)  # dark border (blackish)

    # Wall‑mount height: plates sit at ~2.5m above ground on the façade
    mount_height = 2.5
    top_y = ground_y + mount_height

    # Ajustar dimensiones de la placa según la longitud del nombre de la calle
    name_len = len(street_name) if street_name else 5
    sign_w = max(0.75, min(1.6, 0.10 * name_len))

    # Placas cruzadas de calle (2 letreros perpendiculares en la esquina)
    ca = math.cos(dir_angle); sa = math.sin(dir_angle)

    # Placa principal (nombre de la calle en la dirección del ángulo)
    px = cx + 0.35 * ca; pz = cz + 0.35 * sa
    verts.extend(make_box(px, top_y, pz, sign_w, 0.22, 0.04, color=sign_yellow))
    verts.extend(make_box(px, top_y, pz, sign_w + 0.03, 0.24, 0.02, color=sign_border))

    # Placa secundaria (perpendicular, calle transversal)
    ca_p = -sa; sa_p = ca
    px2 = cx + 0.35 * ca_p; pz2 = cz + 0.35 * sa_p
    verts.extend(make_box(px2, top_y - 0.25, pz2, sign_w, 0.22, 0.04, color=sign_yellow))
    verts.extend(make_box(px2, top_y - 0.25, pz2, sign_w + 0.03, 0.24, 0.02, color=sign_border))

    return verts

def make_sidewalk_3d(sp0_x, sp0_z, sp1_x, sp1_z, y0, y1, half_w, px_norm, pz_norm, sidewalk_w=1.60, curb_h=0.15, curb_type="auto"):
    """
    Banqueta peatonal elevada 0.15m sobre el nivel de calle con guarnición 3D vertical.
    curb_type: 'red' (No estacionarse / Esquinas), 'yellow' (Carga/Comercial), 'gray' (Estándar), 'auto'
    """
    verts = []
    norm_up = (0.0, 1.0, 0.0)
    sidewalk_col = (0.72, 0.70, 0.68, 0.95) # Concreto claro peatonal

    # Selección de color de guarnición (curb) según reglamento urbano
    if curb_type == "red":
        curb_col = (0.85, 0.12, 0.10, 0.95) # Rojo: Prohibido estacionar
    elif curb_type == "yellow":
        curb_col = (0.90, 0.80, 0.10, 0.95) # Amarillo: Carga y descarga
    elif curb_type == "gray":
        curb_col = (0.50, 0.48, 0.46, 0.95) # Gris: Guarnición de concreto natural
    else:
        # Auto: alternar rojo en extremos/esquinas o aleatorio
        curb_col = (0.85, 0.12, 0.10, 0.95) if random.random() < 0.35 else (0.50, 0.48, 0.46, 0.95)

    # Banqueta lado derecho (Puntos en nivel superior + curb en nivel de calle)
    sw_r0_street = (sp0_x + half_w * px_norm, y0, sp0_z + half_w * pz_norm)
    sw_r0_inner  = (sp0_x + half_w * px_norm, y0 + curb_h, sp0_z + half_w * pz_norm)
    sw_r0_outer  = (sp0_x + (half_w + sidewalk_w) * px_norm, y0 + curb_h, sp0_z + (half_w + sidewalk_w) * pz_norm)

    sw_r1_street = (sp1_x + half_w * px_norm, y1, sp1_z + half_w * pz_norm)
    sw_r1_inner  = (sp1_x + half_w * px_norm, y1 + curb_h, sp1_z + half_w * pz_norm)
    sw_r1_outer  = (sp1_x + (half_w + sidewalk_w) * px_norm, y1 + curb_h, sp1_z + (half_w + sidewalk_w) * pz_norm)
    
    # 1. Superficie plana de banqueta derecha
    verts.append((sw_r0_inner, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_r0_outer, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_r1_outer, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_r0_inner, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_r1_outer, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_r1_inner, norm_up, (0,0), sidewalk_col, 0.0))

    # 2. Cara vertical de guarnición derecha (pintada)
    norm_r = (px_norm, 0.0, pz_norm)
    verts.append((sw_r0_street, norm_r, (0,0), curb_col, 0.0))
    verts.append((sw_r0_inner,  norm_r, (0,0), curb_col, 0.0))
    verts.append((sw_r1_inner,  norm_r, (0,0), curb_col, 0.0))
    verts.append((sw_r0_street, norm_r, (0,0), curb_col, 0.0))
    verts.append((sw_r1_inner,  norm_r, (0,0), curb_col, 0.0))
    verts.append((sw_r1_street, norm_r, (0,0), curb_col, 0.0))
    
    # Banqueta lado izquierdo
    sw_l0_street = (sp0_x - half_w * px_norm, y0, sp0_z - half_w * pz_norm)
    sw_l0_inner  = (sp0_x - half_w * px_norm, y0 + curb_h, sp0_z - half_w * pz_norm)
    sw_l0_outer  = (sp0_x - (half_w + sidewalk_w) * px_norm, y0 + curb_h, sp0_z - (half_w + sidewalk_w) * pz_norm)

    sw_l1_street = (sp1_x - half_w * px_norm, y1, sp1_z - half_w * pz_norm)
    sw_l1_inner  = (sp1_x - half_w * px_norm, y1 + curb_h, sp1_z - half_w * pz_norm)
    sw_l1_outer  = (sp1_x - (half_w + sidewalk_w) * px_norm, y1 + curb_h, sp1_z - (half_w + sidewalk_w) * pz_norm)
    
    # 3. Superficie plana de banqueta izquierda
    verts.append((sw_l0_outer, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_l0_inner, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_l1_inner, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_l0_outer, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_l1_inner, norm_up, (0,0), sidewalk_col, 0.0))
    verts.append((sw_l1_outer, norm_up, (0,0), sidewalk_col, 0.0))

    # 4. Cara vertical de guarnición izquierda (pintada)
    norm_l = (-px_norm, 0.0, -pz_norm)
    verts.append((sw_l0_inner,  norm_l, (0,0), curb_col, 0.0))
    verts.append((sw_l0_street, norm_l, (0,0), curb_col, 0.0))
    verts.append((sw_l1_street, norm_l, (0,0), curb_col, 0.0))
    verts.append((sw_l0_inner,  norm_l, (0,0), curb_col, 0.0))
    verts.append((sw_l1_street, norm_l, (0,0), curb_col, 0.0))
    verts.append((sw_l1_inner,  norm_l, (0,0), curb_col, 0.0))
    
    return verts

def make_zebra_crossing_3d(cx,ground_y,cz,road_dir_angle,road_width=8.0):
    verts=[]; stripe_w=0.50; stripe_len=3.60; gap=0.50; num_stripes=int(max(3,(road_width-1.0)/(stripe_w+gap)))
    ca=math.cos(road_dir_angle); sa=math.sin(road_dir_angle); px=-sa; pz=ca; y=ground_y+0.08; white_col=(0.95,0.95,0.95,0.95); norm=(0.0,1.0,0.0) # matID 0.95
    total_span=(num_stripes-1)*(stripe_w+gap); start_offset=-total_span*0.5
    for i in range(num_stripes):
        off=start_offset+i*(stripe_w+gap); scx=cx+off*px; scz=cz+off*pz; hw=stripe_w*0.5; hl=stripe_len*0.5
        q0=(scx-hl*ca-hw*px,y,scz-hl*sa-hw*pz); q1=(scx+hl*ca-hw*px,y,scz+hl*sa-hw*pz); q2=(scx+hl*ca+hw*px,y,scz+hl*sa+hw*pz); q3=(scx-hl*ca+hw*px,y,scz-hl*sa+hw*pz)
        verts.append((q0,norm,(0,0),white_col,0.0)); verts.append((q1,norm,(0,0),white_col,0.0)); verts.append((q2,norm,(0,0),white_col,0.0))
        verts.append((q0,norm,(0,0),white_col,0.0)); verts.append((q2,norm,(0,0),white_col,0.0)); verts.append((q3,norm,(0,0),white_col,0.0))
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
    for i in range(n):
        p0=polygon[i]; p1=polygon[(i+1)%n]
        dx=p1[0]-p0[0]; dz=p1[1]-p0[1]; edge_len=math.hypot(dx,dz)
        if edge_len<0.01: continue
        wall_norm=(-dz/edge_len,0.0,dx/edge_len)
        gy0=ground_heights[i]; gy1=ground_heights[(i+1)%n]
        var=(i*37+int(p0[0]))%15/100.0
        if wall_color_override:
            wall_color = (max(0.1, min(1.0, wall_color_override[0] + var*0.5)),
                          max(0.1, min(1.0, wall_color_override[1] + var*0.5)),
                          max(0.1, min(1.0, wall_color_override[2] + var*0.5)),
                          1.0)
        else:
            wall_color=(0.82+var,0.78+var,0.70+var,1.0)
        uv0,uv1,uv2,uv3=make_facade_uvs(p0,p1,height,category=category)
        q0=(p0[0],gy0,p0[1]); q1=(p1[0],gy1,p1[1]); q2=(p1[0],roof_y,p1[1]); q3=(p0[0],roof_y,p0[1])
        verts.append((q0,wall_norm,uv0,wall_color,0.0)); verts.append((q1,wall_norm,uv1,wall_color,0.0)); verts.append((q2,wall_norm,uv2,wall_color,0.0))
        verts.append((q0,wall_norm,uv0,wall_color,0.0)); verts.append((q2,wall_norm,uv2,wall_color,0.0)); verts.append((q3,wall_norm,uv3,wall_color,0.0))
        if edge_len>6.0 and (int(p0[0]*0.7)+i)%9==0:
            win_y=gy0+height*0.55
            win_w=min(1.2,edge_len*0.22); win_h=1.0
            mid_x=(p0[0]+p1[0])*0.5; mid_z=(p0[1]+p1[1])*0.5
            off=0.05
            wq0=(mid_x-win_w*0.5+wall_norm[0]*off,win_y-win_h*0.5,mid_z+wall_norm[2]*off)
            wq1=(mid_x+win_w*0.5+wall_norm[0]*off,win_y-win_h*0.5,mid_z+wall_norm[2]*off)
            wq2=(mid_x+win_w*0.5+wall_norm[0]*off,win_y+win_h*0.5,mid_z+wall_norm[2]*off)
            wq3=(mid_x-win_w*0.5+wall_norm[0]*off,win_y+win_h*0.5,mid_z+wall_norm[2]*off)
            win_col=(1.0,0.92,0.6,1.0)
            verts.append((wq0,wall_norm,(0,0),win_col,0.9)); verts.append((wq1,wall_norm,(0,0),win_col,0.9)); verts.append((wq2,wall_norm,(0,0),win_col,0.9))
            verts.append((wq0,wall_norm,(0,0),win_col,0.9)); verts.append((wq2,wall_norm,(0,0),win_col,0.9)); verts.append((wq3,wall_norm,(0,0),win_col,0.9))
    return verts
