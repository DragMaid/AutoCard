using System.Text.Json.Nodes;

using AutoCard.Server.Engine;
using AutoCard.Server.Protocol;
using AutoCard.Server.SocketIO;

namespace AutoCard.Server.Rooms;

/// <summary>Whether a room seats two people or one person and the AI module.</summary>
public static class RoomMode
{
    /// <summary>Two human seats.</summary>
    public const string Pvp = "pvp";

    /// <summary>One human seat; the other is driven by the trained agent.</summary>
    public const string Ai = "ai";
}

/// <summary>
/// One live match: its seats, its engine connection, and nothing about the rules.
/// </summary>
/// <remarks>
/// Mutating operations run under <see cref="EnterAsync"/> so that two clients
/// joining at the same instant cannot be handed the same seat. Broadcasting is
/// deliberately outside that lock: it only touches per-connection send channels.
/// </remarks>
public sealed class Room : IAsyncDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);

    /// <summary>Room code, as normalized by the registry.</summary>
    public string RoomId { get; }

    /// <summary>Either <see cref="RoomMode.Pvp"/> or <see cref="RoomMode.Ai"/>.</summary>
    public string Mode { get; }

    /// <summary>The room's seats, indexed by seat number.</summary>
    public IReadOnlyList<Seat> Seats { get; }

    /// <summary>Connection to this room's Python engine.</summary>
    public EngineSocket Engine { get; }

    /// <summary>Highest patch sequence forwarded so far, for gap diagnostics.</summary>
    public int LastSeq { get; private set; }

    /// <summary>True once a START_GAME intent has been sent for this room.</summary>
    public bool Started { get; set; }

    /// <summary>True once the room has been disposed and must not be reused.</summary>
    public bool IsDisposed { get; private set; }

    /// <summary>
    /// Builds a room around an engine that has already completed its handshake.
    /// </summary>
    /// <param name="ready">The engine's description of the room it created.</param>
    /// <param name="engine">The connected engine socket.</param>
    public Room(RoomReady ready, EngineSocket engine)
    {
        RoomId = ready.RoomId;
        Mode = ready.Mode;
        Engine = engine;
        Seats = [.. ready.PlayerIds.Select(
            (playerId, index) => new Seat(index, playerId, ready.AiSeats.Contains(index)))];
    }

    /// <summary>Seats a client may occupy.</summary>
    public IEnumerable<Seat> HumanSeats => Seats.Where(seat => !seat.IsAi);

    /// <summary>True when every human seat has a live connection.</summary>
    public bool IsFull => HumanSeats.All(seat => seat.IsOccupied);

    /// <summary>True when no human seat has a live connection.</summary>
    public bool IsEmpty => HumanSeats.All(seat => !seat.IsOccupied);

    /// <summary>
    /// When the last client left, or null while at least one is still connected.
    /// </summary>
    public DateTimeOffset? EmptySince =>
        IsEmpty
            ? HumanSeats.Select(seat => seat.VacatedAt).Max()
            : null;

    /// <summary>Takes the room's lock for a seat change.</summary>
    /// <param name="cancellationToken">Fires when the host shuts down.</param>
    /// <returns>A handle to release with <c>using</c>.</returns>
    public async Task<IDisposable> EnterAsync(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);
        return new Release(_gate);
    }

    /// <summary>
    /// Claims a free seat for a joining client. Call under <see cref="EnterAsync"/>.
    /// </summary>
    /// <param name="claimedPlayerId">Player id from a previous assignment, on a reconnect.</param>
    /// <param name="grace">How long a vacated seat is reserved for its previous occupant.</param>
    /// <returns>The claimed seat, or null when the room is full.</returns>
    public Seat? ClaimSeat(string? claimedPlayerId, TimeSpan grace)
    {
        var now = DateTimeOffset.UtcNow;
        var candidates = HumanSeats.Where(
            seat => seat.IsClaimableBy(claimedPlayerId, grace, now));

        // Prefer the seat this player held before, so a reconnect is seamless.
        return candidates
            .OrderBy(seat => seat.PlayerId == claimedPlayerId ? 0 : 1)
            .ThenBy(seat => seat.Index)
            .FirstOrDefault();
    }

    /// <summary>The other seat's player id, for the assignment message.</summary>
    /// <param name="seat">The seat being assigned.</param>
    /// <returns>The opposing player id, or null in a one-seat room.</returns>
    public string? OpponentOf(Seat seat) =>
        Seats.FirstOrDefault(other => other.Index != seat.Index)?.PlayerId;

    /// <summary>
    /// Sends one patch to the seat it is addressed to, or to the whole room.
    /// </summary>
    /// <param name="patch">The engine's delta, forwarded byte for byte.</param>
    /// <param name="playerId">
    /// The seat the engine wrote this patch for, or null to send it to everyone.
    /// </param>
    /// <remarks>
    /// Patches are addressed because two players may not see the same board: the
    /// engine blanks out whatever each one is not entitled to know before it
    /// diffs, so a hand or a face-down trap is never on the wire to the wrong
    /// socket. The relay does not read any of it, and in particular does not
    /// transform coordinates: they stay in the engine's canonical frame and each
    /// client mirrors locally from its own seat index.
    /// </remarks>
    public void Deliver(JsonNode patch, string? playerId = null)
    {
        if (patch["seq"]?.GetValue<int>() is { } seq)
        {
            LastSeq = seq;
        }

        foreach (var seat in Seats)
        {
            if (playerId is null || seat.PlayerId == playerId)
            {
                seat.Connection?.Emit(Wire.EventPatch, patch);
            }
        }
    }

    /// <summary>
    /// Tells everyone in the room how full it is.
    /// </summary>
    /// <remarks>
    /// This is what lets a player who opened a room see "waiting for opponent"
    /// and the code to share, and see it clear the moment someone arrives.
    /// </remarks>
    public void BroadcastStatus()
    {
        var status = Status();
        foreach (var seat in Seats)
        {
            seat.Connection?.Emit(Wire.EventRoomStatus, status);
        }
    }

    /// <summary>Describes how full the room is.</summary>
    /// <returns>The status payload.</returns>
    public RoomStatus Status()
    {
        var human = HumanSeats.ToList();
        var seated = human.Count(seat => seat.IsOccupied);
        return new RoomStatus(
            RoomId, Mode, seated, human.Count, Started, seated < human.Count);
    }

    /// <summary>Sends an error to every connected client.</summary>
    /// <param name="message">Text to surface in the UI.</param>
    public void BroadcastError(string message)
    {
        foreach (var seat in Seats)
        {
            seat.Connection?.Emit(Wire.EventError, new GameError(message));
        }
    }

    /// <summary>
    /// Tells the acting player that the engine refused their intent.
    /// </summary>
    /// <param name="refused">The engine's rejection notice.</param>
    /// <remarks>
    /// Only the actor hears about it. A refused intent produces no patch, so
    /// the opponent's board never changed and has nothing to explain.
    /// </remarks>
    public void NotifyRejected(IntentRejected refused)
    {
        var seat = Seats.FirstOrDefault(candidate => candidate.PlayerId == refused.ActorId);
        var text = refused.Reason ?? $"{refused.IntentType ?? "That action"} is not allowed right now";
        seat?.Connection?.Emit(Wire.EventError, new GameError(text));
    }

    /// <summary>Builds a relay-authored intent, used for joins and resyncs.</summary>
    /// <param name="actorId">Player the intent acts for.</param>
    /// <param name="type">Intent type name.</param>
    /// <returns>An intent object ready to forward.</returns>
    public JsonObject SystemIntent(string actorId, string type) => new()
    {
        ["version"] = Wire.Version,
        ["room_id"] = RoomId,
        ["actor_id"] = actorId,
        ["type"] = type,
        ["payload"] = new JsonObject(),
        ["seq"] = 0,
    };

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        if (IsDisposed)
        {
            return;
        }

        IsDisposed = true;
        Engine.SendDispose();
        await Engine.DisposeAsync();
        _gate.Dispose();
    }

    /// <summary>Releases the room lock when the <c>using</c> block ends.</summary>
    private sealed class Release(SemaphoreSlim gate) : IDisposable
    {
        public void Dispose() => gate.Release();
    }
}
