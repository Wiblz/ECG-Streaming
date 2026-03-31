import { api } from '$lib/api/client';
import { parsePaginationParams } from '$lib/api/queryParams';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
  const pagination = parsePaginationParams(url.searchParams);

  // Fetch both devices and collectors in parallel
  const [devicesResponse, collectorsResponse] = await Promise.all([
    api.getAllDevices(pagination),
    api.getCollectors()
  ]);

  return {
    devices: devicesResponse.devices,
    devicesPagination: {
      count: devicesResponse.count,
      total: devicesResponse.total,
      limit: devicesResponse.limit ?? null,
      offset: devicesResponse.offset
    },
    collectors: collectorsResponse.collectors
  };
};
