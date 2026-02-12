import instaloader
import os
import re
import requests
from bs4 import BeautifulSoup

def download_via_media_redirect(shortcode, target_dir):
    """
    Fallback Method 2: Use the /media/?size=l endpoint which redirects to the image.
    """
    print(f"Attempting download via Media Redirect for {shortcode}...")
    url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
    
    try:
        # We need to act like a browser to avoid 403 on the redirect target
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        
        # Check if we actually got an image
        if "image" not in response.headers.get("Content-Type", ""):
            print("Media redirect did not return an image.")
            return None, None
            
        # Save it
        output_dir = os.path.join(target_dir, shortcode)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
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
    """
    print(f"Attempting download via Embed for {shortcode}...")
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(embed_url, headers=headers, timeout=10)
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
        img_data = requests.get(image_url, headers=headers, timeout=10).content
        
        # Save it
        output_dir = os.path.join(target_dir, shortcode)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        filename = f"{shortcode}_embed.jpg"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(img_data)
            
        return filepath, "Caption unavailable in embed mode"
        
    except Exception as e:
        print(f"Embed download failed: {e}")
        return None, None

def download_instagram_image(post_url, target_dir="downloads"):
    """
    Downloads the image from a given Instagram post URL.
    Returns the path to the downloaded image file.
    """
    # Extract shortcode from URL
    match = re.search(r'instagram\.com/p/([^/]+)', post_url)
    if not match:
        # Try checking if it's a reel or something else, but strictly we need shortcode
        match = re.search(r'instagram\.com/reel/([^/]+)', post_url)
    
    if not match:
        raise ValueError("Invalid Instagram URL. Could not find post shortcode.")
    
    shortcode = match.group(1)
    print(f"Processing shortcode: {shortcode}")

    # Method 1: Try Instaloader first
    try:
        print("Method 1: Instaloader")
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=False, 
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        target_path = os.path.join(target_dir, shortcode)
        L.download_post(post, target=shortcode)
        
        # Find local file
        files = os.listdir(target_path) if os.path.exists(target_path) else os.listdir(shortcode)
        # Handle the case where instaloader downloads to CWD or target_dir depending on config
        # Instaloader behavior: target=shortcode creates a folder named shortcode.
        
        search_dir = shortcode # Because L.download_post(target=shortcode) downloads into a folder named shortcode
        if not os.path.exists(search_dir):
             search_dir = os.path.join(target_dir, shortcode)

        if os.path.exists(search_dir):
            files = [f for f in os.listdir(search_dir) if f.endswith('.jpg')]
            if files:
                files.sort()
                return os.path.abspath(os.path.join(search_dir, files[0])), "Caption downloaded"
                
    except Exception as e:
        print(f"Instaloader failed: {e}")
    
    # Method 2: /media/ Redirect (Very reliable for public posts)
    print("Switching to Method 2: Media Redirect...")
    path, caption = download_via_media_redirect(shortcode, target_dir)
    if path:
        return os.path.abspath(path), caption

    # Method 3: Embed Scraper fallback
    print("Switching to Method 3: Embed Scraper...")
    path, caption = download_via_embed(shortcode, target_dir)
    if path:
        return os.path.abspath(path), caption
        
    return None, None
