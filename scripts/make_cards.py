"""Generate shareable PNG cards (one per owner) + an Open Graph image + a touch icon.

Reads the already-built standings.json + config.json. Uses the brand fonts from
assets/fonts/ when present, otherwise falls back to Pillow's default font so cards
still generate. Any failure is swallowed (update.sh calls this with `|| true`) — cards
are a nice-to-have and must never break a publish.
"""

import os
import sys

import store

PAPER = (246, 239, 223)
CARD = (251, 245, 232)
BAND = (24, 77, 52)
INK = (33, 34, 27)
SOFT = (89, 86, 68)
MUT = (138, 131, 108)
GAIN = (46, 106, 67)
LOSS = (162, 64, 44)
GOLD = (168, 129, 46)
CREAM = (244, 239, 223)
RULE = (227, 215, 190)

FONT_DIR = os.path.join(store.ROOT, "assets", "fonts")
CARD_DIR = os.path.join(store.ROOT, "cards")
ASSET_DIR = os.path.join(store.ROOT, "assets")


def _font(names, size):
    from PIL import ImageFont
    for n in names:
        p = os.path.join(FONT_DIR, n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def disp(size):
    return _font(["FamiljenGrotesk-Bold.ttf", "FamiljenGrotesk[wght].ttf", "FamiljenGrotesk-Regular.ttf"], size)


def mono(size):
    return _font(["IBMPlexMono-SemiBold.ttf", "IBMPlexMono-Regular.ttf"], size)


def _w(draw, text, font):
    try:
        return draw.textlength(text, font=font)
    except Exception:
        return font.getbbox(text)[2]


def slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def fmt_pct(v):
    return "—" if v is None else ("+" if v > 0 else "") + f"{v:.2f}%"


def owner_card(d, cfg, o, leader_avg):
    from PIL import Image, ImageDraw
    W = H = 1080
    img = Image.new("RGB", (W, H), PAPER)
    dr = ImageDraw.Draw(img)
    state = d.get("state", "pre")

    dr.rectangle([0, 0, W, 208], fill=BAND)
    t = (cfg.get("title", "The Draft Ledger")).upper()
    f_t = disp(46)
    dr.text(((W - _w(dr, t, f_t)) / 2, 78), t, font=f_t, fill=CREAM)
    dr.rectangle([(W / 2 - 150), 150, (W / 2 + 150), 154], fill=GOLD)

    first = o.get("rank") == 1
    if first:
        dr.rectangle([0, 208, 18, H], fill=GOLD)

    dr.text((70, 268), o["name"], font=disp(66), fill=INK)
    if state == "pre":
        dr.text((72, 360), "PICKS LOCKED · TRADING OPENS JUL 1", font=disp(26), fill=GOLD if first else SOFT)
    else:
        avg = o.get("avg")
        col = GAIN if (avg or 0) >= 0 else LOSS
        dr.text((70, 348), fmt_pct(avg), font=mono(104), fill=col)
        rk = o.get("rank")
        behind = "leader" if rk == 1 else (f"{o.get('points_behind'):.2f} pts back" if o.get("points_behind") is not None else "")
        sub = f"RANK {rk} OF {d.get('owner_count', len(d['standings']))}" + (f" · {behind}" if behind else "")
        dr.text((74, 470), sub, font=disp(28), fill=SOFT)

    y = 600
    for p in o["picks"]:
        dr.rounded_rectangle([70, y, W - 70, y + 110], radius=14, fill=CARD, outline=RULE, width=2)
        dr.text((96, y + 24), p["sym"], font=mono(40), fill=INK)
        dr.text((98, y + 74), p.get("name", "")[:34], font=disp(22), fill=MUT)
        if state != "pre":
            pc = p.get("pct")
            col = GAIN if (pc or 0) >= 0 else LOSS
            s = fmt_pct(pc)
            dr.text((W - 96 - _w(dr, s, mono(40)), y + 36), s, font=mono(40), fill=col)
        else:
            s = p.get("sector", "")
            dr.text((W - 96 - _w(dr, s, disp(22)), y + 44), s, font=disp(22), fill=MUT)
        y += 130

    foot = f"{cfg.get('title','The Draft Ledger')} · {cfg.get('edition','')} · winner picks first"
    dr.text((70, H - 56), foot, font=disp(22), fill=MUT)
    os.makedirs(CARD_DIR, exist_ok=True)
    img.save(os.path.join(CARD_DIR, f"{slug(o['name'])}.png"))


def og_image(d, cfg):
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BAND)
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, W, 12], fill=GOLD)
    t = (cfg.get("title", "The Draft Ledger")).upper()
    dr.text((64, 150), t, font=disp(96), fill=CREAM)
    dr.text((66, 286), cfg.get("subtitle", ""), font=disp(34), fill=(207, 224, 207))
    state = d.get("state", "pre")
    if state == "pre":
        line = "Trading opens July 1 — picks locked"
    else:
        ranked = [s for s in d["standings"] if s.get("rank")]
        line = (f"Leader: {ranked[0]['name']}  {fmt_pct(ranked[0]['avg'])}" if ranked else "")
    dr.rectangle([66, 360, 66 + 220, 364], fill=GOLD)
    dr.text((66, 396), line, font=mono(40), fill=CREAM)
    dr.text((64, H - 60), "Draft-order stock challenge", font=disp(24), fill=(150, 170, 150))
    os.makedirs(ASSET_DIR, exist_ok=True)
    img.save(os.path.join(ASSET_DIR, "og.png"))


def touch_icon(cfg):
    from PIL import Image, ImageDraw
    S = 180
    img = Image.new("RGB", (S, S), BAND)
    dr = ImageDraw.Draw(img)
    f = disp(96)
    t = "DL"
    dr.text(((S - _w(dr, t, f)) / 2, 32), t, font=f, fill=GOLD)
    os.makedirs(ASSET_DIR, exist_ok=True)
    img.save(os.path.join(ASSET_DIR, "apple-touch-icon.png"))


def main():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("cards: Pillow not installed — skipping.")
        return 0
    d = store.load("standings.json", None)
    cfg = store.load("config.json", {})
    if not d or not d.get("standings"):
        print("cards: no standings yet — skipping.")
        return 0
    leader = next((s["avg"] for s in d["standings"] if s.get("rank") == 1), None)
    n = 0
    for o in d["standings"]:
        try:
            owner_card(d, cfg, o, leader)
            n += 1
        except Exception as e:
            print(f"cards: failed for {o.get('name')}: {e}")
    try:
        og_image(d, cfg)
        touch_icon(cfg)
    except Exception as e:
        print(f"cards: og/icon failed: {e}")
    print(f"cards: wrote {n} owner cards + og + icon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
