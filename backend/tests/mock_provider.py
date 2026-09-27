"""Optional manual UI fixture. Never used by the normal app.
Run: .venv/bin/python -m uvicorn backend.tests.mock_provider:app --port 18080
"""
from fastapi import FastAPI

app = FastAPI()

@app.get('/v1/models')
def models():
    return {'data':[{'id':'fixture-python-tutor'}]}

@app.post('/v1/chat/completions')
def chat(payload: dict):
    assert payload['model'] == 'fixture-python-tutor'
    assert payload['messages'][-1]['role'] == 'user'
    return {'choices':[{'message':{'content':'这是本地测试回复。`print()` 会输出文本。\n\n```python\nprint("AI 代码块验证成功")\n```\n\n试着修改引号里的内容。'}}]}
