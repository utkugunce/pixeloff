import argparse
import sys
import os
from downloader import download_instagram_image
from processor import remove_background

def main():
    parser = argparse.ArgumentParser(description="Download Instagram photo and remove background.")
    parser.add_argument("url", help="Instagram Post URL")
    args = parser.parse_args()
    
    url = args.url
    print(f"Starting tool for URL: {url}")
    
    # Step 1: Download
    print("\n--- Step 1: Downloading from Instagram ---")
    image_path, caption = download_instagram_image(url)
    
    if not image_path:
        print("Failed to download image. Exiting.")
        sys.exit(1)
        
    print(f"Image downloaded to: {image_path}")
    print("\n--- POST CAPTION ---")
    try:
        print(caption)
    except UnicodeEncodeError:
        print(caption.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))
    print("--------------------")
    
    # Step 2: Remove Background
    print("\n--- Step 2: Removing Background ---")
    final_path = remove_background(image_path)
    
    if final_path:
        print("\nSUCCESS!")
        print(f"Your processed image is ready at:\n{final_path}")
    else:
        print("Failed to remove background.")
        sys.exit(1)

if __name__ == "__main__":
    main()
