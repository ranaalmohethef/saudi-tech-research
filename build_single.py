"""
Builds diraya.html: the whole site in ONE file you can double-click.

It puts the CSS, the JavaScript, the saved data (static/data.js) and all images
(logos, team photos) inside the HTML file.

Run:
    python make_data_js.py --db     # optional: refresh the saved data from PostgreSQL first
    python build_single.py          # writes diraya.html

When diraya.html is opened by double-click it shows the saved data.
When the same page is served by server.py it reads live data from PostgreSQL.
"""
import base64
import io
import re
from pathlib import Path

STATIC = Path(__file__).parent / "static"
OUT = Path(__file__).parent / "diraya.html"


def data_uri(path, max_px=None):
    raw = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    if max_px:
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(raw))
            img.thumbnail((max_px, max_px))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw, mime = buf.getvalue(), "image/png"
        except ImportError:
            pass  # Pillow not installed: keep the original file
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def main():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    # 1. CSS
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")

    # 2. images referenced in the HTML (logos, favicon, team photos)
    def swap(match):
        attr, name = match.group(1), match.group(2)
        path = STATIC / name
        if not path.is_file():
            return match.group(0)          # missing photo: the page shows initials
        return f'{attr}="{data_uri(path, 240)}"'

    html = re.sub(r'(src|href)="((?:team/)?[\w\-]+\.(?:png|jpg|jpeg))"', swap, html)

    # 3. university logos used by app.js (KAUST.png, KSU.png, ...)
    logos = {p.stem: data_uri(p, 120) for p in STATIC.glob("*.png") if p.stem.isupper()}
    logos_js = "window.UNI_LOGOS = {" + ",".join(f'"{k}":"{v}"' for k, v in logos.items()) + "};"

    # 4. scripts
    for name in ("i18n.js", "data.js", "app.js", "particles.js"):
        code = (STATIC / name).read_text(encoding="utf-8").replace("</script", "<\\/script")
        if name == "data.js":
            code = logos_js + "\n" + code
        html = html.replace(f'<script src="{name}"></script>', f"<script>\n{code}\n</script>")

    OUT.write_text(html, encoding="utf-8")
    print(f"{OUT.name} written ({OUT.stat().st_size / 1e6:.1f} MB), university logos: {', '.join(sorted(logos)) or 'none'}")


if __name__ == "__main__":
    main()
