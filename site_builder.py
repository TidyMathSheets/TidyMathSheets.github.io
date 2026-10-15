"""Static pin website + per-board RSS feeds for Pinterest auto-publishing.

Standalone (standard library only) so it can also run inside the public site repo's
daily GitHub Action. Reads data/pins.json and publishes only pins whose publish time has
passed, so Pinterest picks them up a few per day instead of all at once.

Usage: python3 site_builder.py <site_dir>
"""
import json, os, re, sys, html
from datetime import datetime, timezone
from email.utils import format_datetime


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load(site):
    with open(os.path.join(site, "data", "pins.json")) as f:
        pins = json.load(f)
    cfg_path = os.path.join(site, "data", "site.json")
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    return pins, cfg


def due(pins, now=None):
    now = now or datetime.now(timezone.utc)
    return [p for p in pins if datetime.fromisoformat(p["publish_utc"]) <= now]


CSS = """
:root{--ink:#222;--soft:#666;--bg:#faf8f3;--card:#fff;--line:#e6e2d8}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;
color:var(--ink);background:var(--bg);line-height:1.5}
main{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:clamp(28px,5vw,44px);line-height:1.1;margin:0 0 8px}p.lead{color:var(--soft);margin:0 0 28px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;text-decoration:none;color:inherit}
.card img{width:100%;display:block;aspect-ratio:2/3;object-fit:cover}.card div{padding:12px 14px;font-weight:600;font-size:15px}
.pin{display:grid;grid-template-columns:minmax(0,420px) 1fr;gap:36px;align-items:start}
.pin img{width:100%;border-radius:14px;border:1px solid var(--line)}
.btn{display:inline-block;margin:20px 0;padding:16px 28px;border-radius:999px;color:#fff;font-weight:700;
text-decoration:none;font-size:18px}
footer{margin-top:48px;color:var(--soft);font-size:13px}
@media(max-width:720px){.pin{grid-template-columns:1fr}}
"""


def page(title, body, cfg, extra_head=""):
    verify = cfg.get("pinterest_verify", "")
    meta = f'<meta name="p:domain_verify" content="{html.escape(verify)}"/>' if verify else ""
    shop = html.escape(cfg.get("shop_name", ""))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{meta}{extra_head}
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><main>{body}<footer>{shop + ' · ' if shop else ''}Printable math worksheets for home and classroom.</footer></main></body></html>"""


def pin_page(p, cfg, base):
    img = f"{base}/{p['image']}"
    head = (f'<meta property="og:title" content="{html.escape(p["title"])}">'
            f'<meta property="og:description" content="{html.escape(p["description"])}">'
            f'<meta property="og:image" content="{img}">')
    body = f"""<div class="pin"><img src="../{p['image']}" alt="{html.escape(p['alt'])}">
<div><h1>{html.escape(p['title'])}</h1><p class="lead">{html.escape(p['product_name'])}</p>
<p>{html.escape(p['description'])}</p>
<a class="btn" style="background:{p['color']}" href="{html.escape(p['link'])}">See it on Etsy →</a>
<p><a href="../index.html">More printable math worksheets</a></p></div></div>"""
    return page(p["title"], body, cfg, head)


def rss(items, title, base, board):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>',
           f"<title>{html.escape(title)} — {html.escape(board)}</title><link>{base}/</link>",
           f"<description>{html.escape(board)}</description>"]
    for p in items:
        img = f"{base}/{p['image']}"
        link = f"{base}/p/{p['id']}.html"
        when = format_datetime(datetime.fromisoformat(p["publish_utc"]))
        desc = html.escape(f'<img src="{img}" alt="{p["alt"]}"/><p>{p["description"]}</p>')
        out.append(f"<item><title>{html.escape(p['title'])}</title><link>{link}</link><guid>{link}</guid>"
                   f"<pubDate>{when}</pubDate><description>{desc}</description>"
                   f'<enclosure url="{img}" type="image/jpeg" length="0"/>'
                   f'<media:content url="{img}" medium="image"/></item>')
    out.append("</channel></rss>")
    return "\n".join(out)


def build(site, now=None):
    pins, cfg = load(site)
    base = cfg.get("site_url", "").rstrip("/")
    live = sorted(due(pins, now), key=lambda p: p["publish_utc"], reverse=True)
    os.makedirs(os.path.join(site, "p"), exist_ok=True)
    os.makedirs(os.path.join(site, "feeds"), exist_ok=True)
    for p in live:
        with open(os.path.join(site, "p", f"{p['id']}.html"), "w") as f:
            f.write(pin_page(p, cfg, base))
    cards = "".join(f'<a class="card" href="p/{p["id"]}.html"><img loading="lazy" src="{p["image"]}" '
                    f'alt="{html.escape(p["alt"])}"><div>{html.escape(p["title"])}</div></a>' for p in live[:120])
    name = cfg.get("shop_name") or "Printable Math Worksheets"
    body = (f"<h1>{html.escape(name)}</h1><p class='lead'>No-prep printable math practice with answer keys, "
            f"for homeschool families and teachers.</p><div class='grid'>{cards}</div>")
    with open(os.path.join(site, "index.html"), "w") as f:
        f.write(page(name, body, cfg))
    boards = sorted({p["board"] for p in pins})
    index = {}
    for b in boards:
        items = [p for p in live if p["board"] == b][:50]
        fn = f"feeds/{slugify(b)}.xml"
        with open(os.path.join(site, fn), "w") as f:
            f.write(rss(items, name, base, b))
        index[b] = f"{base}/{fn}"
    with open(os.path.join(site, "feeds", "index.json"), "w") as f:
        json.dump(index, f, indent=2)
    with open(os.path.join(site, ".nojekyll"), "w") as f:
        f.write("")
    return len(live), index


if __name__ == "__main__":
    n, feeds = build(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(f"{n} pins live")
    for b, u in feeds.items():
        print(f"  {b}: {u}")
