using AutoCard.Server.SocketIO;

namespace AutoCard.Server.Rooms;

/// <summary>
/// One position at a room's table.
/// </summary>
/// <remarks>
/// A seat outlives the socket sitting in it. That is what makes a reconnect
/// cheap: the engine still holds the state, so the returning player only needs
/// its old <see cref="PlayerId"/> back plus a fresh snapshot.
/// </remarks>
/// <param name="index">Seat index; 0 is the engine's canonical board frame.</param>
/// <param name="playerId">The engine's id for this seat's player.</param>
/// <param name="isAi">True when the AI module drives this seat and no client may claim it.</param>
public sealed class Seat(int index, string playerId, bool isAi)
{
    /// <summary>Seat index, which the client uses to decide board orientation.</summary>
    public int Index { get; } = index;

    /// <summary>The engine's player id for this seat.</summary>
    public string PlayerId { get; } = playerId;

    /// <summary>True when this seat belongs to the AI rather than a client.</summary>
    public bool IsAi { get; } = isAi;

    /// <summary>The client currently occupying the seat, if any.</summary>
    public SocketIoConnection? Connection { get; set; }

    /// <summary>Display name of the last client to occupy the seat.</summary>
    public string? PlayerName { get; set; }

    /// <summary>When the seat was last vacated, or null if it is occupied or never used.</summary>
    public DateTimeOffset? VacatedAt { get; set; }

    /// <summary>True when a client is connected right now.</summary>
    public bool IsOccupied => Connection is not null;

    /// <summary>
    /// Whether a joining client may take this seat.
    /// </summary>
    /// <param name="claimedPlayerId">Player id the client presented, if it is reconnecting.</param>
    /// <param name="grace">How long a vacated seat is held for its previous occupant.</param>
    /// <param name="now">Current time.</param>
    /// <returns>True when the seat is free to claim.</returns>
    public bool IsClaimableBy(string? claimedPlayerId, TimeSpan grace, DateTimeOffset now)
    {
        if (IsAi || IsOccupied)
        {
            return false;
        }

        // The previous occupant always gets its own seat back.
        if (claimedPlayerId is not null && claimedPlayerId == PlayerId)
        {
            return true;
        }

        // Otherwise the seat is only up for grabs once its grace period lapsed.
        return VacatedAt is null || now - VacatedAt.Value > grace;
    }
}
