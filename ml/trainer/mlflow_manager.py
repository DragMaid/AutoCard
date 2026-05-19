import mlflow
import logging
from functools import wraps
from typing import Callable, TypeVar, Any
from ml.config import Config
import dagshub

F = TypeVar("F", bound=Callable[..., Any])


def if_enabled(func: F) -> F:
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if getattr(self, "enabled", False):
            return func(self, *args, **kwargs)
        return None

    return wrapper  # type: ignore


class MLFlowManager:
    """Manages MLFlow experiment tracking and UI."""

    def __init__(
        self,
        experiment_name: str = Config.EXPERIMENT_NAME,
        dagshub: bool = False,
        enabled: bool = False
    ):
        """Initializes MLFlow manager.

        Args:
            experiment_name: Experiment name.
            enabled: Whether tracking is enabled.
        """
        self.experiment_name = experiment_name
        self.dagshub = dagshub
        self.enabled = enabled

    @if_enabled
    def _setup_mlflow(self) -> None:
        """Configures MLFlow tracking URI and experiment."""
        if self.dagshub:
            dagshub.init(
                repo_owner='DragMaid', repo_name='AutoCard', mlflow=True)
        else:
            url = f"http://{Config.HOST}:{Config.PORT}"
            mlflow.set_tracking_uri(url)
            logging.info(f"MLFlow tracking URI set to {url}")
        mlflow.set_experiment(self.experiment_name)

    @if_enabled
    def start_run(self) -> None:
        """Starts MLFlow run."""
        self._setup_mlflow()
        mlflow.start_run()

    @if_enabled
    def log_metrics(self, metrics: dict, step: int) -> None:
        """Logs metrics to MLFlow.

        Args:
            metrics: Metrics dictionary.
            step: Current step.
        """
        mlflow.log_metrics(metrics, step=step)

    @if_enabled
    def log_params(self, params: dict) -> None:
        """Logs parameters to MLFlow.

        Args:
            params: Parameters dictionary.
        """
        mlflow.log_params(params)

    @if_enabled
    def log_artifact(self, path: str) -> None:
        """Logs parameters to MLFlow.

        Args:
            path: Path to artifact file.
        """
        mlflow.log_artifact(path)

    @if_enabled
    def end_run(self) -> None:
        """Ends current MLFlow run."""
        mlflow.end_run()
