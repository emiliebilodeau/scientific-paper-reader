"""Génère Lecteur.ico (livre ouvert et ondes sonores). Nécessite Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # dessin suréchantillonné puis réduit


def dessiner() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((32, 32, S - 32, S - 32), radius=200, fill=(30, 58, 110))
    # Livre ouvert : deux pages légèrement inclinées
    creme, ombre = (250, 246, 236), (205, 198, 182)
    gauche = [(150, 420), (505, 470), (505, 860), (150, 800)]
    droite = [(519, 470), (874, 420), (874, 800), (519, 860)]
    d.polygon(gauche, fill=creme)
    d.polygon(droite, fill=creme)
    d.line([(512, 468), (512, 862)], fill=ombre, width=14)
    # Lignes de texte
    for i in range(5):
        y = 520 + i * 60
        d.line([(200, y + 6 * i // 5 - 10), (460, y + 30)], fill=(120, 130, 150), width=16)
        d.line([(564, y + 30), (824, y + 6 * i // 5 - 10)], fill=(120, 130, 150), width=16)
    # Ondes sonores au-dessus du livre
    ambre = (255, 184, 48)
    for r, w in ((120, 34), (210, 34), (300, 34)):
        box = (512 - r, 400 - r, 512 + r, 400 + r)
        d.arc(box, start=235, end=305, fill=ambre, width=w)
    return img


def main() -> None:
    img = dessiner()
    sortie = Path(__file__).resolve().parent.parent / "Lecteur.ico"
    tailles = [(n, n) for n in (16, 24, 32, 48, 64, 128, 256)]
    img.resize((256, 256), Image.LANCZOS).save(sortie, sizes=tailles)
    print(sortie)


if __name__ == "__main__":
    main()
