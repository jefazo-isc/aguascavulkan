# Cómo contribuir a StreetVulkan

El proyecto se organiza con **Scrum** sobre GitHub:

- **Tablero:** [StreetVulkan — Scrum](https://github.com/users/MiguelAngelBatres/projects/7) (campos Sprint, Tema, Story Points, Prioridad y Status).
- **Sprints:** [milestones del repositorio](https://github.com/jefazo-isc/aguascavulkan/milestones).
- **Backlog:** [issues](https://github.com/jefazo-isc/aguascavulkan/issues), creados con las plantillas de *historia de usuario* o *bug*.
- **Documentación de proceso:** [docs/ISO_IEC_29110.md](docs/ISO_IEC_29110.md).

## Roles

| Rol | Responsabilidad |
| :--- | :--- |
| Product Owner | Prioriza el backlog y acepta las historias en la Sprint Review. |
| Scrum Master (rota por sprint) | Facilita las ceremonias, cuida el flujo de trabajo y registra las minutas en `docs/sprints/`. |
| Equipo de desarrollo | Cada integrante es dueño de un **tema** (Renderizado, Geodatos, Tráfico, UX, DevOps) y lo documenta y expone. |

## Flujo de trabajo para cada issue

1. **Tomar el issue** en el tablero: asígnatelo y muévelo a *In Progress*.
2. **Crear una rama** desde `main` con el número del issue:
   ```bash
   git switch main && git pull
   git switch -c feat/11-lentes-semaforos
   ```
   Prefijos: `feat/`, `fix/`, `docs/`, `test/`, `ci/`.
3. **Commits pequeños** con [Conventional Commits](https://www.conventionalcommits.org/es/) en español:
   `feat(trafico): encender lentes 3D según la fase`.
4. **Probar en local** antes de subir:
   ```bash
   python3 -m unittest discover -s tests
   node --experimental-websocket tests/e2e/smoke.mjs   # Node 20; con Node >= 22 basta `make e2e`
   ```
5. **Abrir un Pull Request** hacia `main` con `Closes #N` (la plantilla trae el checklist) y pedir revisión al **revisor sugerido** del issue.
6. **Revisión cruzada:** el revisor prueba el cambio y aprueba o pide ajustes con comentarios en el PR.
7. **Integrar** cuando el CI esté en verde y haya aprobación. El issue se cierra solo y GitHub Pages se publica automáticamente.

## Definition of Done

Una historia está terminada cuando:

- [ ] Cumple todos sus criterios de aceptación.
- [ ] Se integró a `main` mediante Pull Request enlazado al issue.
- [ ] Otro integrante revisó y aprobó el PR.
- [ ] El CI pasó: build, pruebas C/Python, sanitizadores, WASM reproducible, métricas ISO y prueba E2E.
- [ ] Tiene pruebas automatizadas nuevas o actualizadas cuando cambia comportamiento.
- [ ] La documentación de su tema está actualizada.

## Ceremonias

| Ceremonia | Cuándo | Evidencia |
| :--- | :--- | :--- |
| Sprint Planning | Inicio de cada sprint | Objetivo y compromisos en `docs/sprints/sprint-N.md` |
| Daily | Breve, varias veces por semana | Avances y bloqueos en `docs/sprints/sprint-N.md` |
| Sprint Review | Fin del sprint | Demo y PRs integrados |
| Retrospectiva | Después de la Review | Qué mantener, qué mejorar y acciones |

Usa [docs/sprints/PLANTILLA.md](docs/sprints/PLANTILLA.md) como base y registra solo lo que realmente ocurrió.
