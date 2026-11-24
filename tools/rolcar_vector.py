"""
rolcar_vector.py
================
Generador 100% procedimental en código (cero PNGs / cero atlas) para:
  1. Emblema ovalado doble anillo ROLCAR.
  2. Tipografía vectorial 3D en relieve ('ROLCAR', 'ServiparteS', 'REFACCIONARIAS')
     con relación de aspecto fija (sin estiramiento horizontal).
  3. Fachadas completas estilo real Rolcar (zócalos, pilastras, cintillo verde/amarillo,
     parapeto blanco con doble línea verde + óvalo superior, vitrinas y bolardos).
  4. Anuncio elevado / tótem doble cara 100% vectorial en código.
"""
import math

MAT_ROL_SOLID = 1.14   # Concreto/stucco/molduras/tipografía Rolcar (shaders/fragment.frag)
MAT_ROL_SHUTTER = 1.18 # Cortina metálica de acero procedural en GLSL (fuera de photoTex 1.25-1.35)

COL_WHITE       = (0.94, 0.94, 0.92, MAT_ROL_SOLID)
COL_GREEN       = (0.04, 0.45, 0.18, MAT_ROL_SOLID)
COL_GREEN_BR    = (0.04, 0.56, 0.22, MAT_ROL_SOLID)
COL_YELLOW      = (0.94, 0.75, 0.05, MAT_ROL_SOLID)
COL_RED         = (0.86, 0.05, 0.05, MAT_ROL_SOLID)
COL_BLACK       = (0.07, 0.07, 0.07, MAT_ROL_SOLID)
COL_PLINTH      = (0.22, 0.16, 0.13, MAT_ROL_SOLID)
COL_STEEL       = (0.62, 0.65, 0.68, MAT_ROL_SOLID)
COL_BASE_CONC   = (0.48, 0.48, 0.50, MAT_ROL_SOLID)
COL_SHUTTER_MAT = (0.48, 0.51, 0.53, MAT_ROL_SHUTTER)


def _emit_quad_on_plane(verts, ox, oy, oz, rx, rz, nx, nz,
                        u0, v0, u1, v1, depth, col, emission=0.0):
    """Emite un quad recto sobre un plano vertical definido por origen, right y normal."""
    p0 = (ox + rx * u0 + nx * depth, oy + v0, oz + rz * u0 + nz * depth)
    p1 = (ox + rx * u1 + nx * depth, oy + v0, oz + rz * u1 + nz * depth)
    p2 = (ox + rx * u1 + nx * depth, oy + v1, oz + rz * u1 + nz * depth)
    p3 = (ox + rx * u0 + nx * depth, oy + v1, oz + rz * u0 + nz * depth)
    nrm = (nx, 0.0, nz)
    verts.append((p0, nrm, (0.0, 1.0), col, emission))
    verts.append((p1, nrm, (1.0, 1.0), col, emission))
    verts.append((p2, nrm, (1.0, 0.0), col, emission))
    verts.append((p0, nrm, (0.0, 1.0), col, emission))
    verts.append((p2, nrm, (1.0, 0.0), col, emission))
    verts.append((p3, nrm, (0.0, 0.0), col, emission))


def _emit_seg_on_plane(verts, ox, oy, oz, rx, rz, nx, nz,
                       ax, ay, bx, by, half_t, depth, col, emission=0.0):
    """Emite un trazo vectorial inclinado u ortogonal de grosor 2*half_t sobre el plano."""
    dx, dy = bx - ax, by - ay
    seg_l = math.hypot(dx, dy)
    if seg_l < 1e-5:
        return
    px, py = (-dy / seg_l) * half_t, (dx / seg_l) * half_t
    pts = [
        (ax - px, ay - py),
        (bx - px, by - py),
        (bx + px, by + py),
        (ax + px, ay + py),
    ]
    nrm = (nx, 0.0, nz)
    q = [(ox + rx * u + nx * depth, oy + v, oz + rz * u + nz * depth) for u, v in pts]
    verts.append((q[0], nrm, (0.0, 0.0), col, emission))
    verts.append((q[1], nrm, (1.0, 0.0), col, emission))
    verts.append((q[2], nrm, (1.0, 1.0), col, emission))
    verts.append((q[0], nrm, (0.0, 0.0), col, emission))
    verts.append((q[2], nrm, (1.0, 1.0), col, emission))
    verts.append((q[3], nrm, (0.0, 1.0), col, emission))


# Glifos vectoriales en caja normalizada x in [0, 1], y in [0, 1]
# Cada trazo es ((x0, y0), (x1, y1))
_VECTOR_FONT = {
    "R": [((0.12, 0.0), (0.12, 1.0)), ((0.12, 0.92), (0.76, 0.92)),
          ((0.80, 0.88), (0.80, 0.54)), ((0.12, 0.50), (0.76, 0.50)),
          ((0.46, 0.50), (0.82, 0.0))],
    "O": [((0.14, 0.08), (0.14, 0.92)), ((0.86, 0.08), (0.86, 0.92)),
          ((0.18, 0.92), (0.82, 0.92)), ((0.18, 0.08), (0.82, 0.08))],
    "L": [((0.14, 0.0), (0.14, 1.0)), ((0.14, 0.08), (0.84, 0.08))],
    "C": [((0.14, 0.10), (0.14, 0.90)), ((0.18, 0.92), (0.86, 0.92)),
          ((0.18, 0.08), (0.86, 0.08))],
    "A": [((0.08, 0.0), (0.44, 0.96)), ((0.56, 0.96), (0.92, 0.0)),
          ((0.40, 0.94), (0.60, 0.94)), ((0.22, 0.36), (0.78, 0.36))],
    "E": [((0.14, 0.0), (0.14, 1.0)), ((0.14, 0.92), (0.84, 0.92)),
          ((0.14, 0.50), (0.72, 0.50)), ((0.14, 0.08), (0.84, 0.08))],
    "F": [((0.14, 0.0), (0.14, 1.0)), ((0.14, 0.92), (0.84, 0.92)),
          ((0.14, 0.50), (0.72, 0.50))],
    "I": [((0.20, 0.92), (0.80, 0.92)), ((0.50, 0.08), (0.50, 0.92)),
          ((0.20, 0.08), (0.80, 0.08))],
    "N": [((0.14, 0.0), (0.14, 1.0)), ((0.16, 0.96), (0.84, 0.04)),
          ((0.86, 0.0), (0.86, 1.0))],
    "S": [((0.82, 0.90), (0.20, 0.90)), ((0.16, 0.90), (0.16, 0.52)),
          ((0.18, 0.52), (0.82, 0.48)), ((0.84, 0.48), (0.84, 0.10)),
          ((0.82, 0.08), (0.16, 0.08))],
    # Minúsculas cursivas / estilizadas para 'ServiparteS'
    "e": [((0.16, 0.46), (0.82, 0.46)), ((0.80, 0.48), (0.72, 0.72)),
          ((0.70, 0.74), (0.24, 0.74)), ((0.18, 0.70), (0.18, 0.14)),
          ((0.22, 0.10), (0.82, 0.10))],
    "r": [((0.22, 0.06), (0.22, 0.74)), ((0.24, 0.62), (0.52, 0.74)),
          ((0.52, 0.74), (0.82, 0.66))],
    "v": [((0.14, 0.74), (0.50, 0.08)), ((0.50, 0.08), (0.86, 0.74))],
    "i": [((0.46, 0.06), (0.46, 0.66)), ((0.46, 0.84), (0.46, 0.98))],
    "p": [((0.20, -0.22), (0.20, 0.74)), ((0.22, 0.72), (0.78, 0.72)),
          ((0.82, 0.68), (0.82, 0.24)), ((0.78, 0.18), (0.22, 0.18))],
    "a": [((0.22, 0.68), (0.74, 0.68)), ((0.78, 0.66), (0.78, 0.08)),
          ((0.76, 0.42), (0.24, 0.42)), ((0.20, 0.40), (0.20, 0.12)),
          ((0.24, 0.08), (0.80, 0.08))],
    "t": [((0.46, 0.08), (0.46, 0.96)), ((0.20, 0.68), (0.78, 0.68)),
          ((0.48, 0.08), (0.80, 0.10))],
}


def emit_vector_text(verts, ox, oy, oz, rx, rz, nx, nz,
                     text, cx, cy, char_h, spacing_scale, stroke_frac,
                     depth, col, skew=0.0, emission=0.0):
    """Dibuja una cadena vectorial 3D centrada en (cx, cy) sobre el plano."""
    if not text:
        return
    char_w = char_h * 0.66
    step = char_w * spacing_scale
    total_w = (len(text) - 1) * step + char_w
    start_x = cx - total_w * 0.5
    half_t = char_h * stroke_frac
    for idx, ch in enumerate(text):
        strokes = _VECTOR_FONT.get(ch)
        if not strokes:
            continue
        gx = start_x + idx * step
        for (x0, y0), (x1, y1) in strokes:
            ax = gx + x0 * char_w + y0 * char_h * skew
            ay = cy - char_h * 0.5 + y0 * char_h
            bx = gx + x1 * char_w + y1 * char_h * skew
            by = cy - char_h * 0.5 + y1 * char_h
            _emit_seg_on_plane(
                verts, ox, oy, oz, rx, rz, nx, nz,
                ax, ay, bx, by, half_t, depth, col, emission=emission
            )


def emit_rolcar_oval_crest(verts, ox, oy, oz, rx, rz, nx, nz,
                           cx, cy, width, height, depth,
                           emission=0.0, with_wordmark=True):
    """Dibuja el emblema ovalado doble borde verde ROLCAR 100% en geometría vectorial."""
    segments = 24
    # Fondo blanco relleno del óvalo (disco elíptico)
    nrm = (nx, 0.0, nz)
    p_center = (ox + rx * cx + nx * depth, oy + cy, oz + rz * cx + nz * depth)
    hw, hh = width * 0.5, height * 0.5
    for i in range(segments):
        a0 = 2.0 * math.pi * i / segments
        a1 = 2.0 * math.pi * (i + 1) / segments
        u0, v0 = cx + hw * math.cos(a0), cy + hh * math.sin(a0)
        u1, v1 = cx + hw * math.cos(a1), cy + hh * math.sin(a1)
        q0 = (ox + rx * u0 + nx * depth, oy + v0, oz + rz * u0 + nz * depth)
        q1 = (ox + rx * u1 + nx * depth, oy + v1, oz + rz * u1 + nz * depth)
        verts.append((p_center, nrm, (0.5, 0.5), COL_WHITE, emission))
        verts.append((q0, nrm, (0.5, 0.5), COL_WHITE, emission))
        verts.append((q1, nrm, (0.5, 0.5), COL_WHITE, emission))

    # Doble anillo verde concéntrico
    for ring_scale, thick in ((0.96, height * 0.055), (0.80, height * 0.045)):
        rw = hw * ring_scale
        rh = hh * ring_scale
        for i in range(segments):
            a0 = 2.0 * math.pi * i / segments
            a1 = 2.0 * math.pi * (i + 1) / segments
            _emit_seg_on_plane(
                verts, ox, oy, oz, rx, rz, nx, nz,
                cx + rw * math.cos(a0), cy + rh * math.sin(a0),
                cx + rw * math.cos(a1), cy + rh * math.sin(a1),
                thick, depth + 0.008, COL_GREEN_BR, emission=emission
            )

    if with_wordmark:
        emit_vector_text(
            verts, ox, oy, oz, rx, rz, nx, nz,
            "ROLCAR", cx, cy,
            char_h=height * 0.42, spacing_scale=1.18, stroke_frac=0.10,
            depth=depth + 0.015, col=COL_GREEN_BR, emission=emission
        )


def emit_rolcar_marquee_sign(verts, ox, oy, oz, rx, rz, nx, nz,
                             wall_w, parapet_bot, parapet_top, depth=0.045, emission=0.16):
    """
    Genera en el parapeto superior blanco de la fachada:
      - Doble franja horizontal verde paralela arriba (interrumpida por el óvalo central).
      - 'ROLCAR' (verde) + 'ServiparteS' (itálica negra) a escala fija sin deformación.
      - 'REFACCIONARIAS' (rojo) centrado debajo.
    """
    par_h = parapet_top - parapet_bot
    if wall_w < 3.6 or par_h < 1.0:
        return

    # Doble línea superior horizontal continua a todo lo ancho
    s1_y0, s1_y1 = parapet_top - par_h * 0.14, parapet_top - par_h * 0.08
    s2_y0, s2_y1 = parapet_top - par_h * 0.23, parapet_top - par_h * 0.17
    ov_w = min(par_h * 0.85, wall_w * 0.18)
    ov_h = par_h * 0.28
    ov_cy = parapet_top - par_h * 0.155
    half_wall = wall_w * 0.5
    gap_half = ov_w * 0.58

    for sy0, sy1 in ((s1_y0, s1_y1), (s2_y0, s2_y1)):
        if wall_w >= 5.5:
            _emit_quad_on_plane(verts, ox, oy, oz, rx, rz, nx, nz,
                                -half_wall, sy0, -gap_half, sy1, depth * 0.55, COL_GREEN)
            _emit_quad_on_plane(verts, ox, oy, oz, rx, rz, nx, nz,
                                gap_half, sy0, half_wall, sy1, depth * 0.55, COL_GREEN)
        else:
            _emit_quad_on_plane(verts, ox, oy, oz, rx, rz, nx, nz,
                                -half_wall, sy0, half_wall, sy1, depth * 0.55, COL_GREEN)

    if wall_w < 5.0:
        return

    emit_rolcar_oval_crest(
        verts, ox, oy, oz, rx, rz, nx, nz,
        0.0, ov_cy, ov_w, ov_h, depth * 0.85, emission=emission * 0.6, with_wordmark=True
    )

    # Relación de aspecto fija (4.6:1) para que nunca se estire en paredes anchas
    avail_h = (s2_y0 - parapet_bot) * 0.86
    sign_h = min(avail_h, (wall_w * 0.84) / 4.6)
    sign_w = sign_h * 4.6

    # Línea principal: ROLCAR (izq) + ServiparteS (der)
    top_y = parapet_bot + (s2_y0 - parapet_bot) * 0.64
    main_h = sign_h * 0.48
    rolcar_cx = -sign_w * 0.24
    servi_cx = sign_w * 0.23

    emit_vector_text(
        verts, ox, oy, oz, rx, rz, nx, nz,
        "ROLCAR", rolcar_cx, top_y,
        char_h=main_h, spacing_scale=1.18, stroke_frac=0.10,
        depth=depth, col=COL_GREEN_BR, emission=emission
    )
    emit_vector_text(
        verts, ox, oy, oz, rx, rz, nx, nz,
        "ServiparteS", servi_cx, top_y - main_h * 0.04,
        char_h=main_h * 0.72, spacing_scale=0.96, stroke_frac=0.075,
        depth=depth, col=COL_BLACK, skew=0.22, emission=0.0
    )

    # Línea secundaria inferior: REFACCIONARIAS en rojo vibrante
    sub_y = parapet_bot + (s2_y0 - parapet_bot) * 0.24
    emit_vector_text(
        verts, ox, oy, oz, rx, rz, nx, nz,
        "REFACCIONARIAS", 0.0, sub_y,
        char_h=sign_h * 0.24, spacing_scale=1.32, stroke_frac=0.10,
        depth=depth, col=COL_RED, emission=emission * 0.8
    )


def build_rolcar_storefront_geometry(verts, polygon, ground_heights, height,
                                     make_cylinder_fn):
    """
    Construye una sucursal Rolcar completa en geometría 3D + shader procedural (cero PNGs).
    """
    # Normalizar sentido horario negativo (area2 < 0) para que wall_norm apunte AFUERA
    # y (p1 - p0) siempre vaya izquierda->derecha viendo desde la calle.
    poly = list(polygon)
    ghs = list(ground_heights)
    n = len(poly)
    area2 = sum(
        poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
        for i in range(n)
    )
    if area2 > 0.0:
        poly.reverse()
        ghs.reverse()

    vit_h = height * 0.54
    band_mid = vit_h + height * 0.04
    band_top = vit_h + height * 0.08
    base_y = min(ghs) if ghs else 0.0

    for i in range(n):
        p0 = poly[i]
        p1 = poly[(i + 1) % n]
        dx = p1[0] - p0[0]
        dz = p1[1] - p0[1]
        edge_len = math.hypot(dx, dz)
        if edge_len < 0.01:
            continue

        rx, rz = dx / edge_len, dz / edge_len
        nx, nz = -rz, rx  # Normal hacia afuera garantizada (area2 < 0)
        gy0, gy1 = ghs[i], ghs[(i + 1) % n]
        oy = base_y
        ox = 0.5 * (p0[0] + p1[0])
        oz = 0.5 * (p0[1] + p1[1])
        half_w = edge_len * 0.5

        # 1. Parapeto blanco superior (vitrinas hasta techo)
        _emit_quad_on_plane(
            verts, ox, oy, oz, rx, rz, nx, nz,
            -half_w, band_top, half_w, height, 0.0, COL_WHITE
        )

        # 2. Cintillo divisorio verde y amarillo continuo saliente
        _emit_quad_on_plane(
            verts, ox, oy, oz, rx, rz, nx, nz,
            -half_w, vit_h, half_w, band_mid, 0.035, COL_YELLOW
        )
        _emit_quad_on_plane(
            verts, ox, oy, oz, rx, rz, nx, nz,
            -half_w, band_mid, half_w, band_top, 0.035, COL_GREEN
        )

        # 3. Planta baja modular: pilastras blancas + zoclo oscuro + vitrina procedural (GLSL 1.28)
        n_bays = max(1, int(round(edge_len / 3.8)))
        bay_w = edge_len / float(n_bays)
        pilaster_w = min(0.36, bay_w * 0.14)
        plinth_h = min(0.45, vit_h * 0.16)

        for bi in range(n_bays):
            bu0 = -half_w + bi * bay_w
            bu1 = bu0 + bay_w
            # Pilastra izquierda + derecha si último módulo
            _emit_quad_on_plane(
                verts, ox, oy, oz, rx, rz, nx, nz,
                bu0, plinth_h, bu0 + pilaster_w, vit_h, 0.05, COL_WHITE
            )
            _emit_quad_on_plane(
                verts, ox, oy, oz, rx, rz, nx, nz,
                bu0, 0.0, bu0 + pilaster_w, plinth_h, 0.06, COL_PLINTH
            )
            if bi == n_bays - 1:
                _emit_quad_on_plane(
                    verts, ox, oy, oz, rx, rz, nx, nz,
                    bu1 - pilaster_w, plinth_h, bu1, vit_h, 0.05, COL_WHITE
                )
                _emit_quad_on_plane(
                    verts, ox, oy, oz, rx, rz, nx, nz,
                    bu1 - pilaster_w, 0.0, bu1, plinth_h, 0.06, COL_PLINTH
                )
            # Sardinel inferior de vitrina
            gu0 = bu0 + pilaster_w
            gu1 = bu1 - (pilaster_w if bi == n_bays - 1 else 0.0)
            sill_h = 0.14
            _emit_quad_on_plane(
                verts, ox, oy, oz, rx, rz, nx, nz,
                gu0, 0.0, gu1, sill_h, 0.02, COL_PLINTH
            )
            # Cortina de acero metálica procedural en GLSL (matID=1.18)
            _emit_quad_on_plane(
                verts, ox, oy, oz, rx, rz, nx, nz,
                gu0, sill_h, gu1, vit_h, 0.0, COL_SHUTTER_MAT
            )

        # 4. Marquesina vectorial 3D fija (ROLCAR ServiparteS REFACCIONARIAS + óvalo)
        emit_rolcar_marquee_sign(
            verts, ox, oy, oz, rx, rz, nx, nz,
            edge_len, band_top, height, depth=0.05, emission=0.16
        )

        # 5. Bolardos amarillos de seguridad frente a fachadas largas
        if edge_len >= 6.5:
            n_bol = max(2, int(edge_len / 2.6))
            for k in range(n_bol):
                t_b = (k + 0.5) / float(n_bol)
                bx = p0[0] + t_b * dx + nx * 0.90
                bz = p0[1] + t_b * dz + nz * 0.90
                by = gy0 + t_b * (gy1 - gy0)
                verts.extend(make_cylinder_fn(bx, by, bz, radius=0.075, height=0.80, segments=6, color=COL_YELLOW))


def build_rolcar_elevated_sign(cx, ground_y, cz, dir_angle, pole_h,
                               make_box_fn, make_cylinder_fn):
    """
    Anuncio elevado / tótem espectacular ROLCAR 100% en código (cero imágenes PNG):
      - Pedestal de concreto + poste metálico tubular.
      - Tablero blanco doble cara (5.6m x 2.8m) con óvalo ROLCAR + ServiparteS + REFACCIONARIAS.
    """
    verts = []
    verts.extend(make_box_fn(cx, ground_y + 0.30, cz, 0.95, 0.60, 0.95, color=COL_BASE_CONC))
    verts.extend(make_cylinder_fn(cx, ground_y + 0.60, cz, radius=0.18, height=pole_h - 0.60, segments=8, color=COL_STEEL))
    verts.extend(make_cylinder_fn(cx, ground_y + pole_h - 1.4, cz, radius=0.22, height=0.35, segments=8, color=COL_GREEN))

    sign_w = 5.6
    sign_h = 2.8
    sign_d = 0.42
    sign_cy = ground_y + pole_h + sign_h * 0.5
    ca, sa = math.cos(dir_angle), math.sin(dir_angle)
    # Normal frontal = (ca, 0, sa); mirando desde el frente (-ca, 0, -sa),
    # derecha del observador = cross((-ca,0,-sa), (0,1,0)) = (sa, 0, -ca).
    right_x, right_z = sa, -ca
    hw, hh, hd = sign_w * 0.5, sign_h * 0.5, sign_d * 0.5

    # Caras front y back en código puro (blanco mate luminoso) + bordes marco verde/amarillo
    for sign_dir, r_dir in ((1.0, 1.0), (-1.0, -1.0)):
        fnx, fnz = ca * sign_dir, sa * sign_dir
        frx, frz = right_x * r_dir, right_z * r_dir
        face_d = hd

        _emit_quad_on_plane(verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
                            -hw, -hh, hw, hh, face_d, COL_WHITE, emission=0.06)
        # Franjas superior/inferior verde y amarilla del gabinete
        _emit_quad_on_plane(verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
                            -hw, hh - 0.20, hw, hh, face_d + 0.008, COL_GREEN, emission=0.06)
        _emit_quad_on_plane(verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
                            -hw, hh - 0.28, hw, hh - 0.20, face_d + 0.008, COL_YELLOW, emission=0.06)
        _emit_quad_on_plane(verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
                            -hw, -hh, hw, -hh + 0.16, face_d + 0.008, COL_YELLOW, emission=0.06)
        _emit_quad_on_plane(verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
                            -hw, -hh + 0.16, hw, -hh + 0.30, face_d + 0.008, COL_GREEN, emission=0.06)

        # Óvalo grande ROLCAR arriba + ServiparteS REFACCIONARIAS debajo (aspecto 1:1 fijo)
        emit_rolcar_oval_crest(
            verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
            0.0, hh * 0.30, 3.8, 1.08, face_d + 0.018, emission=0.14, with_wordmark=True
        )
        emit_vector_text(
            verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
            "ROLCAR", -1.25, -hh * 0.26,
            char_h=0.44, spacing_scale=1.18, stroke_frac=0.10,
            depth=face_d + 0.025, col=COL_GREEN_BR, emission=0.18
        )
        emit_vector_text(
            verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
            "ServiparteS", 1.25, -hh * 0.28,
            char_h=0.34, spacing_scale=0.96, stroke_frac=0.075,
            depth=face_d + 0.025, col=COL_BLACK, skew=0.22, emission=0.0
        )
        emit_vector_text(
            verts, cx, sign_cy, cz, frx, frz, fnx, fnz,
            "REFACCIONARIAS", 0.0, -hh * 0.62,
            char_h=0.24, spacing_scale=1.32, stroke_frac=0.10,
            depth=face_d + 0.025, col=COL_RED, emission=0.16
        )

    # Tapas superior, inferior y costados del gabinete + baliza nocturna superior
    n_up = (0.0, 1.0, 0.0)
    n_dn = (0.0, -1.0, 0.0)
    top_q = [
        (cx - right_x * hw + ca * hd, sign_cy + hh, cz - right_z * hw + sa * hd),
        (cx + right_x * hw + ca * hd, sign_cy + hh, cz + right_z * hw + sa * hd),
        (cx + right_x * hw - ca * hd, sign_cy + hh, cz + right_z * hw - sa * hd),
        (cx - right_x * hw - ca * hd, sign_cy + hh, cz - right_z * hw - sa * hd),
    ]
    bot_q = [(p[0], sign_cy - hh, p[2]) for p in top_q]
    for n_fb, q in ((n_up, top_q), (n_dn, [bot_q[3], bot_q[2], bot_q[1], bot_q[0]])):
        verts.append((q[0], n_fb, (0, 0), COL_GREEN, 0.0))
        verts.append((q[1], n_fb, (0, 0), COL_GREEN, 0.0))
        verts.append((q[2], n_fb, (0, 0), COL_GREEN, 0.0))
        verts.append((q[0], n_fb, (0, 0), COL_GREEN, 0.0))
        verts.append((q[2], n_fb, (0, 0), COL_GREEN, 0.0))
        verts.append((q[3], n_fb, (0, 0), COL_GREEN, 0.0))

    # Costados laterales del gabinete
    _emit_quad_on_plane(verts, cx + right_x * hw, sign_cy, cz + right_z * hw,
                        -ca, -sa, right_x, right_z, -hd, -hh, hd, hh, 0.0, COL_GREEN)
    _emit_quad_on_plane(verts, cx - right_x * hw, sign_cy, cz - right_z * hw,
                        ca, sa, -right_x, -right_z, -hd, -hh, hd, hh, 0.0, COL_GREEN)

    verts.extend(make_box_fn(cx, sign_cy + hh + 0.22, cz, 1.2, 0.30, 0.50, color=COL_YELLOW, emission=1.1))
    return verts
