import { api } from '$lib/api/client'
import type { PageLoad } from './$types'

export const load: PageLoad = async () => {
	// Fetch both devices and collectors in parallel
	const [devicesResponse, collectorsResponse] = await Promise.all([
		api.getAllDevices(),
		api.getCollectors()
	])

	return {
		devices: devicesResponse.devices,
		collectors: collectorsResponse.collectors
	}
}
