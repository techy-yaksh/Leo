"""
L.E.O. Assistant Entry Point Wrapper.
Preserves backward compatibility for Launch_LEO.vbs and legacy execution scripts
by routing directly to the modularized main application runner.
"""

import sys
import os

# Ensure current project directory is in python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main

if __name__ == '__main__':
    main()
