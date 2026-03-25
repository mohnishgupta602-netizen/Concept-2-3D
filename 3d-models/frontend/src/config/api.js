const rawBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').trim();

const normalizedBase = rawBase.endsWith('/') ? rawBase.slice(0, -1) : rawBase;

export function apiUrl(path) {
  const safePath = path.startsWith('/') ? path : `/${path}`;
  const apiPath = safePath.startsWith('/api/') || safePath === '/api' ? safePath : `/api${safePath}`;

  if (normalizedBase === '') return apiPath;

  if (/^https?:\/\//i.test(normalizedBase)) {
    return `${normalizedBase}${apiPath}`;
  }

  return `${normalizedBase}${apiPath}`;
}

export const API_BASE_URL = normalizedBase || 'http://127.0.0.1:8000';
