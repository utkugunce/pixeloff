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
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

_HEADERS = {
    "User-Agent": _USER_AGENTS[0],
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
    "X-ASBD-ID": "129477",
    "X-Requested-With": "XMLHttpRequest",
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
            f.write(content[:8000]) # Increased limit for v1.8
    except: pass

def _shortcode_to_mediaid(shortcode):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id

def download_via_oembed(url, shortcode, target_dir, img_index=1):
    """Method 1: Instagram OEmbed API (Lightweight & Public)"""
    print(f"Attempting OEmbed for {shortcode}...")
    # OEmbed is a public endpoint used to generate post previews/previews
    oembed_url = f"https://api.instagram.com/oembed/?url={quote(url)}"
    try:
        res = requests.get(oembed_url, timeout=10)
        _log_diagnostic(target_dir, f"OEmbed {shortcode}", res.text)
        if res.status_code == 200:
            data = res.json()
            img_url = data.get("thumbnail_url")
            if img_url and img_index == 1: # OEmbed usually only gives the cover
                ir = requests.get(img_url, headers=_HEADERS, timeout=15)
                if ir.status_code == 200:
                    path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                    _ensure_dir(os.path.dirname(path))
                    with open(path, "wb") as f: f.write(ir.content)
                    return path, f"Slide 1 (OEmbed)"
    except: pass
    return None, None

def download_via_polaris_api(shortcode, target_dir, img_index=1):
    """Method 2: Polaris API (v1.8 No-Cookie Tuning)"""
    media_id = _shortcode_to_mediaid(shortcode)
    api_url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
    
    # Random wait to avoid bot detection
    time.sleep(random.uniform(1, 2))
    
    for attempt in range(2):
        # v1.8 Fix: Create a fresh session WITHOUT cookies for the first call
        session = requests.Session()
        session.cookies.clear() 
        
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        headers["X-IG-App-ID"] = "1217981644879628" 
        
        try:
            res = session.get(api_url, headers=headers, timeout=15)
            _log_diagnostic(target_dir, f"Polaris API {shortcode} - Att {attempt+1}", f"Status: {res.status_code}\nHeaders: {dict(res.headers)}\nBody: {res.text[:1000]}")
            
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    slides = []
                    if "carousel_media" in item:
                        for s in item["carousel_media"]:
                            cands = s.get("image_versions2", {}).get("candidates", [])
                            if cands: slides.append(cands[0]["url"])
                    else:
                        cands = item.get("image_versions2", {}).get("candidates", [])
                        if cands: slides.append(cands[0]["url"])
                    
                    if slides and len(slides) >= img_index:
                        img_url = slides[img_index-1]
                        ir = session.get(img_url, headers=_HEADERS, timeout=15)
                        if ir.status_code == 200:
                            path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                            _ensure_dir(os.path.dirname(path))
                            with open(path, "wb") as f: f.write(ir.content)
                            return path, f"Slide {img_index} (Polaris)"
            
            if res.status_code == 429:
                wait_time = random.uniform(5, 10) # Longer wait for 429
                time.sleep(wait_time)
                continue
                
        except Exception as e:
            if attempt == 0: continue
            return None, f"Polaris Error: {e}"
            
    return None, "Polaris API: Blocked or No Data"

def download_via_web_api_legacy(shortcode, target_dir, img_index=1):
    """Method 3: Legacy Web API (__a=1)"""
    time.sleep(random.uniform(1, 2))
    for suffix in ["&__d=dis", "&__d=1"]:
        api_url = f"https://www.instagram.com/p/{shortcode}/?__a=1{suffix}"
        try:
            headers = _HEADERS.copy()
            headers["User-Agent"] = random.choice(_USER_AGENTS)
            res = requests.get(api_url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                media = data.get("items", [{}])[0] if data.get("items") else data.get("graphql", {}).get("shortcode_media")
                if not media: continue
                
                slides = []
                if "carousel_media" in media:
                    slides = [s["image_versions2"]["candidates"][0]["url"] for s in media["carousel_media"]]
                elif "edge_sidecar_to_children" in media:
                    slides = [e["node"]["display_url"] for e in media["edge_sidecar_to_children"]["edges"]]
                else:
                    slides = [media.get("display_url")]
                
                if len(slides) >= img_index:
                    img_url = slides[img_index-1]
                    ir = requests.get(img_url, headers=_HEADERS, timeout=15)
                    if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        return path, f"Slide {img_index} (__a=1)"
        except: continue
    return None, None

def download_via_embed_json(shortcode, target_dir, img_index=1):
    """Method 4: Deep Discovery v1.8"""
    time.sleep(random.uniform(1, 2))
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        res = requests.get(url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Embed HTML {shortcode}", res.text)
        if res.status_code != 200: return None, f"Embed: {res.status_code}"
        
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
                        slides = []
                        if "edge_sidecar_to_children" in media:
                            slides = [e["node"]["display_url"] for e in media["edge_sidecar_to_children"]["edges"]]
                        else:
                            slides = [media.get("display_url")]
                        
                        if len(slides) >= img_index:
                            img_url = slides[img_index-1]
                            ir = requests.get(img_url, headers=_HEADERS, timeout=15)
                            if ir.status_code == 200:
                                path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                                _ensure_dir(os.path.dirname(path))
                                with open(path, "wb") as f: f.write(ir.content)
                                return path, f"Slide {img_index} (Scraper)"
                except: continue

        # v1.8 Deep Unescape Brute-Force
        urls = re.findall(r'https://[^"\'\s]+?\.jpg[^"\'\s]*', decoded_html)
        unique_urls = []
        for u in urls:
            u = u.replace('\\/', '/')
            if "cdninstagram" in u and u not in unique_urls:
                if "/s1080x1080/" in u or "x" not in u: unique_urls.insert(0, u)
                else: unique_urls.append(u)
        
        if len(unique_urls) >= img_index:
            img_url = unique_urls[img_index-1]
            ir = requests.get(img_url, headers=_HEADERS, timeout=15)
            if ir.status_code == 200:
                path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                _ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f: f.write(ir.content)
                return path, f"Slide {img_index} (Brute-Force)"

        return None, "Shadow block or structure mismatch"
    except Exception as e: return None, f"Discovery: {e}"

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """Method 5: Browser Interceptor v1.8"""
    time.sleep(random.uniform(1, 2))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: return None, "Playwright not installed"
    
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception as e: return None, f"Launch: {e}"
            context = browser.new_context(user_agent=random.choice(_USER_AGENTS))
            page = context.new_page()
            
            def handle_res(response):
                if "/graphql/query" in response.url and response.status == 200:
                    try: _log_diagnostic(target_dir, f"Browser GraphQL {shortcode}", response.text())
                    except: pass
            
            page.on("response", handle_res)
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(random.uniform(5, 7))
            
            page.screenshot(path=os.path.join(target_dir, "debug_last_browser.png"))
            
            # Extract URLs from JS state
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
            return None, "Browser failed"
    except Exception as e: return None, f"Browser: {e}"

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
                return path, f"Slide {img_index} (Instaloader)"
    except Exception as e: return None, f"Instaloader: {e}"
    return None, None

def download_instagram_image(url, target_dir="downloads", img_index=1):
    m = re.search(r'instagram\.com/(?:[^/]+/)?(?:p|reel)/([^/?#]+)', url)
    if not m: return None, "Invalid URL"
    shortcode = m.group(1)
    _ensure_dir(target_dir)
    _clean_dir(os.path.join(target_dir, shortcode))
    
    # Initialize diagnostic log
    open(os.path.join(target_dir, "last_response.log"), "w").close()

    methods = [
        (lambda: download_via_oembed(url, shortcode, target_dir, img_index), "OEmbed Fallback"),
        (lambda: download_via_polaris_api(shortcode, target_dir, img_index), "Polaris API"),
        (lambda: download_via_web_api_legacy(shortcode, target_dir, img_index), "Legacy API"),
        (lambda: download_via_embed_json(shortcode, target_dir, img_index), "Deep Scraper"),
        (lambda: download_via_embed_browser(shortcode, target_dir, img_index), "Interception"),
        (lambda: download_via_instaloader(shortcode, target_dir, img_index), "Instaloader")
    ]
    
    errors = []
    for func, name in methods:
        path, status = func()
        if path: return os.path.abspath(path), status
        if status: errors.append(f"[{name}] {status}")
    
    return None, " | ".join(errors)
