const rawBase = (import.meta.env.VITE_API_BASE_URL || '/api').trim();

const normalizedBase = rawBase.endsWith('/') ? rawBase.slice(0, -1) : rawBase;

export function apiUrl(path) {
  const safePath = path.startsWith('/') ? path : `/${path}`;

  if (normalizedBase === '') return safePath;

  if (/^https?:\/\//i.test(normalizedBase)) {
    return `${normalizedBase}${safePath}`;
  }

  return `${normalizedBase}${safePath}`;
}

export const API_BASE_URL = normalizedBase || '/api';
