"""Named unit helpers (mf-conventions: never inline ``* 1e-3``)."""


def mm_to_m(x_mm):
    """Millimetres to metres."""
    return x_mm * 1e-3


def m_to_mm(x_m):
    """Metres to millimetres."""
    return x_m * 1e3
