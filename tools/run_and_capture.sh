#!/bin/bash
set -e
cd /home/yahir/vulkan

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

ART_DIR="/home/yahir/.gemini/antigravity-cli/brain/08ada0bf-55d8-4e57-b5f6-a6899b22a197"
mkdir -p "$ART_DIR" captures

DISPLAY=:0 import -window root "$ART_DIR/captura_1.png"
cp "$ART_DIR/captura_1.png" captures/captura_1.png
echo "[Captura 1/3] Completada"

sleep 4
DISPLAY=:0 wmctrl -i -a "$WIN_ID" || true
DISPLAY=:0 import -window root "$ART_DIR/captura_2.png"
cp "$ART_DIR/captura_2.png" captures/captura_2.png
echo "[Captura 2/3] Completada"

sleep 4
DISPLAY=:0 wmctrl -i -a "$WIN_ID" || true
DISPLAY=:0 import -window root "$ART_DIR/captura_3.png"
cp "$ART_DIR/captura_3.png" captures/captura_3.png
echo "[Captura 3/3] Completada"

echo "ALL_CAPTURES_DONE"
