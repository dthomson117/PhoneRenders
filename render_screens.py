import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from render_lib.main import run

run(script_dir=SCRIPT_DIR)
