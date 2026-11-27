import hashlib
import json
import os
import re
import time
from urllib.parse import quote

import requests

MANIFEST_FILE = os.path.join("output_media", "manifest.json")
OUTPUT_DIR = "output_media"
CURRENT_JOB_FILE = "current_job.json"
QUEUE_FILE = "queue.json"

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
STORY_PUBLISH_DELAY_SEC = 3

BASE_DISCOVERY_TAGS = [
    "#aktüelürünler",
    "#aktüelkatalog",
    "#aktüel",
    "#indirimliürünler",
    "#haftanınhırsatları",
    "#indirim",
    "#kampanya",
    "#alışverişrehberi",
    "#fırsatürünleri",
    "#evihityaçları",
]

ROTATING_GROWTH_TAGS = [
    "#keşfet",
    "#keşfetteyiz",
    "#indirimavcısı",
    "#fırsatavcısı",
    "#ekonomikalışveriş",
    "#güncelbroşür",
    "#haftalıkaktüel",
    "#bütçedostu",
    "#akıllıalışveriş",
    "#katalog",
]

MARKET_KEYWORDS = {
    "a101": "#a101",
    "bim": "#bim",
    "şok": "#şokmarket",
    "sok": "#şokmarket",
    "migros": "#migros",
    "carrefoursa": "#carrefoursa",
    "tarım kredi": "#tarımkredi",
    "hakmar": "#hakmar",
    "macrocenter": "#macrocenter",
    "metro": "#metromarket",
    "gratis": "#gratis",
    "watsons": "#watsons",
    "rossmann": "#rossmann",
    "koçtaş": "#koçtaş",
    "ikea": "#ikea",
    "teknosa": "#teknosa",
    "mediamarkt": "#mediamarkt",
    "vatan": "#vatanbilgisayar",
}

CATEGORY_KEYWORDS = {
    "tv": ["#televizyon", "#elektronik"],
    "led": ["#televizyon", "#elektronik"],
    "telefon": ["#telefon", "#teknoloji"],
    "buzdolabı": ["#beyazeşya", "#mutfak"],
    "çamaşır": ["#beyazeşya"],
    "bulaşık": ["#beyazeşya"],
    "klima": ["#iklimlendirme", "#beyazeşya"],
    "süpürge": ["#elektrikli ev aletleri"],
    "kahve": ["#kahveseverler", "#mutfak"],
    "peynir": ["#kahvaltılık", "#gıda"],
    "zeytin": ["#kahvaltılık", "#gıda"],
    "temizlik": ["#temizlikürünleri"],
    "bebek": ["#annebebek"],
    "oyuncak": ["#çocuk", "#oyuncak"],
    "giyim": ["#moda", "#giyim"],
    "kozmetik": ["#kozmetik", "#bakım"],
}


def get_env_config():
    ig_user_id = (os.getenv("IG_USER_ID") or "").strip()
    ig_access_token = (os.getenv("IG_ACCESS_TOKEN") or "").strip()
    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    branch = (os.getenv("GITHUB_REF_NAME") or "main").strip()
    raw_base_url = (os.getenv("PUBLIC_MEDIA_BASE_URL") or "").strip().rstrip("/")

    if not raw_base_url and repo:
        raw_base_url = f"https://raw.githubusercontent.com/{repo}/refs/heads/{branch}"

    return {
        "ig_user_id": ig_user_id,
        "ig_access_token": ig_access_token,
        "media_base_url": raw_base_url,
    }


def to_public_media_url(local_path, media_base_url):
    normalized = local_path.replace("\\", "/").lstrip("./")
    encoded_path = "/".join(quote(part) for part in normalized.split("/"))
    return f"{media_base_url}/{encoded_path}"


def sanitize_hashtag(tag):
    clean = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]", "", tag.lstrip("#").lower())
    return f"#{clean}" if len(clean) >= 2 else ""


def build_growth_hashtags(title, duration=""):
    text = f"{title} {duration}".lower()
    tags = []
    seen = set()

    def add_tag(t):
        s = sanitize_hashtag(t)
        if s and s not in seen:
            seen.add(s)
            tags.append(s)

    for kw, htag in MARKET_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", text):
            add_tag(htag)

    for kw, cat_tags in CATEGORY_KEYWORDS.items():
        if kw in text:
            for ct in cat_tags:
                add_tag(ct)

    digest = hashlib.md5(f"{title}|{duration}".encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)

    rotated_base = BASE_DISCOVERY_TAGS.copy()
    shift_base = seed % len(rotated_base)
    rotated_base = rotated_base[shift_base:] + rotated_base[:shift_base]
    for bt in rotated_base[:6]:
        add_tag(bt)

    rotated_growth = ROTATING_GROWTH_TAGS.copy()
    shift_growth = (seed // 7) % len(rotated_growth)
    rotated_growth = rotated_growth[shift_growth:] + rotated_growth[:shift_growth]
    for gt in rotated_growth[:4]:
        add_tag(gt)

    return " ".join(tags[:14])


def build_post_caption(title, duration="", url=""):
    lines = [f"✨ {title}"]
    if duration:
        lines.append(f"🗓️ Geçerlilik: {duration}")
    lines.append("")
    lines.append("Fırsatları kaçırmamak için kaydet 📌, ihtiyacın olanı paylaş 🔁")
    lines.append("Güncel katalog ve yeni broşürler için sayfamızı takip et 👇")

    hashtags = build_growth_hashtags(title, duration)
    if hashtags:
        lines.append("")
        lines.append(hashtags)

    caption = "\n".join(lines).strip()
    return caption[:2200]


def api_post(endpoint, params):
    url = f"{GRAPH_BASE_URL}/{endpoint.lstrip('/')}"
    resp = requests.post(url, data=params, timeout=45)
    data = resp.json() if resp.content else {}
    if not resp.ok or "error" in data:
        raise RuntimeError(f"Instagram API hatası ({endpoint}): {data}")
    return data


def api_get(endpoint, params):
    url = f"{GRAPH_BASE_URL}/{endpoint.lstrip('/')}"
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json() if resp.content else {}
    if not resp.ok or "error" in data:
        raise RuntimeError(f"Instagram API GET hatası ({endpoint}): {data}")
    return data


def wait_until_container_ready(creation_id, access_token, max_attempts=12, delay=4):
    for _ in range(max_attempts):
        status = api_get(
            creation_id,
            {"fields": "status_code,status", "access_token": access_token},
        )
        code = (status.get("status_code") or "").upper()
        if code in ("FINISHED", "PUBLISHED", ""):
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Medya konteyneri hataya düştü ({creation_id}): {status}")
        time.sleep(delay)


def publish_single_photo(ig_user_id, access_token, image_url, caption):
    container = api_post(
        f"{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
    )
    creation_id = container["id"]
    wait_until_container_ready(creation_id, access_token)

    published = api_post(
        f"{ig_user_id}/media_publish",
        {
            "creation_id": creation_id,
            "access_token": access_token,
        },
    )
    return published.get("id")


def publish_carousel(ig_user_id, access_token, image_urls, caption):
    child_ids = []
    for img_url in image_urls[:10]:
        child = api_post(
            f"{ig_user_id}/media",
            {
                "image_url": img_url,
                "is_carousel_item": "true",
                "access_token": access_token,
            },
        )
        child_id = child["id"]
        wait_until_container_ready(child_id, access_token)
        child_ids.append(child_id)

    carousel = api_post(
        f"{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": access_token,
        },
    )
    carousel_id = carousel["id"]
    wait_until_container_ready(carousel_id, access_token)

    published = api_post(
        f"{ig_user_id}/media_publish",
        {
            "creation_id": carousel_id,
            "access_token": access_token,
        },
    )
    return published.get("id")


def publish_story(ig_user_id, access_token, story_url):
    container = api_post(
        f"{ig_user_id}/media",
        {
            "image_url": story_url,
            "media_type": "STORIES",
            "access_token": access_token,
        },
    )
    story_id = container["id"]
    wait_until_container_ready(story_id, access_token)

    published = api_post(
        f"{ig_user_id}/media_publish",
        {
            "creation_id": story_id,
            "access_token": access_token,
        },
    )
    return published.get("id")


def advance_queue_after_success():
    if os.path.exists(CURRENT_JOB_FILE):
        os.remove(CURRENT_JOB_FILE)

    if os.path.exists(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            fpath = os.path.join(OUTPUT_DIR, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)

    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)
        if isinstance(queue, list) and queue:
            next_job = queue.pop(0)
            with open(CURRENT_JOB_FILE, "w", encoding="utf-8") as f:
                json.dump(next_job, f, ensure_ascii=False, indent=2)
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue, f, ensure_ascii=False, indent=2)
            print(f"[KUYRUK] Sıradaki iş yüklendi: {next_job.get('title', 'Broşür')}")


def get_story_files(manifest):
    raw_stories = manifest.get("stories")
    if isinstance(raw_stories, list) and raw_stories:
        return [p for p in raw_stories if p and os.path.exists(p)]

    single_story = manifest.get("story")
    if single_story and os.path.exists(single_story):
        return [single_story]

    return []


def run_publisher():
    if not os.path.exists(MANIFEST_FILE):
        print("[YAYINCI] 'output_media/manifest.json' bulunamadı; paylaşım atlandı.")
        return

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    post_files = [p for p in (manifest.get("posts") or []) if os.path.exists(p)]
    story_files = get_story_files(manifest)

    if not post_files and not story_files:
        print("[YAYINCI] Paylaşılacak görsel bulunamadı.")
        return

    cfg = get_env_config()
    if not cfg["ig_user_id"] or not cfg["ig_access_token"]:
        print("[YAYINCI] IG_USER_ID veya IG_ACCESS_TOKEN tanımlı değil; paylaşım atlandı.")
        return

    if not cfg["media_base_url"]:
        print("[YAYINCI] Genel medya URL tabanı bulunamadı.")
        return

    title = manifest.get("title") or "Güncel Aktüel Broşür"
    duration = manifest.get("duration") or ""
    url = manifest.get("url") or ""
    caption = build_post_caption(title, duration, url)

    post_urls = [to_public_media_url(p, cfg["media_base_url"]) for p in post_files]

    if len(post_urls) == 1:
        media_id = publish_single_photo(cfg["ig_user_id"], cfg["ig_access_token"], post_urls[0], caption)
        print(f"[YAYINCI] Tekil gönderi yayınlandı. Media ID: {media_id}")
    elif len(post_urls) > 1:
        media_id = publish_carousel(cfg["ig_user_id"], cfg["ig_access_token"], post_urls, caption)
        print(f"[YAYINCI] Karusel gönderi ({len(post_urls)} görsel) yayınlandı. Media ID: {media_id}")

    total_stories = len(story_files)
    for idx, story_file in enumerate(story_files, start=1):
        story_url = to_public_media_url(story_file, cfg["media_base_url"])
        story_media_id = publish_story(cfg["ig_user_id"], cfg["ig_access_token"], story_url)
        print(f"[YAYINCI] Hikaye {idx}/{total_stories} yayınlandı. Story ID: {story_media_id}")
        if idx < total_stories:
            time.sleep(STORY_PUBLISH_DELAY_SEC)

    advance_queue_after_success()


if __name__ == "__main__":
    run_publisher()
