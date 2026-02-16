import streamlit as st
import os
import sys
import subprocess

# Configure the page
st.set_page_config(
    page_title="PixelOff - Instagram Background Remover",
    page_icon="✨",
    layout="centered"
)

# Robust Dependency Check
def check_dependencies():
    results = []
    # Check rembg/onnx
    try:
        import rembg
        results.append("✅ rembg/onnx: OK")
    except ImportError:
        results.append("❌ rembg/onnx: Missing")
    
    # Check playwright
    try:
        from playwright.sync_api import sync_playwright
        results.append("✅ Playwright: Installed")
    except ImportError:
        results.append("❌ Playwright: Missing")
        
    # Check Chromium path (Streamlit Cloud specific)
    try:
        import subprocess
        import sys
        cmd = [sys.executable, "-m", "playwright", "install", "--dry-run"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if "chromium" in res.stdout.lower():
            results.append("✅ Browser Path: Confirmed")
        else:
            results.append("❓ Browser Path: Not verified")
    except:
        pass
        
    return results

# Sidebar Title
st.sidebar.title("🛠️ Troubleshooting")
st.sidebar.info("**Version:** v2.3 \"HD Restorasyon\"")
model_info_placeholder = st.sidebar.empty()

# Chromium Check (v1.9)
def is_chromium_installed():
    try:
        import subprocess
        import sys
        cmd = [sys.executable, "-m", "playwright", "install", "--dry-run"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return "chromium" in res.stdout.lower()
    except: return False

if not is_chromium_installed():
    st.sidebar.error("⚠️ Chromium Browser Missing")
    if st.sidebar.button("🔧 Fix Browser (Install Chromium)"):
        with st.spinner("Installing... (2-4 mins)"):
            try:
                import sys
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
                st.sidebar.success("Installed! Refresh (F5) and retry.")
            except Exception as e: st.sidebar.error(f"Failed: {e}")

# ... (Existing Code)


# 📂 Diagnostic Download (Always Visible in v1.8)
diag_log = os.path.join("downloads", "last_response.log")
if os.path.exists(diag_log) and os.path.getsize(diag_log) > 0:
    with open(diag_log, "rb") as f:
        st.sidebar.download_button(
            "📂 Download Diagnostic Log",
            data=f,
            file_name="pixeloff_debug_log.txt",
            help="If it fails, download this and send it to support.",
            use_container_width=True
        )

# System Check
if st.sidebar.checkbox("🔍 System Check"):
    for res in check_dependencies():
        st.sidebar.write(res)

if st.sidebar.button("♻️ Clear Model Cache"):
    try:
        import shutil
        cache_path = os.path.expanduser("~/.u2net")
        if os.path.exists(cache_path):
            shutil.rmtree(cache_path, ignore_errors=False)
            st.sidebar.success("Cache cleared!")
        else:
            st.sidebar.info("Cache already empty.")
    except Exception as e:
        st.sidebar.error(f"Could not clear cache: {e}")

if st.sidebar.button("🌐 Install Playwright Browsers"):
    with st.spinner("Installing browsers (this may take 2-4 minutes)..."):
        try:
            import subprocess
            import sys
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                st.sidebar.success("Browsers installed successfully!")
            else:
                st.sidebar.error("Installation failed.")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

st.sidebar.divider()

if st.sidebar.checkbox("🐞 Enable Debug Logs"):
    st.session_state['debug_mode'] = True
else:
    st.session_state['debug_mode'] = False
    
if st.sidebar.checkbox("📸 Visual Debug (Screenshot)"):
    st.session_state['visual_debug'] = True
else:
    st.session_state['visual_debug'] = False

st.sidebar.info("If you see 'Connection Reset' or a black screen, please **refresh the page** (F5).")

# Main Page
st.title("✨ PixelOff")
st.subheader("Instagram Background Remover")

# App description
st.markdown("""
Past an Instagram link below, and it will automatically remove the background from the image. 
Supports Single posts, Reels, and Carousels.
""")

# Input Section
st.write("### 1️⃣ Instagram URL")
url = st.text_input("Paste Instagram Post URL:", placeholder="https://www.instagram.com/p/...")

# Smart Carousel Detection
slide_num = 1
is_carousel = False

if url:
    if "img_index=" in url:
        is_carousel = True
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'img_index' in params:
                slide_num = int(params['img_index'][0])
        except:
            pass

if is_carousel:
    slide_num = st.number_input(
        "📸 Carousel slide number",
        min_value=1, max_value=100, value=slide_num, step=1,
        help="Post found to be a carousel. You can change which slide to download."
    )
else:
    if st.toggle("Manual slide selection", value=False):
        slide_num = st.number_input("📸 Carousel slide number", min_value=1, max_value=100, value=1)

# Model Selection
mode = st.radio(
    "⚙️ Processing Mode",
    ["High Quality (Default)", "Human Focus"],
    help="High Quality: Best for edges/hair.\nHuman Focus: Best for people."
)

model_name = "isnet-general-use" if mode == "High Quality (Default)" else "u2net_human_seg"
model_info_placeholder.caption(f"🤖 **Active Model:** `{model_name}`")

if st.button("Download & Process", type="primary"):
    if not url:
        st.error("Please enter a valid URL.")
    else:
        with st.status("Processing v2.2 (Single Post Optimization)...", expanded=True) as status:
            st.write("🎯 **Targeting Single Post Metadata...**")
            try:
                from downloader import download_instagram_image
                image_path, caption = download_instagram_image(url, img_index=slide_num)
                if not image_path:
                    error_msg = caption if caption else "Unknown error"
                    st.session_state['last_error'] = error_msg
                    status.update(label="Extraction failed. IP block is severe.", state="error", expanded=False)
                    st.error(f"Download failed: {error_msg}")
                    
                    if st.session_state.get('debug_mode'):
                        st.expander("Show detailed error logs").write(error_msg)
                else:
                    status.update(label="Found image!", state="complete", expanded=False)
                    st.session_state['last_image'] = image_path
                    st.session_state['last_error'] = ""
            except Exception as e:
                status.update(label="Critical System Error", state="error")
                st.error(f"Error: {e}")

# Universal Debug Section
if url:
    st.divider()
    if st.session_state.get('visual_debug'):
        debug_shot = os.path.join("downloads", "debug_last_browser.png")
        if os.path.exists(debug_shot):
            with st.expander("📸 Visual Debug (Browser Screenshot)", expanded=True):
                st.image(debug_shot, caption="What the browser saw during extraction")
        elif not st.session_state.get('last_image'):
            st.info("Waiting for browser to capture screenshot...")

    # 429 Guidance with Countdown (v2.1)
    last_err = st.session_state.get('last_error', '')
    
    # Sidebar IP Status Indicator
    ip_status = "🟢 Healthy" if "429" not in last_err else "🔴 Flagged (429)"
    st.sidebar.metric("Streamlit IP Status", ip_status, help="Green: Normal IPs. Red: Instagram is rate-limiting this server. Use Crawler Mode or wait.")

    if not st.session_state.get('last_image') and "429" in last_err:
        import time
        if 'rate_limit_start' not in st.session_state:
            st.session_state['rate_limit_start'] = time.time()
        
        elapsed = time.time() - st.session_state['rate_limit_start']
        remaining = int(60 - elapsed)
        
        if remaining > 0:
            st.warning(f"⚠️ **Instagram Rate Limit (429)**. Server block detected. Please wait **{remaining}s** before refreshing (F5).")
            # Pro Tip for 2.1
            st.info("💡 **v2.1 Crawler Mode** is now active. If this fails, the IP block is deep. Wait 60s and try a different link.")
            time.sleep(1)
            st.rerun()
        else:
            st.success("✅ **Cooldown complete!** You can now refresh (F5) and try again.")
            if st.button("🔄 Try Again Now"):
                st.session_state.pop('rate_limit_start', None)
                st.rerun()
    elif not st.session_state.get('last_image') and last_err:
        st.info("💡 **Tip**: If it keeps failing, try a different slide number or wait a few minutes. Check the 'Troubleshooting' sidebar for more tools.")

# Result Section
image_path = st.session_state.get('last_image')
if image_path and os.path.exists(image_path):
    st.divider()
    st.write("### 2️⃣ Result")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Original")
        st.image(image_path, use_container_width=True)
    with col2:
        st.subheader("No Background")
        with st.spinner(f"Removing background..."):
            from processor import remove_background
            processed_path, error = remove_background(image_path, model_name=model_name)
        if processed_path:
            st.image(processed_path, caption="Result", use_container_width=True)
            with open(processed_path, "rb") as file:
                st.download_button(
                    label="⬇️ Download Processed Image",
                    data=file,
                    file_name="pixeloff_result.png",
                    mime="image/png",
                    type="primary"
                )
        else:
            st.error(f"Failed: {error}")
