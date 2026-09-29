"""Turn pandoc's HTML fragment of the paper into one self-contained post for Blogger.

Paste the result into Blogger's HTML view (not Compose). It carries:
  - MathJax 3 (loaded from a CDN) so every formula is typeset;
  - every figure embedded as a data URI (Blogger cannot see local files);
  - scoped CSS under .paramanu-post, so the blog's theme is left alone.

    python3 blogger_html.py <pandoc fragment> <output html> <paper dir>
"""
import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

src, dst, paper = sys.argv[1], sys.argv[2], Path(sys.argv[3])
html = Path(src).read_text(encoding="utf-8")

# pandoc's custom-style names (from the Word filters) -> CSS classes
STYLE = {
    "Paper Title": "pm-title", "Paper Subtitle": "pm-subtitle", "Paper Author": "pm-author",
    "Paper Date": "pm-date", "Abstract Heading": "pm-abs-h", "Abstract Text": "pm-abs",
    "Keywords": "pm-kw", "Key Insight Title": "pm-box-h", "Key Insight Body": "pm-box",
    "Equation": "pm-eq", "Theorem": "pm-thm", "Proof": "pm-proof", "Definition": "pm-thm",
}


def restyle(m):
    name = m.group(1)
    return f'class="{STYLE.get(name, "pm-" + re.sub(r"[^a-z]+", "-", name.lower()).strip("-"))}"'


html = re.sub(r'data-custom-style="([^"]+)"', restyle, html)
# a div may now carry two class attributes; merge them
html = re.sub(r'class="([^"]+)"\s+class="([^"]+)"', r'class="\1 \2"', html)


def embed(m):
    path = m.group(1)
    f = (paper / "tools" / path).resolve() if path.startswith("..") else (paper / path)
    if not f.exists():
        f = paper / "figures" / Path(path).name
    im = Image.open(f)
    photo = "lifecycle" in f.name
    if im.width > 1500:
        im = im.resize((1500, round(im.height * 1500 / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    if photo:
        im.convert("RGB").save(buf, "JPEG", quality=82, optimize=True)
        mime = "jpeg"
    else:
        im.convert("RGB").quantize(colors=256).save(buf, "PNG", optimize=True)
        mime = "png"
    data = base64.b64encode(buf.getvalue()).decode()
    return f'<img src="data:image/{mime};base64,{data}"'


html = re.sub(r'<img src="([^"]+)"', embed, html)
html = re.sub(r'(<img [^>]*?)style="width:[^"]*"', r'\1style="max-width:100%;height:auto"', html)

CSS = """
<style>
.paramanu-post{font-family:Georgia,'Times New Roman',serif;font-size:17px;line-height:1.6;color:#1a1a1a;max-width:860px;margin:0 auto}
.paramanu-post h1,.paramanu-post h2,.paramanu-post h3{font-family:Georgia,serif;color:#0b2a5b;line-height:1.3;margin:1.4em 0 .5em}
.paramanu-post h1{font-size:1.5em;border-bottom:2px solid #0b2a5b;padding-bottom:.2em}
.paramanu-post h2{font-size:1.2em}
.paramanu-post .pm-title p{font-size:1.6em;font-weight:bold;text-align:center;color:#0b2a5b;margin:.2em 0}
.paramanu-post .pm-subtitle p{font-size:1.2em;text-align:center;margin:.2em 0}
.paramanu-post .pm-author p,.paramanu-post .pm-date p{text-align:center;margin:.2em 0}
.paramanu-post .pm-abs-h p{font-weight:bold;text-align:center;margin-top:1.2em}
.paramanu-post .pm-abs{margin:0 2em;font-size:.95em}
.paramanu-post .pm-kw{margin:0 2em;font-size:.9em}
.paramanu-post .pm-box-h{background:#0b2a5b;color:#fff;border-radius:6px 6px 0 0;padding:.3em .8em;margin-top:1.2em}
.paramanu-post .pm-box-h p{margin:0;font-weight:bold}
.paramanu-post .pm-box{background:#f2f2ff;border:1px solid #0b2a5b;border-top:0;border-radius:0 0 6px 6px;padding:.6em .9em;margin-bottom:1.2em}
.paramanu-post .pm-eq p{display:flex;justify-content:space-between;align-items:center;gap:1em;overflow-x:auto;margin:.8em 0}
.paramanu-post .pm-eq p>.math{flex:1;text-align:center}
.paramanu-post .pm-thm{margin:.8em 0}
.paramanu-post .pm-proof{margin:.4em 0 .9em;color:#333}
.paramanu-post figure{margin:1.2em 0;text-align:center}
.paramanu-post figure img{max-width:100%;height:auto}
.paramanu-post figcaption{font-size:.9em;color:#333;text-align:left;margin-top:.4em}
.paramanu-post table{border-collapse:collapse;margin:1em auto;font-size:.85em;display:block;overflow-x:auto}
.paramanu-post th,.paramanu-post td{border-top:1px solid #ccc;padding:.3em .5em;vertical-align:top;text-align:left}
.paramanu-post thead th{border-bottom:2px solid #0b2a5b}
.paramanu-post caption{caption-side:top;font-size:.9em;margin-bottom:.4em;text-align:left}
.paramanu-post code{font-size:.88em;background:#f4f4f4;padding:0 .2em;border-radius:3px}
.paramanu-post a{color:#0033aa}
.paramanu-post .citation a{color:#1a7a1a;text-decoration:none}
.paramanu-post #refs{font-size:.85em}
.paramanu-post .csl-entry{margin:.3em 0;padding-left:1.5em;text-indent:-1.5em}
</style>
"""
MATHJAX = """
<script>
window.MathJax = {tex: {inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']]},
                  svg: {fontCache: 'global'}};
</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
"""
out = (CSS + MATHJAX + '<div class="paramanu-post">\n' + html + "\n</div>\n")
Path(dst).write_text(out, encoding="utf-8")
print(f"wrote {dst} ({len(out) / 1e6:.1f} MB)")
