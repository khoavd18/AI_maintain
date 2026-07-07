"""Anomaly detection primitives for predictive maintenance."""

from dataclasses import dataclass

import pandas as pd
from sklearn.ensemble import IsolationForest


@dataclass(frozen=True)
class AnomalyDetectionResult:
    """An anomaly score associated with one asset."""

    asset_id: str
    anomaly_score: float
    is_anomaly: bool


class IsolationForestAnomalyDetector:
    """Thin wrapper around scikit-learn IsolationForest."""

    def __init__(self, contamination: float = 0.05, random_state: int = 42) -> None:
        self._model = IsolationForest(contamination=contamination, random_state=random_state)

    def fit(self, features: pd.DataFrame, feature_columns: list[str]) -> "IsolationForestAnomalyDetector":
        """Fit the detector on numeric feature columns."""

        self._model.fit(features[feature_columns])
        return self

    def predict(
        self,
        features: pd.DataFrame,
        feature_columns: list[str],
        asset_id_column: str = "asset_id",
    ) -> list[AnomalyDetectionResult]:
        """Return anomaly results for each asset row."""

        predictions = self._model.predict(features[feature_columns])
        raw_scores = -self._model.decision_function(features[feature_columns])

        return [
            AnomalyDetectionResult(
                asset_id=str(asset_id),
                anomaly_score=float(score),
                is_anomaly=prediction == -1,
            )
            for asset_id, score, prediction in zip(
                features[asset_id_column], raw_scores, predictions, strict=True
            )
        ]
