# Mock Mode for UI Testing

Mock mode allows you to test the frontend UI without requiring a running backend or connected devices. It simulates various device and collector states with realistic data that updates in real-time.

## How to Enable Mock Mode

### Via UI Toggle

Click the **📡 Live Mode** / **🧪 Mock Mode** button in the header (top-right corner) to toggle between real API and mock data.

- **📡 Live Mode**: Uses real API endpoints (default)
- **🧪 Mock Mode**: Uses simulated mock data

**Note:** Toggling mock mode will reload the page to refresh all data.

### Programmatically

You can also enable mock mode programmatically:

```typescript
import { setMockMode } from '$lib/api/client';

// Enable mock mode
setMockMode(true);

// Disable mock mode
setMockMode(false);
```

## Mock Data Features

### Simulated Collectors (4 total)

1. **Lab Station 1** (collector-001)
   - Status: Healthy ✅
   - Connected: Yes
   - Devices: 2 active devices
   - Simulates a fully operational collector with good heartbeat

2. **Mobile Unit 3** (collector-002)
   - Status: Warning ⚠️
   - Connected: Yes
   - Devices: 1 active device
   - Simulates a collector with slow heartbeat (20s delay)

3. **Lab Station 2** (collector-003)
   - Status: Disconnected 🔴
   - Last seen: 5 minutes ago
   - Devices: 2 devices (both disconnected)
   - Simulates a recently disconnected collector

4. **Backup Collector** (collector-004)
   - Status: Disconnected 🔴
   - Last seen: 2 days ago
   - Simulates a long-disconnected spare unit

### Simulated Devices (9 total)

The mock data includes devices in various states:

- **Streaming devices** (2): Actively sending data, synced, with battery levels
- **Connected devices** (1): Connected but still syncing
- **Connecting devices** (1): In connection process
- **Error device** (1): Has an error message (low signal quality, low battery)
- **Disconnected devices** (4): Various disconnection scenarios
- **Unknown status device** (1): Device with unknown status

### Device Features

- **Nicknames**: Some devices have nicknames, others don't
- **Battery levels**: Simulated battery drain over time
- **Sync status**: Various sync confidence levels
- **Sample counts**: Realistic sample count tracking
- **Timestamps**: First seen, last seen, last update
- **Error messages**: Simulated error conditions

## Real-time Updates

When mock mode is enabled, the data automatically updates every 2 seconds to simulate:

- Battery drain
- Sample count increases
- Timestamp updates
- Sync confidence fluctuations
- Collector heartbeat timing

This allows you to test the live update behavior of the UI without a real backend.

## Testing Different Scenarios

### Nickname Management

1. Go to `/devices` page
2. Click the ✏️ icon next to any device
3. Edit the nickname
4. Changes persist in mock mode (until page reload)

### Filter and Sort

1. Go to `/devices` page
2. Use the filters:
   - **All Devices**: Shows all 9 devices
   - **Connected Only**: Shows 4 active devices
   - **Disconnected Only**: Shows 5 inactive devices
3. Try sorting by:
   - **Last Seen**: Recent activity first
   - **Name**: Alphabetical order
   - **Total Samples**: Highest sample count first

### Collector Status

1. View the collector cards at the top of `/devices`
2. Observe different health states:
   - Green (healthy)
   - Yellow (warning)
   - Red (disconnected)

### Dashboard View

1. Go to `/` (Dashboard)
2. The **Active Devices** panel shows only connected devices (4 total)
3. Click **Manage All Devices →** to see all devices including disconnected ones

## Use Cases

- **UI Development**: Test UI changes without backend
- **Visual Testing**: Verify layouts with different data states
- **UX Testing**: Test user flows and interactions
- **Demo Mode**: Show the UI to stakeholders without live data
- **Offline Development**: Work on frontend when backend is unavailable
- **Edge Cases**: Test how UI handles errors, disconnections, etc.

## Limitations

- Mock data resets on page reload
- WebSocket streaming is not simulated
- Sessions and historical data endpoints still use real API
- Nickname changes don't persist across reloads
- No actual ECG waveform data is generated

## Tips

1. **Keep mock mode enabled during development** if you don't need real data
2. **Test both modes** to ensure UI works correctly with real API
3. **Use mock mode for screenshots** and documentation
4. **Toggle back to live mode** before testing actual device connectivity

## Extending Mock Data

To add more mock scenarios, edit `frontend/src/lib/api/mockData.ts`:

```typescript
// Add new mock devices
export function getMockDevices(): DeviceInfo[] {
	return [
		// ... existing devices
		{
			device_id: 'NEW:DE:VI:CE:ID',
			nickname: 'My New Device'
			// ... other properties
		}
	];
}
```

The `updateMockData()` function simulates real-time changes and can be customized for specific testing scenarios.
