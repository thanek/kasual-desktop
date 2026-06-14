"""Tests for the Brightness domain value object."""

from domain.system.brightness import Brightness


class TestBrightness:
    def test_stores_value(self):
        assert Brightness(42).value == 42

    def test_clamps_above_100(self):
        assert Brightness(150).value == 100

    def test_clamps_to_minimum_floor(self):
        # Unlike Volume, brightness never reaches 0 (black screen).
        assert Brightness(0).value == Brightness.MIN

    def test_clamps_below_minimum(self):
        assert Brightness(-5).value == Brightness.MIN

    def test_boundary_100(self):
        assert Brightness(100).value == 100

    def test_adjusted_increases(self):
        assert Brightness(50).adjusted(10).value == 60

    def test_adjusted_decreases(self):
        assert Brightness(50).adjusted(-10).value == 40

    def test_adjusted_clamps_at_max(self):
        assert Brightness(95).adjusted(10).value == 100

    def test_adjusted_clamps_at_minimum(self):
        assert Brightness(Brightness.MIN + 2).adjusted(-10).value == Brightness.MIN

    def test_adjusted_returns_new_instance(self):
        b = Brightness(50)
        assert b.adjusted(10) is not b

    def test_step_constant(self):
        assert Brightness.STEP == 10

    def test_default_constant(self):
        assert Brightness.DEFAULT == 70

    def test_equality(self):
        assert Brightness(42) == Brightness(42)

    def test_inequality(self):
        assert Brightness(42) != Brightness(43)
