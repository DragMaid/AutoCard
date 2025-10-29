from pathlib import Path
import math
import random
import datetime

import torch
import numpy as np
import mlflow


def update_target(current_model, target_model):
    """Copy weights from current_model to target_model."""
    target_model.load_state_dict(current_model.state_dict())


def epsilon_scheduler(eps_start=1.0, eps_final=0.01, eps_decay=50000):
    """Return a function to get epsilon at a given frame index."""
    def function(frame_idx):
        return eps_final + (eps_start - eps_final) \
            * math.exp(-1. * frame_idx / eps_decay)
    return function


def log_training_metrics(frame_idx,
                         max_frames,
                         rewards,
                         lengths,
                         rl_losses,
                         sl_losses,
                         wins,
                         update_freq,
                         duration,
                         logging):
    def mean_safe(x):
        return np.mean(x) if len(x) > 0 else 0.0

    # Compute metrics
    p1_avg_reward = mean_safe(rewards[0])
    p2_avg_reward = mean_safe(rewards[1])
    avg_length = mean_safe(lengths)
    p1_rl, p2_rl = map(mean_safe, rl_losses)
    p1_sl, p2_sl = map(mean_safe, sl_losses)
    p1_wins, p2_wins = wins
    total_wins = max(p1_wins + p2_wins, 1)
    fps = int(update_freq/duration)
    time_left = datetime.timedelta(seconds=int((max_frames-frame_idx)/fps))

    # Console logging
    logging.info(
        f"[Frame {frame_idx}] \n | "
        f"Len={avg_length:.1f} \n | "
        f"Progress={frame_idx/max_frames*100:.2f}% \n | "
        f"FPS={fps} \n | "
        f"Expected time={str(time_left)} \n | "
        f"P1 RL={p1_rl:.4f}, SL={p1_sl:.4f} \n | "
        f"P2 RL={p2_rl:.4f}, SL={p2_sl:.4f} \n | "
        f"P1 Avg R={p1_avg_reward:.2f} \n | "
        f"P2 Avg R={p2_avg_reward:.2f} \n | "
        f"P1 wins={p1_wins} ({p1_wins / total_wins:.2f}) \n | "
        f"P2 wins={p2_wins} ({p2_wins / total_wins:.2f})"
    )

    # MLflow logging
    mlflow.log_metric("P1/Reward/Average", p1_avg_reward, step=frame_idx)
    mlflow.log_metric("P2/Reward/Average", p2_avg_reward, step=frame_idx)
    mlflow.log_metric("Episode/Length", avg_length, step=frame_idx)
    mlflow.log_metric("P1/RL_Loss", p1_rl, step=frame_idx)
    mlflow.log_metric("P1/SL_Loss", p1_sl, step=frame_idx)
    mlflow.log_metric("P2/RL_Loss", p2_rl, step=frame_idx)
    mlflow.log_metric("P2/SL_Loss", p2_sl, step=frame_idx)
    mlflow.log_metric("P1/Wins", p1_wins, step=frame_idx)
    mlflow.log_metric("P2/Wins", p2_wins, step=frame_idx)
    mlflow.log_metric("P1/WinRate", p1_wins / total_wins, step=frame_idx)
    mlflow.log_metric("P2/WinRate", p2_wins / total_wins, step=frame_idx)

    # Reset buffers for next interval
    for buf in [*rewards, *rl_losses, *sl_losses, lengths]:
        buf.clear()


def set_global_seeds(seed=42):
    """Set seeds for reproducibility."""
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)


def hard_update(target, source):
    for t, s in zip(target.parameters(), source.parameters()):
        t.data.copy_(s.data)


def soft_update(target, source, tau):
    for t, s in zip(target.parameters(), source.parameters()):
        t.data.copy_(t.data * (1.0 - tau) + s.data * tau)


def pdqn_select_action_safe(pdqn,
                            env,
                            player_state,
                            action_name,
                            legal_params,
                            epsilon=0.0,
                            train=True):
    """
    Wrapper to select a discrete action and valid parameters safely.

    pdqn: your PDQN model
    env: GameEnv
    player_state: numpy array (state_dim,)
    action_name: string, one of env.ACTIONS
    legal_params: dict from _get_legal_actions for this action
    """
    discrete_idx = env.ACTIONS.index(action_name)
    param_dim = pdqn.param_dim

    # get PDQN raw parameter
    _, raw_params = pdqn.select_action(
        player_state, epsilon=epsilon, train=train)
    # assuming Gaussian outputs in [-1,1], scale if needed
    raw_params = np.clip(raw_params, 0.0, 1.0)

    if action_name == "combine":
        # legal pairs: list of tuples [(i,j), ...]
        pairs = legal_params.get("combine", {}).get("pairs", [])
        if not pairs:
            return discrete_idx, None  # fallback, no legal combine
        # scale raw_params[0:2] to indices range (0..1 -> min-max indices)
        raw_scaled = raw_params[:2] * len(pairs)
        raw_scaled = np.clip(raw_scaled, 0, len(pairs)-1)
        # pick nearest legal pair
        pair_idx = int(round(raw_scaled[0]))
        pair_idx = min(pair_idx, len(pairs)-1)
        selected_param = pairs[pair_idx]
        return discrete_idx, np.array(selected_param)

    else:
        # other actions: just return raw_params clipped to legal dimension
        return discrete_idx, raw_params[:param_dim]


def flatten_action_params(action_params, param_dim=2):
    """
    Convert structured dict of parameters to a flat numeric vector.
    Example:
        {"target_idx": 1, "card_idx": 2} -> np.array([1, 2])
    """
    if isinstance(action_params, dict):
        flat = []
        for v in action_params.values():
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            elif isinstance(v, (int, float)):
                flat.append(v)
            # ignore non-numeric or complex values
        # pad / truncate to param_dim
        flat = (flat + [0.0] * param_dim)[:param_dim]
        return np.array(flat, dtype=np.float32)
    elif isinstance(action_params, (list, np.ndarray)):
        flat = np.array(action_params, dtype=np.float32)
        if flat.shape[0] < param_dim:
            flat = np.pad(flat, (0, param_dim - flat.shape[0]))
        return flat[:param_dim]
    else:
        # fallback — empty vector
        return np.zeros(param_dim, dtype=np.float32)


def save_model(logging, models, policies, checkpoint_path):
    """
    Save all models to a single checkpoint file.

    Args:
        logging: Logger instance
        models: Dict with keys like 'agent_0', 'agent_1', etc.
        policies: Dict with keys like 'agent_0', 'agent_1', etc.
        checkpoint_path: Path object or string to checkpoint file (e.g., 'checkpoints/checkpoint.pth')
    """
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Build checkpoint dict with proper naming
    checkpoint = {}

    # Save models with format: agent_0_model, agent_1_model, etc.
    for key, model in models.items():
        checkpoint[f"{key}_model"] = model.state_dict()

    # Save policies with format: agent_0_policy, agent_1_policy, etc.
    for key, policy in policies.items():
        if policy is not None:  # Handle case where policy might be None
            checkpoint[f"{key}_policy"] = policy.state_dict()

    torch.save(checkpoint, checkpoint_path)
    logging.info(f"Models saved to {checkpoint_path}")


def load_model(logging, models, policies, device="cpu", checkpoint_path=None):
    """
    Load all models from a single checkpoint file.

    Args:
        logging: Logger instance
        models: Dict with keys like 'agent_0', 'agent_1', etc.
        policies: Dict with keys like 'agent_0', 'agent_1', etc.
        device: Device to load models to
        checkpoint_path: Path to checkpoint file
    """
    if checkpoint_path is None:
        checkpoint_path = Path("saves/checkpoint.pth")
    else:
        checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.exists():
        raise ValueError(f"No model found at {checkpoint_path}")

    # Load checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device)

    # Load models
    for key, model in models.items():
        model_key = f"{key}_model"
        if model_key in checkpoint:
            model.load_state_dict(checkpoint[model_key])
            logging.info(f"Loaded {model_key}")
        else:
            logging.warning(f"Model key '{model_key}' not found in checkpoint")

    # Load policies
    for key, policy in policies.items():
        if policy is None:
            continue

        policy_key = f"{key}_policy"
        if policy_key in checkpoint:
            policy.load_state_dict(checkpoint[policy_key])
            logging.info(f"Loaded {policy_key}")
        else:
            logging.warning(
                f"Policy key '{policy_key}' not found in checkpoint")

    logging.info(f"Models loaded from {checkpoint_path}")


def load_single_agent(logging, agent_id: int, dqn_model, policy_model=None,
                      device="cpu", checkpoint_path=None):
    """
    Load a single agent from checkpoint file.

    This is useful for loading one agent to play against.

    Args:
        logging: Logger instance
        agent_id: Which agent to load (0, 1, etc.)
        dqn_model: The DQN model to load weights into
        policy_model: Optional policy model (for PDQN)
        device: Device to load to
        checkpoint_path: Path to checkpoint file

    Returns:
        True if successful, False otherwise
    """
    if checkpoint_path is None:
        checkpoint_path = Path("saves/checkpoint.pth")
    else:
        checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.exists():
        logging.error(f"No model found at {checkpoint_path}")
        return False

    # Load checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device)

    # Load DQN
    model_key = f"agent_{agent_id}_model"
    if model_key in checkpoint:
        dqn_model.load_state_dict(checkpoint[model_key])
        logging.info(f"Loaded {model_key} from {checkpoint_path}")
    else:
        logging.error(f"Model key '{model_key}' not found in checkpoint")
        return False

    # Load policy if provided
    if policy_model is not None:
        policy_key = f"agent_{agent_id}_policy"
        if policy_key in checkpoint:
            policy_model.load_state_dict(checkpoint[policy_key])
            logging.info(f"Loaded {policy_key} from {checkpoint_path}")
        else:
            logging.warning(
                f"Policy key '{policy_key}' not found in checkpoint")

    return True


def load_model_legacy(logging, models, policies, device="cpu", checkpoint_path=None):
    """
    Load models from legacy checkpoint format (p1/p2 naming).

    This function maintains backward compatibility with old checkpoints
    that used 'p1' and 'p2' naming convention.

    Args:
        logging: Logger instance
        models: Dict with keys like 'agent_0', 'agent_1'
        policies: Dict with keys like 'agent_0', 'agent_1'
        device: Device to load models to
        checkpoint_path: Optional custom path, defaults to saves/checkpoint.pth
    """
    if checkpoint_path is None:
        checkpoint_path = Path("saves/checkpoint.pth")
    else:
        checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.exists():
        raise ValueError(f"No model found at {checkpoint_path}")

    # Load checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device)

    # Map legacy keys to new keys
    legacy_to_new = {
        'p1': 'agent_0',
        'p2': 'agent_1',
    }

    # Load models with legacy mapping
    for legacy_key, new_key in legacy_to_new.items():
        model_key = f"{legacy_key}_model"
        if model_key in checkpoint and new_key in models:
            models[new_key].load_state_dict(checkpoint[model_key])
            logging.info(f"Loaded {model_key} -> {new_key}")

        policy_key = f"{legacy_key}_policy"
        if policy_key in checkpoint and new_key in policies:
            if policies[new_key] is not None:
                policies[new_key].load_state_dict(checkpoint[policy_key])
                logging.info(f"Loaded {policy_key} -> {new_key}")

    logging.info(f"Models loaded from {checkpoint_path} (legacy format)")


def detect_and_load_model(logging, models, policies, device="cpu", checkpoint_path=None):
    """
    Automatically detect checkpoint format and load accordingly.

    Tries new format first, falls back to legacy format if needed.

    Args:
        logging: Logger instance
        models: Dict with keys like 'agent_0', 'agent_1'
        policies: Dict with keys like 'agent_0', 'agent_1'
        device: Device to load models to
        checkpoint_path: Optional custom path
    """
    if checkpoint_path is None:
        checkpoint_path = Path("saves/checkpoint.pth")
    else:
        checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.exists():
        raise ValueError(f"No model found at {checkpoint_path}")

    # Load checkpoint to inspect format
    checkpoint = torch.load(checkpoint_path, map_location=device)

    # Detect format by checking keys
    has_new_format = any('agent_' in key for key in checkpoint.keys())
    has_legacy_format = any(key.startswith('p1') or key.startswith('p2')
                            for key in checkpoint.keys())

    if has_new_format:
        load_model(logging, models, policies, device, checkpoint_path)
    elif has_legacy_format:
        logging.info("Detected legacy checkpoint format, converting...")
        load_model_legacy(logging, models, policies, device, checkpoint_path)
    else:
        raise ValueError(f"Unknown checkpoint format in {checkpoint_path}")


def get_checkpoint_info(checkpoint_path):
    """
    Get information about what's in a checkpoint file.

    Args:
        checkpoint_path: Path to checkpoint file

    Returns:
        Dict with info about the checkpoint
    """
    checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.exists():
        return {"exists": False, "error": f"File not found: {checkpoint_path}"}

    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu")

        info = {
            "exists": True,
            "path": str(checkpoint_path),
            "keys": list(checkpoint.keys()),
            "agents": [],
            "has_policies": []
        }

        # Detect agents
        for key in checkpoint.keys():
            if "_model" in key:
                agent_name = key.replace("_model", "")
                info["agents"].append(agent_name)

                # Check if has policy
                policy_key = f"{agent_name}_policy"
                info["has_policies"].append(policy_key in checkpoint)

        return info

    except Exception as e:
        return {"exists": True, "error": str(e)}


# Example usage functions

def save_training_checkpoint(trainer, checkpoint_path="checkpoints/checkpoint.pth"):
    """
    Convenience function to save all agents from trainer.

    Args:
        trainer: Trainer instance with agents
        checkpoint_path: Where to save
    """
    import logging

    models = {f"agent_{i}": agent.dqn for i,
              agent in enumerate(trainer.agents)}
    policies = {f"agent_{i}": agent.policy for i,
                agent in enumerate(trainer.agents)}

    save_model(logging, models, policies, Path(checkpoint_path))


def load_training_checkpoint(trainer, checkpoint_path="checkpoints/checkpoint.pth"):
    """
    Convenience function to load all agents into trainer.

    Args:
        trainer: Trainer instance with agents
        checkpoint_path: Where to load from
    """
    import logging

    models = {f"agent_{i}": agent.dqn for i,
              agent in enumerate(trainer.agents)}
    policies = {f"agent_{i}": agent.policy for i,
                agent in enumerate(trainer.agents)}

    detect_and_load_model(
        logging, models, policies,
        device=trainer.cfg.DEVICE,
        checkpoint_path=Path(checkpoint_path)
    )
