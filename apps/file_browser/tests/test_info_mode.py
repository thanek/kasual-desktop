"""Tests for pure helper functions in info_mode.py."""

import pytest

from info_mode import _human_size, _mime_icon


class TestHumanSize:
    def test_zero_bytes(self):
        assert _human_size(0) == "0 B"

    def test_small_bytes(self):
        assert _human_size(1) == "1 B"
        assert _human_size(1023) == "1023 B"

    def test_kilobytes(self):
        assert _human_size(1024) == "1.0 KB"
        assert _human_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert _human_size(1024 ** 2) == "1.0 MB"

    def test_gigabytes(self):
        assert _human_size(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert _human_size(1024 ** 4) == "1.0 TB"


class TestMimeIcon:
    def test_unknown_returns_generic_file(self):
        assert _mime_icon("") == "fa5s.file"
        assert _mime_icon(None) == "fa5s.file"  # type: ignore[arg-type]

    def test_video(self):
        assert _mime_icon("video/mp4") == "fa5s.film"
        assert _mime_icon("video/mkv") == "fa5s.film"

    def test_audio(self):
        assert _mime_icon("audio/mpeg") == "fa5s.headphones"
        assert _mime_icon("audio/flac") == "fa5s.headphones"

    def test_text(self):
        assert _mime_icon("text/plain") == "fa5s.file-alt"
        assert _mime_icon("text/html") == "fa5s.file-alt"

    def test_pdf(self):
        assert _mime_icon("application/pdf") == "fa5s.file-pdf"

    def test_archive_types(self):
        for mime in (
            "application/zip",
            "application/x-tar",
            "application/gzip",
            "application/x-7z-compressed",
            "application/x-rar-compressed",
        ):
            assert _mime_icon(mime) == "fa5s.file-archive", f"failed for {mime}"

    def test_unknown_application(self):
        assert _mime_icon("application/octet-stream") == "fa5s.file"
