import instaloader
import os
import re

def download_instagram_image(post_url, target_dir="downloads"):
    """
    Downloads the image from a given Instagram post URL.
    Returns the path to the downloaded image file.
    """
    # Create an Instaloader instance
    L = instaloader.Instaloader(
        download_pictures=True,
        download_videos=False, 
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False
    )

    # Extract shortcode from URL
    # URL format: https://www.instagram.com/p/SHORTCODE/
    match = re.search(r'instagram\.com/p/([^/]+)', post_url)
    if not match:
        raise ValueError("Invalid Instagram URL. Could not find post shortcode.")
    
    shortcode = match.group(1)
    
    print(f"Downloading post {shortcode}...")
    
    # Check if img_index query param exists
    img_index = None
    query_match = re.search(r'[?&]img_index=(\d+)', post_url)
    if query_match:
        img_index = query_match.group(1)
        print(f"Detected img_index={img_index} in URL.")
    
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Target directory based on shortcode to keep it clean
        download_path = os.path.join(target_dir, shortcode)
        
        # Download the post
        L.download_post(post, target=shortcode)
        
        # Find the image file
        output_dir = shortcode
        files = os.listdir(output_dir)
        
        # Filter for JPG files
        all_jpgs = [f for f in files if f.endswith('.jpg')]
        
        if not all_jpgs:
            raise FileNotFoundError("No image found in the downloaded post.")
            
        selected_file = None
        
        # Strategy:
        # 1. If img_index is provided, try to find matching file:
        #    - For single image: no suffix usually.
        #    - For carousel: _1, _2, etc.
        #    Instaloader suffixes are 1-based index.
        #    So img_index=1 -> _1.jpg, img_index=2 -> _2.jpg
        
        if img_index:
            # Look for file ending with _{img_index}.jpg
            expected_suffix = f"_{img_index}.jpg"
            # Also handle case where img_index=1 might be the ONLY image (no suffix)
            # But normally instaloader adds suffix only if multiple? No, for carousel it adds _1.
            
            candidates = [f for f in all_jpgs if f.endswith(expected_suffix)]
            if candidates:
                selected_file = candidates[0]
            else:
                print(f"Warning: requested img_index={img_index} not found in files: {all_jpgs}. Falling back to first image.")
        
        if not selected_file:
            # Default to the first one (usually _1.jpg or no suffix)
            # Sort to ensure deterministic order (alphabetical usually works for dates + suffix)
            all_jpgs.sort()
            selected_file = all_jpgs[0]
            
        final_image_path = os.path.abspath(os.path.join(output_dir, selected_file))
        
        caption_text = ""
        if txt_files:
            try:
                with open(os.path.join(output_dir, txt_files[0]), 'r', encoding='utf-8') as f:
                    caption_text = f.read()
            except Exception as e:
                print(f"Could not read caption: {e}")

        final_image_path = os.path.abspath(os.path.join(output_dir, selected_file))
        return final_image_path, caption_text


    except Exception as e:
        print(f"Error downloading post: {e}")
        return None, None
