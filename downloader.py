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
    "X-IG-App-ID": "936619743392459",  # Mobile App ID
    "X-ASBD-ID": "129477",
    "X-Requested-With": "XMLHttpRequest",
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
    print(f"Attempting Web API for {shortcode} (slide {img_index})...")
    # This endpoint often returns JSON directly and is more stable than the embed page
    api_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
    
    headers = _HEADERS.copy()
    headers["X-IG-App-ID"] = "1217981644879628" # Web App ID
    
    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code != 200:
            return None, f"Web API: HTTP {res.status_code}"
            
        data = res.json()
        media = data.get("items", [{}])[0].get("product_type") # Check if it's the right data structure
        
        # Determine items based on structure
        items = data.get("items", [])
        if not items:
             # Try alternate structure (graphql based)
             media = data.get("graphql", {}).get("shortcode_media")
        else:
             media = items[0]

        if not media: return None, "Web API: No media found in JSON"
        
        slides = []
        # Carousel check
        if "carousel_media" in media:
            for s in media["carousel_media"]:
                candidates = s.get("image_versions2", {}).get("candidates", [])
                if candidates:
                    slides.append(candidates[0]["url"])
        elif "edge_sidecar_to_children" in media:
            edges = media["edge_sidecar_to_children"].get("edges", [])
            for e in edges:
                slides.append(e["node"]["display_url"])
        else:
            # Single image
            candidates = media.get("image_versions2", {}).get("candidates", [])
            if candidates:
                slides.append(candidates[0]["url"])
            elif "display_url" in media:
                slides.append(media["display_url"])

        if not slides or len(slides) < img_index:
            return None, f"Web API: Could only find {len(slides)} slides"
            
        img_url = slides[img_index-1].replace('\\/', '/')
        img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
        if img_res.status_code == 200:
            output_dir = os.path.join(target_dir, shortcode)
            _ensure_dir(output_dir)
            path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
            with open(path, "wb") as f: f.write(img_res.content)
            return path, f"Slide {img_index} (Web API)"
            
    except Exception as e:
        return None, f"Web API Error: {e}"
    return None, None

def download_via_mobile_api(shortcode, target_dir, img_index=1):
    """Method 2: Instagram Mobile API (i.instagram.com)"""
    print(f"Attempting mobile API for {shortcode} (slide {img_index})...")
    try:
        media_id = _shortcode_to_mediaid(shortcode)
        api_url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
        headers = {
            "User-Agent": "Instagram 76.0.0.15.395 Android (24/7.0; 640dpi; 1440x2560; samsung; SM-G930F; herolte; samsungexynos8890; en_US; 138226743)",
            "X-IG-App-ID": "936619743392459"
        }
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code != 200: return None, f"Mobile API: HTTP {res.status_code}"
        
        items = res.json().get("items", [])
        if not items: return None, "Mobile API: No items"
        
        item = items[0]
        carousel = item.get("carousel_media", [])
        if carousel:
            if img_index > len(carousel): img_index = len(carousel)
            candidates = carousel[img_index-1].get("image_versions2", {}).get("candidates", [])
        else:
            candidates = item.get("image_versions2", {}).get("candidates", [])
        
        if not candidates: return None, "Mobile API: No image data"
        img_url = candidates[0].get("url")
        
        img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
        if img_res.status_code == 200:
            output_dir = os.path.join(target_dir, shortcode)
            _ensure_dir(output_dir)
            path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
            with open(path, "wb") as f: f.write(img_res.content)
            return path, f"Slide {img_index} (API)"
    except Exception as e: return None, f"Mobile API Error: {e}"
    return None, None

def download_via_embed_json(shortcode, target_dir, img_index=1):
    """Method 3: Multi-Pattern Data Discovery (Resilient Scraper)"""
    print(f"Attempting embed JSON discovery for {shortcode} (slide {img_index})...")
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        res = requests.get(url, headers=_HEADERS, timeout=15)
        if res.status_code != 200: 
            short_html = res.text[:500].replace('\n', ' ')
            return None, f"Embed Page: HTTP {res.status_code}. Response start: {short_html}"
        html = res.text
        
        # Multiple data discovery patterns
        data = None
        
        # Pattern 1: contextJSON (Standard Polaris Embed)
        m = re.search(r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if m:
            s = m.group(1).replace('\\"', '"').replace('\\\\', '\\').replace('\\/', '/')
            try: data = json.loads(s).get('gql_data', {}).get('shortcode_media')
            except: pass
            
        # Pattern 2: _sharedData (Old Web / Fallback)
        if not data:
            m = re.search(r'window\._sharedData\s*=\s*(.*?);</script>', html)
            if m:
                try: 
                    jd = json.loads(m.group(1))
                    data = jd.get('entry_data', {}).get('PostPage', [{}])[0].get('graphql', {}).get('shortcode_media')
                except: pass

        # Pattern 3: __additional_data (Modern Web Fallback)
        if not data:
            m = re.search(r'__additional_data\s*=\s*(.*?);</script>', html)
            if m:
                try: 
                    jd = json.loads(m.group(1))
                    if 'graphql' in jd: data = jd['graphql'].get('shortcode_media')
                    else: data = jd.get('shortcode_media')
                except: pass
        
        # Pattern 4 (Discovery Mode): Brute-force high-res JPG extraction
        if not data:
            print("Structural parsing failed. Entering Brute-Force Discovery...")
            soup = BeautifulSoup(html, 'html.parser')
            all_jpgs = []
            for s in soup.find_all('script'):
                if not s.string: continue
                urls = re.findall(r'https://[^"]+?\.jpg[^"]*', s.string)
                for u in urls:
                    u = u.replace('\\/', '/')
                    if ("/s" in u and "x" in u) or ("cdninstagram" in u):
                        if u not in all_jpgs: all_jpgs.append(u)
            
            # Sort by quality markers (prefer 1080px)
            all_jpgs.sort(key=lambda x: ("1080x1080" in x), reverse=True)
            
            if len(all_jpgs) >= img_index:
                img_url = all_jpgs[img_index-1]
                img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
                if img_res.status_code == 200:
                    output_dir = os.path.join(target_dir, shortcode)
                    _ensure_dir(output_dir)
                    path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
                    with open(path, "wb") as f: f.write(img_res.content)
                    return path, f"Slide {img_index} (Discovery Mode)"

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
                    return path, f"Slide {img_index}/{len(slides)} (JSON)"

        return None, "No slide data found (Structure changed or blocked)"
    except Exception as e: return None, f"Scraper: {e}"

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """Method 4: Headless Browser (Browser Orchestration)"""
    print(f"Attempting Browser for {shortcode} (slide {img_index})...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: return None, "Playwright not installed"
    
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception as e: return None, f"Browser Launch Error: {e}"
            
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            
            # Use extra headers
            page.set_extra_http_headers({
                "X-IG-App-ID": "936619743392459",
                "X-ASBD-ID": "129477"
            })
            
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for content to actually load if it's a slow wall
            time.sleep(3) 

            # Browser discovery using same patterns
            res = page.evaluate(r'''
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
            
            if res:
                edges = res.get('edge_sidecar_to_children', {}).get('edges', [])
                slides = [e['node']['display_url'] for e in edges] if edges else [res['display_url']]
                if len(slides) >= img_index:
                    img_url = slides[img_index-1].replace('\\/', '/')
                    img_res = requests.get(img_url, headers=_HEADERS, timeout=15)
                    if img_res.status_code == 200:
                        output_dir = os.path.join(target_dir, shortcode)
                        _ensure_dir(output_dir)
                        path = os.path.join(output_dir, f"{shortcode}_slide{img_index}.jpg")
                        with open(path, "wb") as f: f.write(img_res.content)
                        browser.close()
                        return path, f"Slide {img_index} (Browser)"
            
            browser.close()
            return None, "Browser extraction failed to find media"
    except Exception as e: return None, f"Browser Error: {e}"

def download_via_instaloader(shortcode, target_dir, img_index=1):
    """Method 5: Instaloader (Last Resort)"""
    print(f"Attempting Instaloader for {shortcode}...")
    try:
        import instaloader
        L = instaloader.Instaloader(download_pictures=True, download_videos=False, save_metadata=False, max_connection_attempts=1, request_timeout=5)
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
        else:
            L.download_post(post, target=shortcode)
            search_dir = os.path.join(target_dir, shortcode)
            if os.path.exists(search_dir):
                files = sorted([f for f in os.listdir(search_dir) if f.endswith('.jpg')])
                if files: return os.path.abspath(os.path.join(search_dir, files[0])), "Instaloader"
    except Exception as e: return None, f"Instaloader Error: {e}"
    return None, None

def download_instagram_image(url, target_dir="downloads", img_index=1):
    """Main Orchestrator"""
    m = re.search(r'instagram\.com/(?:[^/]+/)?(?:p|reel)/([^/?#]+)', url)
    if not m: return None, "Invalid URL"
    shortcode = m.group(1)
    
    # Refresh cleanup
    _clean_dir(os.path.join(target_dir, shortcode))
    
    methods = [
        (download_via_web_api, "Web API (v1.4)"),
        (download_via_mobile_api, "Mobile API"),
        (download_via_embed_json, "Embed Scraper"),
        (download_via_embed_browser, "Headless Browser"),
        (download_via_instaloader, "Instaloader Tool")
    ]
    
    errors = []
    for func, name in methods:
        path, status = func(shortcode, target_dir, img_index)
        if path: return os.path.abspath(path), status
        if status: errors.append(f"[{name}] {status}")
    
    error_summary = " | ".join(errors)
    return None, error_summary
