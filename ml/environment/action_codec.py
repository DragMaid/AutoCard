from dataclasses import dataclass
import math
from typing import Dict, List, Tuple, Any


# TODO: imma consider making an enum for this
@dataclass(frozen=True)
class ActionBlock:
    """Represents a structured action type in the discrete action space.

    Attributes:
        name: The name of the action.
        dims: A list of dimensions for parameter spaces.
        param_names: A list of parameter names.
    """
    name: str
    dims: List[int]
    param_names: List[str]


class ActionCodec:
    """Action Codec to encode and decode the action inputs before passing to model."""

    # NOTE: in order to pretain action map when adding new feature, append
    # the new action block to the end of the BLOCKS list
    BLOCKS: List[ActionBlock] = [
        ActionBlock("end_turn", [], []),

        # NOTE: dimension of 1 mean that the slot will be automatically chose
        ActionBlock("summon", [10], ["monster"]),
        ActionBlock("set_trap", [10], ["trap"]),

        ActionBlock("cast_spell", [10, 21], ["spell", "target"]),

        ActionBlock("attack", [10, 11], ["attacker", "target"]),

        ActionBlock("toggle", [10], ["toggle"]),

        ActionBlock("combine", [10, 10], ["slot_1", "slot_2"]),

        ActionBlock("activate_trap", [10], ["trap"]),
    ]

    OFFSETS: List[int] = []
    BLOCK_SIZES: List[int] = []
    TOTAL_ACTIONS: int = 0

    @classmethod
    def _initialize(cls) -> None:
        """Precompute offsets and total action space size."""
        cls.OFFSETS = []
        cls.BLOCK_SIZES = []

        offset = 0
        for block in cls.BLOCKS:
            size = cls._compute_block_size(block.dims)
            cls.OFFSETS.append(offset)
            cls.BLOCK_SIZES.append(size)
            offset += size

        cls.TOTAL_ACTIONS = offset

    @staticmethod
    def _compute_block_size(dims: List[int]) -> int:
        """Compute the size of a block based on its dimensions."""
        if not dims:
            return 1
        return math.prod(dims)

    @staticmethod
    def _compute_strides(dims: List[int]) -> List[int]:
        """Compute strides for parameter indexing."""
        strides = []
        for i in range(len(dims)):
            stride = math.prod(dims[i + 1:]) if i + 1 < len(dims) else 1
            strides.append(stride)
        return strides

    @classmethod
    def encode(cls, name: str, **params: int) -> int:
        """Encode structured action into flat index.

        Args:
            name: The action name.
            **params: Action parameters.

        Returns:
            Flat integer index of the action.

        Raises:
            ValueError: If an unknown action or invalid parameters are provided.
        """
        for i, block in enumerate(cls.BLOCKS):
            if block.name != name:
                continue

            base = cls.OFFSETS[i]

            if not block.dims:
                return base

            strides = cls._compute_strides(block.dims)

            index = 0
            for dim, stride, param_name in zip(block.dims, strides, block.param_names):
                value = params[param_name]
                if value < 0 or value >= dim:
                    raise ValueError(f"Invalid param {param_name}={
                                     value} for {block.name}")
                index += value * stride

            return base + index

        raise ValueError(f"Unknown action: {name}")

    @classmethod
    def decode(cls, action_id: int) -> Tuple[str, Dict[str, Any]]:
        """Decode flat action index into structured form.

        Args:
            action_id: The flat integer action index.

        Returns:
            A tuple of (action_name, action_parameters).
        """
        for i, block in enumerate(cls.BLOCKS):
            base = cls.OFFSETS[i]
            size = cls.BLOCK_SIZES[i]

            # Determine which segment this action id belongs to
            if base <= action_id < base + size:
                offset = action_id - base

                # Handle blocks with no parameters first hand
                if not block.dims:
                    return block.name, {}

                strides = cls._compute_strides(block.dims)

                params = {}
                # Essentially Base-N decomposition
                for dim, stride, param_name in zip(block.dims, strides, block.param_names):
                    value = offset // stride
                    offset %= stride
                    params[param_name] = value

                return block.name, params

        return "end_turn", {}

    @classmethod
    def num_actions(cls) -> int:
        """Get the total number of actions in the action space."""
        return cls.TOTAL_ACTIONS


ActionCodec._initialize()
