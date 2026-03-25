from __future__ import annotations

import pandas as pd

from core.data_loader import load_external_data_sources


def list_external_sources() -> pd.DataFrame:
    return load_external_data_sources().copy()


def list_sources_for_dataset(dataset: str) -> pd.DataFrame:
    df = load_external_data_sources().copy()
    return df[df["dataset"] == dataset].reset_index(drop=True)
