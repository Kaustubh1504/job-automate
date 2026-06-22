"""Importing this package auto-imports every parser module, running each one's
@register call. Drop a new parser module in this directory and it's picked up
automatically -- no edit here, no edit to the registry.
"""

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
