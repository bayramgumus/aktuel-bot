import json
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.akakce.com/brosurler/"
SEEN_FILE = "seen_brochures.json"
QUEUE_FILE = "queue.json"
CURRENT_JOB_FILE = "current_job.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

SKIP_KEYWORDS = [
    "logo",
    "icon",
    "sprite",
    "avatar",
    "svg",
    "pixel",
    "tracker",
    "facebook",
    "instagram",
    "twitter",
    "youtube",
    "whatsapp",
    "play-store",
    "app-store",
]


def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[UYARI] {filepath} okunamadı, varsayılan kullanılıyor: {e}")
    return default


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_html(url, timeout=20):
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def extract_brochure_links(html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(BASE_URL, href)
        parsed = urlparse(full_url)

        if "akakce.com" not in parsed.netloc:
            continue
        if full_url.rstrip("/") == BASE_URL.rstrip("/"):
            continue
        if "brosur" not in parsed.path.lower():
            continue
        if parsed.path.rstrip("/").endswith("/brosurler"):
            continue

        raw_text = " ".join(a.get_text(" ", strip=True).split())
        title_attr = (a.get("title") or "").strip()
        title = title_attr or raw_text or "Aktüel Broşür"

        parent_text = " ".join(a.parent.get_text(" ", strip=True).split()) if a.parent else raw_text
        time_match = re.search(
            r"(\d+\s*(?:gün|hafta|ay)\s*kaldı|Bugün\s*(?:başlıyor|son)|Yarın\s*başlıyor|Son\s*gün\s*\w+)",
            parent_text,
            re.IGNORECASE,
        )
        duration_info = time_match.group(0) if time_match else ""

        if full_url not in found:
            found[full_url] = {
                "url": full_url,
                "title": title,
                "duration": duration_info,
            }

    return list(found.values())


def pick_best_from_srcset(srcset_val):
    if not srcset_val:
        return ""
    parts = [p.strip() for p in srcset_val.split(",") if p.strip()]
    if not parts:
        return ""
    return parts[-1].split()[0].strip()


def extract_brochure_images(detail_html, page_url):
    soup = BeautifulSoup(detail_html, "html.parser")
    brochure_pages = []
    other_images = []
    seen_img = set()

    for img in soup.find_all("img"):
        srcset = img.get("data-srcset") or img.get("srcset") or ""
        src = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("data-full")
            or img.get("src")
            or pick_best_from_srcset(srcset)
            or ""
        ).strip()

        if not src and srcset:
            src = pick_best_from_srcset(srcset)

        if not src or src.startswith("data:image") or "t.gif" in src:
            continue

        full_img = urljoin(page_url, src)
        lower = full_img.lower()

        if any(skip in lower for skip in SKIP_KEYWORDS):
            continue

        w_attr = img.get("width")
        h_attr = img.get("height")
        try:
            if w_attr and int(re.sub(r"\D", "", str(w_attr)) or 0) < 150:
                continue
            if h_attr and int(re.sub(r"\D", "", str(h_attr)) or 0) < 150:
                continue
        except Exception:
            pass

        if full_img not in seen_img:
            seen_img.add(full_img)
            if "/_bro/" in full_img:
                brochure_pages.append(full_img)
            else:
                other_images.append(full_img)

    images = brochure_pages + other_images

    if not images:
        og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        if og and og.get("content"):
            og_url = urljoin(page_url, og["content"].strip())
            if not any(skip in og_url.lower() for skip in SKIP_KEYWORDS):
                images.append(og_url)

    return images


def run_scraper():
    print("[AVCI] Akakçe broşür taraması başlıyor...")
    seen = load_json(SEEN_FILE, {"urls": []})
    seen_set = set(seen.get("urls", []))
    queue = load_json(QUEUE_FILE, [])

    try:
        main_html = fetch_html(BASE_URL)
    except Exception as e:
        print(f"[HATA] Ana sayfa çekilemedi: {e}")
        return

    candidates = extract_brochure_links(main_html)
    print(f"[AVCI] Sayfada {len(candidates)} aday bağlantı bulundu.")

    new_count = 0
    for item in candidates:
        url = item["url"]
        if url in seen_set:
            continue

        seen_set.add(url)
        images = []
        try:
            detail_html = fetch_html(url)
            images = extract_brochure_images(detail_html, url)
            time.sleep(1.5)
        except Exception as e:
            print(f"[UYARI] Detay sayfası okunamadı ({url}): {e}")

        if not images:
            print(f"[ATLANDI] Görsel bulunamadı: {item['title']} ({url})")
            continue

        brochure_item = {
            "url": url,
            "title": item["title"],
            "duration": item["duration"],
            "images": images,
            "discovered_at": int(time.time()),
        }
        queue.append(brochure_item)
        new_count += 1

    save_json(SEEN_FILE, {"urls": list(seen_set)})
    save_json(QUEUE_FILE, queue)
    print(f"[AVCI] {new_count} yeni broşür kuyruğa eklendi. Toplam kuyruk: {len(queue)}")

    if queue and not os.path.exists(CURRENT_JOB_FILE):
        next_job = queue.pop(0)
        save_json(CURRENT_JOB_FILE, next_job)
        save_json(QUEUE_FILE, queue)
        print(f"[KUYRUK] Sıradaki iş seçildi: {next_job['title']} ({len(next_job['images'])} görsel)")
    elif os.path.exists(CURRENT_JOB_FILE):
        print("[KUYRUK] Halihazırda işlenmeyi bekleyen bir 'current_job.json' mevcut.")
    else:
        print("[KUYRUK] Kuyruk şu an boş.")


if __name__ == "__main__":
    run_scraper()
