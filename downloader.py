# import instaloader (Moved to lazy import)
import os
import shutil
import re
import json
import requests
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
import time
import random

# Constants
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
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
            f.write(content[:5000]) # Limit size
    except: pass

def _shortcode_to_mediaid(shortcode):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id

def download_via_polaris_api(shortcode, target_dir, img_index=1):
    """Method 1: Polaris API (v1.7 with Jittered Retries)"""
    media_id = _shortcode_to_mediaid(shortcode)
    api_url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
    
    for attempt in range(2):
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        headers["X-IG-App-ID"] = "1217981644879628" 
        
        try:
            res = requests.get(api_url, headers=headers, timeout=15)
            _log_diagnostic(target_dir, f"Polaris API Attempt {attempt+1} - {shortcode}", f"Status: {res.status_code}\nContent: {res.text[:1000]}")
            
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    slides = []
                    if "carousel_media" in item:
                        slides = [s.get("image_versions2", {}).get("candidates", [])[0]["url"] for s in item["carousel_media"] if s.get("image_versions2")]
                    else:
                        cands = item.get("image_versions2", {}).get("candidates", [])
                        if cands: slides.append(cands[0]["url"])
                    
                    if slides and len(slides) >= img_index:
                        img_url = slides[img_index-1]
                        ir = requests.get(img_url, headers=_HEADERS, timeout=15)
                        if ir.status_code == 200:
                            path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                            _ensure_dir(os.path.dirname(path))
                            with open(path, "wb") as f: f.write(ir.content)
                            return path, f"Slide {img_index} (Polaris)"
            
            if res.status_code == 429 and attempt == 0:
                wait_time = random.uniform(3, 7)
                print(f"Rate limited (429). Waiting {wait_time:.1f}s and retrying...")
                time.sleep(wait_time)
                continue
                
        except Exception as e:
            if attempt == 0: continue
            return None, f"Polaris API Error: {e}"
            
    return None, "Polaris API: Limit or No Data"

def download_via_web_api_legacy(shortcode, target_dir, img_index=1):
    """Method 2: Legacy Web API (__a=1)"""
    for suffix in ["&__d=dis", "&__d=1", ""]:
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
    """Method 3: Deep Discovery v1.7 (Enhanced Decoding)"""
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        headers = _HEADERS.copy()
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        res = requests.get(url, headers=headers, timeout=15)
        _log_diagnostic(target_dir, f"Embed HTML {shortcode}", res.text)
        if res.status_code != 200: return None, f"Embed HTML: {res.status_code}"
        
        html = res.text
        # Decode Unicode escapes to make regex more effective against obfuscation
        decoded_html = html.encode('utf-8').decode('unicode-escape', errors='ignore')
        
        # Pattern matching for JSON-like structures
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

        # Brute-force discovery in decoded HTML (Systematic)
        # Search for high-res jpg URLs in any attribute
        urls = re.findall(r'https://[^"\'\s]+?\.jpg[^"\'\s]*', decoded_html)
        unique_urls = []
        for u in urls:
            u = u.replace('\\/', '/')
            if "cdninstagram" in u and u not in unique_urls:
                # Prefer 1080px or higher
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

        return None, "Extraction failed: Shadow block or structure mismatch"
    except Exception as e: return None, f"Discovery: {e}"

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """Method 4: Browser Interceptor (v1.7)"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: return None, "Playwright not installed"
    
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        with sync_playwright() as p:
            try: 
                browser = p.chromium.launch(headless=True)
                print("Headless browser launched...")
            except Exception as e: return None, f"Browser Launch: {e}"
            
            context = browser.new_context(user_agent=random.choice(_USER_AGENTS))
            page = context.new_page()
            
            # Intercept all responses to find GraphQL data
            intercepted_data = {"data": None}
            def handle_res(response):
                if "/graphql/query" in response.url and response.status == 200:
                    try:
                        jd = response.json()
                        if "data" in jd and "shortcode_media" in jd["data"]:
                            intercepted_data["data"] = jd["data"]["shortcode_media"]
                            print("GraphQL data intercepted!")
                    except: pass
            
            page.on("response", handle_res)
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)
            
            # Save screenshot for app.py to display
            page.screenshot(path=os.path.join(target_dir, "debug_last_browser.png"))
            
            data = intercepted_data["data"]
            if not data:
                # Fallback: Extract from JS variables
                data = page.evaluate(r'''() => {
                    const scripts = Array.from(document.querySelectorAll('script')).map(s => s.textContent).join(' ');
                    const m = scripts.match(/"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"/);
                    if (m) {
                        const s = m[1].replace(/\\"/g, '"').replace(/\\\\/g, '\\').replace(/\\\//g, '/');
                        return JSON.parse(s).gql_data.shortcode_media;
                    }
                    return null;
                }''')
            
            if data:
                edges = data.get('edge_sidecar_to_children', {}).get('edges', [])
                slides = [e['node']['display_url'] for e in edges] if edges else [data.get('display_url')]
                if len(slides) >= img_index:
                    img_url = slides[img_index-1]
                    ir = requests.get(img_url, headers=_HEADERS, timeout=15)
                    if ir.status_code == 200:
                        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
                        _ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f: f.write(ir.content)
                        browser.close()
                        return path, f"Slide {img_index} (Browser)"
            
            browser.close()
            return None, "Browser failed to find media"
    except Exception as e: return None, f"Browser Error: {e}"

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
    
    # Reset diagnostic log
    open(os.path.join(target_dir, "last_response.log"), "w").close()

    methods = [
        (download_via_polaris_api, "Polaris API"),
        (download_via_web_api_legacy, "Legacy API"),
        (download_via_embed_json, "Scraper Discovery"),
        (download_via_embed_browser, "Interception"),
        (download_via_instaloader, "Instaloader")
    ]
    
    errors = []
    for func, name in methods:
        path, status = func(shortcode, target_dir, img_index)
        if path: return os.path.abspath(path), status
        if status: errors.append(f"[{name}] {status}")
    
    return None, " | ".join(errors)
