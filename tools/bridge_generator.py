#!/usr/bin/env python3
"""
tools/bridge_generator.py - Generador procedural 3D de Puentes Peatonales y Civiles
- Soporta puentes vehiculares / viaductos (tablero, vigas inferiores, pilas de concreto, barreras New Jersey)
- Soporta puentes peatonales (pasarela suspendida, barandales de celosía/tubulares, columnas de acero, escaleras)
"""

import math
try:
    from procedural_props import make_cylinder, make_box, make_railing_3d
except ImportError:
    from tools.procedural_props import make_cylinder, make_box, make_railing_3d

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
        verts.append((q1, norm_up, (1, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (1, 1), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (1, 1), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q3, norm_up, (0, 1), ASPHALT_BRIDGE_COL, 0.0))

        # Señalización vial central sobre viaducto/puente (+0.025m sobre asfalto)
        if road_w >= 7.0:
            hw_str = 0.09
            br_stripe_y0 = y0 + 0.025
            br_stripe_y1 = y1 + 0.025
            col_br_yellow = (0.92, 0.82, 0.12, 0.95)
            bsq0 = (p0[0] - hw_str * px_norm, br_stripe_y0, p0[1] - hw_str * pz_norm)
            bsq1 = (p0[0] + hw_str * px_norm, br_stripe_y0, p0[1] + hw_str * pz_norm)
            bsq2 = (p1[0] + hw_str * px_norm, br_stripe_y1, p1[1] + hw_str * pz_norm)
            bsq3 = (p1[0] - hw_str * px_norm, br_stripe_y1, p1[1] - hw_str * pz_norm)
            verts.append((bsq0, norm_up, (0, 0), col_br_yellow, 0.0))
            verts.append((bsq1, norm_up, (1, 0), col_br_yellow, 0.0))
            verts.append((bsq2, norm_up, (1, 1), col_br_yellow, 0.0))
            verts.append((bsq0, norm_up, (0, 0), col_br_yellow, 0.0))
            verts.append((bsq2, norm_up, (1, 1), col_br_yellow, 0.0))
            verts.append((bsq3, norm_up, (0, 1), col_br_yellow, 0.0))

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

def make_underground_pass_3d(pts_m, road_w=9.5, depth_m=5.4, mesh_grid=None, is_oneway=True, apron_out=None):
    """
    Genera un paso a desnivel vehicular real en trinchera abierta (estilo Aguascalientes):
    - Trinchera a cielo abierto deprimida bajo el nivel de suelo con calzada de asfalto y cunetas.
    - Rampas longitudinales de transición cosenoidal suave.
    - Muros de contención laterales con acabado estriado (PBR shader) y albardilla superior.
    - Barandales perimetrales superiores de protección (make_railing_3d) a ras de calle.
    - Losa de puente superior para la calle transversal en la zona central de cruce con luminarias LED.
    - Señalización horizontal reglamentaria SCT: líneas amarillas de orilla y blancas discontinuas de carril.
    Retorna: (verts, trench_polys)
    """
    verts = []
    trench_polys = []
    if len(pts_m) < 2:
        return verts, trench_polys

    norm_up = (0.0, 1.0, 0.0)
    norm_down = (0.0, -1.0, 0.0)
    half_w = road_w * 0.5
    wall_thickness = 0.40
    coping_w = 0.30
    clear_height = 4.8  # Altura libre dentro de la sección techada

    n_pts = len(pts_m)
    ground_heights = [mesh_grid.get_mesh_height(px, pz) if mesh_grid else 0.0 for px, pz in pts_m]

    cum_dists = [0.0]
    for i in range(n_pts - 1):
        cum_dists.append(cum_dists[-1] + math.hypot(pts_m[i+1][0] - pts_m[i][0], pts_m[i+1][1] - pts_m[i][1]))
    total_len = max(1.0, cum_dists[-1])
    ramp_len = min(70.0, total_len * 0.30)

    # Definir sección de puente superior transversal:
    bridge_w = min(28.0, total_len * 0.35) if total_len >= 55.0 else min(16.0, total_len * 0.4)
    mid_dist = total_len * 0.5
    bridge_start_d = mid_dist - bridge_w * 0.5
    bridge_end_d   = mid_dist + bridge_w * 0.5

    curb_in_col = (0.50, 0.48, 0.46, 0.95)
    coping_col  = (0.75, 0.74, 0.72, 0.95)
    bridge_surface_col = (0.24, 0.24, 0.26, 0.95)

    # Subdividir segmentos largos para que las rampas y muros sigan la curvatura del terreno
    raw_samples = []

    for i in range(n_pts - 1):
        p0 = pts_m[i]; p1 = pts_m[i + 1]
        dx = p1[0] - p0[0]; dz = p1[1] - p0[1]
        seg_len = math.hypot(dx, dz)
        if seg_len < 0.05: continue
        n_sub = max(1, int(math.ceil(seg_len / 6.0)))
        for s in range(n_sub):
            t = s / float(n_sub)
            spx = p0[0] + t * dx; spz = p0[1] + t * dz
            sd = cum_dists[i] + t * seg_len
            s_gy = mesh_grid.get_mesh_height(spx, spz) if mesh_grid else (ground_heights[i] + t * (ground_heights[i + 1] - ground_heights[i]))
            if sd < ramp_len:
                tr = sd / max(1.0, ramp_len)
                s_dip = 0.5 * (1.0 - math.cos(tr * math.pi))
            elif sd > (total_len - ramp_len):
                tr = (total_len - sd) / max(1.0, ramp_len)
                s_dip = 0.5 * (1.0 - math.cos(tr * math.pi))
            else:
                s_dip = 1.0
            s_ry = s_gy + 0.02 - depth_m * s_dip
            raw_samples.append(((spx, spz), sd, s_gy, s_ry, s_dip))

    last_gy = mesh_grid.get_mesh_height(pts_m[-1][0], pts_m[-1][1]) if mesh_grid else ground_heights[-1]
    raw_samples.append((pts_m[-1], total_len, last_gy, last_gy + 0.02, 0.0))

    if len(raw_samples) < 2:
        return verts, trench_polys

    clean_samples = [raw_samples[0]]
    for sample in raw_samples[1:-1]:
        prev_pt = clean_samples[-1][0]
        cur_pt = sample[0]
        if math.hypot(cur_pt[0] - prev_pt[0], cur_pt[1] - prev_pt[1]) >= 0.02:
            clean_samples.append(sample)
    end_sample = raw_samples[-1]
    prev_pt = clean_samples[-1][0]
    if math.hypot(end_sample[0][0] - prev_pt[0], end_sample[0][1] - prev_pt[1]) < 0.02:
        if len(clean_samples) > 1:
            clean_samples[-1] = end_sample
    else:
        clean_samples.append(end_sample)

    if len(clean_samples) < 2:
        return verts, trench_polys

    sub_pts_m = [s[0] for s in clean_samples]
    sub_cum_d = [s[1] for s in clean_samples]
    sub_gy    = [s[2] for s in clean_samples]
    sub_ry    = [s[3] for s in clean_samples]
    sub_dip   = [s[4] for s in clean_samples]

    N_sub = len(sub_pts_m)

    # Normales miter por vértice y vectores tangentes por segmento para sellar codos sin grietas
    seg_fwd = []
    seg_n = []
    for k in range(N_sub - 1):
        sp0 = sub_pts_m[k]; sp1 = sub_pts_m[k + 1]
        kdx = sp1[0] - sp0[0]; kdz = sp1[1] - sp0[1]
        klen = math.hypot(kdx, kdz) or 1.0
        seg_fwd.append((kdx / klen, kdz / klen))
        seg_n.append((-kdz / klen, kdx / klen))

    sub_n = [seg_n[0]]
    for v in range(1, N_sub - 1):
        n_prev = seg_n[v - 1]
        n_curr = seg_n[v]
        sx = n_prev[0] + n_curr[0]
        sz = n_prev[1] + n_curr[1]
        s_len = math.hypot(sx, sz)
        if s_len < 1e-4:
            sub_n.append(n_curr)
        else:
            ux = sx / s_len
            uz = sz / s_len
            dot = ux * n_curr[0] + uz * n_curr[1]
            m = min(1.5, 1.0 / max(0.25, dot))
            sub_n.append((ux * m, uz * m))
    sub_n.append(seg_n[-1])

    seg_is_bridge_deck = []
    for i in range(N_sub - 1):
        mid_d_i = 0.5 * (sub_cum_d[i] + sub_cum_d[i + 1])
        avg_dip_i = 0.5 * (sub_dip[i] + sub_dip[i + 1])
        seg_is_bridge_deck.append((bridge_start_d <= mid_d_i <= bridge_end_d) and (avg_dip_i >= 0.80))

    def _get_sat_uv(pt):
        ux0, uz0, ux1, uz1 = -7712.602, -7834.476, 5439.987, 9103.524
        u_range = max(1.0, ux1 - ux0)
        v_range = max(1.0, uz1 - uz0)
        return ((pt[0] - ux0) / u_range, (pt[2] - uz0) / v_range)

    sat_col = (1.0, 1.0, 1.0, 0.0)
    outer_off = half_w + wall_thickness + coping_w + 2.5
    apron_target = apron_out if apron_out is not None else verts

    def _emit_ground_apron_band(bp0, bn0, bgy0, bp1, bn1, bgy1, off_min, off_max, n_strips):
        strip_step = (off_max - off_min) / float(n_strips)
        bnx0, bnz0 = bn0
        bnx1, bnz1 = bn1
        for s_k in range(n_strips):
            off_a = off_min + s_k * strip_step
            off_b = off_min + (s_k + 1) * strip_step
            a0_x = bp0[0] + off_a * bnx0; a0_z = bp0[1] + off_a * bnz0
            b0_x = bp0[0] + off_b * bnx0; b0_z = bp0[1] + off_b * bnz0
            a1_x = bp1[0] + off_a * bnx1; a1_z = bp1[1] + off_a * bnz1
            b1_x = bp1[0] + off_b * bnx1; b1_z = bp1[1] + off_b * bnz1
            a0_pt = (a0_x, (mesh_grid.get_mesh_height(a0_x, a0_z) if mesh_grid else bgy0) - 0.005, a0_z)
            b0_pt = (b0_x, (mesh_grid.get_mesh_height(b0_x, b0_z) if mesh_grid else bgy0) - 0.005, b0_z)
            a1_pt = (a1_x, (mesh_grid.get_mesh_height(a1_x, a1_z) if mesh_grid else bgy1) - 0.005, a1_z)
            b1_pt = (b1_x, (mesh_grid.get_mesh_height(b1_x, b1_z) if mesh_grid else bgy1) - 0.005, b1_z)
            uv_a0 = _get_sat_uv(a0_pt); uv_b0 = _get_sat_uv(b0_pt)
            uv_a1 = _get_sat_uv(a1_pt); uv_b1 = _get_sat_uv(b1_pt)
            apron_target.append((a0_pt, norm_up, uv_a0, sat_col, 0.0))
            apron_target.append((b0_pt, norm_up, uv_b0, sat_col, 0.0))
            apron_target.append((b1_pt, norm_up, uv_b1, sat_col, 0.0))
            apron_target.append((a0_pt, norm_up, uv_a0, sat_col, 0.0))
            apron_target.append((b1_pt, norm_up, uv_b1, sat_col, 0.0))
            apron_target.append((a1_pt, norm_up, uv_a1, sat_col, 0.0))

    for i in range(N_sub - 1):
        p0 = sub_pts_m[i]; p1 = sub_pts_m[i + 1]
        dx = p1[0] - p0[0]; dz = p1[1] - p0[1]
        seg_len = math.hypot(dx, dz)
        if seg_len < 0.02: continue

        px_norm, pz_norm = seg_n[i]
        nx0, nz0 = sub_n[i]
        nx1, nz1 = sub_n[i + 1]

        y0 = sub_ry[i]; y1 = sub_ry[i + 1]
        gy0 = sub_gy[i]; gy1 = sub_gy[i + 1]
        d0 = sub_cum_d[i]; d1 = sub_cum_d[i + 1]
        mid_d = (d0 + d1) * 0.5
        avg_dip = (sub_dip[i] + sub_dip[i + 1]) * 0.5

        # 1. Calzada de asfalto deprimida (con normales miter para continuidad en quiebres)
        q0 = (p0[0] - half_w * nx0, y0 + 0.10, p0[1] - half_w * nz0)
        q1 = (p0[0] + half_w * nx0, y0 + 0.10, p0[1] + half_w * nz0)
        q2 = (p1[0] + half_w * nx1, y1 + 0.10, p1[1] + half_w * nz1)
        q3 = (p1[0] - half_w * nx1, y1 + 0.10, p1[1] - half_w * nz1)

        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q1, norm_up, (1, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (1, 1), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q0, norm_up, (0, 0), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q2, norm_up, (1, 1), ASPHALT_BRIDGE_COL, 0.0))
        verts.append((q3, norm_up, (0, 1), ASPHALT_BRIDGE_COL, 0.0))

        # 2. Señalización horizontal de calzada (línea continua y líneas discontinuas de carril)
        stripe_y0 = y0 + 0.125
        stripe_y1 = y1 + 0.125
        col_yellow = (0.92, 0.82, 0.12, 0.95)
        col_white  = (0.95, 0.95, 0.95, 0.95)

        if is_oneway:
            # Línea amarilla continua en el borde izquierdo
            hw_edge = 0.075
            left_edge_off = -half_w + 0.35
            e0_l = (p0[0] + (left_edge_off - hw_edge) * nx0, stripe_y0, p0[1] + (left_edge_off - hw_edge) * nz0)
            e1_l = (p0[0] + (left_edge_off + hw_edge) * nx0, stripe_y0, p0[1] + (left_edge_off + hw_edge) * nz0)
            e2_l = (p1[0] + (left_edge_off + hw_edge) * nx1, stripe_y1, p1[1] + (left_edge_off + hw_edge) * nz1)
            e3_l = (p1[0] + (left_edge_off - hw_edge) * nx1, stripe_y1, p1[1] + (left_edge_off - hw_edge) * nz1)
            verts.append((e0_l, norm_up, (0, 0), col_yellow, 0.0))
            verts.append((e1_l, norm_up, (1, 0), col_yellow, 0.0))
            verts.append((e2_l, norm_up, (1, 1), col_yellow, 0.0))
            verts.append((e0_l, norm_up, (0, 0), col_yellow, 0.0))
            verts.append((e2_l, norm_up, (1, 1), col_yellow, 0.0))
            verts.append((e3_l, norm_up, (0, 1), col_yellow, 0.0))

            # Línea blanca continua en el borde derecho
            right_edge_off = half_w - 0.35
            e0_r = (p0[0] + (right_edge_off - hw_edge) * nx0, stripe_y0, p0[1] + (right_edge_off - hw_edge) * nz0)
            e1_r = (p0[0] + (right_edge_off + hw_edge) * nx0, stripe_y0, p0[1] + (right_edge_off + hw_edge) * nz0)
            e2_r = (p1[0] + (right_edge_off + hw_edge) * nx1, stripe_y1, p1[1] + (right_edge_off + hw_edge) * nz1)
            e3_r = (p1[0] + (right_edge_off - hw_edge) * nx1, stripe_y1, p1[1] + (right_edge_off - hw_edge) * nz1)
            verts.append((e0_r, norm_up, (0, 0), col_white, 0.0))
            verts.append((e1_r, norm_up, (1, 0), col_white, 0.0))
            verts.append((e2_r, norm_up, (1, 1), col_white, 0.0))
            verts.append((e0_r, norm_up, (0, 0), col_white, 0.0))
            verts.append((e2_r, norm_up, (1, 1), col_white, 0.0))
            verts.append((e3_r, norm_up, (0, 1), col_white, 0.0))

            # Líneas discontinuas blancas entre carriles (patrón 3m trazo / 3m brecha = ciclo 6m)
            num_lanes = 3 if road_w >= 10.5 else 2
            lane_w = road_w / float(num_lanes)
            hw_dash = 0.06
            if (mid_d % 6.0) < 3.0:
                for l_idx in range(1, num_lanes):
                    lane_off = -half_w + l_idx * lane_w
                    dq0 = (p0[0] + (lane_off - hw_dash) * nx0, stripe_y0, p0[1] + (lane_off - hw_dash) * nz0)
                    dq1 = (p0[0] + (lane_off + hw_dash) * nx0, stripe_y0, p0[1] + (lane_off + hw_dash) * nz0)
                    dq2 = (p1[0] + (lane_off + hw_dash) * nx1, stripe_y1, p1[1] + (lane_off + hw_dash) * nz1)
                    dq3 = (p1[0] + (lane_off - hw_dash) * nx1, stripe_y1, p1[1] + (lane_off - hw_dash) * nz1)
                    verts.append((dq0, norm_up, (0, 0), col_white, 0.0))
                    verts.append((dq1, norm_up, (1, 0), col_white, 0.0))
                    verts.append((dq2, norm_up, (1, 1), col_white, 0.0))
                    verts.append((dq0, norm_up, (0, 0), col_white, 0.0))
                    verts.append((dq2, norm_up, (1, 1), col_white, 0.0))
                    verts.append((dq3, norm_up, (0, 1), col_white, 0.0))
        else:
            # En calzadas de dos sentidos: línea central amarilla continua
            hw_stripe = 0.09
            sq0 = (p0[0] - hw_stripe * nx0, stripe_y0, p0[1] - hw_stripe * nz0)
            sq1 = (p0[0] + hw_stripe * nx0, stripe_y0, p0[1] + hw_stripe * nz0)
            sq2 = (p1[0] + hw_stripe * nx1, stripe_y1, p1[1] + hw_stripe * nz1)
            sq3 = (p1[0] - hw_stripe * nx1, stripe_y1, p1[1] - hw_stripe * nz1)
            verts.append((sq0, norm_up, (0, 0), col_yellow, 0.0))
            verts.append((sq1, norm_up, (1, 0), col_yellow, 0.0))
            verts.append((sq2, norm_up, (1, 1), col_yellow, 0.0))
            verts.append((sq0, norm_up, (0, 0), col_yellow, 0.0))
            verts.append((sq2, norm_up, (1, 1), col_yellow, 0.0))
            verts.append((sq3, norm_up, (0, 1), col_yellow, 0.0))

            if road_w >= 10.5:
                hw_dash = 0.06
                if (mid_d % 6.0) < 3.0:
                    for side_mult in (-0.5, 0.5):
                        lane_off = half_w * side_mult
                        dq0 = (p0[0] + (lane_off - hw_dash) * nx0, stripe_y0, p0[1] + (lane_off - hw_dash) * nz0)
                        dq1 = (p0[0] + (lane_off + hw_dash) * nx0, stripe_y0, p0[1] + (lane_off + hw_dash) * nz0)
                        dq2 = (p1[0] + (lane_off + hw_dash) * nx1, stripe_y1, p1[1] + (lane_off + hw_dash) * nz1)
                        dq3 = (p1[0] + (lane_off - hw_dash) * nx1, stripe_y1, p1[1] + (lane_off - hw_dash) * nz1)
                        verts.append((dq0, norm_up, (0, 0), col_white, 0.0))
                        verts.append((dq1, norm_up, (1, 0), col_white, 0.0))
                        verts.append((dq2, norm_up, (1, 1), col_white, 0.0))
                        verts.append((dq0, norm_up, (0, 0), col_white, 0.0))
                        verts.append((dq2, norm_up, (1, 1), col_white, 0.0))
                        verts.append((dq3, norm_up, (0, 1), col_white, 0.0))

        is_bridge_deck = seg_is_bridge_deck[i]
        is_under_bridge = is_bridge_deck or ((bridge_start_d <= mid_d <= bridge_end_d) and (avg_dip >= 0.80))

        # Si el desnivel es apreciable (dip > 0.01), construir muros de contención y albardillas
        if avg_dip > 0.01:
            wall_top_y0 = gy0 + 0.12 + 0.13 * min(1.0, sub_dip[i] * 5.0)
            wall_top_y1 = gy1 + 0.12 + 0.13 * min(1.0, sub_dip[i + 1] * 5.0)

            # 3. Muro de contención derecho (interior + albardilla + cara exterior cerrada)
            w_r0_bot = q1
            w_r1_bot = q2
            w_r0_top = (p0[0] + (half_w + wall_thickness) * nx0, wall_top_y0, p0[1] + (half_w + wall_thickness) * nz0)
            w_r1_top = (p1[0] + (half_w + wall_thickness) * nx1, wall_top_y1, p1[1] + (half_w + wall_thickness) * nz1)
            norm_r_in = (-px_norm, 0.0, -pz_norm)
            norm_r_out = (px_norm, 0.0, pz_norm)

            verts.append((w_r0_bot, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_r0_top, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_r1_top, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_r0_bot, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_r1_top, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_r1_bot, norm_r_in, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Albardilla superior derecha
            cop_r0_out = (p0[0] + (half_w + wall_thickness + coping_w) * nx0, wall_top_y0, p0[1] + (half_w + wall_thickness + coping_w) * nz0)
            cop_r1_out = (p1[0] + (half_w + wall_thickness + coping_w) * nx1, wall_top_y1, p1[1] + (half_w + wall_thickness + coping_w) * nz1)
            verts.append((w_r0_top, norm_up, (0, 0), coping_col, 0.0))
            verts.append((cop_r0_out, norm_up, (0, 0), coping_col, 0.0))
            verts.append((cop_r1_out, norm_up, (0, 0), coping_col, 0.0))
            verts.append((w_r0_top, norm_up, (0, 0), coping_col, 0.0))
            verts.append((cop_r1_out, norm_up, (0, 0), coping_col, 0.0))
            verts.append((w_r1_top, norm_up, (0, 0), coping_col, 0.0))

            # Muro vertical exterior derecho (cierra volumen sólido bajo la albardilla)
            cop_r0_bot_ext = (cop_r0_out[0], min(y0, gy0) - 0.15, cop_r0_out[2])
            cop_r1_bot_ext = (cop_r1_out[0], min(y1, gy1) - 0.15, cop_r1_out[2])
            verts.append((cop_r0_bot_ext, norm_r_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_r1_out, norm_r_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_r0_out, norm_r_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_r0_bot_ext, norm_r_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_r1_bot_ext, norm_r_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_r1_out, norm_r_out, (0, 0), CONCRETE_PIER_COL, 0.0))

            # 4. Muro de contención izquierdo (interior + albardilla + cara exterior cerrada)
            w_l0_bot = q0
            w_l1_bot = q3
            w_l0_top = (p0[0] - (half_w + wall_thickness) * nx0, wall_top_y0, p0[1] - (half_w + wall_thickness) * nz0)
            w_l1_top = (p1[0] - (half_w + wall_thickness) * nx1, wall_top_y1, p1[1] - (half_w + wall_thickness) * nz1)
            norm_l_in = (px_norm, 0.0, pz_norm)
            norm_l_out = (-px_norm, 0.0, -pz_norm)

            verts.append((w_l0_bot, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_l1_top, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_l0_top, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_l0_bot, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_l1_bot, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((w_l1_top, norm_l_in, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Albardilla superior izquierda
            cop_l0_out = (p0[0] - (half_w + wall_thickness + coping_w) * nx0, wall_top_y0, p0[1] - (half_w + wall_thickness + coping_w) * nz0)
            cop_l1_out = (p1[0] - (half_w + wall_thickness + coping_w) * nx1, wall_top_y1, p1[1] - (half_w + wall_thickness + coping_w) * nz1)
            verts.append((cop_l0_out, norm_up, (0, 0), coping_col, 0.0))
            verts.append((w_l0_top, norm_up, (0, 0), coping_col, 0.0))
            verts.append((w_l1_top, norm_up, (0, 0), coping_col, 0.0))
            verts.append((cop_l0_out, norm_up, (0, 0), coping_col, 0.0))
            verts.append((w_l1_top, norm_up, (0, 0), coping_col, 0.0))
            verts.append((cop_l1_out, norm_up, (0, 0), coping_col, 0.0))

            # Muro vertical exterior izquierdo (cierra volumen sólido bajo la albardilla)
            cop_l0_bot_ext = (cop_l0_out[0], min(y0, gy0) - 0.15, cop_l0_out[2])
            cop_l1_bot_ext = (cop_l1_out[0], min(y1, gy1) - 0.15, cop_l1_out[2])
            verts.append((cop_l0_bot_ext, norm_l_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_l0_out, norm_l_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_l1_out, norm_l_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_l0_bot_ext, norm_l_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_l1_out, norm_l_out, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((cop_l1_bot_ext, norm_l_out, (0, 0), CONCRETE_PIER_COL, 0.0))

            # 5. Barandales perimetrales superiores de protección longitudinal:
            if not is_under_bridge and avg_dip > 0.20:
                r_pts0 = (cop_r0_out[0], cop_r0_out[2])
                r_pts1 = (cop_r1_out[0], cop_r1_out[2])
                verts.extend(make_railing_3d(r_pts0, r_pts1, wall_top_y0, wall_top_y1, height=1.05))

                l_pts0 = (cop_l0_out[0], cop_l0_out[2])
                l_pts1 = (cop_l1_out[0], cop_l1_out[2])
                verts.extend(make_railing_3d(l_pts0, l_pts1, wall_top_y0, wall_top_y1, height=1.05))

            # 5b. Faldón / collar a nivel de suelo (gy - 0.005) subdividido en 4 franjas por lado
            inner_off = half_w + wall_thickness * 0.5
            _emit_ground_apron_band(p0, (nx0, nz0), gy0, p1, (nx1, nz1), gy1, inner_off, outer_off, 4)
            _emit_ground_apron_band(p0, (nx0, nz0), gy0, p1, (nx1, nz1), gy1, -outer_off, -inner_off, 4)

            # Sello inferior bajo la calzada en bocas de rampa para evitar huecos de sub-cuadrantes sin bloquear carriles
            if avg_dip <= 0.12:
                seal_y0 = min(y0, gy0) - 0.02
                seal_y1 = min(y1, gy1) - 0.02
                fl0 = (cop_l0_out[0], seal_y0, cop_l0_out[2])
                fr0 = (cop_r0_out[0], seal_y0, cop_r0_out[2])
                fr1 = (cop_r1_out[0], seal_y1, cop_r1_out[2])
                fl1 = (cop_l1_out[0], seal_y1, cop_l1_out[2])
                uv_cl0 = _get_sat_uv(fl0); uv_cr0 = _get_sat_uv(fr0)
                uv_cl1 = _get_sat_uv(fl1); uv_cr1 = _get_sat_uv(fr1)
                verts.append((fl0, norm_up, uv_cl0, sat_col, 0.0))
                verts.append((fr0, norm_up, uv_cr0, sat_col, 0.0))
                verts.append((fr1, norm_up, uv_cr1, sat_col, 0.0))
                verts.append((fl0, norm_up, uv_cl0, sat_col, 0.0))
                verts.append((fr1, norm_up, uv_cr1, sat_col, 0.0))
                verts.append((fl1, norm_up, uv_cl1, sat_col, 0.0))

            # Polígono de trinchera ampliado al borde exterior de albardilla con normales miter exactas
            trench_poly = [
                (cop_l0_out[0], cop_l0_out[2]),
                (cop_r0_out[0], cop_r0_out[2]),
                (cop_r1_out[0], cop_r1_out[2]),
                (cop_l1_out[0], cop_l1_out[2])
            ]
            trench_polys.append(trench_poly)
        else:
            # Faldón a nivel de suelo (gy - 0.005) en extremos de rampa para sellar sub-cuadrantes contiguos al remate
            _emit_ground_apron_band(p0, (nx0, nz0), gy0, p1, (nx1, nz1), gy1, -outer_off, outer_off, 8)

        # 6. SECCIÓN DE PUENTE SUPERIOR TRANSVERSAL (Losa de cruce superficial)
        if is_bridge_deck:
            roof_bot_y0 = y0 + clear_height
            roof_bot_y1 = y1 + clear_height
            roof_top_y0 = gy0 + 0.12
            roof_top_y1 = gy1 + 0.12

            br_q0 = (p0[0] - half_w * nx0, roof_bot_y0, p0[1] - half_w * nz0)
            br_q1 = (p0[0] + half_w * nx0, roof_bot_y0, p0[1] + half_w * nz0)
            br_q2 = (p1[0] + half_w * nx1, roof_bot_y1, p1[1] + half_w * nz1)
            br_q3 = (p1[0] - half_w * nx1, roof_bot_y1, p1[1] - half_w * nz1)

            # Intradós bajo el puente
            verts.append((br_q0, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((br_q2, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((br_q1, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((br_q0, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((br_q3, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))
            verts.append((br_q2, norm_down, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Extradós del puente a nivel de superficie (alineado al borde exterior de albardillas)
            deck_hw = half_w + wall_thickness + coping_w
            top_q0 = (p0[0] - deck_hw * nx0, roof_top_y0, p0[1] - deck_hw * nz0)
            top_q1 = (p0[0] + deck_hw * nx0, roof_top_y0, p0[1] + deck_hw * nz0)
            top_q2 = (p1[0] + deck_hw * nx1, roof_top_y1, p1[1] + deck_hw * nz1)
            top_q3 = (p1[0] - deck_hw * nx1, roof_top_y1, p1[1] - deck_hw * nz1)

            verts.append((top_q0, norm_up, (0, 0), bridge_surface_col, 0.0))
            verts.append((top_q1, norm_up, (0, 0), bridge_surface_col, 0.0))
            verts.append((top_q2, norm_up, (0, 0), bridge_surface_col, 0.0))
            verts.append((top_q0, norm_up, (0, 0), bridge_surface_col, 0.0))
            verts.append((top_q2, norm_up, (0, 0), bridge_surface_col, 0.0))
            verts.append((top_q3, norm_up, (0, 0), bridge_surface_col, 0.0))

            # Portales de entrada y salida del puente y parapetos de seguridad (transición única)
            is_start_bridge = is_bridge_deck and (i == 0 or not seg_is_bridge_deck[i - 1])
            if is_start_bridge:
                portal_norm = (-seg_fwd[i][0], 0.0, -seg_fwd[i][1])
                verts.append((br_q0, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((br_q1, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((top_q1, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((br_q0, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((top_q1, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((top_q0, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))

                # Parapeto de protección sobre el portal frontal (altura 0.95m)
                parapet_h = 0.95
                p_l_bot = top_q0; p_r_bot = top_q1
                p_l_top = (p_l_bot[0], p_l_bot[1] + parapet_h, p_l_bot[2])
                p_r_top = (p_r_bot[0], p_r_bot[1] + parapet_h, p_r_bot[2])
                verts.append((p_l_bot, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_r_bot, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_r_top, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_l_bot, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_r_top, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_l_top, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))

            is_end_bridge = is_bridge_deck and (i == N_sub - 2 or not seg_is_bridge_deck[i + 1])
            if is_end_bridge:
                portal_norm = (seg_fwd[i][0], 0.0, seg_fwd[i][1])
                verts.append((br_q2, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((br_q3, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((top_q3, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((br_q2, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((top_q3, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((top_q2, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))

                # Parapeto de protección sobre el portal posterior (altura 0.95m)
                parapet_h = 0.95
                p_l_bot = top_q3; p_r_bot = top_q2
                p_l_top = (p_l_bot[0], p_l_bot[1] + parapet_h, p_l_bot[2])
                p_r_top = (p_r_bot[0], p_r_bot[1] + parapet_h, p_r_bot[2])
                verts.append((p_l_bot, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_r_bot, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_r_top, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_l_bot, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_r_top, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))
                verts.append((p_l_top, portal_norm, (0, 0), CONCRETE_PIER_COL, 0.0))

            # Luminarias lineales en el interior techado bajo el puente
            lamp_col = (1.0, 0.95, 0.8, 0.95)
            lamp_y = (roof_bot_y0 + roof_bot_y1) * 0.5 - 0.06
            lamp_cx = (p0[0] + p1[0]) * 0.5
            lamp_cz = (p0[1] + p1[1]) * 0.5
            verts.extend(make_box(lamp_cx, lamp_y, lamp_cz, 0.50, 0.12, seg_len * 0.85, color=lamp_col, emission=1.0))

    # Sellos longitudinales de 4.0m antes del inicio y después del fin para cubrir sub-cuadrantes en remates
    ext0 = (sub_pts_m[0][0] - 4.0 * seg_fwd[0][0], sub_pts_m[0][1] - 4.0 * seg_fwd[0][1])
    ext0_gy = mesh_grid.get_mesh_height(ext0[0], ext0[1]) if mesh_grid else sub_gy[0]
    _emit_ground_apron_band(ext0, sub_n[0], ext0_gy, sub_pts_m[0], sub_n[0], sub_gy[0], -outer_off, outer_off, 8)

    ext1 = (sub_pts_m[-1][0] + 4.0 * seg_fwd[-1][0], sub_pts_m[-1][1] + 4.0 * seg_fwd[-1][1])
    ext1_gy = mesh_grid.get_mesh_height(ext1[0], ext1[1]) if mesh_grid else sub_gy[-1]
    _emit_ground_apron_band(sub_pts_m[-1], sub_n[-1], sub_gy[-1], ext1, sub_n[-1], ext1_gy, -outer_off, outer_off, 8)

    return verts, trench_polys
