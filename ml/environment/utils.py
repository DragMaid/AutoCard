from typing import Any, Optional, Sequence


def safe_index(seq: Sequence[Any], idx: Optional[int]) -> Optional[Any]:
    """Safely retrieve an item from a sequence by index with bounds checking.

    Args:
        seq: The sequence to access.
        idx: The index of the item to retrieve.

    Returns:
        The item at the index, or None if the sequence is empty or index is invalid.
    """
    if not seq:
        return None
    if idx is None:
        idx = 0
    try:
        i = int(idx)
    except (TypeError, ValueError):
        i = 0
    i = max(0, min(i, len(seq) - 1))
    return seq[i]