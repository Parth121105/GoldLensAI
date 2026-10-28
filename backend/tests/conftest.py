"""Test-wide setup.

Apps built from the environment would save imports to backend/data/store. Tests keep
every app in memory unless they pass their own Settings(store_dir=...) pointing at a
temporary folder, so no test writes to the real store or sees another test's data.
Set at import time because some test modules build their app at module level.
"""

import os

os.environ["GOLDLENS_STORE_DIR"] = "off"
