from ml.config import Config as ml_config
from ml.utils import save_model
from ml.storage.reservoir_buffer import ReservoirBuffer
from ml.storage.prioritized_replay_buffer import CustomPrioritizedReplayBuffer
from ml.trainer.agent import Agent
import numpy as np
import websocket
from queue import Queue, Empty
from typing import Any
import threading
import requests
import torch.nn.functional as F
import torch
import pickle
import time
import logging
from core.logger import setup_logging

setup_logging(file="train.log", level=logging.INFO)
logger = logging.getLogger(__name__)


class Learner(Agent):
    def __init__(self, num_actions: int):
        super().__init__(num_actions)
        # Distributed-optimized buffers
        self.replay_buffer = CustomPrioritizedReplayBuffer(
            ml_config.BUFFER_SIZE, alpha=ml_config.ALPHA)
        self.reservoir = ReservoirBuffer(ml_config.BUFFER_SIZE)

    def _update_rl_network(self, batch_data: tuple) -> tuple[torch.Tensor, Any]:
        """Updates DQN network with a provided batch."""
        states, actions, rewards, next_states, dones, weights, idxes = batch_data

        # Convert to tensors
        states = torch.FloatTensor(np.array(states)).to(self.device)
        next_states = torch.FloatTensor(
            np.array(next_states)).to(self.device)
        actions = torch.LongTensor(actions).to(self.device)
        rewards = torch.FloatTensor(rewards).to(self.device)
        dones = torch.FloatTensor(dones).to(self.device)
        weights = torch.FloatTensor(weights).to(self.device)

        # Compute loss
        q_values = self.dqn(states)
        next_q_values = self.dqn(next_states)

        current_q = q_values.gather(1, actions.unsqueeze(1)).squeeze(1)

        # Double DQN logic
        with torch.no_grad():
            next_actions = next_q_values.max(1)[1].unsqueeze(1)
            target_next_q_values = self.target_dqn(next_states)
            next_q_a_values = target_next_q_values.gather(
                1, next_actions).squeeze(1)

        discount_factor = ml_config.GAMMA ** ml_config.MULTI_STEP
        expected_q = rewards + discount_factor * next_q_a_values * (1 - dones)

        # TD Error and Priority Update
        td_error = expected_q - current_q
        loss = (F.smooth_l1_loss(current_q, expected_q,
                reduction='none') * weights).mean()

        # Optimize
        self.rl_optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.dqn.parameters(), max_norm=1.0)
        self.rl_optimizer.step()

        # Return new priorities
        new_prios = torch.abs(td_error).detach().cpu().numpy() + 1e-6
        return loss, (idxes, new_prios)

    def _update_sl_network(self) -> torch.Tensor:
        """Updates average policy network from reservoir."""
        if len(self.reservoir) < ml_config.BATCH_SIZE:
            return None

        states, actions = self.reservoir.sample(ml_config.BATCH_SIZE)

        states = torch.FloatTensor(states).to(self.device)
        actions = torch.LongTensor(actions).to(self.device)

        probs = self.policy(states)
        log_probs = probs.gather(1, actions.unsqueeze(1)).log()
        loss = -log_probs.mean()

        self.sl_optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
        self.sl_optimizer.step()

        return loss


class LearnerLoop:
    def __init__(
        self,
        server_url: str = "http://localhost:5000",
        password: str = "1234"
    ):
        self.agent = Learner(ml_config.NUM_ACTIONS)
        self.server_url = server_url
        self.ws_url = server_url.replace("http", "ws") + "/learner_stream"
        self.password = password

        self.rl_batch_queue = Queue(maxsize=100)
        self.sl_transition_queue = Queue(maxsize=100)
        self.prios_queue = Queue(maxsize=100)

        self._stop_event = threading.Event()

        self.current_loss = 0.0

    def _data_receiver(self):
        """WebSocket client to receive data from server constantly with retry logic."""
        ws_url_with_token = f"{self.ws_url}?token={self.password}"
        logger.info(f"Connecting to data stream at {self.ws_url}")

        def on_message(ws, message):
            try:
                data = pickle.loads(message)
                if "rl_batch" in data:
                    self.rl_batch_queue.put(data["rl_batch"])
                    logger.debug("Received RL batch via WebSocket.")
                if "sl_transitions" in data:
                    self.sl_transition_queue.put(data["sl_transitions"])
                    logger.debug("Received SL transitions via WebSocket.")
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")

        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")

        def on_open(ws):
            logger.info("WebSocket connection established.")

        while not self._stop_event.is_set():
            try:
                ws = websocket.WebSocketApp(
                    ws_url_with_token,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open
                )
                ws.run_forever()
            except Exception as e:
                logger.error(f"WebSocket loop crash: {e}")

            if not self._stop_event.is_set():
                logger.info("Retrying WebSocket connection in 5 seconds...")
                time.sleep(5)

    def run(self) -> None:
        """Executes the learner loop."""
        # Start background data receiver
        receiver_thread = threading.Thread(
            target=self._data_receiver, daemon=True)
        receiver_thread.start()

        logger.info("Starting Learner Loop...")

        step = 1
        frame_idx = 1

        while True:
            frame_idx += 1
            self.insert_transition()

            if len(self.agent.replay_buffer) >= ml_config.SAMPLE_THRESHOLD:
                # Only increment when its actually sampling
                step += 1
                sample = self.agent.replay_buffer.sample(
                    ml_config.BATCH_SIZE, ml_config.BETA)
                loss, (idxes, new_prios) = self.agent._update_rl_network(sample)
                self.current_loss = loss.item()

                # Update local priorities
                self.agent.replay_buffer.update_priorities(idxes, new_prios)

                if step % 100 == 0:
                    logger.info(f"Learner: Step {step}, Loss {
                                self.current_loss:.4f}")

            if len(self.agent.reservoir) >= ml_config.BATCH_SIZE:
                self.agent._update_sl_network()

            if step % ml_config.UPDATE_TARGET_FREQ == 0:
                self.agent.update_target_network()
                logger.info(f"Target network updated at step {step}")

            if step % ml_config.EVALUATION_INTERVAL == 0:
                self.save_checkpoint(step)

            if step % ml_config.PUSH_INTERVAL == 0:
                state_dict = {
                    'dqn': self.agent.dqn.state_dict(),
                    'policy': self.agent.policy.state_dict(),
                    'encoder': self.agent.encoder.state_dict()
                }
                self._push_weights(state_dict)

            if frame_idx % ml_config.METRICS_INTERVAL == 0:
                metrics = {
                    "frame": step,
                    "loss": self.current_loss,
                    "replay_buffer": len(self.agent.replay_buffer),
                    "reservoir": len(self.agent.reservoir)
                }
                self._push_metrics(metrics)

            # Small sleep to prevent 100% CPU usage if queues are empty
            if self.rl_batch_queue.empty() and self.sl_transition_queue.empty():
                time.sleep(0.001)

    def insert_transition(self):
        # Process RL data from queue
        try:
            rl_msg = self.rl_batch_queue.get(timeout=0.01)
            batch, prios = rl_msg
            states, actions, rewards, next_states, dones = batch
            for sample in zip(states, actions, rewards, next_states, dones, prios):
                self.agent.replay_buffer.add(*sample)
        except Empty:
            pass

        # Process SL data from queue
        try:
            sl_transitions = self.sl_transition_queue.get(timeout=0.01)
            for state, action in sl_transitions:
                self.agent.reservoir.push(state, action)
        except Empty:
            pass

    def save_checkpoint(self, frame_idx: int) -> None:
        """Evaluates current performance and saves models."""
        save_folder = ml_config.CHECKPOINT_PATH.parent
        save_path = save_folder / f"cp_{frame_idx}.pth"
        save_model(self.agent, save_path)
        logger.info(f"Checkpoint saved: {save_path}")

    def _push_weights(self, state_dict: dict):
        """Pushes parameters to the central server."""
        headers = {
            "X-Password": self.password,
        }
        try:
            data = pickle.dumps(state_dict)
            files = {'params': ('params.pkl', data)}
            response = requests.post(f"{self.server_url}/push_params", files=files,
                                     headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info("Successfully pushed model parameters to server.")
            else:
                logger.warning(f"Failed to push parameters: Server returned {
                               response.status_code}")
        except Exception as e:
            logger.error(f"Failed to push parameters: {e}")

    def _push_metrics(self, metrics: dict):
        """Pushes training metrics to the central server."""
        headers = {
            "X-Password": self.password,
        }
        try:
            response = requests.post(f"{self.server_url}/update_metrics", json=metrics,
                                     headers=headers, timeout=5)
            if response.status_code != 200:
                logger.warning(f"Failed to push metrics: Server returned {
                               response.status_code}")
        except Exception as e:
            logger.error(f"Failed to push metrics: {e}")


if __name__ == "__main__":
    learner = LearnerLoop(
        server_url=ml_config.SERVER_URL,
        password=ml_config.PASSWORD
    )
    learner.run()
