"""Make the test-only helper module importable as `ghx_util`."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
