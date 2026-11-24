# Guía práctica de metodología de desarrollo — StreetVulkan

## Propósito

Esta guía resume cómo organizar, implementar, verificar y entregar cambios en StreetVulkan. Es una guía operativa para el trabajo futuro, no una afirmación de certificación ni evidencia de que todas las ceremonias descritas históricamente se hayan realizado de forma periódica.

El proyecto combina prácticas **inspiradas en Scrum** para priorizar y revisar incrementos, prácticas de ingeniería de **XP** para probar y refactorizar, y principios de **OpenUP** para atender arquitectura y riesgos desde etapas tempranas. Los documentos OpenUP/TSP/PSP y SCRUM/XP conservan el análisis académico y la trazabilidad del proceso anterior; esta guía distingue esas referencias de la práctica recomendada para cada cambio nuevo.

## Enfoque adoptado

- **Iterativo e incremental:** entregar cambios pequeños que puedan compilarse, probarse y revisarse por separado.
- **Arquitectura y riesgos primero cuando corresponda:** analizar temprano las implicaciones de Vulkan, memoria, geodesia, formatos de datos, generación de activos y compatibilidad web.
- **Calidad integrada al desarrollo:** agregar o actualizar pruebas junto con el cambio; usar compilación estricta, sanitizadores y auditorías disponibles.
- **Evidencia antes que afirmaciones:** registrar si un valor es un objetivo, una medición automatizada, una observación manual o una limitación pendiente.
- **Trazabilidad proporcional:** vincular los requisitos importantes con los módulos afectados, pruebas y documentación pertinente, sin exigir papeleo para cambios triviales.

## Flujo de trabajo para cada cambio

### 1. Definir el problema y el alcance

Antes de editar:

1. Describir el problema o necesidad en una tarea breve.
2. Identificar quién se beneficia y qué resultado observable se espera.
3. Anotar criterios de aceptación comprobables y restricciones relevantes.
4. Localizar módulos, herramientas, datos y documentación afectados.
5. Señalar riesgos, dependencias externas y trabajo que queda explícitamente fuera del alcance.

Para una funcionalidad, puede utilizarse el formato: «Como [perfil], quiero [capacidad], para [beneficio]», acompañado de criterios verificables. Para un defecto, incluir pasos para observarlo y el resultado esperado.

### 2. Planear una entrega pequeña

- Dividir trabajo grande en incrementos revisables.
- Estimar esfuerzo de forma relativa si ayuda a priorizar; tratar las estimaciones como aproximaciones, no compromisos de precisión.
- Identificar las pruebas que demostrarán el comportamiento y decidir si requiere actualización de datos o documentación.
- Registrar la deuda técnica descubierta como trabajo separado, salvo que impida entregar correctamente el cambio actual.

### 3. Implementar y verificar mientras se trabaja

- Mantener cambios enfocados y consistentes con los límites de los módulos existentes.
- Para código nuevo o corregido, escribir una prueba que reproduzca el caso cuando sea viable; después implementar y refactorizar sin perder la prueba.
- En el pipeline geoespacial, preservar procedencia, unidades, coordenadas, licencias y reproducibilidad de los activos.
- No presentar métricas de CI o pruebas headless como evidencia de rendimiento en GPU o validación interactiva.
- Actualizar los documentos y ejemplos cuando una interfaz, comando, limitación o resultado haya cambiado.

### 4. Ejecutar las compuertas disponibles

Desde la raíz del repositorio:

| Comando | Uso |
|---|---|
| `make` | Compilar motor nativo y shaders; requiere GCC, SDL2, Vulkan y `glslangValidator`. |
| `make test` | Compilar y ejecutar las pruebas C, y luego descubrir las pruebas Python configuradas en `tests/`. Requiere las dependencias nativas de compilación. |
| `make asan-test` | Ejecutar el harness C con AddressSanitizer y UndefinedBehaviorSanitizer. |
| `make metrics` | Ejecutar el evaluador de métricas y auditorías configuradas. Leer tanto el estado como el detalle de cada resultado. |
| `make quality` | Limpiar, compilar, ejecutar pruebas, sanitizadores y métricas en secuencia. |

La integración continua está definida en [.github/workflows/ci.yml](../.github/workflows/ci.yml). También valida la reproducibilidad del artefacto WASM y ejecuta verificaciones de métricas. Si una compuerta no puede ejecutarse por falta de dependencias, indicarlo como **no ejecutada**, no como aprobada. Un estado `WARN` representa deuda o cobertura parcial y debe revisarse; no equivale automáticamente a `PASS` ni necesariamente a un fallo bloqueante.

### 5. Revisar y aceptar

Antes de integrar un cambio, revisar:

- ¿Cumple todos los criterios de aceptación y mantiene el alcance acotado?
- ¿Las pruebas nuevas cubren el caso principal y los límites o fallos previsibles?
- ¿Se verificaron compilación, sanitizadores y métricas pertinentes, o se registró por qué no fue posible?
- ¿La documentación describe el comportamiento actual y diferencia objetivos de resultados medidos?
- ¿Se excluyeron secretos, archivos temporales y artefactos generados que no deban versionarse?
- ¿Los cambios son legibles y no introducen deuda accidental?

Una tarea se considera terminada cuando sus criterios se cumplen, las verificaciones pertinentes pasan o sus limitaciones quedan documentadas, y la documentación necesaria está actualizada. El cierre de una iteración no significa que todo el backlog esté terminado ni que toda historia esté aceptada.

## Commits y entregas

Usar commits pequeños, atómicos y con mensajes que expliquen el cambio. El repositorio ya emplea prefijos como `docs:`, `fix:`, `test:` y `ci:`; mantener ese estilo facilita el historial. Separar, cuando sea razonable, documentación, correcciones de comportamiento y cambios de pruebas. No incluir cambios ajenos al objetivo ni afirmar en el mensaje que una validación pasó si no se ejecutó.

## Cómo reportar métricas y estado

Toda cifra o resultado importante debe indicar su categoría:

- **Objetivo:** umbral deseado, aún no demostrado en el entorno relevante.
- **Medido automáticamente:** salida reproducible de una herramienta o prueba; incluir comando o fuente.
- **Verificado manualmente:** comprobado por una persona en un entorno descrito.
- **Pendiente / no verificado:** instrumentado, planificado o no ejecutado.

Las métricas de tamaño de archivos GLB no son una medida directa de VRAM. Los FPS objetivo no son un benchmark si no se midieron en hardware y condiciones especificadas. Las auditorías internas y los documentos asociados a normas sirven como listas de verificación del proyecto; por sí solos no prueban certificación ni conformidad formal con una norma.

## Documentación relacionada

- [Proceso SCRUM-XP y backlog documentado](SCRUM_XP.md)
- [Proceso OpenUP-TSP y formatos PSP documentados](OPENUP_TSP.md)
- [Estimación y trazabilidad](ESTIMACION_Y_TRAZABILIDAD.md)
- [Pruebas y verificaciones](ISO_IEC_29119.md)
- [Calidad del producto y métricas](ISO_IEC_25023.md)
- [Roadmap](ROADMAP_FUTURO.md)
- [README del proyecto](../README.md)
