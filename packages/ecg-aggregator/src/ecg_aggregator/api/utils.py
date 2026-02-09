"""API helper utilities."""

from pydantic import BaseModel


def group_samples_by_device[SampleModelT: BaseModel](
    samples: list[dict], model: type[SampleModelT]
) -> dict[str, list[SampleModelT]]:
    """Group samples by device_id for bandwidth-efficient transmission.

    Args:
        samples: List of sample dictionaries, each containing a 'device_id' field
        model: Pydantic model to validate each sample (device_id will be removed)

    Returns:
        Dictionary mapping device_id to list of samples (with device_id removed)
    """
    devices_data: dict[str, list[SampleModelT]] = {}
    for sample in samples:
        device_id = sample["device_id"]
        if device_id not in devices_data:
            devices_data[device_id] = []
        sample_without_device_id = {k: v for k, v in sample.items() if k != "device_id"}
        devices_data[device_id].append(model.model_validate(sample_without_device_id))
    return devices_data
