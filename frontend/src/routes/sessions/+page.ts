import { api } from '$lib/api/client'
import type { PageLoad } from './$types'

export const load: PageLoad = async () => {
	const response = await api.getSessions()
	return {
		sessions: response.sessions
	}
}
