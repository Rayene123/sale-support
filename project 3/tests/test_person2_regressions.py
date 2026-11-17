"""Regression cases from Person 2's review; no network or paid APIs."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from agent.tools import mytek
from agent.tools.payloads import canonical_action_payload
from sandbox.approvals import record_approval


@pytest.mark.parametrize('label', ['unavailable', 'indisponible', 'out-of-stock', 'out of stock', 'rupture de stock'])
def test_negative_stock_is_never_available(label):
    parser = mytek._CatalogCards()
    parser.feed(f'<article class="product-miniature" data-id-product="1"><span class="{label}" itemprop="availability">{label}</span></article>')
    assert parser.items[0]['availability'] == 'out_of_stock'


class Response:
    def __init__(self, status=200, location=None, chunks=()):
        self.status_code = status
        self.headers = {'Location': location} if location else {}
        self.chunks = chunks
        self.closed = False
        self.read_chunks = 0

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            self.read_chunks += 1
            yield chunk

    def close(self):
        self.closed = True


def mock_fetch(monkeypatch, responses):
    calls = []
    monkeypatch.setattr(mytek.time, 'sleep', lambda _: None)
    def get(url, **kwargs):
        calls.append(url)
        assert kwargs['stream'] and not kwargs['allow_redirects']
        return responses.pop(0)
    monkeypatch.setattr(mytek.requests, 'get', get)
    return calls


@pytest.mark.parametrize('destination', ['http://www.tunisianet.com.tn/a', 'https://evil.test/a', 'https://www.tunisianet.com.tn@evil.test/a', 'https://www.tunisianet.com.tn:444/a'])
def test_redirect_destination_checked_before_request(monkeypatch, destination):
    response = Response(302, destination)
    calls = mock_fetch(monkeypatch, [response])
    with pytest.raises(requests.RequestException):
        mytek._bounded_get('https://www.tunisianet.com.tn/a', timeout=1)
    assert len(calls) == 1 and response.closed


def test_allowed_redirect_preserves_body_and_closes_connections(monkeypatch):
    first, second = Response(302, '/next'), Response(chunks=[b'hello', b' world'])
    calls = mock_fetch(monkeypatch, [first, second])
    result = mytek._bounded_get('https://www.tunisianet.com.tn/a', timeout=1)
    assert result._content == b'hello world'
    assert calls[-1] == 'https://www.tunisianet.com.tn/next'
    assert first.closed and second.closed


def test_stream_stops_at_size_limit(monkeypatch):
    response = Response(chunks=[b'1234', b'5678', b'never read'])
    monkeypatch.setattr(mytek, '_MAX_BYTES', 5)
    mock_fetch(monkeypatch, [response])
    with pytest.raises(requests.RequestException, match='size limit'):
        mytek._bounded_get('https://www.tunisianet.com.tn/a', timeout=1)
    assert response.read_chunks == 2 and response.closed


def test_redirect_loop_is_bounded(monkeypatch):
    responses = [Response(302, '/loop') for _ in range(4)]
    calls = mock_fetch(monkeypatch, responses.copy())
    with pytest.raises(requests.TooManyRedirects):
        mytek._bounded_get('https://www.tunisianet.com.tn/a', timeout=1)
    assert len(calls) == 4 and all(r.closed for r in responses)


def test_approval_persistence_uses_same_money_representation_as_execution():
    payload = {'customer_id':'C-001', 'items':[{'product_id':'P1','name':'Fixture','quantity':2,
        'unit_price_tnd':1.2,'source_url':'https://www.tunisianet.com.tn/a'}],
        'total_tnd':2.4,'source_evidence_ids':['P1']}
    calls=[]
    class Client:
        def rpc(self, name, args):
            calls.append((name,args))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={'success':True,'approval_id':'approval-test'}))
    record_approval(store=SimpleNamespace(client=Client()), action='create_customer_order',
        operation_id='operation-test', run_id='run-test', approval_id='approval-test',
        approved_by='human-test', payload=payload, expires_at=datetime(2030,1,1,tzinfo=timezone.utc))
    saved=calls[0][1]['p_payload']
    assert saved['total_tnd']=='2.40'
    assert saved['items'][0]['unit_price_tnd']=='1.20'
    assert saved['items'][0]['line_total_tnd']=='2.40'
    assert canonical_action_payload('create_customer_order', saved)==saved
