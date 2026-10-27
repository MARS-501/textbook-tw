"""產生 App 圖示（Focus App 配色：黑底、白字）。

執行：uv run python app/build/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONT = Path("C:/Windows/Fonts/msjhbd.ttc")  # 微軟正黑體粗體
SIZE = 256


def draw(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    pen = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), int(size * 0.62))
    box = pen.textbbox((0, 0), "譯", font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    pen.text((x, y), "譯", font=font, fill=(255, 255, 255, 255))
    return image


if __name__ == "__main__":
    big = draw(SIZE)
    big.save(HERE / "icon.png")
    big.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(HERE / "icon.ico")
