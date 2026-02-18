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
def fetch_rendered_html(url, timeout=30000):
    """Uses Playwright to fetch fully rendered HTML (JS executed)."""
    from playwright.sync_api import sync_playwright
    
    html_content = ""
    error_log = ""
    
    try:
        with sync_playwright() as p:
            # Launch options for standard environment
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                # Extra wait for dynamic carousels
                time.sleep(3) 
                
                # Scroll down to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                time.sleep(1)
                
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
