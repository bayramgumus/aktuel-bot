import io
import json
import os
import re
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont

CURRENT_JOB_FILE = "current_job.json"
OUTPUT_DIR = "output_media"

POST_SIZE = (1080, 1350)   # 4:5 Dikey Post
STORY_SIZE = (1080, 1920)  # 9:16 Hikaye

BG_COLOR = (18, 20, 26)          # Koyu lacivert/antrasit zemin
CARD_BG = (255, 255, 255)      # Broşür alanı arka planı
ACCENT_COLOR = (239, 68, 68)   # Vurgu rengi (kırmızı/turuncu ton)
BADGE_BG = (30, 41, 59)        # Üst/alt bilgi şeridi
TEXT_LIGHT = (255, 255, 255)
TEXT_MUTED = (203, 213, 225)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.akakce.com/",
}


def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def clean_title(raw_title):
    text = re.sub(r"\s+", " ", raw_title or "").strip()
    text = re.sub(r"\s*Broşürleri?$", "", text, flags=re.IGNORECASE).strip()
    return text[:70] if text else "Güncel Aktüel Broşür"


def download_image(url, base_url="https://www.akakce.com/brosurler/"):
    full_url = urljoin(base_url, url)
    resp = requests.get(full_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    # Çok küçük ikon/piksel görselleri ele
    if img.width < 200 or img.height < 200:
        raise ValueError(f"Görsel çok küçük ({img.width}x{img.height}), atlandı.")
    return img


def fit_image_inside(img, box_w, box_h):
    ratio = min(box_w / img.width, box_h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def draw_centered_text(draw, text, y, font, fill, max_width):
    # Metni gerekirse iki satıra böl
    words = text.split()
    lines = []
    current = ""
    for w in words:
        trial = f"{current} {w}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
            if len(lines) == 2:
                break
    if current and len(lines) < 2:
        lines.append(current)

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (POST_SIZE[0] - w) // 2 if font.size < 90 else (draw._image.width - w) // 2
        draw.text((x, y + idx * (h + 8)), line, font=font, fill=fill)


def build_post_image(brochure_img, title, duration, page_idx, total_pages):
    w, h = POST_SIZE
    canvas = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    header_h = 150
    footer_h = 120
    pad = 28

    # Üst şerit
    draw.rectangle([0, 0, w, header_h], fill=BADGE_BG)
    draw.rectangle([0, header_h - 6, w, header_h], fill=ACCENT_COLOR)

    title_font = get_font(36, bold=True)
    sub_font = get_font(24, bold=False)

    draw_centered_text(draw, title, 22, title_font, TEXT_LIGHT, w - 80)

    sub_text = duration if duration else "Güncel Kampanya & Aktüel Fırsat"
    if total_pages > 1:
        sub_text = f"{sub_text}  •  Sayfa {page_idx}/{total_pages}"
    draw_centered_text(draw, sub_text, 98, sub_font, TEXT_MUTED, w - 80)

    # Orta broşür alanı
    avail_w = w - pad * 2
    avail_h = h - header_h - footer_h - pad * 2
    box_x = pad
    box_y = header_h + pad

    draw.rounded_rectangle(
        [box_x, box_y, box_x + avail_w, box_y + avail_h],
        radius=20,
        fill=CARD_BG,
    )

    fitted = fit_image_inside(brochure_img, avail_w - 24, avail_h - 24)
    paste_x = box_x + (avail_w - fitted.width) // 2
    paste_y = box_y + (avail_h - fitted.height) // 2
    canvas.paste(fitted, (paste_x, paste_y))

    # Alt şerit
    draw.rectangle([0, h - footer_h, w, h], fill=BADGE_BG)
    footer_text = "Kaydetmeyi unutma • Yeni kataloglar her saat başı"
    draw_centered_text(draw, footer_text, h - footer_h + 38, sub_font, TEXT_LIGHT, w - 80)

    return canvas


def build_story_image(brochure_img, title, duration):
    w, h = STORY_SIZE
    canvas = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    top_h = 220
    bottom_h = 210
    pad = 32

    # Üst alan
    draw.rectangle([0, 0, w, top_h], fill=BADGE_BG)
    draw.rectangle([0, top_h - 8, w, top_h], fill=ACCENT_COLOR)

    tag_font = get_font(26, bold=True)
    title_font = get_font(42, bold=True)
    sub_font = get_font(28, bold=False)

    tag_text = "YENİ AKTÜEL BROŞÜR"
    bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tag_w = bbox[2] - bbox[0] + 36
    tag_x = (w - tag_w) // 2
    draw.rounded_rectangle([tag_x, 24, tag_x + tag_w, 72], radius=16, fill=ACCENT_COLOR)
    draw.text((tag_x + 18, 31), tag_text, font=tag_font, fill=TEXT_LIGHT)

    # Başlığı ortala
    words = title.split()
    short_title = " ".join(words[:7]) if len(words) > 7 else title
    bbox_t = draw.textbbox((0, 0), short_title, font=title_font)
    tw = bbox_t[2] - bbox_t[0]
    draw.text(((w - tw) // 2, 105), short_title, font=title_font, fill=TEXT_LIGHT)

    if duration:
        bbox_d = draw.textbbox((0, 0), duration, font=sub_font)
        dw = bbox_d[2] - bbox_d[0]
        draw.text(((w - dw) // 2, 165), duration, font=sub_font, fill=TEXT_MUTED)

    # Orta hikaye görseli
    avail_w = w - pad * 2
    avail_h = h - top_h - bottom_h - pad * 2
    box_x = pad
    box_y = top_h + pad

    draw.rounded_rectangle(
        [box_x, box_y, box_x + avail_w, box_y + avail_h],
        radius=24,
        fill=CARD_BG,
    )

    fitted = fit_image_inside(brochure_img, avail_w - 28, avail_h - 28)
    paste_x = box_x + (avail_w - fitted.width) // 2
    paste_y = box_y + (avail_h - fitted.height) // 2
    canvas.paste(fitted, (paste_x, paste_y))

    # Alt alan
    draw.rectangle([0, h - bottom_h, w, h], fill=BADGE_BG)
    info_line = "Detaylar ve sayfalar az önce paylaşılan postta"
    bbox_i = draw.textbbox((0, 0), info_line, font=sub_font)
    iw = bbox_i[2] - bbox_i[0]
    draw.text(((w - iw) // 2, h - bottom_h + 75), info_line, font=sub_font, fill=TEXT_LIGHT)

    return canvas


def run_design_factory():
    if not os.path.exists(CURRENT_JOB_FILE):
        print("[TASARIM] İşlenecek 'current_job.json' bulunamadı.")
        return

    with open(CURRENT_JOB_FILE, "r", encoding="utf-8") as f:
        job = json.load(f)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Önceki çıktıları temizle
    for fname in os.listdir(OUTPUT_DIR):
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)

    title = clean_title(job.get("title", ""))
    duration = (job.get("duration") or "").strip()
    raw_images = job.get("images") or []
    page_url = job.get("url") or "https://www.akakce.com/brosurler/"

    downloaded = []
    # Instagram carousel üst sınırı 10 görsel; en fazla 10 sayfa işleyelim
    for img_url in raw_images[:10]:
        try:
            img = download_image(img_url, page_url)
            downloaded.append(img)
        except Exception as e:
            print(f"[UYARI] Görsel indirilemedi ({img_url}): {e}")

    if not downloaded:
        print("[TASARIM] Geçerli broşür görseli bulunamadı; metin kapak kartı üretiliyor.")
        fallback = Image.new("RGB", (900, 1200), (241, 245, 249))
        fdraw = ImageDraw.Draw(fallback)
        ffont = get_font(44, bold=True)
        fdraw.text((80, 520), title[:36], font=ffont, fill=(15, 23, 42))
        downloaded.append(fallback)

    total = len(downloaded)
    post_paths = []
    for idx, img in enumerate(downloaded, start=1):
        post_img = build_post_image(img, title, duration, idx, total)
        out_path = os.path.join(OUTPUT_DIR, f"post_{idx}.jpg")
        post_img.save(out_path, "JPEG", quality=90, optimize=True)
        post_paths.append(out_path)

    story_img = build_story_image(downloaded[0], title, duration)
    story_path = os.path.join(OUTPUT_DIR, "story.jpg")
    story_img.save(story_path, "JPEG", quality=90, optimize=True)

    manifest = {
        "title": title,
        "duration": duration,
        "url": page_url,
        "posts": post_paths,
        "story": story_path,
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[TASARIM] Hazır! {len(post_paths)} post görseli ve 1 hikaye görseli oluşturuldu.")


if __name__ == "__main__":
    run_design_factory()
