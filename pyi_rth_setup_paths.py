"""Runtime Hook para PyInstaller"""

import os
import sys

bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

if bundle_dir not in sys.path:
    sys.path.insert(0, bundle_dir)