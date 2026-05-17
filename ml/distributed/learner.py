import time
import logging
import pickle
import torch
import torch.nn.functional as F
import requests
from typing import Any
from queue import Queue, Empty

from ml.trainer.agent import Agent
from ml.storage.prioritized_replay_buffer import CustomPrioritizedReplayBuffer
from ml.storage.reservoir_buffer import ReservoirBuffer
from ml.utils import save_model

from ml.config import Config as ml_config

logger = logging.getLogger(__name__)


class Learner(Agent):
    def __init__(self, num_actions: int):
        super().__init__(num_actions)
        # Distributed-optimized buffers
        self.replay_buffer = CustomPrioritizedReplayBuffer(
            ml_config.BUFFER_SIZE, alpha=0.6)
        self.reservoir = ReservoirBuffer(ml_config.BUFFER_SIZE)

    def _update_rl_network(self, batch_data: tuple) -> tuple[torch.Tensor, Any]:
        """Updates DQN network with a provided batch."""
        states, actions, rewards, next_states, dones, weights, idxes = batch_data

        # Convert to tensors
        states = torch.FloatTensor(states).to(ml_config.DEVICE)
        next_states = torch.FloatTensor(next_states).to(ml_config.DEVICE)
        actions = torch.LongTensor(actions).to(ml_config.DEVICE)
        rewards = torch.FloatTensor(rewards).to(ml_config.DEVICE)
        dones = torch.FloatTensor(dones).to(ml_config.DEVICE)
        weights = torch.FloatTensor(weights).to(ml_config.DEVICE)

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

        states = torch.FloatTensor(states).to(ml_config.DEVICE)
        actions = torch.LongTensor(actions).to(ml_config.DEVICE)

        probs = self.policy(states)
        log_probs = probs.gather(1, actions.unsqueeze(1)).log()
        loss = -log_probs.mean()

        self.sl_optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
        self.sl_optimizer.step()

        return loss


# TODO: connect the learner to dagshub, log out the grad norm
# TODO: write a script that automatically install everything and run it
class LearnerLoop:
    def __init__(self):
        self.agent = Learner(ml_config.NUM_ACTIONS)

        self.rl_batch_queue = Queue(maxsize=100)
        self.sl_transition_queue = Queue(maxsize=100)
        self.prios_queue = Queue(maxsize=100)

    def run(self) -> None:
        """Executes the learner loop."""
        logger.info("Starting Learner Loop...")
        frame_idx = 0

        while True:
            frame_idx += 1

            try:
                # RL data is (batch, prios)
                rl_msg = self.rl_batch_queue.get_nowait()
                batch, prios = rl_msg
                for i in range(len(prios)):
                    self.agent.replay_buffer.add(
                        batch[0][i], batch[1][i], batch[2][i],
                        batch[3][i], batch[4][i], prios[i]
                    )
            except Empty:
                pass

            try:
                # SL data is a list of (state, action)
                sl_transitions = self.sl_transition_queue.get()
                for state, action in sl_transitions:
                    self.agent.reservoir.push(state, action)
            except Empty:
                pass

            if len(self.agent.replay_buffer) >= ml_config.BATCH_SIZE:
                sample = self.agent.replay_buffer.sample(
                    ml_config.BATCH_SIZE, ml_config.BETA)
                loss, (idxes, new_prios) = self.agent._update_rl_network(sample)

                # Update local priorities
                self.agent.replay_buffer.update_priorities(idxes, new_prios)

                # Queue priorities for TCP thread to send back
                if not self.prios_queue.full():
                    self.prios_queue.put((idxes, new_prios))

            if len(self.agent.reservoir) >= ml_config.BATCH_SIZE:
                self.agent._update_sl_network()

            if frame_idx % ml_config.UPDATE_TARGET_FREQ == 0:
                self.agent.update_target_network()
                logger.info(f"Target network updated at frame {frame_idx}")

            if frame_idx % ml_config.EVALUATION_INTERVAL == 0:
                self.save_checkpoint(frame_idx)

            if frame_idx % ml_config.PUSH_INTERVA == 0:
                state_dict = {
                    'dqn': self.agent.dqn.state_dict(),
                    'policy': self.agent.policy.state_dict()
                }
                self._push_to_server(state_dict)

            # Small sleep to prevent 100% CPU usage if queues are empty
            if self.rl_batch_queue.empty() and self.sl_transition_queue.empty():
                time.sleep(0.001)

    def save_checkpoint(self, frame_idx: int) -> None:
        """Evaluates current performance and saves models."""
        save_folder = ml_config.CHECKPOINT_PATH.parent
        save_path = save_folder / f"cp_{frame_idx}.pth"
        save_model(self.agent, save_path)

    def _push_to_server(self, state_dict: dict):
        """Pushes parameters to the central server."""
        try:
            data = pickle.dumps(state_dict)
            files = {'params': ('params.pkl', data)}
            headers = {"X-Password": self.password}
            requests.post(self.server_url, files=files,
                          headers=headers, timeout=5)
            logger.info("Parameters pushed to server.")
        except Exception as e:
            logger.error(f"Failed to push parameters: {e}")
