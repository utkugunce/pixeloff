import streamlit as st
import os
import shutil
from downloader import download_instagram_image
from processor import remove_background

# Configure the page
st.set_page_config(
    page_title="PixelOff - Instagram Background Remover",
    page_icon="✨",
    layout="centered"
)

st.title("✨ PixelOff")
st.markdown("Instagram fotoğraflarını indir, arkaplanını **PixelOff** ile saniyeler içinde temizle!")

# Input Section
url = st.text_input("Paste Instagram Post URL here:", placeholder="https://www.instagram.com/p/...")

if st.button("Process Image", type="primary"):
    if not url:
        st.error("Please enter a valid URL.")
    else:
        with st.status("Processing...", expanded=True) as status:
            # Step 1: Download
            st.write("📥 Downloading image from Instagram...")
            try:
                # Create a temporary directory or just use 'downloads'
                # The downloader uses 'downloads/{shortcode}' by default
                image_path, caption = download_instagram_image(url)
                
                if not image_path:
                    status.update(label="Download failed!", state="error", expanded=False)
                    st.error("Failed to download image. Please check the URL and try again.")
                    st.stop()
                
                st.write("✅ Download complete!")
                
                # Show Original Image
                st.subheader("Original Image")
                st.image(image_path, caption="Original Image", use_column_width=True)
                
                # Step 2: Remove Background
                st.write("✨ Removing background (AI)...")
                processed_path = remove_background(image_path)
                
                if not processed_path:
                    status.update(label="Processing failed!", state="error", expanded=False)
                    st.error("Failed to remove background.")
                    st.stop()
                    
                status.update(label="Complete!", state="complete", expanded=False)
                
                # Show Processed Image
                st.subheader("Processed Image (No Background)")
                st.image(processed_path, caption="Background Removed", use_column_width=True)
                
                # Download Button
                with open(processed_path, "rb") as file:
                    btn = st.download_button(
                        label="⬇️ Download Processed Image",
                        data=file,
                        file_name=os.path.basename(processed_path),
                        mime="image/png"
                    )
                    
            except Exception as e:
                status.update(label="An error occurred", state="error")
                st.error(f"An unexpected error occurred: {e}")
