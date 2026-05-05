"""
Generate professional hero banner for README.
Creates a 1200x400px banner with gradient background, logo, and tagline.
"""
from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path


def create_hero_banner():
    """Create professional hero banner."""
    # Dimensions
    width, height = 1200, 400

    # Create image with gradient background
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)

    # Create gradient background (blue to purple)
    for y in range(height):
        # Calculate color for this row
        r = int(59 + (139 - 59) * y / height)      # 59 to 139
        g = int(130 + (92 - 130) * y / height)     # 130 to 92
        b = int(246 + (246 - 246) * y / height)    # 246 to 246
        draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

    # Try to load a font, fallback to default
    try:
        title_font = ImageFont.truetype("arial.ttf", 80)
        subtitle_font = ImageFont.truetype("arial.ttf", 32)
        tagline_font = ImageFont.truetype("arial.ttf", 24)
    except:
        # Fallback to default font
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        tagline_font = ImageFont.load_default()

    # Add logo icon (simple graduation cap shape)
    icon_x, icon_y = 100, 120
    icon_size = 160

    # Draw graduation cap
    # Cap top
    cap_points = [
        (icon_x, icon_y + 40),
        (icon_x + icon_size, icon_y + 40),
        (icon_x + icon_size - 20, icon_y),
        (icon_x + 20, icon_y)
    ]
    draw.polygon(cap_points, fill='white', outline='white')

    # Cap base
    draw.rectangle(
        [icon_x + 40, icon_y + 40, icon_x + icon_size - 40, icon_y + 80],
        fill='white',
        outline='white'
    )

    # Tassel
    draw.line([icon_x + icon_size - 40, icon_y, icon_x + icon_size - 20, icon_y + 60], fill='#FFD700', width=3)
    draw.ellipse([icon_x + icon_size - 30, icon_y + 55, icon_x + icon_size - 10, icon_y + 75], fill='#FFD700')

    # Add AI brain icon overlay
    brain_x = icon_x + 60
    brain_y = icon_y + 90
    # Simple circuit pattern
    draw.ellipse([brain_x, brain_y, brain_x + 40, brain_y + 30], outline='white', width=2)
    draw.line([brain_x + 20, brain_y + 15, brain_x + 50, brain_y + 15], fill='white', width=2)
    draw.ellipse([brain_x + 48, brain_y + 10, brain_x + 58, brain_y + 20], fill='white')

    # Add text
    text_x = 300

    # Title
    title = "EduAI Platform"
    try:
        draw.text((text_x, 80), title, fill='white', font=title_font)
    except:
        # If custom font didn't load, use larger default
        for i in range(3):  # Bold effect
            draw.text((text_x + i, 80), title, fill='white')

    # Subtitle
    subtitle = "AI-Powered Personalized Learning"
    try:
        draw.text((text_x, 180), subtitle, fill='white', font=subtitle_font)
    except:
        draw.text((text_x, 180), subtitle, fill='white')

    # Tagline
    tagline = "Multi-Tenant RAG-Grounded Education System"
    try:
        draw.text((text_x, 240), tagline, fill=(245, 245, 245), font=tagline_font)
    except:
        draw.text((text_x, 240), tagline, fill='white')

    # Add badges/pills at bottom
    badge_y = 320
    badges = [
        "Django 5.1",
        "PostgreSQL + pgvector",
        "RAG Pipeline",
        "Multi-Tenant"
    ]

    badge_x = text_x
    for badge_text in badges:
        # Badge background
        badge_width = len(badge_text) * 8 + 20
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_width, badge_y + 30],
            radius=15,
            fill=(255, 255, 255, 50),
            outline='white',
            width=1
        )
        # Badge text
        draw.text((badge_x + 10, badge_y + 8), badge_text, fill='white', font=None)
        badge_x += badge_width + 10

    # Save
    output_path = Path(__file__).parent.parent / "docs" / "images" / "hero-banner.png"
    img.save(output_path, 'PNG', optimize=True)
    print(f"Hero banner saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    create_hero_banner()
