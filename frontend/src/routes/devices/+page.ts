import { api } from '$lib/api/client';
import { parsePaginationParams } from '$lib/api/queryParams';
import type { DeviceListParams } from '$lib/types/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
  const pagination = parsePaginationParams(url.searchParams) ?? { limit: 50, offset: 0 };

  const status = url.searchParams.get('status') as DeviceListParams['status'] | null;
  const sort_by = (url.searchParams.get('sort_by') ?? 'last_seen') as DeviceListParams['sort_by'];
  const sort_order = (url.searchParams.get('sort_order') ??
    'desc') as DeviceListParams['sort_order'];

  // Fetch both devices and collectors in parallel
  const [devicesResponse, collectorsResponse] = await Promise.all([
    api.getAllDevices({ ...pagination, status: status ?? undefined, sort_by, sort_order }),
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
    collectors: collectorsResponse.collectors,
    filters: { status, sort_by, sort_order }
  };
};
