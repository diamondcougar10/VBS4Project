"""Standalone launcher for the Reality Mesh GUI.

Run this file directly to open the post‑processing interface:

```
python RealityMeshStandalone.py
```
"""

import os
import sys
import importlib
import logging
import traceback

def _resource_base() -> str:
    """Return the directory containing bundled resources."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

# Ensure this script can locate ``reality_mesh_gui`` when run from a frozen
# bundle or directly from source.
BASE_DIR = _resource_base()
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    filename='reality_mesh.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("RealityMeshStandalone starting")

print("Starting GUI...")

def main() -> None:
    logging.info("Importing reality_mesh_gui")
    try:
        gui = importlib.import_module("reality_mesh_gui")
        gui.main()
    except Exception:
        logging.exception("Failed to start reality_mesh_gui")
        with open("gui_error.log", "w") as f:
            f.write(traceback.format_exc())
        raise

if __name__ == "__main__":
    main()
