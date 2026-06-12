"""Tests for LogProvider — the log-serving policy over a fake source (no I/O)."""

from domain.shared.log_provider import LogProvider


class FakeSource:
    """In-memory LogSource: revision tracks content unless forced unavailable."""

    def __init__(self, content: str = "", name: str = "kasual.log"):
        self._content = content
        self._name = name
        self.available = True
        self.reads = 0

    def set(self, content: str) -> None:
        self._content = content

    def name(self) -> str:
        return self._name

    def revision(self) -> int:
        return len(self._content) if self.available else -1

    def read(self) -> str:
        self.reads += 1
        return self._content

    def clear(self) -> None:
        self._content = ""


class TestPoll:
    def test_first_poll_serves_content(self):
        provider = LogProvider(FakeSource("hello"))
        assert provider.poll() == "hello"

    def test_unchanged_poll_returns_none_and_skips_read(self):
        source = FakeSource("hello")
        provider = LogProvider(source)
        provider.poll()
        assert provider.poll() is None
        assert source.reads == 1   # second poll did not re-read

    def test_changed_content_is_reserved(self):
        source = FakeSource("a")
        provider = LogProvider(source)
        assert provider.poll() == "a"
        source.set("a longer line")
        assert provider.poll() == "a longer line"

    def test_unavailable_source_returns_none(self):
        source = FakeSource("hello")
        source.available = False
        provider = LogProvider(source)
        assert provider.poll() is None


class TestInvalidate:
    def test_forces_reserve_of_unchanged_content(self):
        source = FakeSource("same")
        provider = LogProvider(source)
        provider.poll()
        provider.invalidate()
        assert provider.poll() == "same"
        assert source.reads == 2


class TestClear:
    def test_empties_source(self):
        source = FakeSource("noisy")
        provider = LogProvider(source)
        provider.clear()
        assert source.revision() == 0

    def test_poll_after_clear_sees_no_change(self):
        source = FakeSource("noisy")
        provider = LogProvider(source)
        provider.poll()
        provider.clear()
        assert provider.poll() is None   # resynced — nothing new to serve


class TestName:
    def test_exposes_source_name(self):
        assert LogProvider(FakeSource(name="abc.log")).name == "abc.log"
