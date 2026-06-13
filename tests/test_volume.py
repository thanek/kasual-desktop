"""Tests for the Volume domain value object."""

from domain.system.volume import Volume


class TestVolume:
    def test_stores_value(self):
        assert Volume(42).value == 42

    def test_clamps_above_100(self):
        assert Volume(150).value == 100

    def test_clamps_below_0(self):
        assert Volume(-5).value == 0

    def test_boundary_0(self):
        assert Volume(0).value == 0

    def test_boundary_100(self):
        assert Volume(100).value == 100

    def test_adjusted_increases(self):
        assert Volume(50).adjusted(5).value == 55

    def test_adjusted_decreases(self):
        assert Volume(50).adjusted(-5).value == 45

    def test_adjusted_clamps_at_max(self):
        assert Volume(98).adjusted(5).value == 100

    def test_adjusted_clamps_at_min(self):
        assert Volume(2).adjusted(-5).value == 0

    def test_adjusted_returns_new_instance(self):
        v = Volume(50)
        assert v.adjusted(5) is not v

    def test_step_constant(self):
        assert Volume.STEP == 5

    def test_default_constant(self):
        assert Volume.DEFAULT == 50

    def test_equality(self):
        assert Volume(42) == Volume(42)

    def test_inequality(self):
        assert Volume(42) != Volume(43)
