from PIL import Image
import os

def remove_background(input_path, output_path=None):
    """
    Removes the background from the image at input_path.
    Saves the result to output_path.
    """
    # Lazy import to prevent app startup lag/timeout
    try:
        from rembg import remove, new_session
    except ImportError as e:
        return None, f"Library Error: {e}"

    if output_path is None:
        file_name = os.path.basename(input_path)
        name, ext = os.path.splitext(file_name)
        new_name = f"{name}_nobg.png"
        directory = os.path.dirname(input_path)
        output_path = os.path.join(directory, new_name)

    print(f"Processing image: {input_path}")
    print("Removing background... Using u2netp model.")

    try:
        with open(input_path, 'rb') as i:
            input_image = i.read()
            
        # Use cached session to prevent reloading model
        session = _get_rembg_session("u2netp")
        output_image = remove(input_image, session=session)
        
        with open(output_path, 'wb') as o:
            o.write(output_image)
        
        # Verify output
        if os.path.getsize(output_path) == 0:
            return None, "Error: Generated file is empty."
            
        print(f"Background removed. Saved to: {output_path}")
        return output_path, None
        
    except Exception as e:
        print(f"Error removing background: {e}")
        return None, str(e)

import streamlit as st

@st.cache_resource(show_spinner=False)
def _get_rembg_session(model_name):
    # Lazy import inside cached function
    from rembg import new_session
    return new_session(model_name)
