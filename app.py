import streamlit as st
import os
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

image_path = None

# Input Section
st.write("### 1️⃣ Instagram URL")
url = st.text_input("Paste Instagram Post URL:", placeholder="https://www.instagram.com/p/...")

# Carousel slide selector
slide_num = st.number_input(
    "📸 Carousel slide number (1 = first photo)",
    min_value=1, max_value=20, value=1, step=1,
    help="If the post is a carousel (multiple photos), choose which slide to download."
)

# Model Selection
mode = st.radio(
    "⚙️ Processing Mode",
    ["High Quality (Default)", "Human Focus"],
    help="High Quality: Best for edges/hair (IS-Net).\nHuman Focus: Best for isolating people from complex backgrounds (u2net_human_seg)."
)

model_name = "isnet-general-use" if mode == "High Quality (Default)" else "u2net_human_seg"

if st.button("Download & Process", type="primary"):
    if not url:
        st.error("Please enter a valid URL.")
    else:
        # If slide > 1, try to install Playwright browsers lazily
        # (Only if mobile/JSON methods fail, though they are prioritized now)
        if slide_num > 1:
            try:
                # We do a quick check to see if we might need browser
                # But actually, successful implementations (JSON/Mobile) don't need it.
                # We'll just let the downloader handle it.
                pass
            except:
                pass

        with st.status("Downloading from Instagram...", expanded=True) as status:
            st.write("📥 Connecting to Instagram...")
            try:
                image_path, caption = download_instagram_image(url, img_index=slide_num)
                if not image_path:
                    error_msg = caption if caption else "Unknown error"
                    status.update(label="Download failed!", state="error", expanded=False)
                    st.error(f"Download failed: {error_msg}")
                    if slide_num > 1:
                        st.info("💡 **Tip**: Carousel downloads can be tricky. Try another slide or post.")
                else:
                    status.update(label="Download complete!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Error", state="error")
                st.error(f"Error: {e}")

# Processing Section
if image_path:
    st.divider()
    st.write("### 2️⃣ Result")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Original")
        st.image(image_path, width="stretch")
        
    with col2:
        st.subheader("No Background")
        with st.spinner(f"Removing background... ({mode})"):
            processed_path, error = remove_background(image_path, model_name=model_name)
            
        if processed_path:
            st.image(processed_path, caption=f"Background Removed ({mode})", width="stretch")
            
            with open(processed_path, "rb") as file:
                st.download_button(
                    label="⬇️ Download Processed Image",
                    data=file,
                    file_name="pixeloff_result.png",
                    mime="image/png",
                    type="primary"
                )
        else:
            st.error(f"Background removal failed: {error}")
