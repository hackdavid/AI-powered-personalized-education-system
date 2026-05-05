"""Extract every ```mermaid ... ``` block from a markdown file and render each to PNG.

Each block becomes docs/figures/fig<N>.png and the markdown block is replaced
with `![<caption>](figures/fig<N>.png)`. Assumes the line immediately AFTER the
closing ``` is a single-line caption like `*Fig. 1. ...*` — the image keeps
that caption right below it.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "report-final.md"
FIG_DIR = ROOT / "docs" / "figures"
MMDC = ROOT / "node_modules" / ".bin" / "mmdc.cmd"

FIG_DIR.mkdir(parents=True, exist_ok=True)

text = REPORT.read_text(encoding="utf-8")

# Find every fenced mermaid block. The trailing newline after the closing ```
# is captured so we can leave the surrounding caption untouched.
pattern = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)

blocks = list(pattern.finditer(text))
if not blocks:
    print("No mermaid blocks found.")
    sys.exit(0)

print(f"Found {len(blocks)} mermaid blocks.")

# Render each block to PNG via mermaid CLI.
new_text_parts: list[str] = []
last_end = 0
for i, match in enumerate(blocks, start=1):
    code = match.group(1)
    mmd_path = FIG_DIR / f"fig{i}.mmd"
    png_path = FIG_DIR / f"fig{i}.png"
    mmd_path.write_text(code, encoding="utf-8")

    print(f"Rendering fig{i}.png ...")
    cmd = [
        str(MMDC),
        "-i", str(mmd_path),
        "-o", str(png_path),
        "-b", "transparent",
        "-w", "1600",     # width, gives crisp output for embedded report
        "-s", "2",        # scale factor
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"mmdc failed for fig{i}")
    print(f"  wrote {png_path}")

    new_text_parts.append(text[last_end:match.start()])
    new_text_parts.append(f"![Figure {i}](figures/fig{i}.png)")
    last_end = match.end()

new_text_parts.append(text[last_end:])
new_text = "".join(new_text_parts)

REPORT.write_text(new_text, encoding="utf-8")
print(f"\nUpdated {REPORT.relative_to(ROOT)} — {len(blocks)} mermaid blocks replaced.")
