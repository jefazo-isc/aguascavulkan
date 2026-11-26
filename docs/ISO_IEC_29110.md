# ISO/IEC 29110 en StreetVulkan — documentación del proceso con Scrum

## Qué es y por qué la usamos

**ISO/IEC 29110** (*Ingeniería de sistemas y software — Perfiles del ciclo de vida para entidades muy pequeñas*) define qué debe documentar un equipo de hasta 25 personas sin la carga de normas pensadas para grandes organizaciones. Usamos el **Perfil Básico** (ISO/IEC TR 29110-5-1-2), que tiene dos procesos:

- **PM — Gestión del Proyecto:** planear, dar seguimiento, controlar y cerrar el proyecto.
- **SI — Implementación de Software:** requisitos, diseño, construcción, pruebas y entrega.

La norma no impone un método: dice **qué productos de trabajo** deben existir, no cómo trabajar. Por eso encaja con Scrum: las ceremonias y artefactos de Scrum producen la evidencia que pide 29110.

Normas de apoyo que ya usa el repositorio: ISO/IEC 25010 (modelo de calidad, [ISO_IEC_25010.md](ISO_IEC_25010.md)), ISO/IEC/IEEE 29119 (pruebas, [ISO_IEC_29119.md](ISO_IEC_29119.md)) e ISO 31000 (riesgos, [ISO_9001_31000.md](ISO_9001_31000.md)). Ninguna implica certificación: son la guía para estructurar la documentación.

## Equivalencia Scrum ↔ ISO/IEC 29110

| ISO/IEC 29110 (Perfil Básico) | En nuestro Scrum | Dónde queda la evidencia |
| :--- | :--- | :--- |
| PM.1 Planificación del proyecto | Product Backlog + Sprint Planning | [Tablero](https://github.com/users/MiguelAngelBatres/projects/7), [milestones](https://github.com/jefazo-isc/aguascavulkan/milestones), `docs/29110/plan-de-proyecto.md` |
| PM.2 Ejecución del plan | Sprint, Dailies | Status del tablero, `docs/sprints/sprint-N.md` |
| PM.3 Evaluación y control | Sprint Review | Milestone cerrado, `docs/29110/registro-de-estado.md` |
| PM.4 Cierre del proyecto | Review y retrospectiva final | `docs/sprints/sprint-3.md`, etiqueta `v1.0` |
| Solicitud de cambio | Issue nuevo con plantilla | [Issues](https://github.com/jefazo-isc/aguascavulkan/issues) |
| Registro de reuniones | Minutas de ceremonias | `docs/sprints/` |
| SI.1 Inicio de la implementación | Configurar repo, CI y flujo de trabajo | [CONTRIBUTING.md](../CONTRIBUTING.md), `.github/workflows/` |
| SI.2 Análisis de requisitos | Historias de usuario + criterios de aceptación | Issues `historia`, `docs/29110/requisitos-*.md` |
| SI.3 Arquitectura y diseño | Diseño técnico por tema | `docs/29110/diseno-*.md` |
| SI.4 Construcción | Ramas, commits y Pull Requests revisados | PRs con `Closes #N` y revisión aprobada |
| SI.5 Integración y pruebas | CI (unitarias, ASan, E2E) + Definition of Done | Runs de GitHub Actions, `docs/29110/pruebas-*.md` |
| SI.6 Entrega del producto | Despliegue continuo a GitHub Pages | `wasm-pages.yml`, `docs/29110/configuracion-y-liberacion.md`, `docs/29110/manual-de-usuario.md` |

## Productos de trabajo y responsables (Sprint 3)

Cada integrante documenta **su propio tema**, el mismo que desarrolla en el Sprint 2, para poder explicarlo en la presentación.

| Producto de trabajo | Proceso | Responsable | Issue |
| :--- | :--- | :--- | :--- |
| Plan de Proyecto y Registro de Estado | PM.1–PM.3 | @MiguelAngelBatres | [#18](https://github.com/jefazo-isc/aguascavulkan/issues/18) |
| Especificación de Requisitos (pipeline geoespacial) | SI.2 | @ArielParra | [#19](https://github.com/jefazo-isc/aguascavulkan/issues/19) |
| Diseño de Software (renderizado y streaming) | SI.3 | @jefazo-isc | [#20](https://github.com/jefazo-isc/aguascavulkan/issues/20) |
| Casos y Reporte de Pruebas (tráfico) | SI.4 / SI.5 | @Maizestream818 | [#21](https://github.com/jefazo-isc/aguascavulkan/issues/21) |
| Manual de Usuario (demo web) | SI.5 | @RichardPrograma | [#22](https://github.com/jefazo-isc/aguascavulkan/issues/22) |
| Configuración del Software y liberación | SI.6 | @Maizestream818 | [#23](https://github.com/jefazo-isc/aguascavulkan/issues/23) |
| Minutas y retrospectiva final | PM.4 | @MiguelAngelBatres | [#24](https://github.com/jefazo-isc/aguascavulkan/issues/24) |

## Historia del proceso

- **Fase previa (octubre – 24 de noviembre de 2026):** desarrollo sin proceso Scrum formal. Incluye el motor nativo C/Vulkan, el pipeline geoespacial en Python y la primera migración web (WebGL2/WebGPU + WASM). La autoría de ese trabajo consta en el historial de Git.
- **Sprint 1 (25 de noviembre):** primer sprint gestionado con backlog, milestone y tablero ([resumen](sprints/sprint-1.md)).
- **Sprint 2 (26 de noviembre – 2 de diciembre):** mejoras por tema, una o dos historias por integrante con revisión cruzada.
- **Sprint 3 (3 – 9 de diciembre):** productos de trabajo ISO/IEC 29110 de esta guía.

## Cómo explicarlo en la presentación

1. *"Usamos Scrum para organizar el trabajo y la norma ISO/IEC 29110 —hecha para equipos pequeños— para decidir qué documentar."*
2. Mostrar el tablero filtrado por sprint y por tema: cada tema tiene un responsable.
3. Mostrar un Pull Request: issue enlazado, revisión de otro integrante y CI en verde (eso cubre SI.4 y SI.5).
4. Mostrar el despliegue automático a GitHub Pages tras el CI (SI.6).
