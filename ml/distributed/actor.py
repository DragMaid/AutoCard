import signal
import random
import logging
import pickle
import queue
import requests
import threading
import concurrent.futures
from tqdm import tqdm
from typing import Any
from core.data.player import Player
from core.logger import setup_logging
from ml.trainer.episode_manager import EpisodeManager
from ml.trainer.training_loop import TrainingLoop
from ml.trainer.agent import Agent
from ml.storage.batch_storage import BatchStorage
from ml.models.average_policy import AveragePolicy
from ml.models.dueling_dqn import DuelingDQN
from ml.utils import epsilon_scheduler
from ml.config import Config as ml_config

logger = logging.getLogger(__name__)


class Actor(Agent):
    """RL agent with DQN and average policy network optimized for actors."""

    def __init__(self, num_actions: int, device: str):
        self.device = device
        self._init_encoder(self.device)

        self.dqn = DuelingDQN(
            self.encoder, num_actions).to(device)
        self.policy = AveragePolicy(
            self.encoder, num_actions).to(device)

    def load_state_dict(self, state_dict: dict):
        """Loads state dict into DQN and policy networks."""
        self.dqn.load_state_dict(state_dict['dqn'])
        self.policy.load_state_dict(state_dict['policy'])
        self.encoder.load_state_dict(state_dict['encoder'])


class ActorLoop(TrainingLoop):
    def __init__(
        self,
        env_factory,
        server_url: str = "http://localhost:5000",
        password: str = "1234",
        device: str = "cpu"
    ):
        self.device = device
        self.env_factory = env_factory
        self.server_url = server_url
        self.password = password
        self.actor_id = None
        self.env = None
        self.current_weights_version = 0
        self.learner_was_connected = False

        # RL storage (with priorities)
        self.rl_batch_storage = BatchStorage(
            ml_config.MULTI_STEP, ml_config.GAMMA)
        self.sl_transitions = []

        self.param_queue = queue.Queue(maxsize=3)

        self.epsilon_scheduler = epsilon_scheduler(
            eps_start=ml_config.EPS_START,
            eps_final=ml_config.EPS_FINAL,
            eps_decay=ml_config.EPS_DECAY
        )

        self._stop_event = threading.Event()

        # Retry settings
        self.retry_base_delay = 1.0
        self.retry_max_delay = 60.0

        # Non-blocking emitter
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _register_with_server(self):
        """Registers with the server to get a unique actor_id with exponential backoff."""
        logger.info("Registering with server...")
        headers = {"X-Password": self.password}
        delay = self.retry_base_delay

        while not self._stop_event.is_set():
            try:
                response = requests.post(
                    f"{self.server_url}/register_actor", headers=headers, timeout=5)
                if response.status_code == 200:
                    self.actor_id = response.json()["actor_id"]
                    logger.info(f"Registered successfully. Actor ID: {
                                self.actor_id}")
                    break
                else:
                    logger.warning(f"Registration failed with status {
                                   response.status_code}. Retrying...")
            except Exception as e:
                logger.error(f"Registration error: {e}. Retrying...")

            self._stop_event.wait(delay + random.uniform(0, 1))
            delay = min(delay * 2, self.retry_max_delay)

    def _seed_env(self):
        """Seeds the environment and random generators based on actor_id."""
        seed = ml_config.SEED + self.actor_id
        random.seed(seed)
        import numpy as np
        np.random.seed(seed)

        # Re-create environment with the new seed if necessary
        self.env = self.env_factory()
        # If GameEnv or GameEngine supports seed, call it
        # self.env.seed(seed)
        logger.info(f"Actor {self.actor_id} initialized with seed {seed}")

    def _wait_for_learner(self):
        """Waits until the server reports that a learner is connected with backoff."""
        if not self.learner_was_connected:
            logger.info(
                f"Actor {self.actor_id}: Waiting for learner to connect...")

        headers = {"X-Password": self.password}
        delay = self.retry_base_delay

        while not self._stop_event.is_set():
            try:
                response = requests.get(
                    f"{self.server_url}/status", headers=headers, timeout=2)

                if response.status_code == 200:
                    status = response.json()
                    if status.get("learner_connected"):
                        if not self.learner_was_connected:
                            logger.info(
                                f"Actor {self.actor_id}: Learner detected.")
                        self.learner_was_connected = True
                        break
                delay = self.retry_base_delay
            except Exception as e:
                logger.error(f"Actor {self.actor_id}: Status check error: {e}")
                delay = min(delay * 2, self.retry_max_delay)

            if self._stop_event.is_set():
                break

            self._stop_event.wait(delay + random.uniform(0, 1))

    def _weight_puller(self):
        """Periodically pulls weights from the server with version checking."""
        headers = {"X-Password": self.password}
        logger.info(
            f"Actor {self.actor_id}: Background weight puller started.")

        while not self._stop_event.is_set():
            try:
                info_res = requests.get(
                    f"{self.server_url}/weights_info", headers=headers, timeout=5)

                if info_res.status_code == 200:
                    server_version = info_res.json().get("version", 0)

                    # Only fetch the new weights if its older than the current one
                    if server_version > self.current_weights_version:
                        logger.info(f"Actor {self.actor_id}: New weights version v{
                                    server_version} detected. Fetching...")

                        response = requests.get(
                            f"{self.server_url}/fetch_params", headers=headers, timeout=10)

                        if response.status_code == 200:
                            new_params = pickle.loads(response.content)
                            if not self.param_queue.full():
                                self.param_queue.put(new_params)
                            else:
                                try:
                                    self.param_queue.get_nowait()
                                    self.param_queue.put(new_params)
                                except queue.Empty:
                                    self.param_queue.put(new_params)

                            self.current_weights_version = int(
                                response.headers.get("X-Weights-Version", server_version))
                            logger.info(f"Actor {self.actor_id}: Updated to weights v{
                                        self.current_weights_version}")

                self._stop_event.wait(15)  # Success delay

            except Exception as e:
                logger.error(
                    f"Actor {self.actor_id}: Weight puller error: {e}")
                self._stop_event.wait(30)

    def run(self) -> None:
        """Executes the actor loop."""
        self._register_with_server()
        if self._stop_event.is_set():
            return

        self._seed_env()
        self._wait_for_learner()

        # Start background weight puller
        self.agent = Actor(ml_config.NUM_ACTIONS, self.device)
        self.episode_manager = EpisodeManager(2)
        puller_thread = threading.Thread(
            target=self._weight_puller, daemon=True)
        puller_thread.start()

        self.env.reset()
        logger.info(
            f"Actor {self.actor_id}: Environment reset. Starting frames.")

        for frame_idx in tqdm(range(1, ml_config.MAX_FRAMES + 1)):
            if self._stop_event.is_set():
                break

            epsilon = self.epsilon_scheduler(frame_idx)
            acting_player = self.env.get_acting_player()
            state = self.env.get_state(acting_player)

            _, done = self._execute_step(
                player=acting_player,
                state=state,
                epsilon=epsilon
            )

            # Non-blocking data emission pipeline
            self._push_data(force_flush=done)

            if done or self._episode_too_long():
                logger.debug(
                    f"Actor {self.actor_id}: Episode ended at frame {frame_idx}")
                self.episode_manager.finalize_episode()
                self.env.reset()

            # Check for local param updates
            try:
                param = self.param_queue.get(block=False)
                self.agent.load_state_dict(param)
                logger.info(
                    f"Actor {self.actor_id}: Network updated from queue.")
            except queue.Empty:
                pass

        logger.info(f"Actor {self.actor_id}: Loop finished cleanly.")

    def _execute_step(self, player: Player, state: Any, epsilon: float) -> tuple[Any, bool]:
        """Executes a single step, collecting transition data for RL and SL."""
        best_response = random.random() >= ml_config.ETA
        mask, _ = self.env.get_legal_actions(player)

        action_id, q_values = self.agent.select_action_with_mask(
            state=state,
            action_mask=mask,
            epsilon=epsilon,
            best_response=best_response
        )

        assert action_id is not None
        next_state, reward, done = self.env.step(action_id)

        q_values_np = q_values.detach().cpu().numpy()[0]
        self.rl_batch_storage.add(state, reward, action_id, done, q_values_np)

        if not best_response:
            self.sl_transitions.append((state, action_id))

        player_idx = self.env.get_player_index(player)
        self.episode_manager.add_reward(player_idx, reward)
        return next_state, done

    def _push_data(self, force_flush: bool = False):
        """Checks thresholds and submits data for emission on a background thread."""
        rl_data = None
        sl_data = None

        # Thread-safe data extraction from storages
        if force_flush or len(self.rl_batch_storage) >= ml_config.BATCH_SIZE:
            if len(self.rl_batch_storage) > 0:
                rl_data = self.rl_batch_storage.make_batch()
                self.rl_batch_storage.reset()

        if force_flush or len(self.sl_transitions) >= ml_config.BATCH_SIZE:
            if len(self.sl_transitions) > 0:
                sl_data = list(self.sl_transitions)
                self.sl_transitions.clear()

        if rl_data is not None or sl_data is not None:
            self.executor.submit(self._background_emit, rl_data, sl_data)

    def _background_emit(self, rl_data: Any = None, sl_data: Any = None):
        """Worker function for background thread to catch and log errors."""
        try:
            self._emit_state_transition(rl_data=rl_data, sl_data=sl_data)
        except Exception as e:
            logger.error(
                f"Actor {self.actor_id}: Background emission error: {e}")

    def _emit_state_transition(self, sl_data=None, rl_data=None):
        """Sends data with connection error tolerance."""
        if self._stop_event.is_set():
            return

        files = {}
        if rl_data is not None:
            files["rl_batch"] = ("rl.pkl", pickle.dumps(rl_data))
        if sl_data is not None:
            files["sl_transitions"] = ("sl.pkl", pickle.dumps(sl_data))

        headers = {
            "X-Password": self.password,
            "X-Actor-ID": str(self.actor_id)
        }

        try:
            response = requests.post(
                f"{self.server_url}/emit_data", files=files, headers=headers, timeout=5)

            if response.status_code == 200:
                learner_connected = response.headers.get(
                    "X-Learner-Connected") == "True"
                if not learner_connected:
                    if self.learner_was_connected:
                        logger.warning(
                            f"Actor {self.actor_id}: Learner disconnected. Waiting for reconnection...")
                    self.learner_was_connected = False
                    self._wait_for_learner()
                else:
                    self.learner_was_connected = True

                server_v = int(response.headers.get("X-Weights-Version", 0))
                if server_v > self.current_weights_version:
                    logger.info(f"Actor {self.actor_id}: Noticed new weights v{
                                 server_v} via emit.")
            else:
                logger.warning(f"Actor {self.actor_id}: Emission failed ({
                               response.status_code}). Waiting...")
                self.learner_was_connected = False
                self._wait_for_learner()
        except Exception as e:
            logger.error(f"Actor {self.actor_id}: Failed to emit: {
                         e}. Waiting for reconnection...")
            self.learner_was_connected = False
            self._wait_for_learner()

    def _episode_too_long(self) -> bool:
        return self.episode_manager.current_episode_length >= ml_config.MAX_ACTIONS_PER_EPISODE


if __name__ == "__main__":
    from core.logic.game_engine import GameEngine
    from ml.environment.environment import GameEnv
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--device", type=str, default="cpu")

    args = parser.parse_args()

    if args.debug:
        import os
        from datetime import datetime
        from core.logger import enable_console
        pid = os.getpid()
        timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
        filename = f"actor_{timestamp}_{pid}.log"
        filepath = ml_config.LOG_FOLDER / "actors" / filename
        setup_logging(file=filepath, level=logging.DEBUG, console=False)
        logger = enable_console(__name__)

    def create_env():
        p1 = Player(player_index=0, name="p1")
        p2 = Player(player_index=1, name="p2", is_opponent=True)
        engine = GameEngine(players=[p1, p2])
        return GameEnv(engine=engine, render=args.render)

    actor = ActorLoop(
        env_factory=create_env,
        server_url=ml_config.SERVER_URL,
        password=ml_config.AUTH_CODE,
        device=args.device
    )

    def handle_sigint(signum, frame):
        logger.info("Ctrl+C detected! Gracefully shutting down tasks...")
        actor._stop_event.set()

    # Make sure the actors don't nuke my computer
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)
    actor.run()
