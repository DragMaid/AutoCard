import torch
import torch.nn as nn
from typing import Optional, Tuple


class CardEncoder(nn.Module):
    """
    MLP-based embedding projection for individual cards.
    """

    def __init__(self, input_dim: int, embed_dim: int, hidden_dim: int = 128, dropout: float = 0.1):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, embed_dim),
            nn.ReLU()
        )

        # Stable initialization
        for m in self.mlp:
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
                nn.init.constant_(m.bias, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, num_cards, card_feature_dim)
        Returns:
            (batch, num_cards, embed_dim)
        """
        return self.mlp(x)


class SelfAttentionEncoder(nn.Module):
    """
    Lightweight transformer encoder block for card interactions.
    """

    def __init__(self, embed_dim: int, num_heads: int = 4, ff_dim: int = 256, dropout: float = 0.1):
        super().__init__()
        self.mha = nn.MultiheadAttention(
            embed_dim, num_heads, dropout=dropout, batch_first=True)
        self.norm1 = nn.LayerNorm(embed_dim)

        self.ff = nn.Sequential(
            nn.Linear(embed_dim, ff_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(ff_dim, embed_dim),
            nn.Dropout(dropout)
        )
        self.norm2 = nn.LayerNorm(embed_dim)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Args:
            x: (batch, num_cards, embed_dim)
            mask: (batch, num_cards) - True for padded positions
        Returns:
            (batch, num_cards, embed_dim)
        """
        # Multi-head self attention
        attn_out, _ = self.mha(x, x, x, key_padding_mask=mask)
        x = self.norm1(x + attn_out)  # Residual + Norm

        # Feed-forward
        ff_out = self.ff(x)
        x = self.norm2(x + ff_out)  # Residual + Norm

        return x


class AttentionPooling(nn.Module):
    """
    Aggregates card embeddings into a fixed-size vector using learned weights.
    """

    def __init__(self, embed_dim: int, hidden_dim: int = 128):
        super().__init__()
        self.scoring = nn.Sequential(
            nn.Linear(embed_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, num_cards, embed_dim)
            mask: (batch, num_cards) - True for padded positions
        Returns:
            pooled: (batch, embed_dim)
            weights: (batch, num_cards, 1)
        """
        scores = self.scoring(x)  # (batch, num_cards, 1)

        if mask is not None:
            # Masked softmax: set padded scores to -inf
            scores = scores.masked_fill(mask.unsqueeze(-1), float('-inf'))

        weights = torch.softmax(scores, dim=1)  # (batch, num_cards, 1)

        # Weighted aggregation
        pooled = torch.sum(weights * x, dim=1)  # (batch, embed_dim)

        return pooled, weights


class GameStateEncoder(nn.Module):
    """
    Orchestrates the encoding of the full game state.
    """

    def __init__(
        self,
        card_dim: int,
        player_dim: int,
        max_hand_cards: int,
        max_board_cards: int,
        embed_dim: int = 128
    ):
        super().__init__()
        self.card_dim = card_dim
        self.player_dim = player_dim
        self.max_hand_cards = max_hand_cards
        self.max_board_cards = max_board_cards
        self.embed_dim = embed_dim

        self.card_encoder = CardEncoder(card_dim, embed_dim)
        self.sa_encoder = SelfAttentionEncoder(embed_dim)
        self.pooling = AttentionPooling(embed_dim)

        # Global player features encoder
        self.player_encoder = nn.Sequential(
            nn.Linear(player_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, embed_dim),
            nn.ReLU()
        )

        # Final embedding dimension:
        # pooled_hand (embed_dim) + pooled_board (embed_dim) + player_features (embed_dim)
        self.output_dim = embed_dim * 3

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Args:
            state: (batch, total_state_dim) or (total_state_dim,)
        Returns:
            (batch, output_dim) or (output_dim,)
        """
        # Handle both 1D and 2D inputs
        is_single_state = (state.dim() == 1)
        if is_single_state:
            state = state.unsqueeze(0)

        batch_size = state.shape[0]

        # Split flat state into components
        # Order in encode_state:
        # [
        # player_feats (single_player_dim * 2),
        # hand (MAX_HAND * card_dim),
        # board (MAX_BOARD * card_dim)
        # ]

        # Player features (2 players * n features each)
        p_offset = self.player_dim
        player_feats = state[:, :p_offset]

        # Hand cards
        h_offset = p_offset + (self.max_hand_cards * self.card_dim)
        hand_cards = state[:, p_offset:h_offset].reshape(
            batch_size, self.max_hand_cards, self.card_dim)

        # Board cards
        b_offset = h_offset + (self.max_board_cards * self.card_dim)
        board_cards = state[:, h_offset:b_offset].reshape(
            batch_size, self.max_board_cards, self.card_dim)

        # Create masks based on existence bit (first bit of card encoding)
        hand_mask = (hand_cards[:, :, 0] == 0)
        board_mask = (board_cards[:, :, 0] == 0)

        # Process Hand
        h_embeds = self.card_encoder(hand_cards)
        h_sa = self.sa_encoder(h_embeds, mask=hand_mask)
        h_pooled, _ = self.pooling(h_sa, mask=hand_mask)

        # Process Board
        b_embeds = self.card_encoder(board_cards)
        b_sa = self.sa_encoder(b_embeds, mask=board_mask)
        b_pooled, _ = self.pooling(b_sa, mask=board_mask)

        # Process Player features
        p_embed = self.player_encoder(player_feats)

        # Concatenate embeddings
        out = torch.cat([h_pooled, b_pooled, p_embed], dim=-1)

        if is_single_state:
            out = out.squeeze(0)

        return out
