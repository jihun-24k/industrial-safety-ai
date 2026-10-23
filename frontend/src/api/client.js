export async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    signal: options.signal || AbortSignal.timeout(90000),
  });

  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('로그인이 필요하거나 만료되었습니다. 다시 로그인해 주세요.');
    }

    const message = typeof data === 'object'
      ? (typeof data.detail === 'string' ? data.detail : data.error)
      : null;
    throw new Error(message || '서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
  }

  return data;
}
