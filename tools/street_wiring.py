"""
street_wiring.py
================
Generador 100% procedimental (cero PNGs) de postes de luz tipo CFE, crucetas,
aisladores, transformadores y cableado aéreo con catenaria parabólica 3D
para los corredores Rolcar en StreetVulkan.

Formato de vértice compatible con FastMeshBuilder:
    (pos, norm, uv, color, emission)
donde color = (r, g, b, MAT_ID) con MAT_ID = 1.14 (concreto/sólido procedural).
"""
import json
import math
import os
from typing import Dict, List, Optional, Tuple

MAT_SOLID = 1.14

COL_CONCRETE    = (0.64, 0.63, 0.60, MAT_SOLID)
COL_STEEL       = (0.42, 0.45, 0.48, MAT_SOLID)
COL_PORCELAIN   = (0.36, 0.21, 0.15, MAT_SOLID)
COL_TRANSFORMER = (0.50, 0.53, 0.56, MAT_SOLID)
COL_CABLE_PWR   = (0.10, 0.10, 0.11, MAT_SOLID)
COL_CABLE_TEL   = (0.06, 0.06, 0.07, MAT_SOLID)

POLE_HEIGHT       = 9.5
CROSSARM_Y_OFFSET = 8.6
INSULATOR_TOP_Y   = CROSSARM_Y_OFFSET + 0.18
TELECOM_Y_OFFSET  = 6.8
INSULATOR_OFFSETS = (-0.95, 0.0, 0.95)


def _normalize(vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
    length = math.sqrt(vx * vx + vy * vy + vz * vz)
    if length < 1e-8:
        return (0.0, 1.0, 0.0)
    inv = 1.0 / length
    return (vx * inv, vy * inv, vz * inv)


def _cross(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _emit_tri(verts: list, p0, p1, p2, norm, col, emission: float = 0.0) -> None:
    verts.append((p0, norm, (0.0, 0.0), col, emission))
    verts.append((p1, norm, (1.0, 0.0), col, emission))
    verts.append((p2, norm, (0.5, 1.0), col, emission))


def _emit_quad(verts: list, p0, p1, p2, p3, norm, col, emission: float = 0.0) -> None:
    verts.append((p0, norm, (0.0, 0.0), col, emission))
    verts.append((p1, norm, (1.0, 0.0), col, emission))
    verts.append((p2, norm, (1.0, 1.0), col, emission))
    verts.append((p0, norm, (0.0, 0.0), col, emission))
    verts.append((p2, norm, (1.0, 1.0), col, emission))
    verts.append((p3, norm, (0.0, 1.0), col, emission))


def _emit_tapered_cylinder(
    verts: list,
    cx: float,
    y0: float,
    cz: float,
    y1: float,
    r0: float,
    r1: float,
    sides: int,
    col,
    cap_top: bool = True,
    cap_bottom: bool = False,
) -> None:
    """Emite un cilindro vertical (octagonal/hexagonal) con posible conicidad."""
    ring0 = []
    ring1 = []
    normals = []
    for i in range(sides):
        a = (2.0 * math.pi * i) / sides
        ca, sa = math.cos(a), math.sin(a)
        ring0.append((cx + ca * r0, y0, cz + sa * r0))
        ring1.append((cx + ca * r1, y1, cz + sa * r1))
        normals.append((ca, 0.0, sa))

    for i in range(sides):
        j = (i + 1) % sides
        nx = 0.5 * (normals[i][0] + normals[j][0])
        nz = 0.5 * (normals[i][2] + normals[j][2])
        nrm = _normalize(nx, 0.0, nz)
        _emit_quad(verts, ring0[i], ring0[j], ring1[j], ring1[i], nrm, col)

    if cap_top:
        top_c = (cx, y1, cz)
        for i in range(sides):
            j = (i + 1) % sides
            _emit_tri(verts, top_c, ring1[i], ring1[j], (0.0, 1.0, 0.0), col)

    if cap_bottom:
        bot_c = (cx, y0, cz)
        for i in range(sides):
            j = (i + 1) % sides
            _emit_tri(verts, bot_c, ring0[j], ring0[i], (0.0, -1.0, 0.0), col)


def _emit_oriented_box(
    verts: list,
    cx: float,
    cy: float,
    cz: float,
    ux: float,
    uz: float,
    half_len: float,
    half_w: float,
    half_h: float,
    col,
) -> None:
    """Emite una caja 3D alineada con el vector unitario horizontal (ux, 0, uz)."""
    vx, vz = -uz, ux
    # 8 esquinas: b = bottom, t = top
    def _pt(su: float, sv: float, sy: float):
        return (
            cx + ux * (su * half_len) + vx * (sv * half_w),
            cy + sy * half_h,
            cz + uz * (su * half_len) + vz * (sv * half_w),
        )

    b00 = _pt(-1.0, -1.0, -1.0)
    b10 = _pt(1.0, -1.0, -1.0)
    b11 = _pt(1.0, 1.0, -1.0)
    b01 = _pt(-1.0, 1.0, -1.0)
    t00 = _pt(-1.0, -1.0, 1.0)
    t10 = _pt(1.0, -1.0, 1.0)
    t11 = _pt(1.0, 1.0, 1.0)
    t01 = _pt(-1.0, 1.0, 1.0)

    _emit_quad(verts, t00, t10, t11, t01, (0.0, 1.0, 0.0), col)   # top
    _emit_quad(verts, b01, b11, b10, b00, (0.0, -1.0, 0.0), col)  # bottom
    _emit_quad(verts, b00, b10, t10, t00, (-vx, 0.0, -vz), col)   # -v face
    _emit_quad(verts, b11, b01, t01, t11, (vx, 0.0, vz), col)     # +v face
    _emit_quad(verts, b10, b11, t11, t10, (ux, 0.0, uz), col)     # +u cap
    _emit_quad(verts, b01, b00, t00, t01, (-ux, 0.0, -uz), col)   # -u cap


def make_utility_pole_3d(
    cx: float,
    ground_y: float,
    cz: float,
    angle: float,
    has_transformer: bool = False,
) -> list:
    """
    Genera un poste de concreto CFE de 9.5m con:
      - Fuste octagonal de concreto (matID=1.14), empotrado 0.3m bajo ground_y.
      - Cruceta de acero a y+8.6m orientada perpendicular al ángulo de la calle.
      - 3 aisladores de porcelana sobre la cruceta.
      - Herraje/ménsula inferior de telecomunicaciones a y+6.8m.
      - Transformador cilíndrico gris opcional en postes seleccionados/esquina.
    """
    verts = []

    # 1. Fuste octagonal de concreto (9.5m sobre suelo, -0.3m anclaje)
    _emit_tapered_cylinder(
        verts,
        cx,
        ground_y - 0.3,
        cz,
        ground_y + POLE_HEIGHT,
        r0=0.16,
        r1=0.10,
        sides=8,
        col=COL_CONCRETE,
        cap_top=True,
        cap_bottom=False,
    )

    # Vector perpendicular al eje de la calle para la cruceta
    perp = angle + math.pi * 0.5
    px, pz = math.cos(perp), math.sin(perp)

    # 2. Cruceta de acero a y + 8.6m (2.2m de ancho)
    arm_y = ground_y + CROSSARM_Y_OFFSET
    _emit_oriented_box(
        verts,
        cx,
        arm_y,
        cz,
        px,
        pz,
        half_len=1.10,
        half_w=0.05,
        half_h=0.05,
        col=COL_STEEL,
    )

    # 3. Tres aisladores de porcelana sobre la cruceta
    for off in INSULATOR_OFFSETS:
        ix = cx + px * off
        iz = cz + pz * off
        _emit_tapered_cylinder(
            verts,
            ix,
            arm_y + 0.04,
            iz,
            arm_y + 0.20,
            r0=0.055,
            r1=0.040,
            sides=6,
            col=COL_PORCELAIN,
            cap_top=True,
            cap_bottom=False,
        )

    # 4. Ménsula inferior de telecomunicaciones/fibra a y + 6.8m
    tel_y = ground_y + TELECOM_Y_OFFSET
    _emit_oriented_box(
        verts,
        cx + px * 0.14,
        tel_y,
        cz + pz * 0.14,
        px,
        pz,
        half_len=0.22,
        half_w=0.035,
        half_h=0.035,
        col=COL_STEEL,
    )

    # 5. Transformador cilíndrico gris opcional (y+7.0m a y+8.0m)
    if has_transformer:
        tx = cx + px * 0.46
        tz = cz + pz * 0.46
        ty0 = ground_y + 7.0
        ty1 = ground_y + 8.0
        _emit_tapered_cylinder(
            verts,
            tx,
            ty0,
            tz,
            ty1,
            r0=0.31,
            r1=0.31,
            sides=8,
            col=COL_TRANSFORMER,
            cap_top=True,
            cap_bottom=True,
        )
        # Dos boquillas aislantes superiores del transformador
        for boff in (-0.12, 0.12):
            _emit_tapered_cylinder(
                verts,
                tx + px * boff,
                ty1,
                tz + pz * boff,
                ty1 + 0.22,
                r0=0.04,
                r1=0.025,
                sides=5,
                col=COL_PORCELAIN,
                cap_top=True,
                cap_bottom=False,
            )

    return verts


def make_catenary_cable_3d(
    p0: Tuple[float, float, float],
    p1: Tuple[float, float, float],
    sag: float = 0.45,
    radius: float = 0.025,
    segments: int = 8,
    color=COL_CABLE_PWR,
) -> list:
    """
    Genera un cable aéreo 3D con catenaria parabólica entre p0 y p1.
    Usa sección triangular (3 lados) para mantener bajo conteo de vértices.
    """
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dz = p1[2] - p0[2]
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist < 1e-4 or segments < 1:
        return []

    # Puntos sobre la curva parabólica: y(t) = lerp - 4*sag*t*(1-t)
    pts = []
    for i in range(segments + 1):
        t = i / segments
        x = p0[0] + dx * t
        y = p0[1] + dy * t - 4.0 * sag * t * (1.0 - t)
        z = p0[2] + dz * t
        pts.append((x, y, z))

    # Marco ortonormal estable a lo largo de la cuerda
    fwd = _normalize(dx, dy, dz)
    up_ref = (0.0, 1.0, 0.0) if abs(fwd[1]) < 0.95 else (1.0, 0.0, 0.0)
    right = _normalize(*_cross(fwd, up_ref))
    up = _normalize(*_cross(right, fwd))

    # 3 direcciones radiales (120 grados) para prisma triangular compacto
    radial_dirs = []
    for k in range(3):
        a = (2.0 * math.pi * k) / 3.0
        ca, sa = math.cos(a), math.sin(a)
        nx = right[0] * ca + up[0] * sa
        ny = right[1] * ca + up[1] * sa
        nz = right[2] * ca + up[2] * sa
        radial_dirs.append((nx, ny, nz))

    rings = []
    for pt in pts:
        ring = [
            (pt[0] + d[0] * radius, pt[1] + d[1] * radius, pt[2] + d[2] * radius)
            for d in radial_dirs
        ]
        rings.append(ring)

    verts = []
    for s in range(segments):
        r_a = rings[s]
        r_b = rings[s + 1]
        for k in range(3):
            kn = (k + 1) % 3
            nrm = _normalize(
                radial_dirs[k][0] + radial_dirs[kn][0],
                radial_dirs[k][1] + radial_dirs[kn][1],
                radial_dirs[k][2] + radial_dirs[kn][2],
            )
            _emit_quad(verts, r_a[k], r_a[kn], r_b[kn], r_b[k], nrm, color)

    return verts


def generate_rolcar_wiring_for_sector(
    x0: float,
    z0: float,
    x1: float,
    z1: float,
    mesh_grid,
    poles_json_path: Optional[str] = None,
) -> list:
    """
    Carga models/utility_poles_rolcar.json, filtra postes y vanos dentro de
    [x0, x1] x [z0, z1], consulta mesh_grid.get_mesh_height(x, z) para la
    altura exacta del terreno y retorna la lista de vértices 3D.
    """
    if poles_json_path is None:
        poles_json_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "models",
            "utility_poles_rolcar.json",
        )
    if not os.path.exists(poles_json_path):
        return []

    with open(poles_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    poles = data.get("poles", [])
    spans = data.get("spans", [])
    if not poles:
        return []

    pole_by_id: Dict[int, dict] = {int(p["id"]): p for p in poles}
    ground_y_cache: Dict[int, float] = {}

    def _get_pole_ground_y(pole: dict) -> float:
        pid = int(pole["id"])
        if pid not in ground_y_cache:
            ground_y_cache[pid] = float(mesh_grid.get_mesh_height(float(pole["x"]), float(pole["z"])))
        return ground_y_cache[pid]

    verts = []

    # 1. Postes dentro del sector
    for p in poles:
        px, pz = float(p["x"]), float(p["z"])
        if x0 <= px <= x1 and z0 <= pz <= z1:
            gy = _get_pole_ground_y(p)
            verts.extend(
                make_utility_pole_3d(
                    px,
                    gy,
                    pz,
                    angle=float(p.get("angle", 0.0)),
                    has_transformer=bool(p.get("has_transformer", False)),
                )
            )

    # 2. Vanos de cableado (3 líneas superiores de energía + 1 troncal inferior telecom)
    for sp in spans:
        pa = pole_by_id.get(int(sp["a"]))
        pb = pole_by_id.get(int(sp["b"]))
        if pa is None or pb is None:
            continue

        ax, az = float(pa["x"]), float(pa["z"])
        bx, bz = float(pb["x"]), float(pb["z"])
        mx, mz = 0.5 * (ax + bx), 0.5 * (az + bz)
        if not (x0 <= mx <= x1 and z0 <= mz <= z1):
            continue

        span_len = math.hypot(bx - ax, bz - az)
        if span_len < 1.0:
            continue

        gy_a = _get_pole_ground_y(pa)
        gy_b = _get_pole_ground_y(pb)

        perp_a = float(pa.get("angle", 0.0)) + math.pi * 0.5
        perp_b = float(pb.get("angle", 0.0)) + math.pi * 0.5
        pax, paz = math.cos(perp_a), math.sin(perp_a)
        pbx, pbz = math.cos(perp_b), math.sin(perp_b)
        # Evitar cruce en X de los cables si las normales de cruceta apuntan en sentidos opuestos
        if pax * pbx + paz * pbz < 0.0:
            pbx, pbz = -pbx, -pbz

        sag_pwr = min(0.85, max(0.25, span_len * 0.015))
        for off in INSULATOR_OFFSETS:
            p0 = (ax + pax * off, gy_a + INSULATOR_TOP_Y, az + paz * off)
            p1 = (bx + pbx * off, gy_b + INSULATOR_TOP_Y, bz + pbz * off)
            verts.extend(
                make_catenary_cable_3d(
                    p0, p1, sag=sag_pwr, radius=0.022, segments=8, color=COL_CABLE_PWR
                )
            )

        # 1 cable troncal inferior de telecomunicaciones/fibra a y + 6.8m
        sag_tel = min(1.05, max(0.30, span_len * 0.018))
        t0 = (ax + pax * 0.14, gy_a + TELECOM_Y_OFFSET, az + paz * 0.14)
        t1 = (bx + pbx * 0.14, gy_b + TELECOM_Y_OFFSET, bz + pbz * 0.14)
        verts.extend(
            make_catenary_cable_3d(
                t0, t1, sag=sag_tel, radius=0.036, segments=8, color=COL_CABLE_TEL
            )
        )

    return verts
