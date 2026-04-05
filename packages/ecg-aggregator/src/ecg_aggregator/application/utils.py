"""Shared application-layer utilities."""

from pydantic import BaseModel


def group_samples_by_device[SampleModelT: BaseModel](
    samples: list[dict], model: type[SampleModelT]
) -> dict[str, list[SampleModelT]]:
    """Group a flat list of sample dicts by device_id, validating each into model."""
    devices_data: dict[str, list[SampleModelT]] = {}
    for sample in samples:
        device_id = sample["device_id"]
        if device_id not in devices_data:
            devices_data[device_id] = []
        sample_without_device_id = {k: v for k, v in sample.items() if k != "device_id"}
        devices_data[device_id].append(model.model_validate(sample_without_device_id))
    return devices_data
