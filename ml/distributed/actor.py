import logging
from core.logger import setup_logging
setup_logging(file=None, level=logging.INFO)

import random
import pickle
import queue
import requests
import time
import threading
from typing import Any
from core.data.player import Player
from ml.environment.environment import GameEnv
from core.logic.game_engine import GameEngine
from ml.trainer.episode_manager import EpisodeManager
from ml.trainer.training_loop import TrainingLoop
from ml.trainer.agent import Agent
from ml.storage.batch_storage import BatchStorage
from ml.models.average_policy import AveragePolicy
from ml.models.dueling_dqn import DuelingDQN
from ml.utils import epsilon_scheduler, set_global_seeds

from ml.config import Config as ml_config

logger = logging.getLogger(__name__)


class Actor(Agent):
    """RL agent with DQN and average policy network optimized for actors."""

    def __init__(self, num_actions: int):
        self._init_encoder()

        self.dqn = DuelingDQN(
            self.encoder, num_actions).to(ml_config.DEVICE)
        self.policy = AveragePolicy(
            self.encoder, num_actions).to(ml_config.DEVICE)

    def load_state_dict(self, state_dict: dict):
        """Loads state dict into DQN and policy networks."""
        self.dqn.load_state_dict(state_dict['dqn'])
        self.policy.load_state_dict(state_dict['policy'])


class ActorLoop(TrainingLoop):
    def __init__(
        self,
        env: GameEnv,
        server_url: str = "http://localhost:5000",
        password: str = "1234"
    ):
        self.env = env
        self.agent = Actor(ml_config.NUM_ACTIONS)
        self.episode_manager = EpisodeManager(2)
        self.server_url = server_url
        self.password = password

        # RL storage (with priorities), different from the ReplayBuffer
        # as this one simply save in order to be emitted later to the learner
        # NOTE: If we toggle best_response per step, n-step logic in
        # BatchStorage might be affected if we skip steps.
        self.rl_batch_storage = BatchStorage(
            ml_config.MULTI_STEP, ml_config.GAMMA)
        self.sl_transitions = []

        self.param_queue = queue.Queue(maxsize=3)

        # TODO: forgot to save the weights for attention encoder
        self.epsilon_scheduler = epsilon_scheduler(
            eps_start=ml_config.EPS_START,
            eps_final=ml_config.EPS_FINAL,
            eps_decay=ml_config.EPS_DECAY
        )

        self._stop_event = threading.Event()

    def _wait_for_learner(self):
        """Waits until the server reports that a learner is connected."""
        logger.info("Waiting for learner to connect to server...")
        headers = {"X-Password": self.password}
        while not self._stop_event.is_set():
            try:
                response = requests.get(
                    f"{self.server_url}/status", headers=headers, timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    if status.get("learner_connected"):
                        logger.info("Learner detected. Starting actor loop.")
                        break
                else:
                    logger.warning(f"Server status check failed: {
                                   response.status_code}")
            except Exception as e:
                logger.error(f"Error checking server status: {e}")

            time.sleep(2)

    def _weight_puller(self):
        """Periodically pulls weights from the server in a background thread."""
        headers = {"X-Password": self.password}
        logger.info("Background weight puller started.")
        while not self._stop_event.is_set():
            try:
                response = requests.get(
                    f"{self.server_url}/fetch_params", headers=headers, timeout=10)
                if response.status_code == 200:
                    new_params = pickle.loads(response.content)
                    if not self.param_queue.full():
                        self.param_queue.put(new_params)
                    else:
                        # Clear old and put new
                        try:
                            self.param_queue.get_nowait()
                            self.param_queue.put(new_params)
                        except queue.Empty:
                            self.param_queue.put(new_params)
                    logger.debug("Successfully pulled new weights.")
                elif response.status_code != 404:
                    logger.warning(f"Failed to pull weights: {
                                   response.status_code}")
            except Exception as e:
                logger.error(f"Weight puller error: {e}")

            # Pull every UPDATE_INTERVAL steps equivalent or fixed time?
            # Using fixed time (e.g. 10 seconds) for simplicity, or can be tied to config
            time.sleep(15)

    def run(self) -> None:
        """Executes the actor loop."""
        self._wait_for_learner()

        # Start background weight puller
        puller_thread = threading.Thread(
            target=self._weight_puller, daemon=True)
        puller_thread.start()

        self.env.reset()

        for frame_idx in range(1, ml_config.MAX_FRAMES + 1):
            if self._stop_event.is_set():
                logger.info("Stop event set. Terminating actor loop.")
                break

            epsilon = self.epsilon_scheduler(frame_idx)
            acting_player = self.env.get_acting_player()
            state = self.env.get_state(acting_player)

            _, done = self._execute_step(
                player=acting_player,
                state=state,
                epsilon=epsilon
            )

            if done or self._episode_too_long():
                logger.info(f"Episode ended at frame {frame_idx}")
                self.episode_manager.finalize_episode()
                self.env.reset()

            # Emit RL data (DQN)
            if len(self.rl_batch_storage) >= ml_config.BATCH_SIZE:
                batch, prios = self.rl_batch_storage.make_batch()
                self.rl_batch_storage.reset()
                self._emit_state_transition(rl_data=(batch, prios))

            # Emit SL data (Average Policy)
            if len(self.sl_transitions) >= ml_config.BATCH_SIZE:
                sl_data = list(self.sl_transitions)
                self.sl_transitions.clear()
                self._emit_state_transition(sl_data=sl_data)

            # Check for local param updates (populated by background thread)
            try:
                param = self.param_queue.get(block=False)
                self.agent.load_state_dict(param)
                logger.info("Network parameters updated from pulled weights.")
            except queue.Empty:
                pass

            # Periodically retrieve transitions from server (if requested)
            if frame_idx % 500 == 0:
                self._retrieve_transitions()

    def _execute_step(self, player: Player, state: Any, epsilon: float) -> tuple[Any, bool]:
        """Executes a single step, collecting transition data for RL and SL."""
        best_response = random.random() >= ml_config.ETA
        mask, _ = self.env.get_legal_actions(player)

        # q_values will be the DQN output if best_response=True, or Policy probs if False
        action_id, q_values = self.agent.select_action_with_mask(
            state=state,
            action_mask=mask,
            epsilon=epsilon,
            best_response=best_response
        )

        assert action_id is not None
        next_state, reward, done = self.env.step(action_id)

        # Convert to numpy array before hand
        q_values_np = q_values.detach().cpu().numpy()[0]
        import numpy as np
        if not np.isfinite(q_values_np).all():
            raise

        self.rl_batch_storage.add(
            state, reward, action_id, done, q_values_np)

        if not best_response:
            self.sl_transitions.append((state, action_id))

        if done:
            self._record_winner()

        player_idx = self.env.get_player_index(player)
        self.episode_manager.add_reward(player_idx, reward)
        return next_state, done

    def _emit_state_transition(self, sl_data=None, rl_data=None):
        """Sends data to the centralized server via HTTP."""
        files = {}

        if rl_data is not None:
            files["rl_batch"] = ("rl.pkl", pickle.dumps(rl_data))

        if sl_data is not None:
            files["sl_batch"] = ("sl.pkl", pickle.dumps(sl_data))

        headers = {"X-Password": self.password}

        try:
            response = requests.post(
                f"{self.server_url}/emit_data", files=files, headers=headers, timeout=10)

            if response.status_code == 200:
                learner_connected = response.headers.get("X-Learner-Connected") == "True"
                if not learner_connected:
                    logger.warning("Learner disconnected. Stopping actor.")
                    self._stop_event.set()

                if response.headers.get('Content-Type') == 'application/octet-stream':
                    new_params = pickle.loads(response.content)
                    self.agent.load_state_dict(new_params)
                    logger.info("Parameters updated from server response.")

            else:
                logger.warning(f"Server error during emission: {
                               response.status_code}")

        except Exception as e:
            logger.error(f"Failed to emit data: {e}")

    def _retrieve_transitions(self):
        """Retrieves transitions from the server."""
        headers = {"X-Password": self.password}
        try:
            response = requests.get(
                f"{self.server_url}/get_data", headers=headers, timeout=5)
            if response.status_code == 200:
                data = pickle.loads(response.content)
                logger.info(f"Retrieved transitions from server: {
                            list(data.keys())}")
                return data
        except Exception as e:
            logger.error(f"Failed to retrieve transitions: {e}")
        return None

    def _episode_too_long(self) -> bool:
        return self.episode_manager.current_episode_length >= ml_config.MAX_ACTIONS_PER_EPISODE


if __name__ == "__main__":
    def new_players():
        p1 = Player(player_index=0, name="p1")
        p2 = Player(player_index=1, name="p2", is_opponent=True)
        return p1, p2
    # TODO: set the seed based on the actor id
    set_global_seeds(42)
    engine = GameEngine(players=new_players())
    # TODO: set args for this later
    env = GameEnv(engine=engine, render=False)
    actor = ActorLoop(env=env)
    actor.run()
