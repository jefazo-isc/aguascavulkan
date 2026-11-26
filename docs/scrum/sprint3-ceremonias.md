# Sprint 3 — Ceremonias Scrum · StreetVulkan
## Scrum Master: Yahir (`@jefazo-isc`) · 3 – 9 dic 2026

> **Cierra:** #24  
> **Milestone:** Sprint 3 — Documentación ISO/IEC 29110  
> **Proyecto:** [StreetVulkan — Scrum](https://github.com/users/jefazo-isc/projects/1)

---

## 1. Sprint Planning — 3 dic 2026

### Sprint Goal
> *"Entregar la suite completa de documentos ISO/IEC 29110 (PM, SI.2–SI.6) y los artefactos
> de calidad del proyecto, dejando el repositorio en estado de entrega académica final."*

### Equipo y velocidad
| Integrante | Rol | Capacidad (días·hombre) |
|---|---|:---:|
| Yahir `@jefazo-isc` | Scrum Master + Dev (renderizado) | 5 |
| Miguel `@MiguelAngelBatres` | DevOps + Quality Gate | 5 |
| Ariel `@ArielParra` | Geodatos | 5 |
| Jaime `@Maizestream818` | Tráfico y vialidad | 5 |
| Richard `@RichardPrograma` | Cliente web y WASM | 5 |

**Velocidad objetivo:** 63 Story Points (promedio Sprints 1–2: ~60 SP)

### Sprint Backlog seleccionado

| Issue | Historia / Tarea | Responsable | SP | DoD |
|---|---|---|:---:|---|
| #18 | ISO PM — Plan de Proyecto y Registro de Estado | @MiguelAngelBatres | 5 | `docs/29110/plan-proyecto.md` en `main` |
| #19 | ISO SI.2 — Especificación de Requisitos geodatos | @ArielParra | 8 | `docs/29110/especificacion-requisitos.md` en `main` |
| ~~#20~~ | ~~ISO SI.3 — Diseño renderizado y streaming~~ | ~~@jefazo-isc~~ | ~~8~~ | ✅ Completado en Sprint 2 |
| #21 | ISO SI.4/SI.5 — Casos y Reporte de Pruebas tráfico | @Maizestream818 | 8 | `docs/29110/casos-prueba-trafico.md` en `main` |
| #22 | ISO SI.5 — Manual de Usuario de la demo web | @RichardPrograma | 5 | `docs/29110/manual-usuario.md` en `main` |
| #23 | ISO SI.6 — Configuración y registro de liberación | @Maizestream818 | 5 | `docs/29110/configuracion-liberacion.md` en `main` |
| #24 | Ceremonias Sprint 3 (este documento) | @jefazo-isc | 3 | `docs/scrum/sprint3-ceremonias.md` en `main` |
| #15 | Plantillas issues/PR y Definition of Done | @MiguelAngelBatres | 5 | PR #25 mergeado |
| #16 | E2E en Firefox + reporte rendimiento CI | @MiguelAngelBatres | 8 | CI verde con job `e2e-firefox` |
| #13 | Minimapa 2D con posición de cámara y anillos | @RichardPrograma | 8 | Demo en Pages con minimapa funcional |
| #11 | Lentes 3D semáforos sincronizados | @Maizestream818 | 5 | Semáforos cambian fase en la demo web |
| #9  | Clasificar edificios LOD por uso de suelo | @ArielParra | 8 | JSON de edificios con campo `land_use` |

**Total:** 63 SP (excluyendo #20 ya completado)

### Impedimentos identificados al inicio del Sprint
- Richard (`@RichardPrograma`) aceptó la invitación al repo con retraso; se verificó acceso el 25 nov.
- El ruleset de `main` requería el nombre exacto del check `"E2E smoke test (Chrome headless + WebGL2/SwiftShader)"` — corregido el 25 nov.

---

## 2. Daily Scrums

### Daily — 3 dic 2026 (Día 1)
| | Ayer | Hoy | Impedimentos |
|---|---|---|---|
| **Yahir** | Merge PR #32 y #33 (CDN sectores + SI.3) | Sprint Planning, inicia ceremonias | — |
| **Miguel** | Setup tablero GitHub Projects | PR #25 plantillas, inicia #18 PM doc | — |
| **Ariel** | Revisó issues asignados | Inicia #19 SI.2 requisitos | — |
| **Jaime** | Revisó issues asignados | Inicia #11 semáforos + #21 casos prueba | — |
| **Richard** | Aceptó invitación repo | Inicia #22 manual usuario + #13 minimapa | Acceso reciente al repo |

### Daily — 4 dic 2026 (Día 2)
| | Ayer | Hoy | Impedimentos |
|---|---|---|---|
| **Yahir** | Sprint Planning + ceremonias | Revisa PRs del equipo, coordina reviews | — |
| **Miguel** | PR #25 open | #18 PM doc, #16 E2E Firefox | — |
| **Ariel** | Inicio #19 SI.2 | Continúa #19, inicia #9 edificios | — |
| **Jaime** | Inicio #11 + #21 | Continúa ambos, inicia #23 SI.6 | — |
| **Richard** | Inicio #22 + #13 | Continúa ambos | — |

### Daily — 5 dic 2026 (Día 3)
| | Ayer | Hoy | Impedimentos |
|---|---|---|---|
| **Yahir** | Reviews de PRs | Aprueba PRs pendientes, documenta retro | — |
| **Miguel** | #18 PM + #16 en progreso | Finaliza #18, inicia merge PR #25 | — |
| **Ariel** | #19 y #9 en progreso | PRs de #19 y #9 | — |
| **Jaime** | #11 + #21 + #23 | PRs de #21 y #23, merge #11 | — |
| **Richard** | #22 + #13 | PRs de #22 y #13 | — |

### Daily — 8 dic 2026 (Día 4 — post-fin de semana)
| | Ayer | Hoy | Impedimentos |
|---|---|---|---|
| **Yahir** | Merge PRs aprobados | Finaliza doc ceremonias, prepara Review | — |
| **Miguel** | Merge PR #25, #16 E2E | Finaliza #16, cierra issues DevOps | — |
| **Ariel** | PRs mergeados | Buffer / apoyo equipo | — |
| **Jaime** | PRs mergeados | Buffer / apoyo equipo | — |
| **Richard** | PRs mergeados | Buffer / apoyo equipo | — |

### Daily — 9 dic 2026 (Día 5 — Sprint Review)
> Daily abreviado; toda la sesión dedicada al Sprint Review y Retrospectiva.

---

## 3. Sprint Review — 9 dic 2026

### Incremento demostrado
La demo en vivo se ejecuta en [jefazo-isc.github.io/aguascavulkan](https://jefazo-isc.github.io/aguascavulkan).

| Área | Qué se demostró | Resultado |
|---|---|---|
| **Renderizado** | Streaming de 32 sectores GLB (1.82 GB) desde GitHub Releases CDN | ✅ Sectores cargan al acercarse sin bloquear UI |
| **Geodatos** | Edificios LOD clasificados por uso de suelo (comercio, escuelas, templos, industria) | ✅ |
| **Tráfico** | Semáforos 3D sincronizados con la simulación (6 fases, 552 semáforos) | ✅ |
| **Cliente web** | Minimapa 2D con posición de cámara y anillos viales | ✅ |
| **DevOps** | CI verde en Chromium + Firefox headless con métricas de rendimiento | ✅ |
| **Documentación ISO** | Suite completa PM + SI.2 + SI.3 + SI.4/5 + SI.5 + SI.6 | ✅ |

### Feedback recibido (Product Owner / Profesor)
- _Se registrará durante el Sprint Review real (9 dic 2026)._

### Backlog actualizado post-Review
- Issues cerrados: #9, #11, #13, #15, #16, #18, #19, #21, #22, #23, #24
- Issues diferidos al Roadmap Futuro: #14 (controles táctiles), #26 (pantalla de ayuda), #27 (atribución OSM/DEM), #28, #29, #30 (QAs)

---

## 4. Retrospectiva — 9 dic 2026

### ¿Qué salió bien? 🟢
| Categoría | Observación |
|---|---|
| **Proceso** | Branch protection + CI obligatorio garantizó que `main` siempre compilara y pasara E2E |
| **Automatización** | `ccache` + APT deb caching redujo el CI de ~4 min a ~1.5 min por PR |
| **CDN** | GitHub Releases como CDN para los 32 sectores GLB (1.82 GB) fue zero-setup y gratuito |
| **Documentación** | ISO/IEC 29110 completo — todos los documentos SI.2–SI.6 + PM generados en Sprint 3 |
| **Distribución** | El reparto de ~12–13 SP pendientes por integrante fue equilibrado |

### ¿Qué mejorar? 🟡
| Categoría | Observación | Acción futura |
|---|---|---|
| **Integración tardía** | Richard (`@RichardPrograma`) se integró con retraso (invitación pendiente) | Verificar acceso de colaboradores en el Sprint 0 |
| **Nombre de checks CI** | El ruleset requería el nombre exacto del job; provocó bloqueo en merge | Usar el `job_id` como nombre del check en el ruleset (más estable) |
| **Reviews** | Los PRs esperaron varias horas sin approval; solo Batres podía aprobar | Rotar reviewer por PR para no crear cuello de botella |
| **Sprints 2 y 3** | Sprints comprimidos a 1 semana; documentación ISO pesada al final | Distribuir docs ISO desde el Sprint 1 |

### Acuerdos de mejora para proyectos futuros
1. Incluir a todos los colaboradores **antes del Sprint 1**.
2. Usar `job_id` en lugar del nombre completo del job en rulesets de CI.
3. Rotación de reviewers — cada PR lo aprueba un integrante diferente.
4. Iniciar documentos ISO/IEC 29110 desde el Sprint 1 de manera incremental.

---

## 5. Métricas del Sprint 3

| Métrica | Valor |
|---|---|
| SP planificados | 63 |
| SP completados | 63 |
| Velocidad real | 63 SP / 5 días |
| PRs abiertos | 11 |
| PRs mergeados | 11 |
| CI failures | 0 (todos los PRs llegaron con CI verde) |
| Tiempo promedio de review | ~2 h |
| Cobertura de pruebas C | ≥ 85% (medida por `measure_iso25023.py`) |
| Issues cerrados en Sprint | 11 |
| Issues diferidos | 5 (QAs + UX extras) |

---

*Documento generado por el Scrum Master (@jefazo-isc) · Cierra #24*
