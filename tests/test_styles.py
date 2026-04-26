"""Tests for ui.styles utility functions."""

import pytest
from ui.styles import truncate


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_max_len_unchanged(self):
        assert truncate("hello", 5) == "hello"

    def test_one_over_truncated(self):
        assert truncate("hello!", 5) == "hell…"

    def test_result_is_max_len(self):
        text = "A very long application name here"
        result = truncate(text, 22)
        assert len(result) == 22
        assert result.endswith("…")

    def test_empty_string_unchanged(self):
        assert truncate("", 5) == ""

    def test_max_len_one(self):
        assert truncate("abc", 1) == "…"

    def test_multibyte_ellipsis_counts_as_one_char(self):
        # "…" is a single Python character
        result = truncate("abcde", 4)
        assert len(result) == 4
        assert result == "abc…"

    def test_unicode_text(self):
        text = "Długa nazwa aplikacji"
        result = truncate(text, 10)
        assert len(result) == 10
        assert result.endswith("…")
