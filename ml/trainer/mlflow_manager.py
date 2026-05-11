import mlflow
import logging


class MLFlowManager:
    """
    Manages MLFlow experiment tracking and UI.
    """

    def __init__(self,
                 config,
                 experiment_name: str = "training"):
        self.experiment_name = experiment_name
        self.cfg = config
        self._setup_mlflow()

    def _setup_mlflow(self):
        """Configure MLFlow tracking URI and experiment."""
        url = "http://localhost:5000"
        mlflow.set_tracking_uri(url)
        mlflow.set_experiment(self.experiment_name)
        logging.info(f"Server is running at {url}")

    def start_run(self):
        """Start MLFlow run and launch UI."""
        mlflow.start_run()

    def log_metrics(self, metrics: dict, step: int):
        """Log metrics to MLFlow."""
        mlflow.log_metrics(metrics, step=step)

    def log_params(self, params: dict):
        """Log parameters to MLFlow."""
        mlflow.log_params(params)

    def end_run(self):
        """End current MLFlow run."""
        mlflow.end_run()
