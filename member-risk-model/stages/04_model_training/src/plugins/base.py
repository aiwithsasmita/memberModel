"""Every algorithm is a plugin with the same interface, listed in config/models.yaml."""
from abc import ABC, abstractmethod
from typing import Any, Dict


class ModelPlugin(ABC):
    name: str = "base"

    def __init__(self, params: Dict[str, Any], seed: int):
        self.params, self.seed = params, seed

    @abstractmethod
    def fit(self, X, y, sample_weight=None, X_valid=None, y_valid=None, w_valid=None): ...

    @abstractmethod
    def predict(self, X): ...

    def get_params(self) -> Dict[str, Any]:
        return dict(self.params)

    @abstractmethod
    def log_model(self, artifact_path: str, signature=None):
        """Log with MLflow inside a start_traced_run context."""
