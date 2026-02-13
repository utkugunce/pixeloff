import instaloader
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
            print(f"Embed page returned status {response.status_code}")
            return None, None
        
        html = response.text
        
        # Look for contextJSON in the HTML
        context_match = re.search(r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if not context_match:
            print("No contextJSON found in embed HTML.")
            return None, None
        
        # Unescape the JSON string
        json_str = context_match.group(1)
        json_str = json_str.replace('\\"', '"')
        json_str = json_str.replace('\\\\', '\\')
        json_str = json_str.replace('\\n', '\n')
        json_str = json_str.replace('\\t', '\t')
        json_str = json_str.replace('\\/', '/')
        
        data = json.loads(json_str)
        
        gql_data = data.get('gql_data')
        if not gql_data:
            print("gql_data is null — Instagram may be blocking this request.")
            return None, None
        
        media = gql_data.get('shortcode_media')
        if not media:
            print("shortcode_media not found in gql_data.")
            return None, None
        
        # Extract carousel slides
        slides = []
        if media.get('edge_sidecar_to_children'):
            edges = media['edge_sidecar_to_children'].get('edges', [])
            for edge in edges:
                node = edge.get('node', {})
                slides.append({
                    'url': node.get('display_url'),
                    'is_video': node.get('is_video', False)
                })
        else:
            # Single image
            slides.append({
                'url': media.get('display_url'),
                'is_video': media.get('is_video', False)
            })
        
        if not slides:
            print("No slides found in gql_data.")
            return None, None
        
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
            return None, None
        
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
            print(f"Image download failed (status {img_response.status_code})")
            return None, None
            
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return None, None
    except Exception as e:
        print(f"Embed JSON extraction failed: {e}")
        return None, None


def download_via_embed_browser(shortcode, target_dir, img_index=1):
    """
    Use Playwright headless browser to render the Instagram embed page
    and extract carousel images by parsing the embedded JSON data.
    This extracts ALL slide URLs from gql_data instead of clicking buttons.
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
            browser = p.chromium.launch(headless=True)
            print("Browser launched. Creating page...")
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            print(f"Navigating to {embed_url}...")
            page.goto(embed_url, wait_until="networkidle", timeout=30000)
            print("Page loaded.")
            
            # Strategy 1: Extract ALL carousel URLs from the embedded JSON data
            # The embed page contains a PolarisEmbedSimple init script with contextJSON
            # that has gql_data containing edge_sidecar_to_children (all slides)
            print("Extracting carousel data from embedded JSON...")
            carousel_urls = page.evaluate(r'''
                () => {
                    try {
                        const scripts = Array.from(document.querySelectorAll('script'));
                        for (const script of scripts) {
                            const text = script.textContent;
                            if (!text.includes('contextJSON')) continue;
                            
                            // Extract the contextJSON value
                            const match = text.match(/"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"/);
                            if (!match) continue;
                            
                            // Unescape the JSON string
                            let jsonStr = match[1]
                                .replace(/\\"/g, '"')
                                .replace(/\\\\/g, '\\')
                                .replace(/\\n/g, '\n')
                                .replace(/\\t/g, '\t');
                            
                            const data = JSON.parse(jsonStr);
                            
                            if (data && data.gql_data && data.gql_data.shortcode_media) {
                                const media = data.gql_data.shortcode_media;
                                
                                // Check if it's a carousel (sidecar)
                                if (media.edge_sidecar_to_children && media.edge_sidecar_to_children.edges) {
                                    return media.edge_sidecar_to_children.edges.map(edge => ({
                                        url: edge.node.display_url,
                                        is_video: edge.node.is_video || false
                                    }));
                                }
                                
                                // Single image post
                                return [{
                                    url: media.display_url,
                                    is_video: media.is_video || false
                                }];
                            }
                        }
                    } catch (e) {
                        console.error('JSON extraction error:', e);
                    }
                    return null;
                }
            ''')
            
            if carousel_urls and len(carousel_urls) > 0:
                print(f"Found {len(carousel_urls)} slides via JSON extraction!")
                
                # Pick the requested slide
                if img_index > len(carousel_urls):
                    print(f"Requested slide {img_index} > total {len(carousel_urls)}, using last.")
                    img_index = len(carousel_urls)
                
                target_slide = carousel_urls[img_index - 1]
                
                if target_slide.get('is_video'):
                    print(f"Slide {img_index} is a video, skipping.")
                    # Try next non-video slide or return error
                    return None, f"Slide {img_index} is a video, not an image."
                
                image_url = target_slide['url']
                print(f"Downloading slide {img_index}: {image_url[:80]}...")
                
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
                else:
                    print(f"Download failed (status {response.status_code})")
            else:
                print("JSON extraction returned no data. Trying DOM fallback...")
            
            # Strategy 2 (Fallback): Click Next buttons to navigate carousel
            print(f"Attempting button-click navigation to slide {img_index}...")
            for i in range(img_index - 1):
                next_btn = page.query_selector('button._afxw') or \
                           page.query_selector('button[aria-label="Next"]') or \
                           page.query_selector('button[aria-label="İleri"]') or \
                           page.query_selector('[role="button"][aria-label="Next"]') or \
                           page.query_selector('[role="button"][aria-label="İleri"]')
                if next_btn:
                    print(f"Clicking next (step {i+1})...")
                    try:
                        next_btn.click(force=True)
                        page.wait_for_timeout(1500)
                    except Exception as e:
                        print(f"Click error: {e}")
                        break
                else:
                    print(f"Next button not found at step {i+1}.")
                    break
            
            page.wait_for_timeout(1000)
            
            # Strategy 3 (Final fallback): Get visible large image from DOM
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
                print("No images found in embed page.")
                return None, "No images found on embed page"
            
            # Prefer EmbeddedMediaImage, then largest
            target_img = None
            for img in images:
                if 'EmbeddedMediaImage' in img.get('className', ''):
                    target_img = img
                    break
            if not target_img:
                target_img = max(images, key=lambda x: x.get('width', 0))
            
            image_url = target_img['src']
            print(f"Found image via DOM: {image_url[:80]}...")
            
            response = requests.get(image_url, headers=_HEADERS, timeout=15)
            if response.status_code == 200:
                output_dir = os.path.join(target_dir, shortcode)
                _ensure_dir(output_dir)
                filename = f"{shortcode}_slide{img_index}.jpg"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(response.content)
                return filepath, "Caption unavailable (DOM fallback)"
            
            return None, "Failed to download image"
                
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

    # Method 3: Embed JSON (lightweight, no browser needed — parses embed HTML for carousel data)
    print(f"Method 3: Embed JSON extraction...")
    path, caption = download_via_embed_json(shortcode, target_dir, img_index)
    if path:
        return os.path.abspath(path), caption

    # Method 4: Playwright Embed Browser (heavy, needs browser installed)
    print(f"Method 4: Embed Browser (Playwright)...")
    path, caption = download_via_embed_browser(shortcode, target_dir, img_index)
    if path:
        return os.path.abspath(path), caption

    # Method 5: Instaloader (supports carousel, but often blocked on cloud)
    print("Method 5: Instaloader (Last Resort)...")
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
