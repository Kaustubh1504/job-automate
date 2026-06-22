"""Notification providers: deliver newly-live Listings to some channel.

A provider is a class registered under a name and constructed from its own
config (e.g. a Discord webhook URL). It exposes a single method, send(listings).
A new provider is added by dropping a module in notifiers/ and decorating its
class with @register("name") -- the same registry pattern parsers use. Nothing
here changes.
"""

from typing import Protocol


class Notifier(Protocol):
    def send(self, listings) -> None:
        """Deliver the given list[Listing]. A no-op on an empty list."""
        ...


_PROVIDERS = {}


def register(name):
    def deco(cls):
        _PROVIDERS[name] = cls
        return cls
    return deco


def get_notifier(name):
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise KeyError(f"no notifier registered as {name!r}; have {sorted(_PROVIDERS)}")
