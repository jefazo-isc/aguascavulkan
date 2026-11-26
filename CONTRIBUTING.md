# Guía de Contribución — StreetVulkan

El proyecto se organiza con **Scrum** sobre GitHub:

- **Tablero (backlog y sprints):** [StreetVulkan — Scrum](https://github.com/users/MiguelAngelBatres/projects/7)
- **Sprints:** [milestones del repositorio](https://github.com/jefazo-isc/aguascavulkan/milestones)
- **Backlog:** [issues](https://github.com/jefazo-isc/aguascavulkan/issues), creados con las plantillas de *historia de usuario* o *bug*
- **Documentación del proceso:** [docs/ISO_IEC_29110.md](docs/ISO_IEC_29110.md)

### Roles

| Rol | Responsabilidad |
| :--- | :--- |
| Product Owner | Prioriza el backlog y acepta las historias en la Sprint Review. |
| Scrum Master (rota por sprint) | Facilita las ceremonias, cuida el flujo de trabajo y registra las minutas en `docs/sprints/`. |
| Equipo de desarrollo | Cada integrante es dueño de un **tema** (Renderizado, Geodatos, Tráfico, UX, DevOps): lo desarrolla, lo documenta y lo expone. |

---

## Flujo obligatorio para toda integración a `main`

Ningún cambio se integra directamente a `main`. **Todo cambio pasa por Pull Request** revisado por al menos un integrante del equipo.

---

## 1. Crear tu rama de trabajo

Desde `main` actualizado:

```bash
git checkout main && git pull origin main
git checkout -b feat/<numero-issue>-descripcion-corta
# Ejemplos:
#   feat/7-hosting-cors-sectores
#   fix/15-bug-renderizado-noche
#   docs/20-diseno-29110
```

**Convención de nombres de rama:**
| Prefijo | Cuándo usarlo |
|---|---|
| `feat/` | Nueva funcionalidad |
| `fix/` | Corrección de bug |
| `docs/` | Solo documentación |
| `refactor/` | Refactor sin cambio de comportamiento |
| `ci/` | Cambios en workflows / CI |

---

## 2. Hacer commits

Usar **Conventional Commits** en todos los mensajes:

```
<tipo>(<alcance>): descripción corta

Cuerpo opcional con más detalle.

Closes #<numero-issue>
```

| Tipo | Uso |
|---|---|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `refactor` | Refactor sin cambio funcional |
| `docs` | Documentación |
| `ci` | Cambios en CI/CD |
| `test` | Añadir / modificar tests |
| `chore` | Tareas de mantenimiento |

Ejemplo:
```
feat(sector-streaming): servir GLBs desde GitHub Releases CDN

Agrega external_base_url en sectors.json inyectado por CI.
El cliente web lee la URL externa antes que los paths locales.

Closes #7
```

---

## 3. Verificar localmente antes de pushear

```bash
# Build completo + tests C + tests Python
make test

# Build web (WAT → WASM + sintaxis JS)
make web-build

# ASan/UBSan (opcional pero recomendado)
make asan-test

# Prueba E2E en Chrome headless (Node >= 22; en Node 20: node --experimental-websocket tests/e2e/smoke.mjs)
make e2e
```

---

## 4. Abrir el Pull Request

```bash
git push origin feat/<numero-issue>-descripcion
# Luego en GitHub: New Pull Request → base: main ← compare: tu-rama
```

El cuerpo del PR **debe incluir**:
- `Closes #<numero>` para cerrar el issue automáticamente al mergear
- Descripción breve de qué cambia y por qué
- Capturas de pantalla si hay cambios visuales

---

## 5. Definition of Done

Un PR puede mergearse **solo cuando**:

- [ ] Al menos **1 aprobación** de otro integrante del equipo
- [ ] El check **`build-and-test`** (CI) está en verde
- [ ] El check **`e2e-smoke`** (CI) está en verde
- [ ] No hay conflictos con `main`
- [ ] README / documentación actualizada si aplica

---

## 6. Reglas de la rama `main`

La rama `main` está protegida con las siguientes reglas (configuradas via GitHub Rulesets):

| Regla | Estado |
|---|---|
| Pull Request obligatorio | ✅ |
| Mínimo 1 aprobación | ✅ |
| CI `build-and-test` en verde | ✅ |
| CI `e2e-smoke` en verde | ✅ |
| Force-push bloqueado | ✅ |
| Borrado de rama bloqueado | ✅ |

---

## 7. Ceremonias Scrum

| Ceremonia | Cuándo | Evidencia |
| :--- | :--- | :--- |
| Sprint Planning | Inicio de cada sprint | Objetivo y compromisos en `docs/sprints/sprint-N.md` |
| Daily | Breve, varias veces por semana | Avances y bloqueos en `docs/sprints/sprint-N.md` |
| Sprint Review | Fin del sprint | Demo y PRs integrados |
| Retrospectiva | Después de la Review | Qué mantener, qué mejorar y acciones |

Usa [docs/sprints/PLANTILLA.md](docs/sprints/PLANTILLA.md) como base y registra solo lo que realmente ocurrió.

---

## Contacto del equipo

| Rol | Usuario GitHub |
|---|---|
| Responsable Renderizado / DevOps | @jefazo-isc |
| Revisor | @MiguelAngelBatres |
