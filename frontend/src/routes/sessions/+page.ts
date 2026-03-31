import { api } from '$lib/api/client';
import { parsePaginationParams } from '$lib/api/queryParams';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
  const pagination = parsePaginationParams(url.searchParams);

  const [sessionsResponse, devicesResponse] = await Promise.all([
    api.getSessions(pagination),
    api.getAllDevices()
  ]);
  return {
    sessions: sessionsResponse.sessions,
    sessionsPagination: {
      count: sessionsResponse.count,
      total: sessionsResponse.total,
      limit: sessionsResponse.limit ?? null,
      offset: sessionsResponse.offset
    },
    devices: devicesResponse.devices
  };
};
