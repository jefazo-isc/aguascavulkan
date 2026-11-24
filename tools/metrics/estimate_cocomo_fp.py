#!/usr/bin/env python3
"""Calculadora de SLOC/KLOC, Puntos de Funcion (IFPUG), COSMIC y COCOMO-II para StreetVulkan."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THIRD_PARTY = {"cgltf.h", "stb_image.h"}

# Factores de escala nominales de COCOMO-II (PREC, FLEX, RESL, TEAM, PMAT)
NOMINAL_SCALE_FACTORS = {
    "PREC": 3.72,
    "FLEX": 3.04,
    "RESL": 4.24,
    "TEAM": 3.29,
    "PMAT": 4.68,
}

IFPUG_WEIGHTS = {"EI": 4, "EO": 5, "EQ": 4, "ILF": 10, "EIF": 7}

# Catalogo explicito y trazable IFPUG (cada funcion elemental ligada a archivos fuente reales)
IFPUG_CATALOG = [
    # External Inputs (EI) - peso 4
    {
        "id": "EI-01",
        "type": "EI",
        "description": "Entrada interactiva de camara libre (WASD, Espacio/Ctrl y raton)",
        "source": "src/main.c, include/math_camera.h",
    },
    {
        "id": "EI-02",
        "type": "EI",
        "description": "Comandos de menu de pausa y testing (ESC/P, F1-F8, T, L/F, flechas)",
        "source": "include/pause_menu.h",
    },
    {
        "id": "EI-03",
        "type": "EI",
        "description": "Parametros CLI de extraccion cartografica OSM, Overture y DENUE",
        "source": "tools/osm_extractor.py, tools/open_buildings_fetcher.py",
    },
    {
        "id": "EI-04",
        "type": "EI",
        "description": "Parametros CLI del pipeline procedural (sectores GLB, grafo vial y atlas)",
        "source": "tools/generate_sector.py, tools/generate_road_graph.py, tools/generate_texture_atlas.py",
    },
    {
        "id": "EI-05",
        "type": "EI",
        "description": "Importacion de planos fotograficos y generacion de monumentos OBJ con Gemini",
        "source": "tools/photo_plane_importer.py, tools/photo_scene_extractor.py, tools/gemini_obj_generator.py",
    },
    {
        "id": "EI-06",
        "type": "EI",
        "description": "Configuracion por variables de entorno (TEST_FRAMES, TEST_PAUSE, GEMINI_API_KEY)",
        "source": "src/main.c, tools/gemini_integration.py",
    },
    # External Outputs (EO) - peso 5
    {
        "id": "EO-01",
        "type": "EO",
        "description": "Renderizado 3D Vulkan con iluminacion dia/noche, farolas y vehiculos instanciados",
        "source": "src/vulkan.c, shaders/vertex.vert, shaders/fragment.frag",
    },
    {
        "id": "EO-02",
        "type": "EO",
        "description": "Overlay HUD de telemetria ISO 25010/25022 y menu visual de pausa",
        "source": "include/debug_overlay.h, include/pause_menu.h",
    },
    {
        "id": "EO-03",
        "type": "EO",
        "description": "Exportacion de telemetria JSON y scorecard de calidad ISO/IEC 25040",
        "source": "include/telemetry.h, tools/metrics/evaluate_iso25040.py",
    },
    {
        "id": "EO-04",
        "type": "EO",
        "description": "Generacion de macro-sectores GLB 2.0, grafo binario road_network.bin y chunks.json",
        "source": "tools/split_glb_to_sectors.py, tools/generate_road_graph.py, tools/gltf_writer.py",
    },
    {
        "id": "EO-05",
        "type": "EO",
        "description": "Exportacion de modelos GLB de flota vehicular/peatonal y cuadrantes satelitales",
        "source": "tools/convert_car_models.py, tools/procedural_peds.py, tools/split_satellite_texture.py",
    },
    # External Inquiries (EQ) - peso 4
    {
        "id": "EQ-01",
        "type": "EQ",
        "description": "Consulta de cota topografica DEM continua (vulkan_get_ground_elevation / terrain_dem_get_elevation)",
        "source": "src/vulkan.c, include/terrain_dem_data.h",
    },
    {
        "id": "EQ-02",
        "type": "EQ",
        "description": "Consulta espacial del estado de semaforo por coordenada (traffic_system_get_light_state_at)",
        "source": "src/traffic_system.c",
    },
    {
        "id": "EQ-03",
        "type": "EQ",
        "description": "Consulta de visibilidad frustum por AABB y seleccion de chunks visibles",
        "source": "include/frustum_cull.h, include/chunk_system.h",
    },
    {
        "id": "EQ-04",
        "type": "EQ",
        "description": "Consulta de capacidades de GPU fisica Vulkan, extensiones WSI y formato de swapchain",
        "source": "src/vulkan_device.c, src/vulkan_swapchain.c",
    },
    # Internal Logical Files (ILF) - peso 10
    {
        "id": "ILF-01",
        "type": "ILF",
        "description": "Grafo vial binario CSR en memoria y disco (RoadGraph / models/road_network.bin)",
        "source": "src/road_graph.c, include/road_graph.h",
    },
    {
        "id": "ILF-02",
        "type": "ILF",
        "description": "Estado de flota vehicular y hash espacial en CPU/GPU (CarSystem / 200 vehiculos)",
        "source": "src/car_system.c, include/car_system.h",
    },
    {
        "id": "ILF-03",
        "type": "ILF",
        "description": "Estado de intersecciones, fases y luminarias semaforicas (TrafficSystem / traffic_signals.json)",
        "source": "src/traffic_system.c, include/traffic_system.h",
    },
    {
        "id": "ILF-04",
        "type": "ILF",
        "description": "Indice espacial de macro-sectores y subasignadores de VRAM/RAM (SectorSystem / VulkanMemoryPool)",
        "source": "src/sector_system.c, include/sector_system.h, src/vulkan_memory_pool.c",
    },
    {
        "id": "ILF-05",
        "type": "ILF",
        "description": "Banco de luces dinamicas y buffer uniforme GPU (LightingSystem / LightingUBO)",
        "source": "include/lighting_system.h",
    },
    {
        "id": "ILF-06",
        "type": "ILF",
        "description": "Catalogo semantico de edificios clasificados y estado peatonal (classified_buildings.json, PedSystem)",
        "source": "tools/classify_buildings.py, src/ped_system.c, include/ped_system.h",
    },
    # External Interface Files (EIF) - peso 7
    {
        "id": "EIF-01",
        "type": "EIF",
        "description": "Cartografia externa OpenStreetMap y Overture Maps (XML/GeoJSON)",
        "source": "tools/osm_extractor.py, tools/open_buildings_fetcher.py",
    },
    {
        "id": "EIF-02",
        "type": "EIF",
        "description": "Elevacion satelital NASA SRTM / AWS Terrarium DEM (caches JSON y grilla embebida)",
        "source": "tools/geo_dem.py, include/terrain_dem_data.h",
    },
    {
        "id": "EIF-03",
        "type": "EIF",
        "description": "Diccionario estadistico INEGI DENUE y datos comerciales Rolcar",
        "source": "tools/extract_rolcar.py, tools/rolcar_vector.py",
    },
    {
        "id": "EIF-04",
        "type": "EIF",
        "description": "Cuadrantes de textura satelital PNG y activos externos glTF/OBJ",
        "source": "src/vulkan_texture.c, src/vulkan_gltf.c, src/obj_loader.c",
    },
]

# Procesos funcionales COSMIC (ISO/IEC 19761) explicitos y trazables
COSMIC_PROCESSES = [
    {
        "id": "CFP-01",
        "name": "Renderizado y Streaming de Sectores",
        "trigger": "Cambio de posicion de camara o inicio de fotograma (vulkan_draw)",
        "E": 2,
        "X": 2,
        "R": 3,
        "W": 1,
        "modules": [
            "src/vulkan.c",
            "src/sector_system.c",
            "src/vulkan_gltf.c",
            "src/vulkan_memory_pool.c",
            "src/vulkan_swapchain.c",
            "include/frustum_cull.h",
        ],
    },
    {
        "id": "CFP-02",
        "name": "Simulacion Vehicular y Semaforos",
        "trigger": "Tick de simulacion a paso fijo de 60 Hz o cambio de modo semaforico",
        "E": 2,
        "X": 2,
        "R": 2,
        "W": 2,
        "modules": [
            "src/car_system.c",
            "src/traffic_system.c",
            "src/road_graph.c",
            "include/lighting_system.h",
        ],
    },
    {
        "id": "CFP-03",
        "name": "Simulacion Peatonal",
        "trigger": "Tick de actualizacion peatonal (ped_system_update)",
        "E": 1,
        "X": 1,
        "R": 2,
        "W": 1,
        "modules": [
            "src/ped_system.c",
            "include/ped_system.h",
            "tools/procedural_peds.py",
        ],
    },
    {
        "id": "CFP-04",
        "name": "Camara Libre, Menu de Pausa y Telemetria HUD",
        "trigger": "Evento SDL2 de teclado/raton o cierre de cuadro (telemetry_frame_end)",
        "E": 3,
        "X": 2,
        "R": 1,
        "W": 1,
        "modules": [
            "src/main.c",
            "include/math_camera.h",
            "include/debug_overlay.h",
            "include/pause_menu.h",
            "include/telemetry.h",
        ],
    },
    {
        "id": "CFP-05",
        "name": "Pipeline Procedural Python y Calidad",
        "trigger": "Ejecucion CLI de generacion geoespacial o evaluacion make metrics",
        "E": 3,
        "X": 2,
        "R": 3,
        "W": 3,
        "modules": [
            "tools/generate_sector.py",
            "tools/generate_road_graph.py",
            "tools/geo_dem.py",
            "tools/metrics/validate_data_quality.py",
            "tools/metrics/evaluate_iso25040.py",
        ],
    },
]


def count_sloc_file(path):
    """Cuenta lineas logicas no vacias ni de comentario puro en un archivo fuente."""
    sloc = 0
    in_block_comment = False
    is_python = path.endswith(".py")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if is_python:
                if line.startswith("#"):
                    continue
                sloc += 1
            else:
                if in_block_comment:
                    if "*/" in line:
                        in_block_comment = False
                    continue
                if line.startswith("/*"):
                    if "*/" not in line:
                        in_block_comment = True
                    continue
                if line.startswith("//"):
                    continue
                sloc += 1
    return sloc


def collect_project_sloc(root=ROOT):
    """Recopila SLOC por lenguaje (C, H, GLSL, Python) excluyendo cabeceras de terceros."""
    buckets = {"C": 0, "H": 0, "GLSL": 0, "Python": 0}
    mapping = [
        ("src", (".c",), "C"),
        ("include", (".h",), "H"),
        ("shaders", (".vert", ".frag"), "GLSL"),
        ("tools", (".py",), "Python"),
    ]
    for folder, exts, key in mapping:
        base = os.path.join(root, folder)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for fn in filenames:
                if fn in THIRD_PARTY:
                    continue
                if fn.endswith(exts):
                    buckets[key] += count_sloc_file(os.path.join(dirpath, fn))
    return buckets


def summarize_ifpug_catalog(catalog=None):
    """Resume conteos por tipo (EI, EO, EQ, ILF, EIF) a partir del catalogo explicito."""
    items = IFPUG_CATALOG if catalog is None else catalog
    counts = {k: 0 for k in IFPUG_WEIGHTS}
    for item in items:
        ftype = item.get("type", "")
        if ftype in counts:
            counts[ftype] += 1
    return counts


def compute_ifpug_ufp(counts):
    """Calcula UFP usando pesos promedio IFPUG (EI=4, EO=5, EQ=4, ILF=10, EIF=7)."""
    return sum(counts.get(k, 0) * w for k, w in IFPUG_WEIGHTS.items())


def compute_cosmic_cfp(processes):
    """Calcula Puntos de Funcion COSMIC (ISO/IEC 19761): suma de Entry, Exit, Read, Write."""
    total = 0
    for proc in processes:
        total += proc.get("E", 0) + proc.get("X", 0) + proc.get("R", 0) + proc.get("W", 0)
    return total


def compute_cocomo_ii(ksloc, scale_factors=None, eaf=1.0):
    """Calcula esfuerzo (PM) y duracion (TDEV en meses) bajo COCOMO-II Post-Architecture."""
    sf = scale_factors or NOMINAL_SCALE_FACTORS
    a = 2.94
    b = 0.91
    e = b + 0.01 * sum(sf.values())
    pm = a * (ksloc ** e) * eaf
    tdev = 3.67 * (pm ** (0.28 + 0.2 * (e - b)))
    team = pm / tdev if tdev > 0 else 0.0
    return {"ksloc": ksloc, "E": e, "PM": pm, "TDEV_months": tdev, "avg_team": team}


def main():
    sloc = collect_project_sloc()
    total_sloc = sum(sloc.values())
    total_ksloc = total_sloc / 1000.0

    ifpug_counts = summarize_ifpug_catalog(IFPUG_CATALOG)
    ufp = compute_ifpug_ufp(ifpug_counts)
    cfp = compute_cosmic_cfp(COSMIC_PROCESSES)
    est_actual = compute_cocomo_ii(total_ksloc)

    # Estimacion para ROADMAP_FUTURO.md (4 modulos ~ 2.5 KSLOC estimados)
    est_roadmap = compute_cocomo_ii(2.5)

    print("=== Metricas de Tamano y Estimacion COCOMO-II ===")
    for k, v in sloc.items():
        print(f"  SLOC {k:6s}: {v}")
    print(f"  Total SLOC : {total_sloc} ({total_ksloc:.3f} KSLOC, excluyendo 3rd-party)")
    print(f"  IFPUG UFP  : {ufp} puntos de funcion ({ifpug_counts})")
    print(f"  COSMIC CFP : {cfp} puntos de funcion (ISO/IEC 19761)")
    print(
        f"  COCOMO-II (Base Actual {total_ksloc:.2f} KSLOC): "
        f"E={est_actual['E']:.4f}, Esfuerzo={est_actual['PM']:.2f} PM, "
        f"Tiempo={est_actual['TDEV_months']:.2f} meses, Equipo={est_actual['avg_team']:.2f}"
    )
    print(
        f"  COCOMO-II (Roadmap Futuro 2.50 KSLOC): "
        f"Esfuerzo={est_roadmap['PM']:.2f} PM, "
        f"Tiempo={est_roadmap['TDEV_months']:.2f} meses, Equipo={est_roadmap['avg_team']:.2f}"
    )

    print("\n--- Catalogo IFPUG Trazable ---")
    for item in IFPUG_CATALOG:
        w = IFPUG_WEIGHTS[item["type"]]
        print(f"  [{item['id']}] ({item['type']}, peso={w}) {item['description']} -> {item['source']}")

    print("\n--- Procesos Funcionales COSMIC (ISO/IEC 19761) ---")
    for proc in COSMIC_PROCESSES:
        sub_cfp = proc["E"] + proc["X"] + proc["R"] + proc["W"]
        mods = ", ".join(proc["modules"])
        print(
            f"  [{proc['id']}] {proc['name']} | Trigger: {proc['trigger']} | "
            f"E={proc['E']}, X={proc['X']}, R={proc['R']}, W={proc['W']} -> {sub_cfp} CFP | Modulos: {mods}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
