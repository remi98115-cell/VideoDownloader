from PIL import Image, ImageDraw
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_logo(size=1024):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(size * 0.04)
    radius = int(size * 0.20)

    # Background
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=(24, 24, 27, 255),
    )

    # Subtle border
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        outline=(50, 50, 56, 255),
        width=int(size * 0.012),
    )

    cx, cy = size // 2, size // 2
    tri_w = int(size * 0.32)
    tri_h = int(size * 0.38)
    offset_x = int(size * 0.045)

    # Play triangle - accent blue #3b82f6
    points = [
        (cx - tri_w // 2 + offset_x, cy - tri_h // 2),
        (cx + tri_w // 2 + offset_x, cy),
        (cx - tri_w // 2 + offset_x, cy + tri_h // 2),
    ]
    draw.polygon(points, fill=(59, 130, 246, 255))

    # Download arrow below play button
    arrow_w = int(size * 0.10)
    arrow_h = int(size * 0.06)
    arrow_y = cy + tri_h // 2 + int(size * 0.06)
    arrow_cx = cx + offset_x // 2

    # Arrow stem
    stem_w = int(size * 0.025)
    draw.rectangle(
        [arrow_cx - stem_w, arrow_y - int(size * 0.03),
         arrow_cx + stem_w, arrow_y + int(size * 0.02)],
        fill=(59, 130, 246, 200),
    )

    # Arrow head
    draw.polygon(
        [
            (arrow_cx - arrow_w // 2, arrow_y),
            (arrow_cx + arrow_w // 2, arrow_y),
            (arrow_cx, arrow_y + arrow_h),
        ],
        fill=(59, 130, 246, 200),
    )

    # Base line under arrow
    line_y = arrow_y + arrow_h + int(size * 0.015)
    line_w = int(size * 0.10)
    line_h = int(size * 0.012)
    draw.rounded_rectangle(
        [arrow_cx - line_w, line_y, arrow_cx + line_w, line_y + line_h],
        radius=line_h // 2,
        fill=(59, 130, 246, 150),
    )

    return img


logo = create_logo(1024)

# PNG
logo.save(os.path.join(BASE_DIR, "icon.png"), "PNG")

# ICO - let Pillow handle the resizing
ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
logo.save(os.path.join(BASE_DIR, "icon.ico"), format="ICO", sizes=ico_sizes)

# macOS
logo_256 = logo.resize((256, 256), Image.LANCZOS)
logo_256.save(os.path.join(BASE_DIR, "icon.icns"), "PNG")

ico_size = os.path.getsize(os.path.join(BASE_DIR, "icon.ico"))
print(f"Icons created: icon.png, icon.ico ({ico_size} bytes), icon.icns")
