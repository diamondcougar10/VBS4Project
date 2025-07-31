"""Standalone launcher for the Reality Mesh GUI.

Run this file directly to open the post‑processing interface:

```
python RealityMeshStandalone.py
```
"""

import os
import sys

# Ensure this script can locate the bundled GUI module regardless of where it's launched from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from reality_mesh_gui import main

if __name__ == "__main__":
    main()
