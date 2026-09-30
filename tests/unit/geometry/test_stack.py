import pytest

from moduleforge.geometry import default_amb_stack, default_dbc_stack


@pytest.mark.parametrize("make,ceramic,t,k", [(default_dbc_stack, "Al2O3", 0.38e-3, 24.0),
                                              (default_amb_stack, "Si3N4", 0.32e-3, 90.0)])
def test_z_bookkeeping_bottom_up(make, ceramic, t, k):
    s = make()
    assert [la.name for la in s.layers] == ["baseplate", "solder", "backside_cu", "ceramic", "top_cu"]
    assert s.z_bottom("baseplate") == 0.0  # z = 0 at baseplate bottom
    # each layer starts where the previous one ends; total = sum of thicknesses
    for a, b in zip(s.layers[:-1], s.layers[1:], strict=True):
        assert s.z_top(a.name) == pytest.approx(s.z_bottom(b.name), rel=1e-12)
    assert s.z_top("top_cu") == pytest.approx(s.total_thickness, rel=1e-12)
    assert s.z_top("top_cu") == pytest.approx(3.0e-3 + 0.1e-3 + 0.3e-3 + t + 0.3e-3, rel=1e-12)
    assert s.layer("ceramic").material == ceramic and s.layer("ceramic").thickness == t
    assert s.layer("ceramic").k == k and s.layer("ceramic").sigma == 0.0
    assert s.layer("top_cu").sigma == pytest.approx(5.8e7)


def test_conductive_planes():
    assert default_dbc_stack().conductive_plane_names == ("baseplate", "backside_cu")
