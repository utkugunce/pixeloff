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
    page_title = "Unknown"
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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )
            
            page = context.new_page()
            
            # 🕵️ Script Injection to hide "navigator.webdriver"
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                
                # 🖱️ HUMANIZATION: Wiggle Mouse to pass weak CF checks
                try:
                    page.mouse.move(100, 100)
                    time.sleep(0.2)
                    page.mouse.move(200, 200)
                    time.sleep(0.2)
                    page.evaluate("window.scrollTo(0, 500)")
                except: pass

                time.sleep(3) 

                # Handle Redirects/Navigations (Fix Execution Context Error)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except: pass
                
                # Capture Info
                page_title = page.title()
                
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

    return html_content, page_title, error_log

# --- RELAY METHODS ---

# --- RELAY METHODS ---

# --- RELAY METHODS ---

def download_via_sssinstagram(original_url, shortcode, target_dir, img_index=1):
    """Method 1: SSSInstagram (Form)"""
    from playwright.sync_api import sync_playwright
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
            page = browser.new_page()
            
            try:
                page.goto("https://sssinstagram.com/en", timeout=30000)
                page.wait_for_load_state("domcontentloaded")
                
                # Close cookies/popups if any (Press Escape)
                page.keyboard.press("Escape")
                
                page.fill('input#main_page_text', original_url)
                page.click('button#submit')
                
                # Wait for result
                try: page.wait_for_selector('.download-wrapper, .result-box', timeout=20000)
                except: return None, f"SSSInstagram: Timeout. Title: '{page.title()}'"
                
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                slides = []
                for a in soup.select('.download-wrapper a, a.download-button'):
                    href = a.get('href')
                    if href: slides.append(href)
                
                if slides and len(slides) >= img_index:
                    return _download_file(slides[img_index-1], target_dir, shortcode, img_index, "SSSInstagram")
                    
                return None, "SSSInstagram: No slides"
            finally:
                browser.close()
    except Exception as e: return None, f"SSSInstagram Error: {e}"

def download_via_fastdl(original_url, shortcode, target_dir, img_index=1):
    """Method 2: FastDL (Debug Mode)"""
    from playwright.sync_api import sync_playwright
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
            page = browser.new_page()
            
            try:
                page.goto("https://fastdl.app/en", timeout=30000)
                page.wait_for_load_state("networkidle")
                
                page.fill('input[type="text"]', original_url)
                page.keyboard.press("Enter")
                
                # Wait for ANY link to appear in the output area
                try: page.wait_for_selector('div.output-list, a[download]', timeout=20000)
                except: return None, f"FastDL: Timeout. Title: '{page.title()}'"
                
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Debugging Logic
                found_links = [a.get('href') for a in soup.select('a[href]')]
                
                slides = []
                for a in soup.select('a[href*="googlevideo"], a[href*="cdninstagram"], a[download], a.button--filled'):
                    href = a.get('href')
                    if href and "fastdl" not in href and "javascript" not in href:
                        slides.append(href)
                
                if slides and len(slides) >= img_index:
                    return _download_file(slides[img_index-1], target_dir, shortcode, img_index, "FastDL")
                
                # Return debug info
                debug_info = f"Found {len(found_links)} links, {len(slides)} matched. First 3 found: {found_links[:3]}"
                return None, f"FastDL: No content. {debug_info}"

            finally:
                browser.close()
    except Exception as e: return None, f"FastDL Error: {e}"

def download_via_indown(shortcode, target_dir, img_index, original_url):
    """Method 3: Indown (Relaxed)"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            try:
                page.goto("https://indown.io/", timeout=30000)
                # Close potential popup
                time.sleep(1)
                page.keyboard.press("Escape")
                
                page.fill('input#link', original_url)
                page.click('button[type="submit"]')
                
                try: page.wait_for_selector('#result', timeout=20000)
                except: return None, "Indown: Timeout"
                
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                slides = []
                # Relaxed: Any link inside #result
                for a in soup.select('div#result a[href]'):
                    href = a.get('href')
                    if href and "javascript" not in href and len(href) > 20:
                        slides.append(href)
                
                if slides and len(slides) >= img_index:
                    return _download_file(slides[img_index-1], target_dir, shortcode, img_index, "Indown")
                return None, f"Indown: No slides. Found {len(slides)} potential links."
            finally:
                browser.close()
    except Exception as e: return None, f"Indown Error: {e}"

def download_via_savefree(original_url, shortcode, target_dir, img_index=1):
    """Method 3: SaveFree (Backup Form)"""
    from playwright.sync_api import sync_playwright
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                page.goto("https://savefree.app/en", timeout=30000)
                time.sleep(2)
                
                page.fill('input#input-url', original_url)
                page.click('#btn-submit')
                
                try: page.wait_for_selector('.download-items', timeout=15000)
                except: 
                    # Try clicking again?
                    page.screenshot(path=os.path.join(target_dir, "debug_savefree_fail.png"))
                    return None, "SaveFree: Timeout"
                
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                slides = []
                items = soup.select('.download-item')
                for item in items:
                    a = item.select_one('a.download-btn')
                    if a: slides.append(a.get('href'))
                
                if slides and len(slides) >= img_index:
                    return _download_file(slides[img_index-1], target_dir, shortcode, img_index, "SaveFree")
                    
                return None, "SaveFree: No content found"
            finally:
                browser.close()
    except Exception as e:
        return None, f"SaveFree Error: {e}"

def download_via_imginn(shortcode, target_dir, img_index=1):
    """Method 4: Imginn (Direct)"""
    url = f"https://imginn.com/p/{shortcode}/"
    
    html, title, error = fetch_rendered_html(url, target_dir)
    if not html: return None, f"Imginn Browser Error: {error}"
    
    soup = BeautifulSoup(html, 'html.parser')
    slides = []
    
    downloads = soup.select('.downloads a.btn-primary')
    if downloads:
        slides = [a.get('href') for a in downloads if a.get('href')]
    
    if not slides:
        imgs = soup.select('img.img-fluid')
        slides = [img.get('src') for img in imgs if img.get('src')]

    if slides and len(slides) >= img_index:
        img_url = slides[img_index-1]
        if img_url.startswith("//"): img_url = "https:" + img_url
        return _download_file(img_url, target_dir, shortcode, img_index, "Imginn")
        
    return None, f"Imginn: Content not found. Title: '{title}'"

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
        (lambda: download_via_sssinstagram(url, shortcode, target_dir, img_index), "SSSInstagram (Form)"),
        (lambda: download_via_fastdl(url, shortcode, target_dir, img_index), "FastDL (Debug)"),
        (lambda: download_via_indown(shortcode, target_dir, img_index, url), "Indown (Relaxed)"),
    ]
    
    errors = []
    for func, name in methods:
        path, status = func()
        if path: return os.path.abspath(path), status, errors
        if status: errors.append(f"[{name}] {status}")
    
    return None, " | ".join(errors), errors
