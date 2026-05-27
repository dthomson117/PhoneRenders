import os

import bpy


def scan_screenshots(screens_dir_path, supported_exts):
    """Return a sorted list of image filepaths in the directory."""
    abs_dir = bpy.path.abspath(screens_dir_path)
    if not os.path.isdir(abs_dir):
        raise RuntimeError(f"Screenshots directory not found: {abs_dir}")

    files = []
    for fn in sorted(os.listdir(abs_dir)):
        if fn.startswith('.'):
            continue
        if fn.lower().endswith(supported_exts):
            files.append(os.path.join(abs_dir, fn))
    return files
