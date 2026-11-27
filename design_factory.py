import io
import json
import os
import re
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont

CURRENT_JOB_FILE = "current_job.json"
OUTPUT_DIR = "output_media"
CUSTOM_LOGO_PATH = "logo.png"

POST_SIZE = (1080, 1350)   # 4:5 Dikey Post
STORY_SIZE = (1080, 1920)  # 9:16 Hikaye

BG_COLOR = (255, 255, 255)   # Beyaz zemin

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


def _fetch_single_image(full_url):
    resp = requests.get(full_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    if img.width < 220 or img.height < 220:
        raise ValueError(f"Görsel çok küçük ({img.width}x{img.height}), atlandı.")
    return img


def download_image(url, base_url="https://www.akakce.com/brosurler/"):
    full_url = urljoin(base_url, url)
    if "/_bro/y/" in full_url:
        hq_url = full_url.replace("/_bro/y/", "/_bro/u/")
        try:
            return _fetch_single_image(hq_url)
        except Exception as e:
            print(f"[UYARI] Yüksek kaliteli sürüm alınamadı ({hq_url}), yedek deneniyor: {e}")
    return _fetch_single_image(full_url)


def fit_brochure_to_canvas(brochure_img, canvas_w, canvas_h, margin=0):
    avail_w = max(1, canvas_w - margin * 2)
    avail_h = max(1, canvas_h - margin * 2)
    ratio = min(avail_w / brochure_img.width, avail_h / brochure_img.height)
    new_w = max(1, int(brochure_img.width * ratio))
    new_h = max(1, int(brochure_img.height * ratio))
    return brochure_img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def draw_corner_brand_badge(canvas, is_story=False):
    w, h = canvas.size

    if os.path.exists(CUSTOM_LOGO_PATH):
        try:
            logo = Image.open(CUSTOM_LOGO_PATH).convert("RGBA")
            max_logo_w = 165 if is_story else 145
            max_logo_h = 90 if is_story else 80
            ratio = min(max_logo_w / logo.width, max_logo_h / logo.height)
            logo = logo.resize(
                (max(1, int(logo.width * ratio)), max(1, int(logo.height * ratio))),
                Image.Resampling.LANCZOS,
            )
            pad_x = 12
            pad_y = 20 if is_story else 12
            pos_x = max(0, w - logo.width - pad_x)
            pos_y = max(0, h - logo.height - pad_y)

            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            overlay.paste(logo, (pos_x, pos_y), logo)
            merged = Image.alpha_composite(canvas.convert("RGBA"), overlay)
            canvas.paste(merged.convert("RGB"), (0, 0))
            return
        except Exception as e:
            print(f"[UYARI] Özel logo yüklenemedi, metin rozet kullanılacak: {e}")

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    font_size = 22 if is_story else 20
    font = get_font(font_size, bold=True)
    label = "Aktüel Kelebek"

    bbox = odraw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    px = 16
    py = 9
    box_w = text_w + px * 2
    box_h = text_h + py * 2

    margin_right = 12
    margin_bottom = 20 if is_story else 12

    x1 = w - margin_right - box_w
    y1 = h - margin_bottom - box_h
    x2 = w - margin_right
    y2 = h - margin_bottom

    odraw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=14,
        fill=(15, 23, 42, 215),
        outline=(255, 255, 255, 70),
        width=1,
    )
    odraw.text((x1 + px, y1 + py - 2), label, font=font, fill=(255, 255, 255, 245))

    merged = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    canvas.paste(merged.convert("RGB"), (0, 0))


def compose_clean_canvas(brochure_img, size, is_story=False):
    w, h = size
    canvas = Image.new("RGB", (w, h), BG_COLOR)
    fitted = fit_brochure_to_canvas(brochure_img, w, h, margin=0)
    paste_x = (w - fitted.width) // 2
    paste_y = (h - fitted.height) // 2
    canvas.paste(fitted, (paste_x, paste_y))
    draw_corner_brand_badge(canvas, is_story=is_story)
    return canvas


def run_design_factory():
    if not os.path.exists(CURRENT_JOB_FILE):
        print("[TASARIM] İşlenecek 'current_job.json' bulunamadı.")
        return

    with open(CURRENT_JOB_FILE, "r", encoding="utf-8") as f:
        job = json.load(f)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for fname in os.listdir(OUTPUT_DIR):
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)

    title = clean_title(job.get("title", ""))
    duration = (job.get("duration") or "").strip()
    raw_images = job.get("images") or []
    page_url = job.get("url") or "https://www.akakce.com/brosurler/"

    prioritized_images = sorted(
        raw_images,
        key=lambda u: (0 if "/_bro/" in str(u) else 1),
    )

    downloaded = []
    for img_url in prioritized_images[:10]:
        try:
            img = download_image(img_url, page_url)
            downloaded.append(img)
        except Exception as e:
            print(f"[UYARI] Görsel indirilemedi ({img_url}): {e}")

    if not downloaded:
        print("[TASARIM] İndirilebilir geçerli görsel bulunamadı; üretim atlandı.")
        return

    post_paths = []
    for idx, img in enumerate(downloaded, start=1):
        post_img = compose_clean_canvas(img, POST_SIZE, is_story=False)
        out_path = os.path.join(OUTPUT_DIR, f"post_{idx}.jpg")
        post_img.save(out_path, "JPEG", quality=95, subsampling=0, optimize=True)
        post_paths.append(out_path)

    story_img = compose_clean_canvas(downloaded[0], STORY_SIZE, is_story=True)
    story_path = os.path.join(OUTPUT_DIR, "story.jpg")
    story_img.save(story_path, "JPEG", quality=95, subsampling=0, optimize=True)

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
