import type { PaginationParams } from '$lib/types/api';

export function parsePaginationParams(searchParams: URLSearchParams): PaginationParams | undefined {
  const limit = searchParams.get('limit');
  const offset = searchParams.get('offset');

  if (limit === null && offset === null) {
    return undefined;
  }

  return {
    limit: limit !== null ? Number(limit) : undefined,
    offset: offset !== null ? Number(offset) : undefined
  };
}

export function buildSearchParams(
  params?: Record<string, string | number | null | undefined>
): URLSearchParams {
  const searchParams = new URLSearchParams();

  if (!params) {
    return searchParams;
  }

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      searchParams.set(key, String(value));
    }
  }

  return searchParams;
}

export function withSearchParams(path: string, searchParams: URLSearchParams): string {
  const query = searchParams.toString();
  return query ? `${path}?${query}` : path;
}
