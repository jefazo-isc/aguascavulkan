# Pruebas de Software — ISO/IEC/IEEE 29119

## 1. Política y Estrategia de Pruebas (ISO/IEC/IEEE 29119-1 / 29119-2)
**StreetVulkan** adopta un enfoque de verificación continua multi-nivel alineado con **ISO/IEC/IEEE 29119** y **Extreme Programming (XP)**, garantizando la confiabilidad tanto del núcleo en C/Vulkan como de los generadores geoespaciales y métricas en Python.

## 2. Niveles y Tipos de Prueba
| Nivel | Alcance | Implementación | Criterio de Aceptación |
|---|---|---|---|
| **Pruebas Unitarias C** | Tráfico, grafo vial (`RGP1`), carga OBJ, peatones, pool VRAM, vehículos, sectores, glTF | [test_c_modules.c](../tests/test_c_modules.c) | 0 fallos en `make test` |
| **Análisis Dinámico de Memoria** | Detección de errores de memoria y comportamiento indefinido | Target `asan-test` en [Makefile](../Makefile) | Exit code 0 bajo ASan + UBSan |
| **Pruebas Unitarias Python** | Topografía 2D, IFPUG, COSMIC, COCOMO-II, mantenibilidad, auditores ISO | [test_python_tools.py](../tests/test_python_tools.py) | Sin fallos en la ejecución de `unittest` |
| **Calidad de Datos** | Integridad de sectores `.glb`, `road_network.bin`, `chunks.json`, DEMs y DENUE | [validate_data_quality.py](../tools/metrics/validate_data_quality.py) | Resultado según reporte; revisar advertencias y errores |

## 3. Técnicas de Diseño de Pruebas (ISO/IEC/IEEE 29119-4)
- **Partición de equivalencia y valores límite**: Probados en triangulación degenerada, punteros nulos en `road_graph_load`, límites de capacidad en `ped_system_spawn` y clasificación de códigos de salida (`0=PASS`, `2=WARN`, `1=FAIL`) en `evaluate_iso25040.py`.
- **Aislamiento con mocks y directorios temporales**: Utilizado en `test_maintainability_headers_and_debt_detection` para validar detección de deuda técnica y exclusión de cabeceras de terceros sin acoplar al sistema de archivos real.

## 4. Entorno y Automatización (CI)
- La ejecución local se centraliza mediante `make test`, `make asan-test` y `make quality`.
- La integración continua en [ci.yml](../.github/workflows/ci.yml) ejecuta compilación, pruebas C/Python, sanitizadores y verificaciones automatizadas en cada `push` y `pull_request` sobre `main`.
- La presencia y estructura de la infraestructura de pruebas se revisa mediante [audit_iso29119.py](../tools/metrics/audit_iso29119.py); esta auditoría no demuestra por sí sola conformidad formal con la norma.
