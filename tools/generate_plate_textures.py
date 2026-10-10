import os
import re
from pathlib import Path
from typing import Set

from PIL import Image, ImageDraw, ImageFont

# Import OSM extractor utilities to reuse parsing logic
from osm_extractor import fetch_osm_data, parse_osm_data
from geo_dem import geo_to_meters

# Configuration
OUTPUT_DIR = Path('assets/plates')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_SIZE = (256, 64)  # width x height
BG_COLOR = (217, 199, 26)  # Approximate yellow (0.85,0.78,0.10) in 0-255 range
BORDER_COLOR = (13, 13, 13)  # Black border
BORDER_THICKNESS = 3
FONT_SIZE = 32
# Use a default sans‑serif font; fallback to built‑in if not found
try:
    FONT = ImageFont.truetype('DejaVuSans-Bold.ttf', FONT_SIZE)
except OSError:
    FONT = ImageFont.load_default()

def sanitize_name(name: str) -> str:
    """Convert a street name into a safe filename.
    Spaces become underscores, non‑alphanumeric chars are removed.
    """
    name = name.strip().replace(' ', '_')
    name = re.sub(r'[^A-Za-z0-9_\-]', '', name)
    return name or 'unnamed'

def generate_texture(name: str, out_path: Path) -> None:
    """Create a PNG image with the given street name.
    The image has a yellow background, a black border, and centered black text
    (Aguascalientes street-name plate style).
    """
    img = Image.new('RGB', IMAGE_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)
    # Draw black border
    for i in range(BORDER_THICKNESS):
        rect = [i, i, IMAGE_SIZE[0] - i - 1, IMAGE_SIZE[1] - i - 1]
        draw.rectangle(rect, outline=BORDER_COLOR)
    # Calculate text size and position
    text = name
    try:
        bbox = draw.textbbox((0, 0), text, font=FONT)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (IMAGE_SIZE[0] - text_w) // 2 - bbox[0]
        text_y = (IMAGE_SIZE[1] - text_h) // 2 - bbox[1]
    except AttributeError:
        text_w, text_h = FONT.getsize(text)
        text_x = (IMAGE_SIZE[0] - text_w) // 2
        text_y = (IMAGE_SIZE[1] - text_h) // 2
    draw.text((text_x, text_y), text, fill=BORDER_COLOR, font=FONT)
    img.save(out_path, format='PNG')
    print(f"Generated texture: {out_path}")

def collect_unique_names(highways) -> Set[str]:
    """Extract a set of unique street names from the OSM highway data."""
    names = set()
    for _, tags, _ in highways:
        name = tags.get('name')
        if name:
            names.add(name)
    return names

def main():
    # Define the bounding box for Aguascalientes centre (same as generate_sector)
    origin_lat = 21.8807
    origin_lon = -102.2965
    min_lon = -102.3110
    min_lat = 21.8690
    max_lon = -102.2815
    max_lat = 21.8940

    # Fetch and parse OSM data (same as generate_sector)
    osm_xml = fetch_osm_data(min_lon, min_lat, max_lon, max_lat)
    _, _, highways, *rest = parse_osm_data(osm_xml)

    unique_names = collect_unique_names(highways)
    print(f"Found {len(unique_names)} unique street names.")
    for name in sorted(unique_names):
        filename = sanitize_name(name) + '.png'
        out_path = OUTPUT_DIR / filename
        generate_texture(name, out_path)

if __name__ == '__main__':
    main()
