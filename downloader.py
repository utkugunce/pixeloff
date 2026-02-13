import instaloader
import os
import shutil
import re
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

def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """
    Use Playwright headless browser to render the Instagram embed page
    and extract carousel images. Works on cloud servers where Instaloader
    gets blocked.
    """
    print(f"Attempting download via Embed Browser for {shortcode} (slide {img_index})...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Skipping browser method.")
        return None, "Playwright library not found"
    
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    
    try:
        with sync_playwright() as p:
            print("Launching browser...")
            browser = p.chromium.launch(headless=True) # Ensure headless=True for cloud
            print("Browser launched. Creating page...")
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            print(f"Navigating to {embed_url}...")
            page.goto(embed_url, wait_until="networkidle", timeout=20000) # Increased timeout
            print("Page loaded. Waiting 2s...")
            
            # Click "Next" button (img_index - 1) times to reach the desired slide
            for i in range(img_index - 1):
                # Try different selectors for the Next button
                # ._afxw is the class for the Next button in embed view (verified by agent)
                next_btn = page.query_selector('button._afxw') or \
                           page.query_selector('button[aria-label="Next"]') or \
                           page.query_selector('button[aria-label="İleri"]') or \
                           page.query_selector('div[role="button"][aria-label="Next"]') or \
                           page.query_selector('div[role="button"][aria-label="İleri"]')
                
                if next_btn:
                    print(f"Clicking next button (step {i+1})...")
                    try:
                        next_btn.click(force=True) # Force click in case of overlays
                        page.wait_for_timeout(1000)  # Wait for slide transition
                        # Debug: take screenshot
                        # page.screenshot(path=os.path.join(target_dir, f"debug_slide_{i+1}.png"))
                    except Exception as e:
                         print(f"Error clicking next button: {e}")
                else:
                    print(f"Next button not found at step {i+1}. Max slides may be reached.")
                    # Take a screenshot to see why
                    debug_path = os.path.join(target_dir, f"debug_failed_nav_{shortcode}.png")
                    try:
                        page.screenshot(path=debug_path)
                        print(f"Saved debug screenshot to {debug_path}")
                    except:
                        pass
                    break
            
            # Wait a bit more for high-res image to load
            page.wait_for_timeout(1000)

            # Collect all large images from the DOM
            
            # Collect all large images from the DOM
            images = page.evaluate('''
                () => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    return imgs
                        .filter(img => img.naturalWidth >= 500 || img.src.includes('s1080x1080'))
                        .map(img => ({
                            src: img.src,
                            className: img.className,
                            width: img.naturalWidth
                        }));
                }
            ''')
            
            browser.close()
            
            if not images:
                print("No large images found in embed page.")
                return None, None
            
            # Pick the best image: prefer EmbeddedMediaImage class, otherwise largest
            target_img = None
            for img in images:
                if 'EmbeddedMediaImage' in img.get('className', ''):
                    target_img = img
                    break
            if not target_img:
                # Get the largest image
                target_img = max(images, key=lambda x: x.get('width', 0))
            
            image_url = target_img['src']
            print(f"Found image URL via embed browser: {image_url[:80]}...")
            
            # Download the image
            response = requests.get(image_url, headers=_HEADERS, timeout=15)
            
            if response.status_code == 200:
                output_dir = os.path.join(target_dir, shortcode)
                _ensure_dir(output_dir)
                
                filename = f"{shortcode}_slide{img_index}.jpg"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(response.content)
                
                return filepath, "Caption unavailable in embed browser mode"
            else:
                print(f"Failed to download image (status: {response.status_code})")
                return None, None
                
    except Exception as e:
        print(f"Embed browser download failed: {e}")
        return None, f"Browser Error: {e}"

def download_via_media_redirect(shortcode, target_dir):
    """
    Fallback Method 2: Use the /media/?size=l endpoint which redirects to the image.
    Note: This only works for the first image of a carousel post.
    """
    print(f"Attempting download via Media Redirect for {shortcode}...")
    url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
    
    try:
        # We need to act like a browser to avoid 403 on the redirect target
        response = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        
        # Check if we actually got an image
        if "image" not in response.headers.get("Content-Type", ""):
            print("Media redirect did not return an image.")
            return None, None
            
        # Save it
        output_dir = os.path.join(target_dir, shortcode)
        _ensure_dir(output_dir)
            
        filename = f"{shortcode}_media.jpg"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(response.content)
            
        return filepath, "Caption unavailable in media mode"
        
    except Exception as e:
        print(f"Media redirect failed: {e}")
        return None, None

def download_via_embed(shortcode, target_dir):
    """
    Fallback Method 3: Try to download image via Instagram Embed page.
    Note: This only works for the first image of a carousel post.
    """
    print(f"Attempting download via Embed for {shortcode}...")
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(embed_url, headers=_HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"Embed page returned status {response.status_code}")
            return None, None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find the image in the embed page
        # Usually it's an img with class 'EmbeddedMediaImage'
        img_tag = soup.find('img', class_='EmbeddedMediaImage')
        
        if not img_tag:
            # Fallback: look for any image that looks like the main one
            # searching for the one with the largest resolution usually works, but let's just grab the first valid jpg
            print("EmbeddedMediaImage class not found, searching specific pattern...")
            return None, None
            
        image_url = img_tag.get('src')
        if not image_url:
            return None, None
            
        # Download the image
        print(f"Found image URL via embed: {image_url}")
        img_data = requests.get(image_url, headers=_HEADERS, timeout=10).content
        
        # Save it
        output_dir = os.path.join(target_dir, shortcode)
        _ensure_dir(output_dir)
            
        filename = f"{shortcode}_embed.jpg"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(img_data)
            
        return filepath, "Caption unavailable in embed mode"
        
    except Exception as e:
        print(f"Embed download failed: {e}")
        return None, None

def _parse_img_index(post_url):
    """
    Parse the img_index query parameter from the URL.
    Returns 1-based index (default 1 if not present).
    """
    try:
        parsed = urlparse(post_url)
        params = parse_qs(parsed.query)
        if 'img_index' in params:
            idx = int(params['img_index'][0])
            if idx >= 1:
                return idx
    except (ValueError, IndexError):
        pass
    return 1

def download_instagram_image(post_url, target_dir="downloads", img_index=None):
    """
    Downloads the image from a given Instagram post URL.
    Supports carousel posts via img_index parameter or ?img_index=N in URL.
    Returns the path to the downloaded image file.
    """
    # Extract shortcode from URL
    # Support URLs with or without username: instagram.com/p/CODE or instagram.com/username/p/CODE
    match = re.search(r'instagram\.com/(?:[^/]+/)?p/([^/?#]+)', post_url)
    if not match:
        # Try checking if it's a reel: instagram.com/reel/CODE or instagram.com/username/reel/CODE
        match = re.search(r'instagram\.com/(?:[^/]+/)?reel/([^/?#]+)', post_url)
    
    if not match:
        raise ValueError("Invalid Instagram URL. Could not find post shortcode.")
    
    shortcode = match.group(1)
    # Use provided img_index, or parse from URL, default to 1
    if img_index is None:
        img_index = _parse_img_index(post_url)
    print(f"Processing shortcode: {shortcode}, img_index: {img_index}")
    
    # Clean up target directory before downloading to avoid stale files
    # (e.g. if previous download was slide 1 and now we want slide 2)
    output_dir = os.path.join(target_dir, shortcode)
    _clean_dir(output_dir)

    # Methods 1 & 2 (Media Redirect / Embed scraper) can only fetch the first image.
    # If user wants a specific slide (img_index > 1), skip directly to browser/Instaloader.
    if img_index == 1:
        # Method 1: Media Redirect (Fastest, usually works for public posts)
        print("Method 1: Media Redirect...")
        path, caption = download_via_media_redirect(shortcode, target_dir)
        if path:
            return os.path.abspath(path), caption

        # Method 2: Embed Scraper (Good backup, no JS needed)
        print("Method 2: Embed Scraper...")
        path, caption = download_via_embed(shortcode, target_dir)
        if path:
            return os.path.abspath(path), caption
    else:
        print(f"Carousel image #{img_index} requested — skipping Media Redirect & static Embed.")

    # Method 3: Playwright Embed Browser (supports carousel slide selection, works on cloud)
    print(f"Method 3: Embed Browser (Playwright)...")
    path, caption = download_via_embed_browser(shortcode, target_dir, img_index)
    if path:
        return os.path.abspath(path), caption

    # Method 4: Instaloader (supports carousel, but often blocked on cloud)
    print("Method 4: Instaloader (Last Resort)...")
    try:
        # Configure to fail faster
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=False, 
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            max_connection_attempts=1, # Fail fast
            request_timeout=5,
        )
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Handle carousel (sidecar) posts with specific img_index
        if post.typename == 'GraphSidecar' and img_index >= 1:
            sidecar_nodes = list(post.get_sidecar_nodes())
            total_slides = len(sidecar_nodes)
            
            if img_index > total_slides:
                print(f"Warning: img_index={img_index} exceeds total slides ({total_slides}). Using last slide.")
                img_index = total_slides
            
            target_node = sidecar_nodes[img_index - 1]  # Convert 1-based to 0-based
            image_url = target_node.display_url
            
            print(f"Downloading carousel slide {img_index}/{total_slides}...")
            
            # Download the specific slide
            output_dir = os.path.join(target_dir, shortcode)
            _ensure_dir(output_dir)
            
            response = requests.get(image_url, headers=_HEADERS, timeout=15)
            
            if response.status_code == 200 and "image" in response.headers.get("Content-Type", ""):
                filename = f"{shortcode}_slide{img_index}.jpg"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(response.content)
                return os.path.abspath(filepath), post.caption or "Caption downloaded"
            else:
                print(f"Failed to download slide image (status: {response.status_code})")
        else:
            # Single image post or img_index=1: download normally
            L.download_post(post, target=shortcode)
            
            # Find local file
            search_dir = shortcode
            if not os.path.exists(search_dir):
                 search_dir = os.path.join(target_dir, shortcode)

            if os.path.exists(search_dir):
                files = [f for f in os.listdir(search_dir) if f.endswith('.jpg')]
                if files:
                    files.sort()
                    return os.path.abspath(os.path.join(search_dir, files[0])), "Caption downloaded"
                
    except Exception as e:
        print(f"Instaloader failed: {e}")
        
    if img_index > 1:
        return None, f"Carousel slide {img_index} could not be downloaded. Browser or Instaloader needed but both failed."
    return None, "All download methods failed for this post."
