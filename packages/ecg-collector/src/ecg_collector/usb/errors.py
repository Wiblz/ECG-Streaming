"""USB-specific error types."""


class UsbConfigNotReadyError(RuntimeError):
    """Raised when a USB collector exists but is not ready to send config."""
