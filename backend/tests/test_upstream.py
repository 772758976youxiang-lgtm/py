import asyncio
import httpx
import pytest
from fastapi import HTTPException
from backend import ai


def transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(ai.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))


def test_http_transport_auth_payload_and_json(monkeypatch):
    def respond(request):
        assert request.headers['Authorization']=='Bearer fake-key'
        assert b'"model":"test-model"' in request.content
        return httpx.Response(200,json={'choices':[{'message':{'content':'ok'}}]})
    transport(monkeypatch,respond)
    provider=dict(protocol='openai-chat',url='https://example.com/v1')
    result=asyncio.run(ai.chat(provider,'fake-key','test-model',[dict(role='user',content='hello')],'en'))
    assert result=='ok'


@pytest.mark.parametrize('status', [401,403,404,429,500,302])
def test_upstream_errors_do_not_expose_response_secrets(monkeypatch,status):
    transport(monkeypatch,lambda request:httpx.Response(status,text='secret-key echoed by an upstream'))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(ai.request_json('GET','https://example.com/v1/models',{}))
    assert caught.value.status_code==502
    assert 'secret-key' not in caught.value.detail


def test_upstream_timeout(monkeypatch):
    def respond(request):raise httpx.ReadTimeout('timeout')
    transport(monkeypatch,respond)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(ai.request_json('GET','https://example.com',{}))
    assert caught.value.status_code==504


@pytest.mark.parametrize('body',[b'<html>not JSON</html>',b'[]',b'x'*(2*1024*1024+1)])
def test_malformed_and_oversized_upstream(monkeypatch,body):
    transport(monkeypatch,lambda request:httpx.Response(200,content=body))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(ai.request_json('GET','https://example.com',{}))
    assert caught.value.status_code==502


def test_keyless_local_provider_omits_authorization(monkeypatch):
    def respond(request):
        assert 'authorization' not in request.headers
        return httpx.Response(200,json={'data':[{'id':'local'}]})
    transport(monkeypatch,respond)
    assert asyncio.run(ai.models(dict(protocol='openai-chat',url='http://127.0.0.1:18080/v1'),''))==['local']
