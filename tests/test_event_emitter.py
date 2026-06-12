"""Tests for the framework-agnostic EventEmitter / Unsubscribe pub-sub hub."""

from domain.shared.event_emitter import EventEmitter, Unsubscribe


class TestSubscribeEmit:
    def test_handler_receives_event(self):
        bus = EventEmitter[int]()
        seen: list[int] = []
        bus.subscribe(seen.append)
        bus.emit(42)
        assert seen == [42]

    def test_multiple_handlers_all_fire_in_order(self):
        bus = EventEmitter[str]()
        order: list[str] = []
        bus.subscribe(lambda e: order.append("a"))
        bus.subscribe(lambda e: order.append("b"))
        bus.emit("x")
        assert order == ["a", "b"]

    def test_emit_with_no_handlers_is_noop(self):
        EventEmitter[int]().emit(1)  # must not raise


class TestUnsubscribe:
    def test_token_detaches_handler(self):
        bus = EventEmitter[int]()
        seen: list[int] = []
        token = bus.subscribe(seen.append)
        token()
        bus.emit(1)
        assert seen == []

    def test_token_is_idempotent(self):
        bus = EventEmitter[int]()
        token = bus.subscribe(lambda e: None)
        token()
        token()  # second call must not raise

    def test_only_named_handler_is_removed(self):
        bus = EventEmitter[int]()
        kept: list[int] = []
        token = bus.subscribe(lambda e: None)
        bus.subscribe(kept.append)
        token()
        bus.emit(7)
        assert kept == [7]

    def test_returns_unsubscribe_instance(self):
        token = EventEmitter[int]().subscribe(lambda e: None)
        assert isinstance(token, Unsubscribe)


class TestReentrancy:
    def test_handler_may_unsubscribe_during_emit(self):
        bus = EventEmitter[int]()
        seen: list[int] = []

        def once(_evt: int) -> None:
            seen.append(_evt)
            token()

        token = bus.subscribe(once)
        bus.emit(1)
        bus.emit(2)
        assert seen == [1]   # detached itself during the first emit

    def test_clear_removes_all(self):
        bus = EventEmitter[int]()
        seen: list[int] = []
        bus.subscribe(seen.append)
        bus.subscribe(seen.append)
        bus.clear()
        bus.emit(1)
        assert seen == []
