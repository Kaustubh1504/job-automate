"""Parser factory.

Maps a parser name to the callable that turns an HTTP response into a
list[Listing]. Parser modules register themselves with @register, so a new
format is added by dropping a module in parsers/ and decorating its parse
function. Nothing here changes.
"""

_PARSERS = {}


def register(name):
    def deco(fn):
        _PARSERS[name] = fn
        return fn
    return deco


def get_parser(name):
    try:
        return _PARSERS[name]
    except KeyError:
        raise KeyError(f"no parser registered as {name!r}; have {sorted(_PARSERS)}")
