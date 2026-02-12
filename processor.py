from PIL import Image
import os

def remove_background(input_path, output_path=None):
    """
    Removes the background from the image at input_path.
    Saves the result to output_path.
    """
    # Lazy import to prevent app startup lag/timeout
    try:
        from rembg import remove
    except ImportError:
        print("Error: rembg not installed.")
        return None
    if output_path is None:
        file_name = os.path.basename(input_path)
        name, ext = os.path.splitext(file_name)
        new_name = f"{name}_nobg.png"
        directory = os.path.dirname(input_path)
        output_path = os.path.join(directory, new_name)

    print(f"Processing image: {input_path}")
    print("Removing background... This may take a moment for the first run.")

    try:
        with open(input_path, 'rb') as i:
            with open(output_path, 'wb') as o:
                input_image = i.read()
                output_image = remove(input_image)
                o.write(output_image)
        
        print(f"Background removed. Saved to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error removing background: {e}")
        return None
