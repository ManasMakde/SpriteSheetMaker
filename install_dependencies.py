import sys
import subprocess
import traceback
import os


def has_dependencies():

    # Add current path to sys.path
    current_dir = os.path.dirname(__file__)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        
    
    # Check if contains
    is_valid = False
    try:
        # Add imports here
        import PIL

        is_valid = True
    except Exception:
        is_valid = False
    

    # Remove current path to sys.path
    if current_dir in sys.path:
        sys.path.remove(current_dir)


    return is_valid

def install_dependency(package_name):
    try:
        print(f"[SpriteSheetMaker] Installing {package_name}. This may take a few moments...")
        python_exe = sys.executable
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        args = [python_exe, "-m", "pip", "install", "--no-cache-dir", "--target", plugin_dir, package_name]
        subprocess.check_call(
            args,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
    except subprocess.CalledProcessError as e:
        print("[SpriteSheetMaker] pip install returned non-zero; traceback:\n", traceback.format_exc())
        raise e
    except Exception as e:
        print(f"[SpriteSheetMaker] Installation failed: {e} \n {traceback.format_exc()}")
        raise e
    
def install_all_dependencies(context):
    if has_dependencies():
        print("[SpriteSheetMaker] Dependencies already installed!")
        return

    # Install all one by one
    for dep in ["pillow"]:
        install_dependency(dep)
    
    # After installation, check again
    if has_dependencies():
        print("[SpriteSheetMaker] Dependencies installed successfully")
    else:
        print("[SpriteSheetMaker] Dependencies installed but failed to import. See console for details")
