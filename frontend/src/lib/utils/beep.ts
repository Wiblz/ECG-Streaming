/**
 * BeepGenerator - Generates audio beeps using the Web Audio API
 *
 * Features:
 * - Lazy AudioContext initialization (after user interaction)
 * - Mutable audio (can be toggled on/off)
 * - Volume control
 * - Smooth sine wave with ramping to avoid clicking sounds
 */
export class BeepGenerator {
	private audioContext: AudioContext | null = null
	private gainNode: GainNode | null = null
	private muted: boolean = false
	private volume: number = 0.3

	/**
	 * Initialize the AudioContext and gain node.
	 * Should be called after user interaction to avoid browser warnings.
	 */
	private initAudio(): void {
		if (!this.audioContext) {
			this.audioContext = new AudioContext()
			this.gainNode = this.audioContext.createGain()
			this.gainNode.connect(this.audioContext.destination)
			this.gainNode.gain.value = this.muted ? 0 : this.volume
		}
	}

	/**
	 * Play a beep sound
	 * @param frequency - Frequency in Hz (default: 800Hz)
	 * @param duration - Duration in milliseconds (default: 100ms)
	 */
	beep(frequency: number = 800, duration: number = 100): void {
		this.initAudio()
		if (!this.audioContext || !this.gainNode) return

		const oscillator = this.audioContext.createOscillator()
		const gainRamp = this.audioContext.createGain()

		oscillator.connect(gainRamp)
		gainRamp.connect(this.gainNode)

		oscillator.frequency.value = frequency
		oscillator.type = 'sine' // Smoothest sound

		// Ramp to avoid clicking sounds
		const now = this.audioContext.currentTime
		gainRamp.gain.setValueAtTime(0, now)
		gainRamp.gain.linearRampToValueAtTime(1, now + 0.01)
		gainRamp.gain.exponentialRampToValueAtTime(0.01, now + duration / 1000)

		oscillator.start(now)
		oscillator.stop(now + duration / 1000)
	}

	/**
	 * Set the volume level
	 * @param volume - Volume level (0.0 to 1.0)
	 */
	setVolume(volume: number): void {
		this.volume = Math.max(0, Math.min(1, volume))
		if (this.gainNode && !this.muted) {
			this.gainNode.gain.value = this.volume
		}
	}

	/**
	 * Mute or unmute the audio
	 * @param muted - Whether to mute the audio
	 */
	setMuted(muted: boolean): void {
		this.muted = muted
		if (this.gainNode) {
			this.gainNode.gain.value = muted ? 0 : this.volume
		}
	}

	/**
	 * Get the current muted state
	 */
	isMuted(): boolean {
		return this.muted
	}
}
