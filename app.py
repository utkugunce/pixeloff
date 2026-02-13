import streamlit as st
import os

# Configure the page
st.set_page_config(
    page_title="PixelOff - Instagram Background Remover",
    page_icon="✨",
    layout="centered"
)

# Robust Dependency Check
def check_dependencies():
    results = {}
    try:
        import PIL
        results["Pillow"] = "✅"
    except: results["Pillow"] = "❌"
    
    try:
        import rembg
        results["rembg"] = "✅"
    except Exception as e: 
        results["rembg"] = f"❌ ({str(e)})"
    
    try:
        import onnxruntime
        results["onnx"] = "✅"
    except Exception as e: 
        results["onnx"] = f"❌ ({str(e)})"
        
    return results

st.title("✨ PixelOff")
st.markdown("Instagram fotoğraflarını indir, arkaplanını **PixelOff** ile saniyeler içinde temizle!")

# Sidebar Troubleshooting
with st.sidebar:
    st.header("🛠️ Troubleshooting")
    
    # System Check
    if st.checkbox("🔍 System Check"):
        deps = check_dependencies()
        for k, v in deps.items():
            st.write(f"**{k}**: {v}")
        st.write(f"**CWD**: `{os.getcwd()}`")
            
    if st.button("♻️ Clear Model Cache", help="Clears loaded models from memory."):
        st.cache_resource.clear()
        st.success("Cache cleared!")

    if st.button("🌐 Install Playwright Browsers", help="Use if you see 'Executable doesn't exist' error. This downloads Chromium."):
        with st.spinner("Installing browsers (this may take 2-3 minutes)..."):
            try:
                import subprocess
                # Install only chromium to save space and time
                result = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True)
                if result.returncode == 0:
                    st.success("Browsers installed successfully!")
                else:
                    st.error(f"Installation failed: {result.stderr}")
            except Exception as e:
                st.error(f"Error: {e}")
    
    st.info("If you see 'Connection Reset' or a black screen, please **refresh the page** (F5).")

# Main Imports (wrapped to catch startup errors)
try:
    from downloader import download_instagram_image
    from processor import remove_background
except Exception as e:
    st.error(f"⚠️ Critical Startup Error: {e}")
    st.stop()

image_path = None

# Input Section
st.write("### 1️⃣ Instagram URL")
url = st.text_input("Paste Instagram Post URL:", placeholder="https://www.instagram.com/p/...")

# Carousel slide selector
slide_num = st.number_input(
    "📸 Carousel slide number (1 = first photo)",
    min_value=1, max_value=50, value=1, step=1,
    help="If the post is a carousel, choose which slide to download (e.g. 6)."
)

# Model Selection
mode = st.radio(
    "⚙️ Processing Mode",
    ["High Quality (Default)", "Human Focus"],
    help="High Quality: Best for edges/hair.\nHuman Focus: Best for isolating people from backgrounds."
)

model_name = "isnet-general-use" if mode == "High Quality (Default)" else "u2net_human_seg"

if st.button("Download & Process", type="primary"):
    if not url:
        st.error("Please enter a valid URL.")
    else:
        with st.status("Downloading from Instagram...", expanded=True) as status:
            st.write("📥 Connecting to Instagram...")
            try:
                image_path, caption = download_instagram_image(url, img_index=slide_num)
                if not image_path:
                    error_msg = caption if caption else "Unknown error"
                    status.update(label="Download failed!", state="error", expanded=False)
                    st.error(f"Download failed: {error_msg}")
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
            st.image(processed_path, caption=f"Result ({mode})", width="stretch")
            
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
