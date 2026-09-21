"""Deterministic main-thread timeout orderings."""
from threading import Event, Thread

import pytest

from test_simple_v2_bridge import CocoaMainThread


def dispatcher(schedule):
    value = CocoaMainThread.__new__(CocoaMainThread)
    value.timeout = 0
    value.schedule = schedule
    return value


def test_pending_timeout_cancels_queued_callback():
    queued, writes = [], []
    with pytest.raises(TimeoutError) as error:
        dispatcher(queued.append).call(lambda: writes.append("write"))
    queued.pop()()
    assert writes == []
    assert error.value.execution == "cancelled"


def test_running_timeout_retains_execution_and_never_repeats_callback():
    started, finish = Event(), Event()
    writes, threads = [], []

    def callback():
        started.set()
        assert finish.wait(2)
        writes.append("write")

    def schedule(callback):
        thread = Thread(target=callback)
        threads.append(thread)
        thread.start()
        assert started.wait(2)

    try:
        with pytest.raises(TimeoutError) as error:
            dispatcher(schedule).call(callback)
        assert error.value.execution == "uncertain"
    finally:
        finish.set()
        for thread in threads:
            thread.join(2)
    assert writes == ["write"]


def test_completed_callback_wins_timeout_boundary():
    assert dispatcher(lambda callback: callback()).call(lambda: 42) == 42


def test_callback_error_survives_dispatch():
    with pytest.raises(ValueError, match="native failure"):
        dispatcher(lambda callback: callback()).call(
            lambda: (_ for _ in ()).throw(ValueError("native failure")))


@pytest.mark.parametrize('execution', ['cancelled', 'uncertain'])
@pytest.mark.parametrize('path,payload', [('/v1/apply', {'patch': {'jobId': 'job_existing'}}),
                                        ('/v1/discard', {'jobId': 'job_existing'}),
                                        ('/v1/accept', {'jobId': 'job_existing', 'save': {'saveId': 'job_existing'}})])
def test_http_timeout_error_keeps_job_identity(execution, path, payload):
    import io
    import json
    from types import SimpleNamespace as NS
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    from glyphs_mcp_bridge.main_thread import DispatchTimeout
    def call(_): raise DispatchTimeout(execution)
    server = BridgeHTTPServer.__new__(BridgeHTTPServer)
    server.token, server.main_thread = 'test-token', NS(call=call)
    handler = server._handler().__new__(server._handler())
    body = json.dumps(payload).encode()
    handler.path, handler.rfile = path, io.BytesIO(body)
    handler.headers = {'Authorization': 'Bearer test-token', 'Content-Length': str(len(body))}
    replies = []
    handler._reply = lambda status, body: replies.append((status, body))
    handler.do_POST()
    status, body = replies[0]
    assert status == 503
    expected = {'execution': execution, 'jobId': 'job_existing'}
    if path == '/v1/accept':
        expected['saveId'] = 'job_existing'
    assert body['error']['details'] == expected
