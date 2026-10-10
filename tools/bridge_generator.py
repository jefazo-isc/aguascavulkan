#!/usr/bin/env python3
"""
tools/bridge_generator.py - Generador procedural 3D de Puentes Peatonales y Civiles
- Soporta puentes vehiculares / viaductos (tablero, vigas inferiores, pilas de concreto, barreras New Jersey)
- Soporta puentes peatonales (pasarela suspendida, barandales de celosía/tubulares, columnas de acero, escaleras)
"""

import math
try:
    from procedural_props import make_cylinder, make_box
except ImportError:
    from tools.procedural_props import make_cylinder, make_box

# Materiales y colores (sincronizados con fragment.frag)
# matID 0.95 = Nivel de calle / asfalto y concreto vial
# matID 0.95 con color oscuro = asfalto
# matID 0.95 con color claro  = concreto
ASPHALT_BRIDGE_COL = (0.24, 0.24, 0.26, 0.95)
CONCRETE_PIER_COL  = (0.68, 0.67, 0.65, 0.95)
BARRIER_CONCRETE_COL = (0.75, 0.74, 0.72, 0.95)
STEEL_STRUCTURE_COL = (0.22, 0.24, 0.28, 0.95)
PEDESTRIAN_FLOOR_COL = (0.70, 0.69, 0.67, 0.95)
RAILING_COL         = (0.88, 0.88, 0.90, 0.95)

def make_civil_bridge_3d(pts_m, road_w=9.0, clearance_h=5.8, mesh_grid=None, min_x=-1e9, max_x=1e9, min_z=-1e9, max_z=1e9):
    """
    Genera un viaducto o puente vehicular 3D.
    - pts_m: lista de coordenadas 2D (x, z) en metros del centerline.
    - clearance_h: altura libre del tablero sobre el terreno en el tramo central.
    - mesh_grid: instancia de MeshElevationGrid para proyectar la cota del terreno.
    """
    verts = []
    if len(pts_m) < 2:
        return verts

    norm_up = (0.0, 1.0, 0.0)
    norm_down = (0.0, -1.0, 0.0)
    half_w = road_w * 0.5
    deck_thickness = 0.90  # Grosor estructural del tablero de concreto
    barrier_h = 0.85       # Altura barrera New Jersey
    barrier_w = 0.35       # Ancho barrera

    # 1. Calcular cotas de elevación Y a lo largo del puente
    # Suavizar perfil longitudinal: rampas en extremos conectadas al suelo y altura máxima al centro
    ground_heights = []
    for px, pz in pts_m:
        gy = mesh_grid.get_mesh_height(px, pz) if mesh_grid else 0.0
        ground_heights.append(gy)

    n_pts = len(pts_m)
    deck_heights = []
    
    # Si el puente tiene solo 2 o 3 nodos, subdividirlo longitudinalmente para formar rampas suaves
    subdivided_pts = []
    if n_pts == 2:
        p_a, p_b = pts_m[0], pts_m[1]
        steps_sub = 8
        for s in range(steps_sub + 1):
            ts = s / float(steps_sub)
            subdivided_pts.append((p_a[0] + ts * (p_b[0] - p_a[0]), p_a[1] + ts * (p_b[1] - p_a[1])))
        pts_m = subdivided_pts
        n_pts = len(pts_m)
        ground_heights = [mesh_grid.get_mesh_height(px, pz) if mesh_grid else 0.0 for px, pz in pts_m]

    # Altura del puente: elevación central con rampas parabólicas que nacen exactamente desde el suelo en extremos
    max_ground = max(ground_heights)
    target_bridge_y = max_ground + clearance_h

    for i in range(n_pts):
        gy = ground_heights[i]
        t = i / float(n_pts - 1)
        # Rampa con forma de seno suave: exactamente en el suelo en extremos t=0 y t=1 (peso 0)
        elevation_weight = math.sin(t * math.pi)
        bridge_y = gy + (target_bridge_y - gy) * elevation_weight
        deck_heights.append(bridge_y)

    # 2. Generar tableros y barreras por segmento
    total_len_acc = 0.0
    pier_interval = 14.0  # Columnas cada 14 metros para soporte masivo y continuo
    dist_since_pier = pier_interval * 0.4

    for i in range(n_pts - 1):
        p0 = pts_m[i]
        p1 = pts_m[i + 1]
        dx = p1[0] - p0[0]
        dz = p1[1] - p0[1]
        seg_len = math.hypot(dx, dz)
        if seg_len < 0.1:
            continue

        px_norm = -dz / seg_len
        pz_norm = dx / seg_len

        y0 = deck_heights[i]
        y1 = deck_heights[i + 1]

        # Vértices del tablero superior (asfalto de calzada)
        q0 = (p0[0] - half_w * px_norm, y0, p0[1] - half_w * pz_norm)
        q1 = (p0[0] + half_w * px_norm, y0, p0[1] + half_w * pz_norm)
        q2 = (p1[0] + half_w * px_norm, y1, p1[1] + half_w * pz_norm)
        q3 = (p1[0] - half_w * px_norm, y1, p1[1] - half_w * pz_norm)

        # Superficie de rodamiento superior (Asfalto)
        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q1, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q3, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))

        # Fondo inferior del tablero (Concreto)
        bq0 = (q0[0], max(mesh_grid.get_mesh_height(q0[0], q0[2]) if mesh_grid else y0-deck_thickness, y0 - deck_thickness), q0[2])
        bq1 = (q1[0], max(mesh_grid.get_mesh_height(q1[0], q1[2]) if mesh_grid else y0-deck_thickness, y0 - deck_thickness), q1[2])
        bq2 = (q2[0], max(mesh_grid.get_mesh_height(q2[0], q2[2]) if mesh_grid else y1-deck_thickness, y1 - deck_thickness), q2[2])
        bq3 = (q3[0], max(mesh_grid.get_mesh_height(q3[0], q3[2]) if mesh_grid else y1-deck_thickness, y1 - deck_thickness), q3[2])

        verts.append((bq0, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq2, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq1, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq0, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq3, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq2, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))

        # Vigas longitudinales de soporte estructural (Girders) para darle cuerpo y profundidad
        beam_w = 0.55
        beam_drop = 0.65
        center_y0 = (y0 - deck_thickness) - beam_drop
        center_y1 = (y1 - deck_thickness) - beam_drop
        c_mid0 = (p0[0], center_y0, p0[1])
        c_mid1 = (p1[0], center_y1, p1[1])
        verts.extend(make_box((p0[0]+p1[0])*0.5, (center_y0+center_y1)*0.5, (p0[1]+p1[1])*0.5, road_w * 0.70, beam_drop, seg_len, color=CONCRETE_PIER_COL))

        # Costados verticales del tablero
        norm_r = (px_norm, 0.0, pz_norm)
        norm_l = (-px_norm, 0.0, -pz_norm)
        # Costado derecho
        verts.append((q1, norm_r, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq1, norm_r, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq2, norm_r, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q1, norm_r, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq2, norm_r, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q2, norm_r, (0, 0), CONCRETE_PIER_COL, 0.0))
        # Costado izquierdo
        verts.append((q3, norm_l, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq3, norm_l, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq0, norm_l, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q3, norm_l, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((bq0, norm_l, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q0, norm_l, (0, 0), CONCRETE_PIER_COL, 0.0))

        # Barreras de protección de concreto (New Jersey) en ambos bordes
        # Borde derecho
        bar_r_out0 = (q1[0], y0 + barrier_h, q1[2])
        bar_r_in0  = (q1[0] - barrier_w * px_norm, y0 + barrier_h, q1[2] - barrier_w * pz_norm)
        bar_r_out1 = (q2[0], y1 + barrier_h, q2[2])
        bar_r_in1  = (q2[0] - barrier_w * px_norm, y1 + barrier_h, q2[2] - barrier_w * pz_norm)
        verts.append((bar_r_out0, norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_r_out1, norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_r_in1,  norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_r_out0, norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_r_in1,  norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_r_in0,  norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))

        # Borde izquierdo
        bar_l_out0 = (q0[0], y0 + barrier_h, q0[2])
        bar_l_in0  = (q0[0] + barrier_w * px_norm, y0 + barrier_h, q0[2] + barrier_w * pz_norm)
        bar_l_out1 = (q3[0], y1 + barrier_h, q3[2])
        bar_l_in1  = (q3[0] + barrier_w * px_norm, y1 + barrier_h, q3[2] + barrier_w * pz_norm)
        verts.append((bar_l_out0, norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_l_in0,  norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_l_in1,  norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_l_out0, norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_l_in1,  norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))
        verts.append((bar_l_out1, norm_up, (0, 0), BARRIER_CONCRETE_COL, 0.0))

        # 3. Pilas / Columnas cilíndricas de concreto reforzado hacia el terreno
        dist_since_pier += seg_len
        if dist_since_pier >= pier_interval and i < (n_pts - 1):
            dist_since_pier = 0.0
            pier_x = (p0[0] + p1[0]) * 0.5
            pier_z = (p0[1] + p1[1]) * 0.5
            pier_top_y = ((y0 + y1) * 0.5) - deck_thickness
            pier_bot_y = mesh_grid.get_mesh_height(pier_x, pier_z) if mesh_grid else 0.0
            pier_h = pier_top_y - pier_bot_y

            # Colocar columnas a partir de 1.2 metros de elevación
            if pier_h > 1.2:
                # Doble columna de soporte cilíndrica de concreto macizo
                pier_r = 0.70
                offset_w = half_w * 0.45
                p_r_x = pier_x + offset_w * px_norm
                p_r_z = pier_z + offset_w * pz_norm
                p_l_x = pier_x - offset_w * px_norm
                p_l_z = pier_z - offset_w * pz_norm

                verts.extend(make_cylinder(p_r_x, pier_bot_y, p_r_z, pier_r, pier_h, segments=8, color=CONCRETE_PIER_COL))
                verts.extend(make_cylinder(p_l_x, pier_bot_y, p_l_z, pier_r, pier_h, segments=8, color=CONCRETE_PIER_COL))
                # Viga cabezal superior que une las columnas con el tablero
                verts.extend(make_box(pier_x, pier_top_y - 0.40, pier_z, road_w * 0.88, 0.80, 1.8, color=CONCRETE_PIER_COL))
            else:
                # Estribo de soporte bajo en el suelo (Abutment)
                verts.extend(make_box(pier_x, (pier_top_y + pier_bot_y) * 0.5, pier_z, road_w * 0.95, max(0.4, pier_h + 0.3), 2.2, color=CONCRETE_PIER_COL))

    return verts

def make_pedestrian_bridge_3d(pts_m, width=2.4, clearance_h=5.4, mesh_grid=None):
    """
    Genera un puente peatonal elevado sobre vía.
    - Pasarela con piso peatonal de concreto/placa de acero
    - Barandales metálicos a ambos costados
    - Columnas tubulares de soporte a los lados
    - Escaleras / rampas peatonales en extremos
    """
    verts = []
    if len(pts_m) < 2:
        return verts

    norm_up = (0.0, 1.0, 0.0)
    norm_down = (0.0, -1.0, 0.0)
    half_w = width * 0.5
    deck_thickness = 0.45
    railing_h = 1.25

    ground_heights = [mesh_grid.get_mesh_height(px, pz) if mesh_grid else 0.0 for px, pz in pts_m]
    max_ground = max(ground_heights)
    bridge_y = max_ground + clearance_h

    n_pts = len(pts_m)
    for i in range(n_pts - 1):
        p0 = pts_m[i]
        p1 = pts_m[i + 1]
        dx = p1[0] - p0[0]
        dz = p1[1] - p0[1]
        seg_len = math.hypot(dx, dz)
        if seg_len < 0.1:
            continue

        px_norm = -dz / seg_len
        pz_norm = dx / seg_len

        # Pasarela principal
        q0 = (p0[0] - half_w * px_norm, bridge_y, p0[1] - half_w * pz_norm)
        q1 = (p0[0] + half_w * px_norm, bridge_y, p0[1] + half_w * pz_norm)
        q2 = (p1[0] + half_w * px_norm, bridge_y, p1[1] + half_w * pz_norm)
        q3 = (p1[0] - half_w * px_norm, bridge_y, p1[1] - half_w * pz_norm)

        # Superficie de la pasarela
        verts.append((q0, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
        verts.append((q1, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
        verts.append((q2, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
        verts.append((q0, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
        verts.append((q2, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
        verts.append((q3, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))

        # Viga inferior de cajón estructural (Steel Truss Girder)
        bq0 = (q0[0], bridge_y - deck_thickness, q0[2])
        bq1 = (q1[0], bridge_y - deck_thickness, q1[2])
        bq2 = (q2[0], bridge_y - deck_thickness, q2[2])
        bq3 = (q3[0], bridge_y - deck_thickness, q3[2])
        verts.append((bq0, norm_down, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq2, norm_down, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq1, norm_down, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq0, norm_down, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq3, norm_down, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq2, norm_down, (0, 0), STEEL_STRUCTURE_COL, 0.0))

        # Caras laterales del tablero de la pasarela
        norm_r = (px_norm, 0.0, pz_norm)
        norm_l = (-px_norm, 0.0, -pz_norm)
        verts.append((q1, norm_r, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq1, norm_r, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq2, norm_r, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((q1, norm_r, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq2, norm_r, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((q2, norm_r, (0, 0), STEEL_STRUCTURE_COL, 0.0))

        verts.append((q3, norm_l, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq3, norm_l, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq0, norm_l, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((q3, norm_l, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((bq0, norm_l, (0, 0), STEEL_STRUCTURE_COL, 0.0))
        verts.append((q0, norm_l, (0, 0), STEEL_STRUCTURE_COL, 0.0))

        # Barandales tubulares con orientación exacta 3D (pasamanos superior e intermedio)
        for h_bar in [railing_h, railing_h * 0.5]:
            # Pasamanos derecho
            br0 = (q1[0], bridge_y + h_bar, q1[2])
            br1 = (q2[0], bridge_y + h_bar, q2[2])
            # Quad vertical delgado
            verts.append((br0, norm_r, (0, 0), RAILING_COL, 0.0))
            verts.append(((br0[0], br0[1]-0.08, br0[2]), norm_r, (0, 0), RAILING_COL, 0.0))
            verts.append(((br1[0], br1[1]-0.08, br1[2]), norm_r, (0, 0), RAILING_COL, 0.0))
            verts.append((br0, norm_r, (0, 0), RAILING_COL, 0.0))
            verts.append(((br1[0], br1[1]-0.08, br1[2]), norm_r, (0, 0), RAILING_COL, 0.0))
            verts.append((br1, norm_r, (0, 0), RAILING_COL, 0.0))

            # Pasamanos izquierdo
            bl0 = (q0[0], bridge_y + h_bar, q0[2])
            bl1 = (q3[0], bridge_y + h_bar, q3[2])
            verts.append((bl0, norm_l, (0, 0), RAILING_COL, 0.0))
            verts.append(((bl1[0], bl1[1]-0.08, bl1[2]), norm_l, (0, 0), RAILING_COL, 0.0))
            verts.append(((bl0[0], bl0[1]-0.08, bl0[2]), norm_l, (0, 0), RAILING_COL, 0.0))
            verts.append((bl0, norm_l, (0, 0), RAILING_COL, 0.0))
            verts.append((bl1, norm_l, (0, 0), RAILING_COL, 0.0))
            verts.append(((bl1[0], bl1[1]-0.08, bl1[2]), norm_l, (0, 0), RAILING_COL, 0.0))

        # Postes verticales del barandal a intervalos de 2 metros
        n_posts = max(2, int(seg_len / 2.0))
        for p_idx in range(n_posts + 1):
            t_p = p_idx / float(n_posts)
            post_r_x = q1[0] + t_p * (q2[0] - q1[0])
            post_r_z = q1[2] + t_p * (q2[2] - q1[2])
            post_l_x = q0[0] + t_p * (q3[0] - q0[0])
            post_l_z = q0[2] + t_p * (q3[2] - q0[2])
            verts.extend(make_box(post_r_x, bridge_y + railing_h * 0.5, post_r_z, 0.07, railing_h, 0.07, color=RAILING_COL))
            verts.extend(make_box(post_l_x, bridge_y + railing_h * 0.5, post_l_z, 0.07, railing_h, 0.07, color=RAILING_COL))

    # Columnas estructurales y escaleras en ambos extremos orientadas hacia afuera del puente
    # Extremo inicio (pts[0]): sale alejándose de pts[1] -> vector = pts[0] - pts[1]
    # Extremo fin (pts[-1]): sale alejándose de pts[-2] -> vector = pts[-1] - pts[-2]
    endpoints_info = [
        (pts_m[0], pts_m[1]),    # Extremo inicio
        (pts_m[-1], pts_m[-2])   # Extremo fin
    ]

    for pt_curr, pt_adj in endpoints_info:
        px, pz = pt_curr[0], pt_curr[1]
        bot_y = mesh_grid.get_mesh_height(px, pz) if mesh_grid else 0.0
        h_col = bridge_y - bot_y

        # Vector unitario hacia afuera del puente
        edx = pt_curr[0] - pt_adj[0]
        edz = pt_curr[1] - pt_adj[1]
        elen = math.hypot(edx, edz) or 1.0
        dir_x = edx / elen
        dir_z = edz / elen
        perp_x = -dir_z
        perp_z = dir_x

        if h_col > 1.2:
            # Columnas cilíndricas dobles de acero
            verts.extend(make_cylinder(px - perp_x * half_w * 0.8, bot_y, pz - perp_z * half_w * 0.8, 0.22, h_col, segments=8, color=STEEL_STRUCTURE_COL))
            verts.extend(make_cylinder(px + perp_x * half_w * 0.8, bot_y, pz + perp_z * half_w * 0.8, 0.22, h_col, segments=8, color=STEEL_STRUCTURE_COL))
            # Viga cabezal de soporte transversal
            verts.extend(make_box(px, bridge_y - deck_thickness * 0.5, pz, width * 1.1, deck_thickness, 0.5, color=STEEL_STRUCTURE_COL))

            # Descanso de inicio de escaleras
            landing_len = 2.2
            l_p0 = (px - perp_x * half_w, bridge_y, pz - perp_z * half_w)
            l_p1 = (px + perp_x * half_w, bridge_y, pz + perp_z * half_w)
            l_p2 = (l_p1[0] + dir_x * landing_len, bridge_y, l_p1[2] + dir_z * landing_len)
            l_p3 = (l_p0[0] + dir_x * landing_len, bridge_y, l_p0[2] + dir_z * landing_len)
            verts.append((l_p0, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
            verts.append((l_p1, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
            verts.append((l_p2, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
            verts.append((l_p0, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
            verts.append((l_p2, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
            verts.append((l_p3, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))

            # Peldaños de escalera construidos con quads alineados exactamente al vector del puente
            stair_steps = 18
            tread_depth = 0.45   # 45cm de huella
            stair_w = width * 0.88
            stair_half_w = stair_w * 0.5

            for step in range(stair_steps):
                t_s0 = step / float(stair_steps)
                t_s1 = (step + 1) / float(stair_steps)
                sy0 = bridge_y - t_s0 * h_col
                sy1 = bridge_y - t_s1 * h_col
                dist0 = landing_len + step * tread_depth
                dist1 = dist0 + tread_depth

                # Centro huella
                c0_x = px + dir_x * dist0
                c0_z = pz + dir_z * dist0
                c1_x = px + dir_x * dist1
                c1_z = pz + dir_z * dist1

                # Huella superior horizontal
                st_p0 = (c0_x - perp_x * stair_half_w, sy1, c0_z - perp_z * stair_half_w)
                st_p1 = (c0_x + perp_x * stair_half_w, sy1, c0_z + perp_z * stair_half_w)
                st_p2 = (c1_x + perp_x * stair_half_w, sy1, c1_z + perp_z * stair_half_w)
                st_p3 = (c1_x - perp_x * stair_half_w, sy1, c1_z - perp_z * stair_half_w)
                verts.append((st_p0, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p1, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p2, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p0, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p2, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p3, norm_up, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))

                # Contrahuella vertical
                ch_p0 = (st_p0[0], sy0, st_p0[2])
                ch_p1 = (st_p1[0], sy0, st_p1[2])
                norm_rise = (-dir_x, 0.0, -dir_z)
                verts.append((st_p0, norm_rise, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((ch_p0, norm_rise, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((ch_p1, norm_rise, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p0, norm_rise, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((ch_p1, norm_rise, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))
                verts.append((st_p1, norm_rise, (0, 0), PEDESTRIAN_FLOOR_COL, 0.0))

                # Barandal pasamanos inclinado a ambos lados
                r_r0 = (st_p1[0], sy1 + railing_h, st_p1[2])
                r_r1 = (st_p2[0], sy1 + railing_h, st_p2[2])
                r_l0 = (st_p0[0], sy1 + railing_h, st_p0[2])
                r_l1 = (st_p3[0], sy1 + railing_h, st_p3[2])
                # Postes verticales cada 2 peldaños
                if step % 2 == 0:
                    verts.extend(make_box(st_p1[0], sy1 + railing_h*0.5, st_p1[2], 0.06, railing_h, 0.06, color=RAILING_COL))
                    verts.extend(make_box(st_p0[0], sy1 + railing_h*0.5, st_p0[2], 0.06, railing_h, 0.06, color=RAILING_COL))

            # Zancas de acero estructural inclinadas a los costados
            total_stair_len = landing_len + stair_steps * tread_depth
            end_x = px + dir_x * total_stair_len
            end_z = pz + dir_z * total_stair_len
            end_y = mesh_grid.get_mesh_height(end_x, end_z) if mesh_grid else bot_y

            # Pedestal de anclaje de concreto en el suelo / banqueta
            verts.extend(make_box(end_x, end_y + 0.25, end_z, width * 1.05, 0.50, 1.4, color=CONCRETE_PIER_COL))

    return verts

def make_underground_pass_3d(pts_m, road_w=9.5, depth_m=5.2, mesh_grid=None):
    """
    Genera un paso a desnivel subterráneo / túnel vehicular:
    - Calzada deprimida bajo el nivel de suelo
    - Muros de contención laterales de concreto
    - Techo / losa superior en la sección central cubierta
    - Portales de entrada y salida con muros de ala (wingwalls)
    - Iluminación emisiva en el interior del túnel
    """
    verts = []
    if len(pts_m) < 2:
        return verts

    norm_up = (0.0, 1.0, 0.0)
    norm_down = (0.0, -1.0, 0.0)
    half_w = road_w * 0.5
    wall_thickness = 0.55
    roof_thickness = 0.60
    clear_height = 4.8  # Altura libre dentro del túnel

    n_pts = len(pts_m)
    ground_heights = [mesh_grid.get_mesh_height(px, pz) if mesh_grid else 0.0 for px, pz in pts_m]

    # Calcular distancias acumuladas a lo largo del túnel
    cum_dists = [0.0]
    for i in range(n_pts - 1):
        cum_dists.append(cum_dists[-1] + math.hypot(pts_m[i+1][0] - pts_m[i][0], pts_m[i+1][1] - pts_m[i][1]))
    total_len = cum_dists[-1]
    ramp_len = min(65.0, total_len * 0.25)

    # Calcular cota de fondo de calzada:
    # Rampa de descenso en los primeros `ramp_len` metros, galería plana a -depth_m, y rampa de subida al final
    road_heights = []
    for i in range(n_pts):
        gy = ground_heights[i]
        d = cum_dists[i]
        if d < ramp_len:
            # Rampa de entrada (desciende desde 0m hasta -depth_m)
            tr = d / max(1.0, ramp_len)
            dip = 0.5 * (1.0 - math.cos(tr * math.pi))
        elif d > (total_len - ramp_len):
            # Rampa de salida (asciende desde -depth_m hasta 0m)
            tr = (total_len - d) / max(1.0, ramp_len)
            dip = 0.5 * (1.0 - math.cos(tr * math.pi))
        else:
            # Interior profundo del paso a desnivel
            dip = 1.0
        road_y = gy - depth_m * dip
        road_heights.append(road_y)

    for i in range(n_pts - 1):
        p0 = pts_m[i]
        p1 = pts_m[i + 1]
        dx = p1[0] - p0[0]
        dz = p1[1] - p0[1]
        seg_len = math.hypot(dx, dz)
        if seg_len < 0.1:
            continue

        px_norm = -dz / seg_len
        pz_norm = dx / seg_len

        y0 = road_heights[i]
        y1 = road_heights[i + 1]
        gy0 = ground_heights[i]
        gy1 = ground_heights[i + 1]

        # Calzada de asfalto deprimida
        q0 = (p0[0] - half_w * px_norm, y0 + 0.08, p0[1] - half_w * pz_norm)
        q1 = (p0[0] + half_w * px_norm, y0 + 0.08, p0[1] + half_w * pz_norm)
        q2 = (p1[0] + half_w * px_norm, y1 + 0.08, p1[1] + half_w * pz_norm)
        q3 = (p1[0] - half_w * px_norm, y1 + 0.08, p1[1] - half_w * pz_norm)

        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q1, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q3, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))

        # Muro de contención derecho (concreto desde la calzada deprimida hasta el suelo)
        top_r0 = (q1[0] + wall_thickness * px_norm, gy0 + 0.8, q1[2] + wall_thickness * pz_norm)
        top_r1 = (q2[0] + wall_thickness * px_norm, gy1 + 0.8, q2[2] + wall_thickness * pz_norm)
        norm_r_in = (-px_norm, 0.0, -pz_norm)

        verts.append((q1, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((top_r0, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((top_r1, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q1, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((top_r1, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q2, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))

        # Muro de contención izquierdo
        top_l0 = (q0[0] - wall_thickness * px_norm, gy0 + 0.8, q0[2] - wall_thickness * pz_norm)
        top_l1 = (q3[0] - wall_thickness * px_norm, gy1 + 0.8, q3[2] - wall_thickness * pz_norm)
        norm_l_in = (px_norm, 0.0, pz_norm)

        verts.append((q0, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((top_l1, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((top_l0, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q0, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((q3, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
        verts.append((top_l1, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))

        # Sección cubierta de túnel solo en el tramo central profundo
        # y asegurando que la losa superior quede a ras de la rasante del terreno sin flotar ni tapar
        mid_depth = (gy0 - y0 + gy1 - y1) * 0.5
        is_covered = mid_depth >= 4.0

        if is_covered:
            roof_bot_y0 = y0 + clear_height
            roof_bot_y1 = y1 + clear_height
            roof_top_y0 = max(roof_bot_y0 + 0.35, gy0)
            roof_top_y1 = max(roof_bot_y1 + 0.35, gy1)

            rq0 = (q0[0], roof_bot_y0, q0[2])
            rq1 = (q1[0], roof_bot_y0, q1[2])
            rq2 = (q2[0], roof_bot_y1, q2[2])
            rq3 = (q3[0], roof_bot_y1, q3[2])

            # Intradós (techo interior del túnel)
            verts.append((rq0, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((rq2, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((rq1, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((rq0, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((rq3, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((rq2, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Extradós (losa de techo a nivel de suelo transitable)
            trq0 = (q0[0], roof_top_y0, q0[2])
            trq1 = (q1[0], roof_top_y0, q1[2])
            trq2 = (q2[0], roof_top_y1, q2[2])
            trq3 = (q3[0], roof_top_y1, q3[2])
            verts.append((trq0, norm_up, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((trq1, norm_up, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((trq2, norm_up, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((trq0, norm_up, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((trq2, norm_up, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((trq3, norm_up, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Si el segmento anterior era abierto (trinchera), este es el portal de entrada:
            # Construir frontón/dintel sobre el vano (entre el dintel del túnel y la rasante)
            prev_covered = (i > 0) and (((ground_heights[i-1] - road_heights[i-1] + gy0 - y0) * 0.5) >= 4.0)
            if not prev_covered:
                portal_norm = (-dx / seg_len, 0.0, -dz / seg_len)
                verts.append((rq0, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((rq1, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((trq1, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((rq0, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((trq1, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((trq0, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Si el segmento siguiente es abierto, este es el portal de salida:
            next_covered = (i < n_pts - 2) and (((gy1 - y1 + ground_heights[i+2] - road_heights[i+2]) * 0.5) >= 4.0)
            if not next_covered:
                portal_norm = (dx / seg_len, 0.0, dz / seg_len)
                verts.append((rq2, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((rq3, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((trq3, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((rq2, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((trq3, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((trq2, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Lámparas emisivas lineales en el intradós del túnel
            lamp_col = (1.0, 0.95, 0.8, 0.95)
            lamp_y = (roof_bot_y0 + roof_bot_y1) * 0.5 - 0.05
            lamp_cx = (p0[0] + p1[0]) * 0.5
            lamp_cz = (p0[1] + p1[1]) * 0.5
            verts.extend(make_box(lamp_cx, lamp_y, lamp_cz, 0.45, 0.12, seg_len * 0.8, color=lamp_col, emission=1.0))

    return verts
