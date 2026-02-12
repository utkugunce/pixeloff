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
st.write("### 1️⃣ Choose your image source")
tab1, tab2 = st.tabs(["🔗 Instagram URL", "📁 Upload Image"])

image_path = None

with tab1:
    url = st.text_input("Paste Instagram Post URL:", placeholder="https://www.instagram.com/p/...")
    if st.button("Download & Process", type="primary"):
        if not url:
            st.error("Please enter a valid URL.")
        else:
            with st.status("Downloading from Instagram...", expanded=True) as status:
                st.write("📥 Connecting to Instagram...")
                try:
                    image_path, caption = download_instagram_image(url)
                    if not image_path:
                        status.update(label="Download failed!", state="error", expanded=False)
                        st.error("Instagram blocked the download (common in cloud servers). Please try uploading the image directly in the 'Upload Image' tab.")
                    else:
                        status.update(label="Download complete!", state="complete", expanded=False)
                except Exception as e:
                    status.update(label="Error", state="error")
                    st.error(f"Error: {e}")

with tab2:
    uploaded_file = st.file_uploader("Upload an image (JPG/PNG)", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        # Save uploaded file to specific path
        if not os.path.exists("uploads"):
            os.makedirs("uploads")
        image_path = os.path.join("uploads", uploaded_file.name)
        with open(image_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Image uploaded: {uploaded_file.name}")

# Processing Section
if image_path:
    st.divider()
    st.write("### 2️⃣ Result")
    
    col1, col2 = st.columns(2)
    
        with col1:
        st.subheader("Original")
        st.image(image_path, use_container_width=True)
        
    with col2:
        st.subheader("No Background")
        with st.spinner("Removing background... (using lightweight model)"):
            processed_path, error = remove_background(image_path)
            
        if processed_path:
            st.image(processed_path, caption="Background Removed", use_container_width=True)
            
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
