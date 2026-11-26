# Guía de Contribución — StreetVulkan

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

## Contacto del equipo

| Rol | Usuario GitHub |
|---|---|
| Responsable Renderizado / DevOps | @jefazo-isc |
| Revisor | @MiguelAngelBatres |
