let token = '';
export class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
export async function connect() {
  const response = await fetch('/api/session');
  if (!response.ok) throw new ApiError('Cannot connect to backend', response.status);
  token = (await response.json()).token;
}
export async function api(path, {method='GET', body, signal}={}, refreshed=false) {
  let response;
  try {
    response = await fetch(`/api${path}`, {method, signal, headers:{'Content-Type':'application/json','X-Lab-Token':token},
      ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  } catch (e) { if (e.name === 'AbortError') throw e; throw new ApiError('无法连接后端 / Backend unavailable', 0); }
  if (response.status === 401 && !refreshed) {
    await connect();
    return api(path, {method, body, signal}, true);
  }
  let data;
  try { data = await response.json(); } catch { throw new ApiError('Invalid API response', response.status); }
  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail) ? detail.map(x=>`${x.loc.slice(1).join('.')}: ${x.msg}`).join('\n') : detail;
    throw new ApiError(message || `HTTP ${response.status}`, response.status);
  }
  return data;
}
