"""Standalone launcher for the Reality Mesh GUI.

Run this file directly to open the post‑processing interface:

```
python RealityMeshStandalone.py
```
"""

import os
import sys
import importlib

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

def main() -> None:
    gui = importlib.import_module("reality_mesh_gui")
    gui.main()

if __name__ == "__main__":
    main()
