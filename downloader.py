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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
    "X-ASBD-ID": "129477",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

def _ensure_dir(path):
    """Safely create directory."""
    os.makedirs(path, exist_ok=True)

def _clean_dir(path):
    """Clean up directory before new download."""
    if os.path.exists(path):
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path): os.unlink(file_path)
            except: pass

def _shortcode_to_mediaid(shortcode):
    """Convert Instagram shortcode to numeric media ID."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id

def download_via_web_api(shortcode, target_dir, img_index=1):
    """Method 1: Instagram Web API (__a=1)"""
    api_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
    headers = _HEADERS.copy()
    headers["X-IG-App-ID"] = "1217981644879628"
    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code != 200: return None, f"Web API: HTTP {res.status_code}"
        data = res.json()
        items = data.get("items", [])
        if not items:
            media = data.get("graphql", {}).get("shortcode_media")
        else:
            media = items[0]
        if not media: return None, "Web API: No media found"
        
        slides = []
        if "carousel_media" in media:
            slides = [s.get("image_versions2", {}).get("candidates", [])[0]["url"] for s in media["carousel_media"]]
        elif "edge_sidecar_to_children" in media:
            slides = [e["node"]["display_url"] for e in media["edge_sidecar_to_children"].get("edges", [])]
        else:
            cand = media.get("image_versions2", {}).get("candidates", [])
            slides = [cand[0]["url"]] if cand else [media.get("display_url")]

        if not slides or len(slides) < img_index: return None, "Web API: Index out of range"
        img_url = slides[img_index-1].replace('\\/', '/')
        img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
        if img_res.status_code == 200:
            output_dir = os.path.join(target_dir, shortcode)
            _ensure_dir(output_dir)
            path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
            with open(path, "wb") as f: f.write(img_res.content)
            return path, f"Slide {img_index} (Web API)"
    except Exception as e: return None, f"Web API: {e}"
    return None, None

def download_via_embed_json(shortcode, target_dir, img_index=1):
    """Method 2: Discovery Engine (Resilient Scraper)"""
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        res = requests.get(url, headers=_HEADERS, timeout=15)
        if res.status_code != 200: return None, f"Embed Page: HTTP {res.status_code}"
        html = res.text
        data = None
        
        # Pattern 1: contextJSON
        m = re.search(r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if m:
            s = m.group(1).replace('\\"', '"').replace('\\\\', '\\').replace('\\/', '/')
            try: data = json.loads(s).get('gql_data', {}).get('shortcode_media')
            except: pass
            
        # Pattern 2: _sharedData
        if not data:
            m = re.search(r'window\._sharedData\s*=\s*(.*?);</script>', html)
            if m:
                try: 
                    jd = json.loads(m.group(1))
                    data = jd.get('entry_data', {}).get('PostPage', [{}])[0].get('graphql', {}).get('shortcode_media')
                except: pass

        # Pattern 3: __additional_data
        if not data:
            m = re.search(r'__additional_data\s*=\s*(.*?);</script>', html)
            if m:
                try: 
                    jd = json.loads(m.group(1))
                    data = jd['graphql'].get('shortcode_media') if 'graphql' in jd else jd.get('shortcode_media')
                except: pass
        
        # Pattern 4: PolarisEmbedSimple (Newest)
        if not data:
            m = re.search(r'PolarisEmbedSimple\s*=\s*(.*?);</script>', html)
            if m:
                try: data = json.loads(m.group(1)).get('shortcode_media')
                except: pass

        # Pattern 5: Brute-force discovery
        if not data:
            soup = BeautifulSoup(html, 'html.parser')
            all_jpgs = []
            for s in soup.find_all('script'):
                if not s.string: continue
                urls = re.findall(r'https://[^"]+?\.jpg[^"]*', s.string)
                for u in urls:
                    u = u.replace('\\/', '/')
                    if ("/s" in u and "x" in u) or ("cdninstagram" in u):
                        if u not in all_jpgs: all_jpgs.append(u)
            all_jpgs.sort(key=lambda x: ("1080x1080" in x), reverse=True)
            if len(all_jpgs) >= img_index:
                img_url = all_jpgs[img_index-1]
                img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
                if img_res.status_code == 200:
                    output_dir = os.path.join(target_dir, shortcode)
                    _ensure_dir(output_dir)
                    path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
                    with open(path, "wb") as f: f.write(img_res.content)
                    return path, f"Slide {img_index} (Discovery)"

        if data:
            slides = []
            if data.get('edge_sidecar_to_children'):
                edges = data['edge_sidecar_to_children'].get('edges', [])
                slides = [{'url': e['node']['display_url'], 'is_v': e['node']['is_video']} for e in edges]
            else:
                slides = [{'url': data['display_url'], 'is_v': data['is_video']}]
            
            if slides and img_index <= len(slides):
                s = slides[img_index-1]
                if s['is_v']: return None, "Video slide"
                img_url = s['url'].replace('\\/', '/')
                img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
                if img_res.status_code == 200:
                    output_dir = os.path.join(target_dir, shortcode)
                    _ensure_dir(output_dir)
                    path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
                    with open(path, "wb") as f: f.write(img_res.content)
                    return path, f"Slide {img_index}/{len(slides)} (Scraper)"
        return None, "No slide data found"
    except Exception as e: return None, f"Scraper: {e}"

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """Method 3: Interception Browser (v1.5)"""
    print(f"Attempting Interception Browser for {shortcode}...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: return None, "Playwright not installed"
    
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception as e: return None, f"Launch: {e}"
            context = browser.new_context(user_agent=_HEADERS["User-Agent"])
            page = context.new_page()
            
            intercepted_data = {"data": None}
            def handle_response(response):
                if "/graphql/query" in response.url and response.status == 200:
                    try:
                        jd = response.json()
                        if "data" in jd and "shortcode_media" in jd["data"]:
                            intercepted_data["data"] = jd["data"]["shortcode_media"]
                    except: pass

            page.on("response", handle_response)
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)  # Wait for background GraphQL queries

            # Fallback to evaluate if interception failed
            if not intercepted_data["data"]:
                intercepted_data["data"] = page.evaluate(r'''
                    () => {
                        const scripts = Array.from(document.querySelectorAll('script')).map(s => s.textContent).join(' ');
                        const m = scripts.match(/"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"/);
                        if (m) {
                            const s = m[1].replace(/\\"/g, '"').replace(/\\\\/g, '\\').replace(/\\\//g, '/');
                            return JSON.parse(s).gql_data.shortcode_media;
                        }
                        return null;
                    }
                ''')

            # Save debug screenshot if requested (system check)
            screenshot_path = os.path.join(target_dir, "debug_last_browser.png")
            page.screenshot(path=screenshot_path)

            if intercepted_data["data"]:
                data = intercepted_data["data"]
                edges = data.get('edge_sidecar_to_children', {}).get('edges', [])
                slides = [e['node']['display_url'] for e in edges] if edges else [data.get('display_url')]
                if slides and len(slides) >= img_index:
                    img_url = slides[img_index-1].replace('\\/', '/')
                    img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
                    if img_res.status_code == 200:
                        output_dir = os.path.join(target_dir, shortcode)
                        _ensure_dir(output_dir)
                        path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
                        with open(path, "wb") as f: f.write(img_res.content)
                        browser.close()
                        return path, f"Slide {img_index} (Interception)"
            
            browser.close()
            return None, "Browser interception failed to find media"
    except Exception as e: return None, f"Browser: {e}"

def download_via_instaloader(shortcode, target_dir, img_index=1):
    """Method 4: Instaloader Tool"""
    try:
        import instaloader
        L = instaloader.Instaloader(download_pictures=True, download_videos=False, save_metadata=False, max_connection_attempts=1, request_timeout=10)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        if post.typename == 'GraphSidecar':
            nodes = list(post.get_sidecar_nodes())
            if img_index > len(nodes): img_index = len(nodes)
            img_url = nodes[img_index-1].display_url
            res = requests.get(img_url, headers=_HEADERS, timeout=15)
            if res.status_code == 200:
                output_dir = os.path.join(target_dir, shortcode)
                _ensure_dir(output_dir)
                path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
                with open(path, "wb") as f: f.write(res.content)
                return path, f"Slide {img_index} (Instaloader)"
    except Exception as e: return None, f"Instaloader: {e}"
    return None, None

def download_instagram_image(url, target_dir="downloads", img_index=1):
    """Main Entry"""
    m = re.search(r'instagram\.com/(?:[^/]+/)?(?:p|reel)/([^/?#]+)', url)
    if not m: return None, "Invalid URL"
    shortcode = m.group(1)
    _clean_dir(os.path.join(target_dir, shortcode))
    
    methods = [
        (download_via_web_api, "Web API"),
        (download_via_embed_json, "Scraper Discovery"),
        (download_via_embed_browser, "Browser Interception"),
        (download_via_instaloader, "Instaloader")
    ]
    
    errors = []
    for func, name in methods:
        path, status = func(shortcode, target_dir, img_index)
        if path: return os.path.abspath(path), status
        if status: errors.append(f"[{name}] {status}")
    return None, " | ".join(errors)
