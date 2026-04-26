import os
import sys

# Must be set before PySide6 is imported so Qt uses the offscreen platform
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make src/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
