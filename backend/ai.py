"""Provider adapters. User-selected model IDs are passed through unchanged."""
import httpx
from fastapi import HTTPException

SYSTEM = ('You are a patient Python tutor. Explain the cause of errors and teach the underlying idea. '
          'Return executable Python in fenced python code blocks. Never claim to have run code. ')


async def request_json(method, url, headers, payload=None):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), follow_redirects=False) as client:
            # Bound the upstream body rather than loading an unlimited response into memory.
            async with client.stream(method, url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    status = response.status_code
                    hints = {401: 'API 密钥无效', 403: '没有访问权限', 404: 'API 地址或模型不存在',
                             429: '请求频率或额度受限'}
                    raise HTTPException(502, f'模型服务返回 HTTP {status}：{hints.get(status, "请检查服务商状态及配置")}。')
                if 300 <= response.status_code < 400:
                    raise HTTPException(502, 'API 地址发生重定向，请填写最终 API 地址。')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2 * 1024 * 1024:
                        raise HTTPException(502, '模型服务返回的数据过大。')
                import json
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise ValueError('not an object')
                return result
    except httpx.TimeoutException:
        raise HTTPException(504, '模型服务响应超时，请稍后重试。')
    except httpx.RequestError:
        raise HTTPException(502, '无法连接模型服务，请检查 API 地址和网络。')
    except (ValueError, UnicodeError):
        raise HTTPException(502, '模型服务返回的不是有效 JSON。')


def headers(provider, key):
    if provider['protocol'] == 'anthropic-messages':
        return {**({'x-api-key': key} if key else {}), 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}
    return {**({'Authorization': f'Bearer {key}'} if key else {}), 'Content-Type': 'application/json'}


async def models(provider, key):
    result = await request_json('GET', provider['url'].rstrip('/') + '/models', headers(provider, key))
    rows = result.get('data', [])
    if not isinstance(rows, list):
        raise HTTPException(502, '模型列表格式不受支持，可手动填写模型 ID。')
    ids = sorted({r['id'] for r in rows if isinstance(r, dict) and isinstance(r.get('id'), str) and len(r['id']) <= 200})
    if not ids:
        raise HTTPException(502, '未获取到模型，可手动填写模型 ID。')
    return ids[:500]


async def chat(provider, key, model, messages, language):
    protocol = provider['protocol']
    system = SYSTEM + ('Reply in Chinese.' if language == 'zh' else 'Reply in English.')
    if protocol == 'openai-chat':
        endpoint = '/chat/completions'
        payload = dict(model=model, messages=[dict(role='system', content=system)] + messages)
    elif protocol == 'openai-responses':
        endpoint = '/responses'
        payload = dict(model=model, instructions=system, input=messages, store=False)
    else:
        endpoint = '/messages'
        payload = dict(model=model, system=system, messages=messages, max_tokens=4096)
    data = await request_json('POST', provider['url'].rstrip('/') + endpoint, headers(provider, key), payload)
    try:
        if protocol == 'openai-chat':
            message = data['choices'][0]['message']
            reply = message.get('content') or message.get('refusal')
        elif protocol == 'openai-responses':
            reply = '\n'.join(part.get('text', '') or part.get('refusal', '')
                              for item in data.get('output', []) if item.get('type') == 'message'
                              for part in item.get('content', []) if part.get('type') in ('output_text', 'refusal'))
        else:
            reply = '\n'.join(p['text'] for p in data.get('content', []) if p.get('type') == 'text')
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError('empty')
        return reply.strip()
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise HTTPException(502, '模型未返回可显示的文本，请检查模型及 API 协议。')
