#!/usr/bin/env bash
# =============================================================================
# upload_sectors_gh_release.sh
# Sube los 32 sectores GLB del Primer Anillo a GitHub Releases (tag: sectors-v1)
# para servir desde CDN con CORS nativo hacia GitHub Pages.
#
# Uso:
#   chmod +x tools/upload_sectors_gh_release.sh
#   ./tools/upload_sectors_gh_release.sh
#
# Requisitos:
#   - gh CLI autenticado (gh auth status)
#   - Estar en la raíz del repo
# =============================================================================
set -euo pipefail

REPO="jefazo-isc/aguascavulkan"
TAG="sectors-v1"
SECTORS_DIR="models/sectors"

# Coordenadas del Primer Anillo (mismo set que en wasm-pages.yml y sectors.json)
PRIMER_ANILLO=(
  "-3_-2" "-3_-1" "-3_0"  "-3_1"
  "-2_-3" "-2_-2" "-2_-1" "-2_0"  "-2_1"  "-2_2"
  "-1_-3" "-1_-2" "-1_-1" "-1_0"  "-1_1"  "-1_2"
  "0_-3"  "0_-2"  "0_-1"  "0_0"   "0_1"   "0_2"
  "1_-3"  "1_-2"  "1_-1"  "1_0"   "1_1"   "1_2"
  "2_-2"  "2_-1"  "2_0"   "2_1"
)

echo "=== StreetVulkan — Sector GLB Upload a GitHub Releases ==="
echo "    Repo   : ${REPO}"
echo "    Tag    : ${TAG}"
echo "    Anillo : Primer Anillo (32 sectores)"
echo ""

# Verificar autenticación
gh auth status --hostname github.com 2>&1 | grep -q "Logged in" || {
  echo "❌ No estás autenticado. Ejecuta: gh auth login"
  exit 1
}

# Crear el release si no existe aún
if ! gh release view "${TAG}" --repo "${REPO}" &>/dev/null; then
  echo "📦 Creando release '${TAG}'..."
  gh release create "${TAG}" \
    --repo "${REPO}" \
    --title "Sectores GLB — Primer Anillo Aguascalientes" \
    --notes "$(cat <<'NOTES'
Sectores 3D del **Primer Anillo** de Aguascalientes (~32 sectores, geometría detallada con fachadas, banquetas y postes CFE).

Servidos como CDN para la demo en GitHub Pages: https://jefazo-isc.github.io/aguascavulkan/

El cliente web (`web/sector-manager.js`) descarga estos GLBs bajo demanda al acercarse, usando streaming LRU con radio de carga de 2400 m.
NOTES
)" \
    --prerelease
  echo "✅ Release '${TAG}' creado."
else
  echo "ℹ️  Release '${TAG}' ya existe, se agregarán/reemplazarán archivos."
fi

echo ""
echo "⬆️  Subiendo sectores del Primer Anillo..."
SUCCESS=0
SKIP=0
FAIL=0

for COORD in "${PRIMER_ANILLO[@]}"; do
  GLB="${SECTORS_DIR}/sector_${COORD}.glb"
  CHUNKS="${SECTORS_DIR}/chunks_${COORD}.json"

  if [ -f "${GLB}" ] && [ "$(stat -c%s "${GLB}")" -gt 100000 ]; then
    echo -n "  → sector_${COORD}.glb ($(du -sh "${GLB}" | cut -f1)) ... "
    if gh release upload "${TAG}" "${GLB}" --repo "${REPO}" --clobber 2>/dev/null; then
      echo "✅"
      SUCCESS=$((SUCCESS + 1))
    else
      echo "❌ FALLÓ"
      FAIL=$((FAIL + 1))
    fi
  else
    echo "  ⚠️  sector_${COORD}.glb no encontrado o vacío — omitido"
    SKIP=$((SKIP + 1))
  fi

  if [ -f "${CHUNKS}" ]; then
    echo -n "  → chunks_${COORD}.json ... "
    gh release upload "${TAG}" "${CHUNKS}" --repo "${REPO}" --clobber 2>/dev/null && echo "✅" || echo "❌"
  fi
done

echo ""
echo "=== Resumen ==="
echo "  ✅ Subidos : ${SUCCESS}"
echo "  ⚠️  Omitidos: ${SKIP}"
echo "  ❌ Fallidos : ${FAIL}"
echo ""
echo "🌐 Release: https://github.com/${REPO}/releases/tag/${TAG}"
echo "📦 CDN URL base: https://github.com/${REPO}/releases/download/${TAG}/"
