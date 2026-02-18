import os
import shutil
import re
import json
import time
import random
from bs4 import BeautifulSoup

# Helper: Clean URLs to remove query params/resizing
def _clean_instagram_url(url):
    return url.split("?")[0]

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def _clean_dir(path):
    if os.path.exists(path):
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path): os.unlink(file_path)
            except: pass

def _shortcode_to_mediaid(shortcode):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id

# --- CORE BROWSER ENGINE ---
def fetch_rendered_html(url, target_dir, timeout=30000):
    """Uses Playwright to fetch fully rendered HTML (JS executed)."""
    from playwright.sync_api import sync_playwright
    
    html_content = ""
    error_log = ""
    
    try:
        with sync_playwright() as p:
            # Launch options for stealth (v5.1)
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox', 
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled', # 🕵️ Hide automation flag
                    '--disable-infobars',
                    '--window-size=1920,1080'
                ]
            )
            
            # Context with real-user fingerprint
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            
            page = context.new_page()
            
            # 🕵️ Script Injection to hide "navigator.webdriver"
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                # Extra wait for dynamic carousels
                time.sleep(4) 
                
                # Scroll down to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                time.sleep(1)
                
                # 📸 DEBUG: Take Screenshot
                debug_path = os.path.join(target_dir, "debug_view.png")
                page.screenshot(path=debug_path)
                
                html_content = page.content()
            except Exception as e:
                error_log = str(e)
            finally:
                browser.close()
                
    except Exception as e:
        error_log = f"Playwright Init Error: {e}"

    return html_content, error_log

# --- RELAY METHODS ---

def download_via_picuki(shortcode, target_dir, img_index=1):
    """Method 1: Picuki (High Reliability)"""
    media_id = _shortcode_to_mediaid(shortcode)
    url = f"https://www.picuki.com/media/{media_id}"
    
    html, error = fetch_rendered_html(url, target_dir)
    if not html: return None, f"Picuki Browser Error: {error}"
    
    soup = BeautifulSoup(html, 'html.parser')
    slides = []

    # 1. Carousel (Owl Carousel)
    # Picuki uses OwlCarousel. We look for images inside owl-item not referenced as cloned
    carousel_items = soup.select('.owl-item:not(.cloned) img')
    if carousel_items:
        # Owl carousel sometimes duplicates items, we de-dupe by URL
        slides = list(dict.fromkeys([img.get('src') for img in carousel_items]))
    
    # 2. Single Video (Poster)
    if not slides:
        video = soup.select_one('video')
        if video and video.get('poster'): slides = [video.get('poster')]

    # 3. Single Photo (Try multiple selectors)
    if not slides:
        for selector in ['.single-photo img', '.post-image', '.photo-wrapper img']:
            img = soup.select_one(selector)
            if img: 
                slides = [img.get('src')]
                break

    # 4. Content fallback (Broadest)
    if not slides:
        # check for just ANY image in the content area that looks large
        imgs = soup.select('.content-box img')
        if imgs: slides = [imgs[0].get('src')]

    if slides and len(slides) >= img_index:
        img_url = slides[img_index-1]
        return _download_file(img_url, target_dir, shortcode, img_index, "Picuki")

    return None, "Picuki: Content not found in rendered page"

def download_via_imginn(shortcode, target_dir, img_index=1):
    """Method 2: Imginn/Imgann"""
    url = f"https://imginn.com/p/{shortcode}/"
    
    html, error = fetch_rendered_html(url, target_dir)
    if not html: return None, f"Imginn Browser Error: {error}"
    
    soup = BeautifulSoup(html, 'html.parser')
    slides = []
    
    # Imginn typically lists download buttons for all items
    downloads = soup.select('.downloads a.btn-primary')
    if downloads:
        slides = [a.get('href') for a in downloads if a.get('href')]
    
    # Fallback to images (Broad)
    if not slides:
        imgs = soup.select('img.img-fluid')
        slides = [img.get('src') for img in imgs if img.get('src')]

    if slides and len(slides) >= img_index:
        img_url = slides[img_index-1]
        if img_url.startswith("//"): img_url = "https:" + img_url
        return _download_file(img_url, target_dir, shortcode, img_index, "Imginn")
        
    return None, "Imginn: Content not found"

def _download_file(url, target_dir, shortcode, img_index, source_name):
    import requests
    try:
        # Clean URL
        clean_url = _clean_instagram_url(url)
        clean_url = clean_url.replace("https://", "").replace("//", "")
        clean_url = f"https://{clean_url}"

        # Standard headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        path = os.path.join(os.path.join(target_dir, shortcode), f"{shortcode}_slide{img_index}.jpg")
        _ensure_dir(os.path.dirname(path))

        res = requests.get(clean_url, headers=headers, timeout=20)
        if res.status_code == 200:
            with open(path, "wb") as f: f.write(res.content)
            return path, f"Relay ({source_name})"
        else:
            return None, f"HTTP {res.status_code} on Clean download"
    except Exception as e:
        return None, f"Download Error: {e}"


def download_instagram_image(url, target_dir="downloads", img_index=1):
    m = re.search(r'instagram\.com/(?:[^/]+/)?(?:p|reel)/([^/?#]+)', url)
    if not m: return None, "Invalid URL"
    shortcode = m.group(1)
    _ensure_dir(target_dir)
    _clean_dir(os.path.join(target_dir, shortcode))
    
    methods = [
        (lambda: download_via_picuki(shortcode, target_dir, img_index), "Picuki Browser"),
        (lambda: download_via_imginn(shortcode, target_dir, img_index), "Imginn Browser"),
    ]
    
    errors = []
    for func, name in methods:
        path, status = func()
        if path: return os.path.abspath(path), status, errors
        if status: errors.append(f"[{name}] {status}")
    
    return None, " | ".join(errors), errors
