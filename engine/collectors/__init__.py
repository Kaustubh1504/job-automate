"""Importing this package auto-imports every collector module, running each
one's @register call. Drop a new collector module in this directory and it's
picked up automatically -- no edit here, no edit to the registry. base.py carries
no @register and is simply imported.
"""

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
