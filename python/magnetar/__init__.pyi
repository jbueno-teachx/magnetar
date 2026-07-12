# SPDX-License-Identifier: CC0-1.0
"""Type stubs for magnetar."""

# Explicit re-exports (name as name) so type checkers and Ruff F401 agree.
from magnetar.units import (
    Coulomb as Coulomb,
    Gram as Gram,
    Meter as Meter,
    Second as Second,
    Tesla as Tesla,
    Vec3 as Vec3,
    Volt as Volt,
    coulomb as coulomb,
    gram as gram,
    meter as meter,
    meters as meters,
    second as second,
    tesla as tesla,
    volt as volt,
)

__version__: str
__all__: list[str]
