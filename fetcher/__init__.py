"""Importing this package auto-imports every backend module, running each one's
@register call. Drop a new backend module in this directory (e.g. a headless
browser) and it's picked up automatically -- no edit here, no edit to the
registry. config.py and base.py carry no @register and are simply imported.
"""

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
