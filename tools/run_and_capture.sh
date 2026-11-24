#!/bin/bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

pkill -9 -f "./street_vulkan" || true
sleep 1

DISPLAY=:0 ./street_vulkan &
VULKAN_PID=$!
echo "Vulkan PID: $VULKAN_PID"

WIN_ID=""
for i in {1..25}; do
    sleep 0.4
    WIN_ID=$(DISPLAY=:0 wmctrl -l | grep "StreetView Vulkan" | awk '{print $1}' | head -n 1 || true)
    if [ -n "$WIN_ID" ]; then
        echo "Ventana encontrada: $WIN_ID"
        break
    fi
done

sleep 2
DISPLAY=:0 wmctrl -i -a "$WIN_ID" || DISPLAY=:0 wmctrl -a "StreetView Vulkan" || true
sleep 1

CAPTURE_DIR="${CAPTURE_DIR:-$REPO_ROOT/captures}"
ART_DIR="${ART_DIR:-}"
mkdir -p "$CAPTURE_DIR"
if [ -n "$ART_DIR" ]; then
    mkdir -p "$ART_DIR"
fi

DISPLAY=:0 import -window root "$CAPTURE_DIR/captura_1.png"
if [ -n "$ART_DIR" ]; then cp "$CAPTURE_DIR/captura_1.png" "$ART_DIR/captura_1.png"; fi
echo "[Captura 1/3] Completada"

sleep 4
DISPLAY=:0 wmctrl -i -a "$WIN_ID" || true
DISPLAY=:0 import -window root "$CAPTURE_DIR/captura_2.png"
if [ -n "$ART_DIR" ]; then cp "$CAPTURE_DIR/captura_2.png" "$ART_DIR/captura_2.png"; fi
echo "[Captura 2/3] Completada"

sleep 4
DISPLAY=:0 wmctrl -i -a "$WIN_ID" || true
DISPLAY=:0 import -window root "$CAPTURE_DIR/captura_3.png"
if [ -n "$ART_DIR" ]; then cp "$CAPTURE_DIR/captura_3.png" "$ART_DIR/captura_3.png"; fi
echo "[Captura 3/3] Completada"

echo "ALL_CAPTURES_DONE"
