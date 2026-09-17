"""Generate fictional documents; no customer or personal data."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent / "samples"


def font(size):
    for path in (
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def generate():
    ROOT.mkdir(exist_ok=True)
    for slug, total in [("clean", "214.00"), ("mismatch", "219.00")]:
        im = Image.new("RGB", (1000, 1280), "#ffffff")
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 1000, 18), fill="#182a46")
        d.text((70, 70), "INVOICE", fill="#182a46", font=font(54))
        d.text(
            (70, 150), "Fictional sample / AI Workbench", fill="#677387", font=font(25)
        )
        texts = [
            "Supplier: Pacific Demo Supplies",
            "Invoice number: INV-2026-041",
            "Date: 2026-09-17",
            "Currency: USD",
        ]
        for i, value in enumerate(texts):
            d.text((70, 260 + i * 65), value, fill="#162238", font=font(32))
        d.line((70, 560, 930, 560), fill="#ccd3dd", width=2)
        d.text((70, 605), "Description", fill="#677387", font=font(27))
        d.text((720, 605), "Amount", fill="#677387", font=font(27))
        d.text((70, 680), "Workshop equipment kit", fill="#162238", font=font(30))
        d.text((720, 680), "200.00", fill="#162238", font=font(30))
        d.line((70, 770, 930, 770), fill="#ccd3dd", width=2)
        for i, value in enumerate(
            ["Subtotal: 200.00", "Tax: 14.00", f"Total: {total}"]
        ):
            d.text((510, 830 + i * 70), value, fill="#162238", font=font(34))
        d.text(
            (70, 1150),
            "SYNTHETIC DOCUMENT - NOT PAYABLE",
            fill="#677387",
            font=font(24),
        )
        im.save(ROOT / f"{slug}.png")
    Image.open(ROOT / "clean.png").filter(ImageFilter.GaussianBlur(1.7)).save(
        ROOT / "soft-scan.png"
    )


if __name__ == "__main__":
    generate()
