"""Small synthetic datasets for demos and notebooks."""

import pandas as pd

from src.data_generation.generate_data import generate_dataset


def generate_sample_assets() -> pd.DataFrame:
    """Return a tiny asset inventory suitable for local demos."""

    return generate_dataset(asset_count=6, days=2, seed=42)["assets"]


def generate_sample_sensor_readings() -> pd.DataFrame:
    """Return sample sensor readings with one intentionally elevated value."""

    return generate_dataset(asset_count=6, days=2, seed=42)["sensor_readings"]
