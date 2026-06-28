import os
import shutil
import tempfile
import subprocess


# To Set
EXCLUDE_PATHS = [
    "__pycache__",
    ".git",
    ".github",
    "images",
    ".gitignore",
    "build.py",
    "README.md"
]
BUILD_ZIP_PREFIX = "sprite_sheet_maker"


# Properties
BLENDER_CMD = "blender"
BLENDER_ARGS = ["--command", "extension", "build", "--split-platforms"]


# Methods
def get_source_dir():
    source_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(source_dir):
        print(f"WARNING: source dir not found {source_dir}")
        return None
    return source_dir

def copy_to_temp(source_dir):
    temp_base = tempfile.gettempdir()
    folder_name = os.path.basename(source_dir)
    dest_dir = os.path.join(temp_base, folder_name)

    if os.path.exists(dest_dir):
        print(f"removing existing temp dir {dest_dir}")
        shutil.rmtree(dest_dir)

    print(f"copying {source_dir} to {dest_dir}")
    shutil.copytree(source_dir, dest_dir)

    return dest_dir

def delete_excluded(dest_dir, exclude_paths):
    for rel_path in exclude_paths:
        full_path = os.path.join(dest_dir, rel_path)

        if not os.path.exists(full_path):
            print(f"excluded path not found skipping {rel_path}")
            continue

        if os.path.isdir(full_path):
            print(f"deleting dir {full_path}")
            shutil.rmtree(full_path)
        else:
            print(f"deleting file {full_path}")
            os.remove(full_path)

def run_blender_build(work_dir):
    cmd = [BLENDER_CMD] + BLENDER_ARGS
    print(f"running {' '.join(cmd)} in {work_dir}")

    result = subprocess.run(cmd, cwd=work_dir)

    if result.returncode != 0:
        print(f"WARNING: blender exited with code {result.returncode}")
        return False

    return True

def move_zips(work_dir, dest_dir):
    zips = [f for f in os.listdir(work_dir) if f.endswith(".zip") and f.startswith(BUILD_ZIP_PREFIX)]

    if not zips:
        print("WARNING: no zip files found after build")
        return

    for zip_name in zips:
        src = os.path.join(work_dir, zip_name)
        dst = os.path.join(dest_dir, zip_name)
        print(f"moving {zip_name} to {dest_dir}")
        shutil.move(src, dst)

def main():

    # Get the directory this file is in (a.k.a source directory)
    source_dir = get_source_dir()
    if not source_dir:
        print("WARNING: aborting no valid source dir")
        return


    # Copy to temp dir
    dest_dir = copy_to_temp(source_dir)
    if not dest_dir:
        print("WARNING: aborting copy failed")
        return


    # Delete unnecessary files & folders
    delete_excluded(dest_dir, EXCLUDE_PATHS)


    # Build .zip files
    success = run_blender_build(dest_dir)
    if not success:
        print("WARNING: build failed")
        return


    # Move .zip files back to source directory
    move_zips(dest_dir, source_dir)


    # Cleanup temp dir
    print(f"cleaning up temp dir {dest_dir}")
    shutil.rmtree(dest_dir)
    print("build complete")


# Main
if __name__ == "__main__":
    main()