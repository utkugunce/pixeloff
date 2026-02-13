# import instaloader (Moved to lazy import)
import os
import shutil
import re
import json
import requests
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

# Constants
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def _ensure_dir(path):
    """Safely create directory."""
    os.makedirs(path, exist_ok=True)

def _clean_dir(path):
    """Clean up directory before new download to avoid stale files."""
    if os.path.exists(path):
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error cleaning {file_path}: {e}")

def _shortcode_to_mediaid(shortcode):
    """Convert Instagram shortcode to numeric media ID."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id


def download_via_mobile_api(shortcode, target_dir, img_index=1):
    """
    Use Instagram's private mobile API to get post/carousel data.
    This uses a different channel than the web embed page.
    """
    print(f"Attempting mobile API for {shortcode} (slide {img_index})...")
    
    try:
        media_id = _shortcode_to_mediaid(shortcode)
        api_url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
        
        mobile_headers = {
            "User-Agent": "Instagram 76.0.0.15.395 Android (24/7.0; 640dpi; 1440x2560; samsung; SM-G930F; herolte; samsungexynos8890; en_US; 138226743)",
            "X-IG-App-ID": "936619743392459",
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "X-IG-Capabilities": "3brTvw==",
            "X-IG-Connection-Type": "WIFI",
        }
        
        response = requests.get(api_url, headers=mobile_headers, timeout=15)
        print(f"Mobile API status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Mobile API returned {response.status_code}")
            return None, f"Mobile API: HTTP {response.status_code}"
        
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            print("Mobile API returned no items")
            return None, "Mobile API: no items returned"
        
        item = items[0]
        carousel_media = item.get("carousel_media", [])
        
        if carousel_media:
            # Carousel post
            total = len(carousel_media)
            print(f"Found carousel with {total} slides via mobile API!")
            
            if img_index > total:
                print(f"Requested slide {img_index} > total {total}, using last.")
                img_index = total
            
            slide = carousel_media[img_index - 1]
            candidates = slide.get("image_versions2", {}).get("candidates", [])
        else:
            # Single image
            print("Single image post via mobile API")
            candidates = item.get("image_versions2", {}).get("candidates", [])
        
        if not candidates:
            print("No image candidates found")
            return None, "Mobile API: no image data"
        
        # Get highest resolution
        best = max(candidates, key=lambda c: c.get("width", 0) * c.get("height", 0))
        image_url = best.get("url")
        
        if not image_url:
            return None, "Mobile API: no image URL"
        
        print(f"Downloading via mobile API: {image_url[:80]}...")
        
        img_response = requests.get(image_url, headers=_HEADERS, timeout=15)
        if img_response.status_code == 200:
            output_dir = os.path.join(target_dir, shortcode)
            _ensure_dir(output_dir)
            filename = f"{shortcode}_slide{img_index}.jpg"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(img_response.content)
            return filepath, f"Slide {img_index} (via mobile API)"
        else:
            print(f"Image download failed: {img_response.status_code}")
            return None, None
            
    except Exception as e:
        print(f"Mobile API failed: {e}")
        return None, f"Mobile API error: {e}"


def download_via_embed_json(shortcode, target_dir, img_index=1):
    """
    Lightweight method: fetch embed page HTML with requests and parse
    the contextJSON/gql_data for ALL carousel slide URLs.
    No browser/Playwright needed.
    """
    print(f"Attempting embed JSON extraction for {shortcode} (slide {img_index})...")
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    
    try:
        response = requests.get(embed_url, headers=_HEADERS, timeout=15)
        if response.status_code != 200:
            return None, f"Embed page returned status {response.status_code}"
        
        html = response.text
        
        # Strategy 1: Direct Regex on HTML
        json_str = None
        context_match = re.search(r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if context_match:
            json_str = context_match.group(1)
        else:
            # Strategy 2: BeautifulSoup to find script tags containing contextJSON
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup.find_all('script'):
                if script.string and '"contextJSON"' in script.string:
                    inner_match = re.search(r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"', script.string)
                    if inner_match:
                        json_str = inner_match.group(1)
                        break
        
        if not json_str:
            return None, "No contextJSON found in embed HTML"
        
        # Unescape the JSON string
        json_str = json_str.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\t', '\t').replace('\\/', '/')
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, f"JSON parse error: {e}"

        gql_data = data.get('gql_data')
        if not gql_data:
            return None, "gql_data is null in embed JSON"
        
        media = gql_data.get('shortcode_media')
        if not media:
            return None, "shortcode_media not found in gql_data"
        
        # Extract carousel slides
        slides = []
        if media.get('edge_sidecar_to_children') and media['edge_sidecar_to_children'].get('edges'):
            edges = media['edge_sidecar_to_children'].get('edges', [])
            for edge in edges:
                node = edge.get('node', {})
                slides.append({
                    'url': node.get('display_url'),
                    'is_video': node.get('is_video', False)
                })
        else:
            # Single image post in gql_data
            slides.append({
                'url': media.get('display_url'),
                'is_video': media.get('is_video', False)
            })
        
        if not slides or not slides[0].get('url'):
            return None, "No valid image slides found in gql_data"
        
        print(f"Found {len(slides)} slides via embed JSON!")
        
        # Pick the requested slide
        if img_index > len(slides):
            print(f"Requested slide {img_index} > total {len(slides)}, using last.")
            img_index = len(slides)
        
        target_slide = slides[img_index - 1]
        
        if target_slide.get('is_video'):
            return None, f"Slide {img_index} is a video, not an image."
        
        image_url = target_slide.get('url')
        if not image_url:
            return None, "Slide URL is empty"
            
        # Fix escaped slashes just in case
        image_url = image_url.replace(r'\/', '/')
        
        print(f"Downloading slide {img_index}/{len(slides)}: {image_url[:80]}...")
        
        img_response = requests.get(image_url, headers=_HEADERS, timeout=15)
        if img_response.status_code == 200 and 'image' in img_response.headers.get('Content-Type', ''):
            output_dir = os.path.join(target_dir, shortcode)
            _ensure_dir(output_dir)
            filename = f"{shortcode}_slide{img_index}.jpg"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(img_response.content)
            return filepath, f"Slide {img_index}/{len(slides)}"
        else:
            return None, f"Image download status {img_response.status_code}"
            
    except Exception as e:
        return None, f"Embed JSON extraction error: {e}"


def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """
    Use Playwright headless browser to render the Instagram embed page.
    """
    print(f"Attempting download via Embed Browser for {shortcode} (slide {img_index})...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Playwright library not found"
    
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    
    try:
        with sync_playwright() as p:
            print("Launching browser...")
            # We use try/except for launch to catch missing executable error specifically
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as launch_err:
                print(f"Browser launch failed: {launch_err}")
                return None, f"Browser launch failed: {launch_err}"

            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(embed_url, wait_until="networkidle", timeout=30000)
            
            # Extract carousel URLs from page context
            carousel_urls = page.evaluate(r'''
                () => {
                    try {
                        const scripts = Array.from(document.querySelectorAll('script'));
                        for (const script of scripts) {
                            const text = script.textContent;
                            if (!text.includes('contextJSON')) continue;
                            const match = text.match(/"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"/);
                            if (!match) continue;
                            let jsonStr = match[1].replace(/\\"/g, '"').replace(/\\\\/g, '\\').replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\\//g, '/');
                            const data = JSON.parse(jsonStr);
                            if (data && data.gql_data && data.gql_data.shortcode_media) {
                                const media = data.gql_data.shortcode_media;
                                if (media.edge_sidecar_to_children && media.edge_sidecar_to_children.edges) {
                                    return media.edge_sidecar_to_children.edges.map(edge => ({
                                        url: edge.node.display_url,
                                        is_video: edge.node.is_video || false
                                    }));
                                }
                                return [{url: media.display_url, is_video: media.is_video || false}];
                            }
                        }
                    } catch (e) {}
                    return null;
                }
            ''')
            
            if carousel_urls and len(carousel_urls) > 0:
                if img_index > len(carousel_urls): img_index = len(carousel_urls)
                target_slide = carousel_urls[img_index - 1]
                if target_slide.get('is_video'):
                    browser.close()
                    return None, f"Slide {img_index} is a video"
                
                image_url = target_slide['url'].replace(r'\/', '/')
                response = requests.get(image_url, headers=_HEADERS, timeout=15)
                if response.status_code == 200:
                    output_dir = os.path.join(target_dir, shortcode)
                    _ensure_dir(output_dir)
                    filename = f"{shortcode}_slide{img_index}.jpg"
                    filepath = os.path.join(output_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    browser.close()
                    return filepath, f"Slide {img_index}/{len(carousel_urls)}"
            
            browser.close()
            return None, "Could not extract image from browser page"
                
    except Exception as e:
        return None, f"Browser Error: {e}"

def download_via_media_redirect(shortcode, target_dir):
    """Fallback: /media/?size=l"""
    url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
    try:
        response = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        if "image" not in response.headers.get("Content-Type", ""): return None, None
        output_dir = os.path.join(target_dir, shortcode)
        _ensure_dir(output_dir)
        filepath = os.path.join(output_dir, f"{shortcode}_media.jpg")
        with open(filepath, "wb") as f: f.write(response.content)
        return filepath, "Media redirect"
    except: return None, None

def download_via_embed(shortcode, target_dir):
    """Fallback: Embed page soup scraping"""
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        response = requests.get(embed_url, headers=_HEADERS, timeout=10)
        if response.status_code != 200: return None, None
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find('img', class_='EmbeddedMediaImage')
        if not img_tag: return None, None
        image_url = img_tag.get('src')
        if not image_url: return None, None
        img_data = requests.get(image_url, headers=_HEADERS, timeout=10).content
        output_dir = os.path.join(target_dir, shortcode)
        _ensure_dir(output_dir)
        filepath = os.path.join(output_dir, f"{shortcode}_embed.jpg")
        with open(filepath, "wb") as f: f.write(img_data)
        return filepath, "Embed scraper"
    except: return None, None

def _parse_img_index(post_url):
    try:
        parsed = urlparse(post_url)
        params = parse_qs(parsed.query)
        if 'img_index' in params:
            idx = int(params['img_index'][0])
            if idx >= 1: return idx
    except: pass
    return 1

def download_instagram_image(post_url, target_dir="downloads", img_index=None):
    """Main entry point for downloading Instagram images."""
    match = re.search(r'instagram\.com/(?:[^/]+/)?(?:p|reel)/([^/?#]+)', post_url)
    if not match: raise ValueError("Invalid Instagram URL.")
    
    shortcode = match.group(1)
    if img_index is None: img_index = _parse_img_index(post_url)
    
    output_dir = os.path.join(target_dir, shortcode)
    _clean_dir(output_dir)

    # Methods for Slide 1 only
    if img_index == 1:
        path, cap = download_via_media_redirect(shortcode, target_dir)
        if path: return os.path.abspath(path), cap
        path, cap = download_via_embed(shortcode, target_dir)
        if path: return os.path.abspath(path), cap

    errors = []
    # Method 3: Mobile API
    path, cap = download_via_mobile_api(shortcode, target_dir, img_index)
    if path: return os.path.abspath(path), cap
    if cap: errors.append(cap)

    # Method 4: Embed JSON
    path, cap = download_via_embed_json(shortcode, target_dir, img_index)
    if path: return os.path.abspath(path), cap
    if cap: errors.append(cap)

    # Method 5: Playwright
    path, cap = download_via_embed_browser(shortcode, target_dir, img_index)
    if path: return os.path.abspath(path), cap
    if cap: errors.append(cap)

    # Method 6: Instaloader
    print("Method 6: Instaloader...")
    try:
        import instaloader
        L = instaloader.Instaloader(download_pictures=True, download_videos=False, save_metadata=False, max_connection_attempts=1, request_timeout=5)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        if post.typename == 'GraphSidecar' and img_index >= 1:
            nodes = list(post.get_sidecar_nodes())
            if img_index > len(nodes): img_index = len(nodes)
            image_url = nodes[img_index - 1].display_url
            response = requests.get(image_url, headers=_HEADERS, timeout=15)
            if response.status_code == 200:
                _ensure_dir(output_dir)
                filename = f"{shortcode}_slide{img_index}.jpg"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f: f.write(response.content)
                return os.path.abspath(filepath), post.caption
        else:
            L.download_post(post, target=shortcode)
            search_dir = os.path.join(target_dir, shortcode)
            if os.path.exists(search_dir):
                files = sorted([f for f in os.listdir(search_dir) if f.endswith('.jpg')])
                if files: return os.path.abspath(os.path.join(search_dir, files[0])), post.caption
    except Exception as e:
        errors.append(f"Instaloader: {e}")
        
    error_detail = " | ".join(errors) if errors else "All methods failed"
    return None, f"Slide {img_index} failed. Details: {error_detail}"
