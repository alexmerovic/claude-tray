# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Free to use. Modifying, copying or redistributing this code is not permitted.
# License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
"""Gera ClaudeTray.ico a partir do icone oficial (icon-source.svg).

O PNG de 1024 px ja vem versionado (icon-1024.png), entao o build normal NAO
precisa de Node nem de rasterizador de SVG - so do Pillow. Para regerar o PNG
depois de mexer no SVG:

    cd packaging/icon-tools && npm install sharp
    node -e "require('sharp')('../icon-source.svg',{density:600}).resize(1024,1024).png().toFile('../icon-1024.png')"

Rodar:  python packaging/make_icon.py
"""

from pathlib import Path

from PIL import Image

AQUI = Path(__file__).parent
ORIGEM = AQUI / "icon-1024.png"
TAMANHOS = [16, 24, 32, 48, 64, 128, 256]


def base() -> Image.Image:
    """PNG oficial recortado no conteudo.

    O SVG deixa margem transparente em volta (sobra da sombra). Sem o recorte,
    o icone apareceria pequeno demais no meio do quadrado que a bandeja e a
    barra de tarefas reservam.
    """
    img = Image.open(ORIGEM).convert("RGBA")
    caixa = img.getbbox()
    return img.crop(caixa) if caixa else img


def main() -> None:
    oficial = base()
    # Cada tamanho reduzido a partir do 1024 com LANCZOS; o Windows escolhe o
    # que couber na tela (16 na bandeja, 32 no atalho, 256 no Explorer).
    imagens = [oficial.resize((t, t), Image.LANCZOS) for t in TAMANHOS]
    imagens[-1].save(AQUI / "ClaudeTray.ico", sizes=[(t, t) for t in TAMANHOS],
                     append_images=imagens[:-1])
    oficial.resize((512, 512), Image.LANCZOS).save(AQUI / "ClaudeTray.png")
    print("ok:", AQUI / "ClaudeTray.ico")


if __name__ == "__main__":
    main()
