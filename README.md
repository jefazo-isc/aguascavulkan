# StreetVulkan 🏙️

Motor de renderizado 3D y simulación urbana en C usando **Vulkan API** y **SDL2**. Generación procedural de ciudad (calles, banquetas elevadas 3D con guarniciones rojas/amarillas, semáforos dinámicos, edificios clasificados e iluminación emisiva) impulsado por scripts en Python.

---

## 🚀 Requisitos Previos

- **GCC** (con soporte para C11/C99).
- **Vulkan SDK** (`libvulkan-dev` / `vulkan-tools`).
- **glslangValidator** (incluido en Vulkan SDK para compilar GLSL a SPIR-V).
- **SDL2** (`libsdl2-dev`).
- **Python 3** con `Pillow` y `numpy` (para los scripts en `tools/`).

En Debian/Ubuntu/Devuan:
```bash
sudo apt update
sudo apt install build-essential libsdl2-dev libvulkan-dev vulkan-tools glslang-tools python3-pip
pip install pillow numpy
```

---

## 🛠️ Compilación y Ejecución

Compilar el motor:
```bash
make clean && make
```

Ejecutar el motor:
```bash
./street_vulkan
```

Controles:
- **WASD / Espacio / Ctrl**: Movimiento de la cámara libre.
- **Ratón**: Orientación (Pitch & Yaw).
- **TAB**: Capturar / Liberar ratón.
- **ESC**: Salir / Liberar ratón.

---

## 🎨 Generación Procedural de Texturas y Mallas 3D

Para generar el atlas de texturas 16x16 pixel-art:
```bash
python3 tools/generate_texture_atlas.py
```

Para procesar la ciudad 3D y los sectores urbanos:
```bash
python3 tools/generate_sector.py
```

---

## 📂 Estructura del Proyecto

- `src/`: Código fuente de C (`main.c`, `vulkan.c`, `traffic_system.c`, etc.).
- `include/`: Archivos de cabecera (`.h`).
- `shaders/`: Código fuente GLSL (`vertex.vert`, `fragment.frag`).
- `tools/`: Generadores procedurales y scripts de visión artificial en Python.
- `assets/`: Recursos gráficos y atlas de texturas.
- `models/`: Mallas y cachés locales.
- `docs/`: Documentación técnica, roadmaps y estándares de calidad ([ISO/IEC 25010](file:///home/yahir/vulkan/docs/ISO_IEC_25010.md), [ISO/IEC 25023](file:///home/yahir/vulkan/docs/ISO_IEC_25023.md)).

---

## 📋 Estándares de Calidad

El proyecto se rige bajo la familia de normas internacionales **ISO/IEC SQuaRE**:
- **[ISO/IEC 25010](file:///home/yahir/vulkan/docs/ISO_IEC_25010.md)**: Modelo de calidad del producto de software (evaluación de las 8 características: Adecuación Funcional, Eficiencia de Desempeño, Compatibilidad, Usabilidad, Fiabilidad, Seguridad, Mantenibilidad y Portabilidad).
- **[ISO/IEC 25023](file:///home/yahir/vulkan/docs/ISO_IEC_25023.md)**: Medición cuantitativa de la calidad (catálogo de 24 métricas objetivas, fórmulas matemáticas, métodos de medición y scorecard de cumplimiento).
