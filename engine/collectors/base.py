"""Collector registry.

A collector is a callable(src) -> list[Listing] that does its own data
acquisition -- unlike a parser, there's no single URL or ETag; it may fan out
over many endpoints internally. Selected via the "collector" key on a SOURCES
entry. Mirrors the parser / notifier / fetcher registries.
"""

_COLLECTORS = {}


def register(name):
    def deco(fn):
        _COLLECTORS[name] = fn
        return fn
    return deco


def get_collector(name):
    try:
        return _COLLECTORS[name]
    except KeyError:
        raise KeyError(f"no collector registered as {name!r}; have {sorted(_COLLECTORS)}")
