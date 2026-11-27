import json
import os
import time
import requests

MANIFEST_PATH = os.path.join("output_media", "manifest.json")
CURRENT_JOB_FILE = "current_job.json"

IG_USER_ID = os.environ.get("IG_USER_ID", "").strip()
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
GRAPH_BASE = "https://graph.facebook.com/v21.0"


def upload_temp_image(filepath):
    """Yerel görseli geçici olarak herkese açık HTTPS URL'ye çevirir."""
    uploaders = [
        ("https://0x0.st", "file"),
        ("https://catbox.moe/user/api.php", "fileToUpload"),
    ]
    for url, field_name in uploaders:
        try:
            with open(filepath, "rb") as f:
                data = {"reqtype": "fileupload"} if "catbox" in url else {}
                headers = {"User-Agent": "AktuelBot/1.0"}
                resp = requests.post(url, files={field_name: f}, data=data, headers=headers, timeout=30)
                resp.raise_for_status()
                link = resp.text.strip()
                if link.startswith("http"):
                    return link
        except Exception as e:
            print(f"[UYARI] Görsel yükleme başarısız ({url}): {e}")
    raise RuntimeError(f"Görsel geçici URL'ye yüklenemedi: {filepath}")


def create_ig_container(payload):
    url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    payload["access_token"] = IG_ACCESS_TOKEN
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def wait_until_ready(creation_id, max_wait=60):
    url = f"{GRAPH_BASE}/{creation_id}"
    params = {"fields": "status_code", "access_token": IG_ACCESS_TOKEN}
    elapsed = 0
    while elapsed < max_wait:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        status = resp.json().get("status_code", "FINISHED")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram container hatası: {resp.text}")
        time.sleep(3)
        elapsed += 3


def publish_container(creation_id):
    url = f"{GRAPH_BASE}/{IG_USER_ID}/media_publish"
    data = {"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN}
    resp = requests.post(url, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json().get("id")


def build_caption(title, duration):
    lines = [f"📌 {title}"]
    if duration:
        lines.append(f"⏳ {duration}")
    lines.append("")
    lines.append("Güncel aktüel katalog ve indirim fırsatları için kaydetmeyi unutma!")
    lines.append("#aktüel #aktüelürünler #indirim #katalog #fırsat")
    return "\n".join(lines)


def publish_post(image_urls, caption):
    if len(image_urls) == 1:
        cid = create_ig_container({
            "image_url": image_urls[0],
            "caption": caption,
        })
        wait_until_ready(cid)
        return publish_container(cid)

    # Carousel (çoklu sayfa) post
    child_ids = []
    for img_url in image_urls[:10]:
        child_id = create_ig_container({
            "image_url": img_url,
            "is_carousel_item": "true",
        })
        wait_until_ready(child_id)
        child_ids.append(child_id)

    carousel_id = create_ig_container({
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
    })
    wait_until_ready(carousel_id)
    return publish_container(carousel_id)


def publish_story(story_url):
    cid = create_ig_container({
        "image_url": story_url,
        "media_type": "STORIES",
    })
    wait_until_ready(cid)
    return publish_container(cid)


def run_publisher():
    if not os.path.exists(MANIFEST_PATH):
        print("[YAYIN] manifest.json bulunamadı; paylaşılacak iş yok.")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    post_files = manifest.get("posts") or []
    story_file = manifest.get("story")
    title = manifest.get("title", "Güncel Aktüel Broşür")
    duration = manifest.get("duration", "")

    if not post_files:
        print("[YAYIN] Post görseli bulunamadı.")
        return

    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("[UYARI] IG_USER_ID veya IG_ACCESS_TOKEN tanımlı değil. Görseller hazırlandı ama Instagram yayını atlandı.")
        return

    post_urls = [upload_temp_image(p) for p in post_files]
    caption = build_caption(title, duration)
    post_id = publish_post(post_urls, caption)
    print(f"[YAYIN] Post yayınlandı! ID: {post_id}")

    if story_file and os.path.exists(story_file):
        time.sleep(5)
        story_url = upload_temp_image(story_file)
        story_id = publish_story(story_url)
        print(f"[YAYIN] Hikaye yayınlandı! ID: {story_id}")

    # İş tamamlandıysa current_job.json'u temizle
    if os.path.exists(CURRENT_JOB_FILE):
        os.remove(CURRENT_JOB_FILE)


if __name__ == "__main__":
    run_publisher()
