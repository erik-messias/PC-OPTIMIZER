import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="nexus_test_")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
