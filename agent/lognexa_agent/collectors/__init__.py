"""Collector registry: returns the collector classes for the current OS."""

from __future__ import annotations

import os


def collectors_for_platform() -> list:
    if os.name == "nt":
        from lognexa_agent.collectors.windows import WINDOWS_COLLECTORS

        return WINDOWS_COLLECTORS
    from lognexa_agent.collectors.linux import LINUX_COLLECTORS

    return LINUX_COLLECTORS
