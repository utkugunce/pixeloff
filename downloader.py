# import instaloader (Moved to lazy import)
import os
import shutil
import re
import json
import requests
from urllib.parse import urlparse, parse_qs, quote
from bs4 import BeautifulSoup
import time
import random

# Constants
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Googlebot/2.1 (+http://www.google.com/bot.html)"
]

_HEADERS = {
    "User-Agent": _USER_AGENTS[0],
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
    "X-ASBD-ID": "129477",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
    "Origin": "https://www.instagram.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def _clean_dir(path):
    if os.path.exists(path):
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path): os.unlink(file_path)
            except: pass

def _log_diagnostic(target_dir, label, content):
    """Save raw response for remote debugging."""
    try:
        diag_path = os.path.join(target_dir, "last_response.log")
        with open(diag_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- {label} ({time.ctime()}) ---\n")
            f.write(content[:10000])
    except: pass

def _shortcode_to_mediaid(shortcode):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id

def _clean_instagram_url(url):
    """Refine URL to get better quality if possible."""
    # Remove resizing (/s640x640/, /p320x320/)
    # Remove other potential resizing params
    url = re.sub(r'/e35/', '/', url)
    url = re.sub(r'/sh0\.08/', '/', url)
    return url

def _clean_instagram_url_hard(url):
    """v4.0 Extreme Clean: Strip EVERYTHING that looks like a resizing/processing token."""
    # Remove query string completely
    url = url.split("?")[0]
    # Remove common patterns in path
    url = re.sub(r'/[sp]\d+x\d+/', '/', url)
    url = re.sub(r'/c\d+\.\d+\.\d+\.\d+/', '/', url)
    url = re.sub(r'/e\d+/', '/', url)
    url = re.sub(r'/sh\d+\.\d+/', '/', url)
    # Re-normalize slashes
    url = url.replace("//", "/").replace("https:/", "https://")
    return url

def download_via_crawler(url, shortcode, target_dir, img_index=1):
    """Method 1: Crawler Mimic (v2.2 Single Post Optimized)"""
    headers = {
        "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        session = requests.Session()
        res = session.get(url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Crawler HTML {shortcode}", res.text)
        
        if res.status_code == 200:
            html = res.text
            
            # v2.3 Fix: Prioritize JSON-LD for High Quality
            # JSON-LD often contains the "contentUrl" which is the original uploaded media
            # Try multiple JSON-LD Patterns (v4.0 Resiliency)
            json_patterns = [
                r'<script type="application/ld\+json">(.*?)</script>',
                r'{"@context":"https://schema\.org","@type":"ImageObject"(.*?)}'
            ]
            for pattern in json_patterns:
                try:
                    matches = re.findall(pattern, html, re.DOTALL)
                    for match_content in matches:
                        # Clean match if it's the second pattern
                        if not match_content.startswith('{'): match_content = '{' + match_content + '}'
                        data = json.loads(match_content)
                        img_url = data.get("contentUrl") or data.get("image", {}).get("url")
                        if img_url and img_index == 1:
                            path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                            _ensure_dir(os.path.dirname(path))
                            # Download
                            res_img = session.get(img_url, headers=_HEADERS, timeout=15)
                            if res_img.status_code == 200:
                                with open(path, "wb") as f: f.write(res_img.content)
                                return path, "Single Post (JSON-LD High-Res)"
                except: continue

            # Fallback 1: Twitter Image (Prioritize over OG for better aspect ratio)
            tw_img = re.search(r'<meta name="twitter:image" content="(.*?)"', html)
            if tw_img and img_index == 1:
                img_url = tw_img.group(1).replace("&amp;", "&")
                # Try cleaning twitter image too
                clean_url = _clean_instagram_url(img_url)
                ir = session.get(clean_url, headers=_HEADERS, timeout=15)
                if ir.status_code != 200: ir = session.get(img_url, headers=_HEADERS, timeout=15)

                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, "Single Post (Twitter-Meta)"

            # Fallback 2: OG Image (Standard - often cropped)
            # v2.3 Fix: Clean the URL to remove cropping/resizing
            og_img = re.search(r'<meta property="og:image" content="(.*?)"', html)
            if og_img and img_index == 1:
                raw_url = og_img.group(1).replace("&amp;", "&")
                img_url = _clean_instagram_url(raw_url)
                
                # Try cleaned URL first
                ir = session.get(img_url, headers=_HEADERS, timeout=15)
                if ir.status_code != 200:
                    # Fallback to raw URL if cleaning broke the signature
                    ir = session.get(raw_url, headers=_HEADERS, timeout=15)
                    
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, "Single Post (OG-Meta cleaned)"
            
            # Fallback 2: Twitter Image
            tw_img = re.search(r'<meta name="twitter:image" content="(.*?)"', html)
            if tw_img and img_index == 1:
                img_url = tw_img.group(1).replace("&amp;", "&")
                ir = session.get(img_url, headers=_HEADERS, timeout=15)
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, "Single Post (Twitter-Meta)"

        return None, f"Crawler: HTTP {res.status_code}"
    except Exception as e: return None, f"Crawler: {e}"

def download_via_oembed(url, shortcode, target_dir, img_index=1):
    """Method 2: OEmbed (v2.2)"""
    oembed_url = f"https://www.instagram.com/oembed/?url={quote(url)}"
    try:
        session = requests.Session()
        res = session.get(oembed_url, timeout=10)
        _log_diagnostic(target_dir, f"OEmbed {shortcode}", res.text)
        if res.status_code == 200:
            data = res.json()
            img_url = data.get("thumbnail_url")
            if img_url and img_index == 1:
                # v2.3 Fix: Try High Res first
                clean_url = _clean_instagram_url(img_url)
                ir = session.get(clean_url, headers=_HEADERS, timeout=15)
                if ir.status_code != 200:
                    ir = session.get(img_url, headers=_HEADERS, timeout=15)
                
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, "Single Post (OEmbed)"
        return None, f"OEmbed: HTTP {res.status_code}"
    except: return None, "OEmbed: Error"

def download_via_mobile_api(shortcode, target_dir, img_index=1):
    """Method 3: i.instagram.com Mobile API"""
    media_id = _shortcode_to_mediaid(shortcode)
    api_url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
    
    headers = _HEADERS.copy()
    headers["User-Agent"] = "Instagram 350.0.0.32.115 Android (33/13; 480dpi; 1080x2400; samsung; SM-G998B; p3s; exynos2100; en_US; 578652230)"
    headers["X-IG-App-ID"] = "936619743392459"
    
    try:
        session = requests.Session()
        res = session.get(api_url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Mobile API {shortcode}", f"Status: {res.status_code}\nBody: {res.text[:1000]}")
        
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            if items:
                item = items[0]
                slides = []
                if "carousel_media" in item:
                    slides = [s["image_versions2"]["candidates"][0]["url"] for s in item["carousel_media"] if s.get("image_versions2")]
                else:
                    cands = item.get("image_versions2", {}).get("candidates", [])
                    if cands: slides.append(cands[0]["url"])
                
                if slides and len(slides) >= img_index:
                    raw_url = slides[img_index-1]
                    clean_url = _clean_instagram_url(raw_url)
                    
                    ir = session.get(clean_url, headers=_HEADERS, timeout=15)
                    if ir.status_code != 200: ir = session.get(raw_url, headers=_HEADERS, timeout=15)
                    
                    if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        return path, f"Slide {img_index} (Mobile API)"
        return None, f"Mobile API: HTTP {res.status_code}"
    except Exception as e: return None, f"Mobile API: {e}"

def download_via_polaris_api(shortcode, target_dir, img_index=1):
    """Method 4: Polaris API"""
    media_id = _shortcode_to_mediaid(shortcode)
    api_url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
    
    headers = _HEADERS.copy()
    headers["User-Agent"] = random.choice(_USER_AGENTS)
    headers["X-IG-App-ID"] = "1217981644879628"
    
    try:
        session = requests.Session()
        res = session.get(api_url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Polaris API {shortcode}", res.text)
        if res.status_code == 200:
            items = res.json().get("items", [])
            if items:
                item = items[0]
                slides = []
                if "carousel_media" in item:
                    slides = [s["image_versions2"]["candidates"][0]["url"] for s in item["carousel_media"] if s.get("image_versions2")]
                else:
                    cands = item.get("image_versions2", {}).get("candidates", [])
                    if cands: slides.append(cands[0]["url"])
                
                if slides and len(slides) >= img_index:
                    raw_url = slides[img_index-1]
                    clean_url = _clean_instagram_url(raw_url)
                    
                    ir = session.get(clean_url, headers=_HEADERS, timeout=15)
                    if ir.status_code != 200: ir = session.get(raw_url, headers=_HEADERS, timeout=15)

                    if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        return path, f"Slide {img_index} (Polaris)"
        return None, f"Polaris: HTTP {res.status_code}"
    except Exception as e: return None, f"Polaris: {e}"

def download_via_embed_json(shortcode, target_dir, img_index=1):
    """Method 5: Deep Scraper"""
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        session = requests.Session()
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        res = session.get(url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Embed HTML {shortcode}", res.text)
        if res.status_code != 200: return None, f"Scraper: HTTP {res.status_code}"
        
        html = res.text
        decoded_html = html.encode('utf-8').decode('unicode-escape', errors='ignore')
        
        patterns = [
            r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"',
            r'window\._sharedData\s*=\s*(.*?);</script>',
            r'__additional_data\s*=\s*(.*?);</script>',
            r'PolarisEmbedSimple\s*=\s*(.*?);</script>'
        ]
        
        for p in patterns:
            m = re.search(p, html)
            if m:
                try:
                    s = m.group(1)
                    if "contextJSON" in p: s = s.replace('\\"', '"').replace('\\\\', '\\').replace('\\/', '/')
                    data = json.loads(s)
                    def find_media(obj):
                        if isinstance(obj, dict):
                            if "shortcode_media" in obj: return obj["shortcode_media"]
                            for v in obj.values():
                                r = find_media(v)
                                if r: return r
                        elif isinstance(obj, list):
                            for v in obj:
                                r = find_media(v)
                                if r: return r
                        return None
                    media = find_media(data)
                    if media:
                        edges = media.get("edge_sidecar_to_children", {}).get("edges", [])
                        slides = [e["node"]["display_url"] for e in edges] if edges else [media.get("display_url")]
                        if len(slides) >= img_index:
                            raw_url = slides[img_index-1]
                            clean_url = _clean_instagram_url(raw_url)
                            
                            ir = session.get(clean_url, headers=_HEADERS, timeout=15)
                            if ir.status_code != 200: ir = session.get(raw_url, headers=_HEADERS, timeout=15)

                            if ir.status_code == 200:
                                path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                                _ensure_dir(os.path.dirname(path))
                                with open(path, "wb") as f: f.write(ir.content)
                                return path, f"Slide {img_index} (Scraper)"
                except: continue
        return None, "Scraper: No match"
    except Exception as e: return None, f"Scraper: {e}"

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """Method 6: Browser Interception"""
    try: from playwright.sync_api import sync_playwright
    except ImportError: return None, "Browser: Missing Playwright"
    
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception as e: return None, f"Browser: Launch Failed ({e})"
            context = browser.new_context(user_agent=random.choice(_USER_AGENTS))
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)
            page.screenshot(path=os.path.join(target_dir, "debug_last_browser.png"))
            
            res = page.evaluate(r'''() => {
                const scripts = Array.from(document.querySelectorAll('script')).map(s => s.textContent).join(' ');
                const match = scripts.match(/"display_url"\s*:\s*"([^"]+)"/g);
                if (match) return match.map(m => m.split('"')[3].replace(/\\/g, ''));
                return null;
            }''')
            
            if res and len(res) >= img_index:
                ir = requests.get(res[img_index-1], headers=_HEADERS, timeout=15)
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    browser.close()
                    return path, f"Slide {img_index} (Browser)"
            browser.close()
            return None, "Browser: Not found"
    except Exception as e: return None, f"Browser: {e}"

def download_via_relay(url, shortcode, target_dir, img_index=1):
    """Method 3: Third-Party Relay (SnapInsta/Indown via Playwright)"""
    # v3.0: Bypass IP Ban by using public downloader services as a proxy
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # Launch browser (headless) with stealth args
            try: 
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
            except: return None, "Relay: Browser Launch Failed"
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # 1. Try SaveVid (Formerly SaveIG) - v4.0 Primary
            try:
                page.goto("https://savevid.net/en/instagram-video-downloader", timeout=15000)
                time.sleep(random.uniform(2, 4)) # Stealth
                page.fill('#s_input', url)
                time.sleep(random.uniform(1, 2))
                page.click('button.btn-default')
                
                # Wait for results with extra time for Cloudflare/Loading
                page.wait_for_selector('a.download-items__btn', timeout=15000)
                download_link = page.get_attribute('a.download-items__btn', 'href')
                
                if download_link:
                    clean_link = _clean_instagram_url(download_link)
                    ir = requests.get(clean_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    if ir.status_code != 200: ir = requests.get(download_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}_savevid.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        browser.close()
                        return path, "Relay Mode (SaveVid)"
            except: pass

            # 2. Try SnapInsta
            try:
                page.goto("https://snapinsta.app/", timeout=15000)
                time.sleep(random.uniform(1, 3))
                page.fill('input[name="url"]', url)
                page.click('.btn-get')
                
                try: page.wait_for_selector('.download-bottom a', timeout=10000)
                except: pass
                download_link = page.get_attribute('.download-bottom a', 'href')
                
                if download_link:
                    clean_link = _clean_instagram_url(download_link)
                    ir = requests.get(clean_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    if ir.status_code != 200: ir = requests.get(download_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}_snapinsta.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        browser.close()
                        return path, "Relay Mode (SnapInsta)"
            except: pass

            # 3. Try Indown.io
            try:
                page.goto("https://indown.io/", timeout=15000)
                time.sleep(random.uniform(1, 3))
                page.fill('input#link', url)
                page.click('#get')
                
                try: page.wait_for_selector('#result', timeout=15000)
                except: pass
                download_link = page.get_attribute('a.btn-download', 'href') 
                
                if download_link:
                     clean_link = _clean_instagram_url(download_link)
                     ir = requests.get(clean_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                     if ir.status_code != 200: ir = requests.get(download_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                     if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}_indown.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        browser.close()
                        return path, "Relay Mode (Indown)"
            except: pass
            
            # v4.0 Extra: Try FastDL.app
            try:
                page.goto("https://fastdl.app/en", timeout=15000)
                time.sleep(random.uniform(1, 2))
                page.fill('#s_input', url)
                page.click('button.btn-premium')
                page.wait_for_selector('a.download-items__btn', timeout=10000)
                download_link = page.get_attribute('a.download-items__btn', 'href')
                if download_link:
                     clean_link = _clean_instagram_url(download_link)
                     ir = requests.get(clean_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                     if ir.status_code != 200: ir = requests.get(download_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                     if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}_fastdl.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        browser.close()
                        return path, "Relay Mode (FastDL)"
            except: pass

            browser.close()
            return None, "Relay: All services failed"

    except Exception as e:
        return None, f"Relay Error: {e}"

def download_via_instaloader(shortcode, target_dir, img_index=1):
    try:
        import instaloader
        L = instaloader.Instaloader(download_pictures=True, download_videos=False, save_metadata=False, max_connection_attempts=1, request_timeout=10)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        nodes = list(post.get_sidecar_nodes()) if post.typename == 'GraphSidecar' else [post]
        if len(nodes) >= img_index:
            img_url = nodes[img_index-1].display_url
            res = requests.get(img_url, headers=_HEADERS, timeout=15)
            if res.status_code == 200:
                path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                _ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f: f.write(res.content)
                return path, "Single Post (Instaloader)"
    except Exception as e: return None, f"Instaloader: {e}"
    return None, None

def download_via_picuki(shortcode, target_dir, img_index=1):
    """Method 7: Picuki (Public Viewer Relay)"""
    try:
        media_id = _shortcode_to_mediaid(shortcode)
        url = f"https://www.picuki.com/media/{media_id}"
        
        session = requests.Session()
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        
        res = session.get(url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Picuki {shortcode}", res.text)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Detect Carousel
            carousel = soup.select('.owl-carousel .item img')
            if carousel:
                slides = [img.get('src') for img in carousel]
            else:
                # Single Image/Video
                # Check for video first just in case (though we want image)
                # Picuki shows video poster as image
                img_elem = soup.select_one('.single-profile-pic img')
                slides = [img_elem.get('src')] if img_elem else []

            if slides and len(slides) >= img_index:
                img_url = slides[img_index-1]
                # Picuki images might be proxied or direct
                ir = session.get(img_url, headers=headers, timeout=15)
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}_picuki.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, "Relay Mode (Picuki)"
        return None, f"Picuki: HTTP {res.status_code} or Content Missing"
    except Exception as e: return None, f"Picuki: {e}"

def download_via_imginn(shortcode, target_dir, img_index=1):
    """Method 8: Imginn (Public Viewer Relay)"""
    try:
        url = f"https://imginn.com/p/{shortcode}/"
        
        session = requests.Session()
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        # Imginn sometimes requires cookies/specific headers, keeping it simple first
        
        res = session.get(url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Imginn {shortcode}", res.text)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Imginn structure varies, but usually .downloads a for download links
            downloads = soup.select('.downloads a.btn-primary')
            # If standard post
            if not downloads:
                # Check for other structures
                pass

            slides = [a.get('href') for a in downloads if a.get('href')]
            
            # Imginn puts video cover and video file, we need to filter for images if possible
            # But for PixelOff we generally want the image representation.
            # Imginn usually lists all media. 
            # Note: Imginn might mix video and image buttons.
            
            if slides and len(slides) >= img_index:
                img_url = slides[img_index-1]
                if img_url.startswith("//"): img_url = "https:" + img_url
                
                ir = session.get(img_url, headers=headers, timeout=15)
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}_imginn.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, "Relay Mode (Imginn)"

        return None, f"Imginn: HTTP {res.status_code} or Content Missing"
    except Exception as e: return None, f"Imginn: {e}"

def download_instagram_image(url, target_dir="downloads", img_index=1):
    m = re.search(r'instagram\.com/(?:[^/]+/)?(?:p|reel)/([^/?#]+)', url)
    if not m: return None, "Invalid URL"
    shortcode = m.group(1)
    _ensure_dir(target_dir)
    _clean_dir(os.path.join(target_dir, shortcode))
    
    open(os.path.join(target_dir, "last_response.log"), "w").close()

    methods = [
        (lambda: download_via_picuki(shortcode, target_dir, img_index), "Picuki Relay (**NEW**)"),
        (lambda: download_via_imginn(shortcode, target_dir, img_index), "Imginn Relay (**NEW**)"),
        (lambda: download_via_mobile_api(shortcode, target_dir, img_index), "Mobile API"),
        (lambda: download_via_embed_json(shortcode, target_dir, img_index), "Deep Scraper"),
        (lambda: download_via_relay(url, shortcode, target_dir, img_index), "Relay Mode (v3.0)"),
        (lambda: download_via_oembed(url, shortcode, target_dir, img_index), "OEmbed"),
        (lambda: download_via_polaris_api(shortcode, target_dir, img_index), "Polaris API"),
        (lambda: download_via_crawler(url, shortcode, target_dir, img_index), "Single Post Mode (Meta)"),
        (lambda: download_via_embed_browser(shortcode, target_dir, img_index), "Interception"),
        (lambda: download_via_instaloader(shortcode, target_dir, img_index), "Instaloader")
    ]
    
    errors = []
    for func, name in methods:
        path, status = func()
        if path: return os.path.abspath(path), status, errors
        if status: errors.append(f"[{name}] {status}")
        time.sleep(random.uniform(1, 2))
    
    return None, " | ".join(errors), errors
