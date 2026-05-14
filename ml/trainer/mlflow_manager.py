import mlflow
import logging
from typing import Any


class MLFlowManager:
    """Manages MLFlow experiment tracking and UI."""

    def __init__(self, config: Any, experiment_name: str = "training"):
        """Initializes MLFlow manager.

        Args:
            config: Configuration object.
            experiment_name: Experiment name.
        """
        self.experiment_name = experiment_name
        self.cfg = config
        self._setup_mlflow()

    def _setup_mlflow(self) -> None:
        """Configures MLFlow tracking URI and experiment."""
        url = "http://localhost:5000"
        mlflow.set_tracking_uri(url)
        mlflow.set_experiment(self.experiment_name)
        logging.info(f"Server is running at {url}")

    def start_run(self) -> None:
        """Starts MLFlow run and launches UI."""
        mlflow.start_run()

    def log_metrics(self, metrics: dict, step: int) -> None:
        """Logs metrics to MLFlow.

        Args:
            metrics: Metrics dictionary.
            step: Current step.
        """
        mlflow.log_metrics(metrics, step=step)

    def log_params(self, params: dict) -> None:
        """Logs parameters to MLFlow.

        Args:
            params: Parameters dictionary.
        """
        mlflow.log_params(params)

    def end_run(self) -> None:
        """Ends current MLFlow run."""
        mlflow.end_run()
