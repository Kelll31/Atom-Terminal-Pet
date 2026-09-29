"""Иконка Патрика: морская звезда с глазами.

Рисуется кодом, а не берётся из файла, по двум причинам: в трее иконка нужна
сразу и не должна зависеть от того, доехал ли ресурс до сборки, а для .exe и
установщика тот же самый рисунок выгружается в .ico одной командой:

    python tray_icon.py packaging/atompet.ico
"""

from __future__ import annotations

import math
import sys

from PIL import Image, ImageDraw

SKIN = (250, 146, 166, 255)
OUTLINE = (58, 24, 34, 255)
WHITE = (255, 253, 250, 255)
PUPIL = (30, 18, 22, 255)

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build_image(size: int = 256) -> Image.Image:
    # Рисуем с четырёхкратным запасом и уменьшаем: у Pillow нет сглаживания
    # контуров, а без него на 16×16 звезда выглядит рваной.
    scale = 4
    big = size * scale
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    center = big / 2
    outer = big * 0.47
    inner = outer * 0.56   # толстые лучи: тонкие на 16×16 съедаются масштабом

    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = outer if i % 2 == 0 else inner
        points.append((center + math.cos(angle) * radius, center + math.sin(angle) * radius))

    line = max(2, int(big * 0.035))
    draw.polygon(points, fill=SKIN)
    draw.line(points + [points[0]], fill=OUTLINE, width=line, joint="curve")

    eye_dx = big * 0.15
    eye_y = big * 0.42
    eye_r = big * 0.115
    pupil_r = eye_r * 0.55

    for sign in (-1, 1):
        ex = center + sign * eye_dx
        draw.ellipse([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
                     fill=WHITE, outline=OUTLINE, width=line)
        # Зрачки слегка сведены к центру — тот же «дурашливый» взгляд, что на экране
        px = ex - sign * eye_r * 0.18
        draw.ellipse([px - pupil_r, eye_y - pupil_r, px + pupil_r, eye_y + pupil_r], fill=PUPIL)

    return image.resize((size, size), Image.LANCZOS)


def write_ico(path: str) -> None:
    build_image(256).save(path, format="ICO", sizes=ICO_SIZES)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "atompet.ico"
    write_ico(target)
    print(f"Иконка записана: {target}")
