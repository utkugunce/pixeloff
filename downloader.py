# import instaloader (Moved to lazy import)
import os
import shutil
import re
import json
import requests
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
import time

# Constants
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
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
            f.write(content[:5000]) # Limit size
    except: pass

def _shortcode_to_mediaid(shortcode):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id

def download_via_polaris_api(shortcode, target_dir, img_index=1):
    """Method 1: Polaris API (Official Web API)"""
    print(f"Attempting Polaris API for {shortcode}...")
    media_id = _shortcode_to_mediaid(shortcode)
    # This is the modern endpoint used by the web app
    api_url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
    
    headers = _HEADERS.copy()
    headers["X-IG-App-ID"] = "1217981644879628" # Web ID
    
    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Polaris API {shortcode}", res.text)
        
        if res.status_code != 200: return None, f"Polaris API: HTTP {res.status_code}"
        
        data = res.json()
        items = data.get("items", [])
        if not items: return None, "Polaris API: No items"
        
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
            img_url = slides[img_index-1].replace('\\/', '/')
            img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
            if img_res.status_code == 200:
                path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                _ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f: f.write(img_res.content)
                return path, f"Slide {img_index} (Polaris)"
    except Exception as e: return None, f"Polaris API: {e}"
    return None, None

def download_via_web_api_legacy(shortcode, target_dir, img_index=1):
    """Method 2: Legacy Web API (__a=1)"""
    for suffix in ["&__d=dis", "&__d=1", ""]:
        api_url = f"https://www.instagram.com/p/{shortcode}/?__a=1{suffix}"
        try:
            res = requests.get(api_url, headers=_HEADERS, timeout=10)
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
                    img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
                    if img_res.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(img_res.content)
                        return path, f"Slide {img_index} (__a=1)"
        except: continue
    return None, None

def download_via_embed_json(shortcode, target_dir, img_index=1):
    """Method 3: Deep Discovery (v1.6)"""
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        res = requests.get(url, headers=_HEADERS, timeout=15)
        _log_diagnostic(target_dir, f"Embed HTML {shortcode}", res.text)
        if res.status_code != 200: return None, f"Embed HTML: {res.status_code}"
        
        html = res.text
        # Decode Unicode escapes (\u002f -> /) to make regex easier
        decoded_html = html.encode('utf-8').decode('unicode-escape', errors='ignore')
        
        # Aggressive Search Patterns
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
                    # Traverse for shortcode_media
                    def find_media(obj):
                        if isinstance(obj, dict):
                            if "shortcode_media" in obj: return obj["shortcode_media"]
                            for v in obj.values():
                                res = find_media(v)
                                if res: return res
                        elif isinstance(obj, list):
                            for v in obj:
                                res = find_media(v)
                                if res: return res
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

        # Brute-force discovery in decoded HTML
        urls = re.findall(r'https://[^"\'\s]+?\.jpg[^"\'\s]*', decoded_html)
        unique_urls = []
        for u in urls:
            if "cdninstagram" in u and u not in unique_urls: 
                # Pick high res
                if "/s1080x1080/" in u or "/v/" not in u: unique_urls.append(u)
        
        if len(unique_urls) >= img_index:
            img_url = unique_urls[img_index-1]
            ir = requests.get(img_url, headers=_HEADERS, timeout=15)
            if ir.status_code == 200:
                path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                _ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f: f.write(ir.content)
                return path, f"Slide {img_index} (Brute-Force)"

        return None, "No data matching slide index found"
    except Exception as e: return None, f"Discovery: {e}"

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """Method 4: Browser Interceptor (v1.6)"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: return None, "Playwright not installed"
    
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception as e: return None, f"Browser Launch: {e}"
            context = browser.new_context(user_agent=_HEADERS["User-Agent"])
            page = context.new_page()
            
            # Diagnostic: Capture all JSON responses
            def handle_res(response):
                if "json" in response.headers.get("content-type", ""):
                    try: _log_diagnostic(target_dir, f"Browser JSON {response.url}", response.text())
                    except: pass
            page.on("response", handle_res)
            
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)
            
            # Save screenshot for debug
            page.screenshot(path=os.path.join(target_dir, "debug_last_browser.png"))
            
            # Final attempt to pull from page state
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
            return None, "Browser failed to find slide"
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
        (download_via_polaris_api, "Polaris API"),
        (download_via_web_api_legacy, "Legacy API"),
        (download_via_embed_json, "Deep Scraper"),
        (download_via_embed_browser, "Interception"),
        (download_via_instaloader, "Instaloader")
    ]
    
    errors = []
    for func, name in methods:
        path, status = func(shortcode, target_dir, img_index)
        if path: return os.path.abspath(path), status
        if status: errors.append(f"[{name}] {status}")
    
    return None, " | ".join(errors)
