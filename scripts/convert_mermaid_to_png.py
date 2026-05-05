"""
Convert Mermaid diagram files to PNG images.
Uses Mermaid Ink API (https://mermaid.ink) for conversion.
"""
import os
import base64
import requests
from pathlib import Path
import urllib.parse


def mermaid_to_png(mermaid_file, output_file):
    """Convert a single Mermaid file to PNG."""
    # Read Mermaid content
    with open(mermaid_file, 'r', encoding='utf-8') as f:
        mermaid_code = f.read()

    # Encode for URL
    encoded = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')

    # Use Mermaid Ink API
    url = f"https://mermaid.ink/img/{encoded}?type=png&theme=default"

    print(f"Converting {mermaid_file.name}...")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        with open(output_file, 'wb') as f:
            f.write(response.content)

        print(f"  Saved to {output_file.name}")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


def convert_all_diagrams():
    """Convert all Mermaid diagrams to PNG."""
    base_dir = Path(__file__).parent.parent
    diagrams_dir = base_dir / "docs" / "diagrams"
    images_dir = base_dir / "docs" / "images"

    images_dir.mkdir(parents=True, exist_ok=True)

    # Get all .mmd files
    mermaid_files = sorted(diagrams_dir.glob("*.mmd"))

    if not mermaid_files:
        print("No Mermaid files found!")
        return

    print(f"Found {len(mermaid_files)} Mermaid diagrams to convert\n")

    success_count = 0
    for mmd_file in mermaid_files:
        # Generate output filename
        png_file = images_dir / f"diagram-{mmd_file.stem}.png"

        if mermaid_to_png(mmd_file, png_file):
            success_count += 1

    print(f"\nConversion complete: {success_count}/{len(mermaid_files)} diagrams converted")


if __name__ == "__main__":
    convert_all_diagrams()
