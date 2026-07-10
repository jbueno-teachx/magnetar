"""Physical magnitudes as distinct float types.

These are zero-cost at runtime (``NewType`` wrappers around ``float``) but give
type checkers a way to catch unit mix-ups before formulas get messy, e.g.
passing a charge where a mass was expected.

Convention used in magnetar
---------------------------
* time            → :class:`Second`
* distance        → :class:`Meter` / :data:`Position`
* magnetic field  → :class:`Tesla`
* electric charge → :class:`Coulomb`
* mass            → :class:`Gram`  (grams, not kilograms)
* potential       → :class:`Volt`
"""

from __future__ import annotations

from typing import NewType, SupportsFloat, Tuple

# ---------------------------------------------------------------------------
# Unit-tagged scalars
# ---------------------------------------------------------------------------

Second = NewType("Second", float)
Meter = NewType("Meter", float)
Tesla = NewType("Tesla", float)
Coulomb = NewType("Coulomb", float)
Gram = NewType("Gram", float)
Volt = NewType("Volt", float)

# 3D position / displacement in meters.
Vec3 = Tuple[Meter, Meter, Meter]
Position = Vec3

# ---------------------------------------------------------------------------
# Constructors (prefer these at call sites so the unit is obvious)
# ---------------------------------------------------------------------------


def second(value: SupportsFloat) -> Second:
    """Time duration / clock reading in seconds (s)."""
    return Second(float(value))


def meter(value: SupportsFloat) -> Meter:
    """Distance / coordinate component in meters (m)."""
    return Meter(float(value))


def meters(x: SupportsFloat, y: SupportsFloat, z: SupportsFloat) -> Position:
    """Build a 3D position or displacement in meters."""
    return (meter(x), meter(y), meter(z))


def position(x: SupportsFloat, y: SupportsFloat, z: SupportsFloat) -> Position:
    """Alias for :func:`meters` — a particle position in meters."""
    return meters(x, y, z)


def tesla(value: SupportsFloat) -> Tesla:
    """Magnetic field strength in tesla (T)."""
    return Tesla(float(value))


def coulomb(value: SupportsFloat) -> Coulomb:
    """Electric charge in coulomb (C)."""
    return Coulomb(float(value))


def gram(value: SupportsFloat) -> Gram:
    """Mass in grams (g)."""
    return Gram(float(value))


def volt(value: SupportsFloat) -> Volt:
    """Electric potential in volt (V)."""
    return Volt(float(value))


# ---------------------------------------------------------------------------
# Conversions used by physics formulas (SI / MKS helpers)
# ---------------------------------------------------------------------------


def grams_to_kg(mass: Gram) -> float:
    """Convert grams → kilograms for F = ma style formulas."""
    return float(mass) * 1.0e-3


def kg_to_grams(mass_kg: SupportsFloat) -> Gram:
    """Convert kilograms → grams."""
    return Gram(float(mass_kg) * 1.0e3)


def as_position(
    value: Tuple[SupportsFloat, SupportsFloat, SupportsFloat] | Position,
) -> Position:
    """Coerce a plain ``(x, y, z)`` triple into a :data:`Position` (meters)."""
    return meters(value[0], value[1], value[2])


# Back-compat alias used by older call sites.
as_vec3 = as_position
