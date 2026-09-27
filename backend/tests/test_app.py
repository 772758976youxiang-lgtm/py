import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend import ai


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as c:
        c.headers['X-Lab-Token'] = c.get('/api/session').json()['token']
        yield c


def note(client, content='print("你好")'):
    response = client.post('/api/notes', json={'title':'测试', 'content':content})
    assert response.status_code == 201
    return response.json()


def run(client, code, timeout=5):
    r = client.post('/api/runs', json={'code':code, 'timeout':timeout})
    assert r.status_code == 201, r.text
    return r.json()['id']


def wait_run(client, rid, predicate=lambda j: j['status'] != 'running'):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        job = client.get('/api/runs/' + rid).json()
        if predicate(job):
            return job
        time.sleep(.025)
    pytest.fail(f'run did not finish: {job}')


def test_persistence_and_conflict(client, tmp_path):
    n = note(client)
    changed = {k:n[k] for k in ('title','content','revision')}
    changed['content'] = 'print(42)'
    r = client.put('/api/notes/' + n['id'], json=changed)
    assert r.status_code == 200
    assert r.json()['revision'] == 2
    assert client.put('/api/notes/' + n['id'], json=changed).status_code == 409
    with TestClient(create_app(tmp_path)) as second:
        second.headers['X-Lab-Token'] = second.get('/api/session').json()['token']
        assert second.get('/api/notes').json()[0]['content'] == 'print(42)'
    assert client.delete('/api/notes/' + n['id']).status_code == 200
    assert client.get('/api/notes').json() == []


def test_settings_import_export_validation(client):
    s = client.get('/api/settings').json()
    s.update(theme='dark',language='en',tabSize=2)
    assert client.put('/api/settings',json=s).json() == s
    assert client.get('/api/settings').json() == s
    s['timeout'] = 100
    assert client.put('/api/settings',json=s).status_code == 422
    rows = [{'title':'a','content':'a=1'},{'title':'b','content':'b=2'}]
    assert len(client.post('/api/import',json={'notes':rows}).json()['ids']) == 2
    assert len(client.get('/api/export').json()['notes']) == 2
    assert client.post('/api/import',json={'notes':[{'title':'bad','content':5}]}).status_code == 422
    assert len(client.get('/api/notes').json()) == 2


def test_provider_encryption_and_key_preservation(client,tmp_path):
    p=dict(id='test',name='测试',url='https://api.example.com/v1',protocol='openai-chat',key='secret-test-key',models=['a','a',' b '])
    r=client.post('/api/providers',json=p)
    assert r.status_code == 201
    assert r.json()['has_key'] and r.json()['models']==['a','b']
    assert 'secret-test-key' not in r.text
    assert b'secret-test-key' not in (tmp_path/'lab.sqlite3').read_bytes()
    assert client.post('/api/providers',json=p).status_code == 409
    p['key']='';p['name']='renamed'
    assert client.put('/api/providers/test',json=p).json()['has_key']
    p['clear_key']=True
    assert not client.put('/api/providers/test',json=p).json()['has_key']
    p['url']='http://example.com/v1'
    assert client.put('/api/providers/test',json=p).status_code == 422
    assert client.delete('/api/providers/test').status_code == 200


def test_request_guard(client):
    assert client.get('/api/notes',headers={'X-Lab-Token':''}).status_code == 401
    assert client.get('/api/session',headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/runs',headers={'Origin':'null'},json={'code':'print(1)'}).status_code == 403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code == 400
    assert client.get('/api/session',headers={'Origin':'http://127.0.0.1:5173'}).status_code == 200


def test_real_python_and_errors(client):
    rid=run(client,'import json\nprint(json.dumps({"a": 42}))\nprint("你好")')
    j=wait_run(client,rid)
    assert j['status']=='completed' and j['exit_code']==0
    assert j['stdout']=='{"a": 42}\n你好\n'
    j=wait_run(client,run(client,'print(1/0)'))
    assert j['status']=='error' and 'ZeroDivisionError' in j['stderr']
    assert 'main.py' in j['stderr'] and 'worker.py' not in j['stderr']
    j=wait_run(client,run(client,'if True print(1)'))
    assert j['status']=='error' and 'SyntaxError' in j['stderr']


def test_interactive_stdin_and_eof(client):
    rid=run(client,'name=input("Name: ")\nprint("Hello", name)')
    wait_run(client,rid,lambda j:'Name:' in j['stdout'])
    assert client.post(f'/api/runs/{rid}/input',json={'text':'小明\n'}).status_code==200
    j=wait_run(client,rid)
    assert 'Hello 小明' in j['stdout']
    rid=run(client,'import sys\nprint("Ready", flush=True)\nprint(sys.stdin.read())')
    wait_run(client,rid,lambda j:'Ready' in j['stdout'])
    assert client.post(f'/api/runs/{rid}/input',json={'text':'abc','eof':True}).status_code==200
    assert 'abc' in wait_run(client,rid)['stdout']


def test_timeout_stop_output_limit_and_single_run(client):
    j=wait_run(client,run(client,'while True: pass',timeout=2))
    assert j['status']=='timeout'
    rid=run(client,'import time\nprint("start",flush=True)\ntime.sleep(10)')
    wait_run(client,rid,lambda j:'start' in j['stdout'])
    assert client.post('/api/runs',json={'code':'print(1)'}).status_code==409
    j=client.post(f'/api/runs/{rid}/stop').json()
    assert j['status']=='stopped'
    j=wait_run(client,run(client,'while True: print("x" * 4096)'))
    assert j['status']=='output_limit'
    assert len(j['stdout'].encode())<=128*1024
    assert wait_run(client,run(client,'print("next")'))['status']=='completed'


@pytest.mark.parametrize('protocol', ['openai-chat','openai-responses','anthropic-messages'])
def test_ai_protocols_chat_storage_models_and_cascade(client,monkeypatch,protocol):
    calls=[]
    async def fake(method,url,headers,payload=None):
        calls.append((method,url,headers,payload))
        if method=='GET':return {'data':[{'id':'model-a'},{'id':'model-b'}]}
        if protocol=='openai-chat':return {'choices':[{'message':{'content':'解释\n```python\nprint(42)\n```'}}]}
        if protocol=='openai-responses':return {'output':[{'type':'reasoning','summary':[]},{'type':'message','content':[{'type':'output_text','text':'解释'}]}]}
        return {'content':[{'type':'text','text':'解释'}]}
    monkeypatch.setattr(ai,'request_json',fake)
    p=dict(id='test',name='Test',url='https://api.example.com/v1',protocol=protocol,key='key-test',models=[])
    assert client.post('/api/providers',json=p).status_code==201
    assert client.post('/api/providers/test/models').json()['models']==['model-a','model-b']
    n=note(client)
    body=dict(message='解释代码',code='print(42)',provider_id='test',model='model-a')
    r=client.post(f'/api/notes/{n["id"]}/chat',json=body)
    assert r.status_code==200, r.text
    assert len(r.json()['messages'])==2
    method,url,headers,payload=calls[-1]
    assert payload['model']=='model-a'
    turns=payload.get('input',payload.get('messages'))
    assert 'print(42)' in turns[-1]['content']
    if protocol=='anthropic-messages':assert headers['x-api-key']=='key-test' and payload['max_tokens']==4096
    else:assert headers['Authorization']=='Bearer key-test'
    body['message']='继续';body['code']=''
    assert client.post(f'/api/notes/{n["id"]}/chat',json=body).status_code==200
    turns=calls[-1][3].get('input',calls[-1][3].get('messages'))
    assert any('print(42)' in x['content'] for x in turns[:-1])
    assert len(client.get(f'/api/notes/{n["id"]}/messages').json())==4
    assert client.delete('/api/notes/'+n['id']).status_code==200
    with client.app.state.store.connect() as db:assert db.execute('SELECT count(*) FROM messages').fetchone()[0]==0


def test_ai_failure_does_not_corrupt_history(client,monkeypatch):
    async def fake(*args,**kwargs):return {'unexpected':'response'}
    monkeypatch.setattr(ai,'request_json',fake)
    n=note(client)
    body=dict(message='hi',provider_id='deepseek',model='test')
    assert client.post(f'/api/notes/{n["id"]}/chat',json=body).status_code==502
    assert client.get(f'/api/notes/{n["id"]}/messages').json()==[]


def test_recover_active_run_after_frontend_reload(client):
    n=note(client)
    r=client.post('/api/runs',json={'code':'import time\ntime.sleep(5)','note_id':n['id']})
    rid=r.json()['id']
    recovery=client.get('/api/runs/active').json()
    assert recovery['run']['id']==rid
    assert recovery['note_id']==n['id'] and 'time.sleep' in recovery['code']
    client.post(f'/api/runs/{rid}/stop')
    assert client.get('/api/runs/active').json()=={'run':None}
