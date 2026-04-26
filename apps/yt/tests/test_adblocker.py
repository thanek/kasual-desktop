"""Tests for adblocker.py — URL blocking logic and JS patch content."""

from unittest.mock import MagicMock

import pytest

from adblocker import AdBlocker, JS_PATCH


class TestAdBlocker:
    def _make_info(self, url: str, blocked_holder: list):
        info = MagicMock()
        info.requestUrl.return_value.toString.return_value = url
        info.block.side_effect = lambda b: blocked_holder.append(b)
        return info

    def _is_blocked(self, url: str) -> bool:
        blocker = AdBlocker()
        result = []
        blocker.interceptRequest(self._make_info(url, result))
        return bool(result and result[0])

    def test_blocks_doubleclick(self):
        assert self._is_blocked("https://doubleclick.net/pixel")

    def test_blocks_googleads(self):
        assert self._is_blocked("https://googleads.g.doubleclick.net/pagead/viewthroughconversion")

    def test_blocks_ads_stats_endpoint(self):
        assert self._is_blocked("https://www.youtube.com/api/stats/ads?foobar=1")

    def test_blocks_pagead(self):
        assert self._is_blocked("https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js")

    def test_allows_normal_youtube(self):
        assert not self._is_blocked("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_allows_youtube_api(self):
        assert not self._is_blocked("https://www.youtube.com/api/timedtext")


class TestJsPatch:
    def test_is_non_empty_string(self):
        assert isinstance(JS_PATCH, str)
        assert len(JS_PATCH) > 0

    def test_patches_json_parse(self):
        assert "JSON.parse" in JS_PATCH

    def test_removes_ad_placements(self):
        assert "adPlacements" in JS_PATCH

    def test_contains_skip_button_logic(self):
        assert "ytp-ad-skip-button" in JS_PATCH
