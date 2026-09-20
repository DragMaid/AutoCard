using System.Text.Json;
using System.Text.Json.Nodes;

using AutoCard.Server.Configuration;
using AutoCard.Server.Protocol;
using AutoCard.Server.Rooms;
using AutoCard.Server.SocketIO;
using AutoCard.Server.Util;

using Microsoft.Extensions.Options;

namespace AutoCard.Server.Game;

/// <summary>
/// Translates client events into room operations.
/// </summary>
/// <remarks>
/// This class is the whole "game API": identity, room lifecycle, seat assignment
/// and message routing. It never inspects a payload beyond the envelope, never
/// decides an outcome and never touches a coordinate — the rules live in exactly
/// one place, and it is not here.
/// </remarks>
public sealed class GameGateway(
    RoomRegistry rooms,
    Matchmaker matchmaker,
    IOptions<ServerOptions> options,
    ILogger<GameGateway> logger,
    IHostApplicationLifetime lifetime)
{
    private readonly ServerOptions _options = options.Value;

    /// <summary>Attaches this gateway's handlers to a Socket.IO server.</summary>
    /// <param name="server">The server to wire up.</param>
    public void Register(SocketIoServer server)
    {
        server.On(Wire.EventJoin, OnJoinAsync);
        server.On(Wire.EventCreateRoom, OnCreateRoomAsync);
        server.On(Wire.EventMatchmake, OnMatchmakeAsync);
        server.On(Wire.EventCancelMatchmake, OnCancelMatchmakeAsync);
        server.On(Wire.EventAction, OnActionAsync);
        server.Disconnected = OnDisconnectedAsync;
    }

    // ------------------------------------------------------------------
    // Entering a room
    // ------------------------------------------------------------------

    /// <summary>Seats a client in the room it named.</summary>
    private async Task OnJoinAsync(SocketIoConnection connection, JsonElement data)
    {
        if (Reseat(connection))
        {
            return;
        }

        var request = Read<JoinRequest>(data);
        var roomId = RoomRegistry.NormalizeRoomId(request?.RoomId);
        var mode = RoomRegistry.ResolveMode(request?.Mode, roomId);

        var room = await OpenAsync(connection, () => rooms.GetOrCreateAsync(
            roomId, mode, lifetime.ApplicationStopping));
        if (room is null)
        {
            return;
        }

        await SeatAsync(connection, room, request?.PlayerName, request?.PlayerId);
    }

    /// <summary>Opens a fresh room under a server-chosen code and seats the creator.</summary>
    private async Task OnCreateRoomAsync(SocketIoConnection connection, JsonElement data)
    {
        if (Reseat(connection))
        {
            return;
        }

        var request = Read<CreateRoomRequest>(data);
        var mode = RoomRegistry.ResolveMode(request?.Mode, string.Empty);

        var room = await OpenAsync(connection, () => rooms.CreateFreshAsync(
            mode, lifetime.ApplicationStopping));
        if (room is null)
        {
            return;
        }

        await SeatAsync(connection, room, request?.PlayerName, null);
    }

    // ------------------------------------------------------------------
    // Matchmaking
    // ------------------------------------------------------------------

    /// <summary>Queues a client for quick match and pairs whoever is ready.</summary>
    private async Task OnMatchmakeAsync(SocketIoConnection connection, JsonElement data)
    {
        if (Reseat(connection))
        {
            return;
        }

        var request = Read<MatchmakeRequest>(data);
        matchmaker.Enqueue(connection, request?.PlayerName);

        while (matchmaker.TryTakePair() is { } pair)
        {
            await PairAsync(pair.First, pair.Second);
        }

        ReportQueue();
    }

    /// <summary>Withdraws a client from the quick-match queue.</summary>
    private Task OnCancelMatchmakeAsync(SocketIoConnection connection, JsonElement data)
    {
        if (matchmaker.Remove(connection))
        {
            connection.Emit(Wire.EventQueued, new QueueStatus(0, matchmaker.Count));
            ReportQueue();
        }

        return Task.CompletedTask;
    }

    /// <summary>Opens a room for two matched players and seats them both.</summary>
    private async Task PairAsync(Waiting first, Waiting second)
    {
        Room room;
        try
        {
            room = await rooms.CreateFreshAsync(RoomMode.Pvp, lifetime.ApplicationStopping);
        }
        catch (Exception ex)
        {
            // Both players are told rather than silently re-queued: a failure
            // here means the engine is down, and retrying would only stall them.
            logger.LogError(ex, "Matchmaking could not open a room");
            var message = new GameError("Could not start a match. Try again in a moment.");
            first.Connection.Emit(Wire.EventError, message);
            second.Connection.Emit(Wire.EventError, message);
            return;
        }

        logger.LogInformation("Matched two players into room {RoomId}", room.RoomId);

        // Neither seating announces, so the first player never hears that they
        // are alone in a room. They are not: their opponent is being seated in
        // the same breath, and a "waiting for opponent" status in between is
        // what put a share-this-code screen in front of a match that had
        // already been made.
        await SeatAsync(first.Connection, room, first.PlayerName, null, announce: false);
        await SeatAsync(second.Connection, room, second.PlayerName, null, announce: false);
        room.BroadcastStatus();
    }

    /// <summary>Tells everyone still waiting where they are in the queue.</summary>
    private void ReportQueue()
    {
        var waiting = matchmaker.Snapshot();
        for (var index = 0; index < waiting.Count; index++)
        {
            waiting[index].Connection.Emit(
                Wire.EventQueued, new QueueStatus(index + 1, waiting.Count));
        }
    }

    // ------------------------------------------------------------------
    // Seating
    // ------------------------------------------------------------------

    /// <summary>
    /// Claims a seat for a client and hands it the board.
    /// </summary>
    /// <param name="connection">The client to seat.</param>
    /// <param name="room">The room to seat it in.</param>
    /// <param name="playerName">Display name for logging.</param>
    /// <param name="claimedPlayerId">Player id from a previous assignment, on a reconnect.</param>
    /// <param name="announce">
    /// Whether to broadcast the room's occupancy afterwards. Matchmaking seats
    /// two players back to back and announces once at the end, so nobody is
    /// told about the half-filled room that existed in between.
    /// </param>
    private async Task SeatAsync(
        SocketIoConnection connection,
        Room room,
        string? playerName,
        string? claimedPlayerId,
        bool announce = true)
    {
        using (await room.EnterAsync(lifetime.ApplicationStopping))
        {
            var seat = room.ClaimSeat(claimedPlayerId, _options.ReconnectGrace);
            if (seat is null)
            {
                connection.Emit(Wire.EventError, new GameError("Room is full"));
                return;
            }

            seat.Connection = connection;
            seat.PlayerName = playerName;
            seat.VacatedAt = null;
            connection.UserState = new PlayerSession(
                room, seat, new TokenBucket(_options.IntentBurst, _options.IntentsPerSecond));

            SendAssignment(connection, room, seat);

            // Deal before snapshotting, so the player who completes the table
            // sees its opening hand in the very first patch it applies.
            if (!room.Started && room.IsFull)
            {
                room.Started = true;
                room.Engine.SendIntent(room.SystemIntent(seat.PlayerId, Wire.IntentStartGame));
            }

            room.Engine.SendIntent(room.SystemIntent(seat.PlayerId, Wire.IntentRequestSync));

            if (announce)
            {
                room.BroadcastStatus();
            }

            logger.LogInformation(
                "{Name} took seat {Seat} in room {RoomId} ({Mode})",
                playerName ?? "player", seat.Index, room.RoomId, room.Mode);
        }
    }

    /// <summary>
    /// Re-sends the assignment when an already-seated client asks to enter again.
    /// </summary>
    /// <param name="connection">The client.</param>
    /// <returns>True when the client already held a seat and was handled.</returns>
    /// <remarks>
    /// A second entry request would otherwise strand the first seat, so the
    /// client is simply reminded of the one it has.
    /// </remarks>
    private static bool Reseat(SocketIoConnection connection)
    {
        if (connection.UserState is not PlayerSession session)
        {
            return false;
        }

        SendAssignment(connection, session.Room, session.Seat);
        session.Room.BroadcastStatus();
        return true;
    }

    /// <summary>Runs a room-opening call, reporting failure to the client.</summary>
    /// <param name="connection">Client to tell if the engine is unreachable.</param>
    /// <param name="open">The registry call to make.</param>
    /// <returns>The room, or null when it could not be opened.</returns>
    private async Task<Room?> OpenAsync(SocketIoConnection connection, Func<Task<Room>> open)
    {
        try
        {
            return await open();
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Could not open a room");
            connection.Emit(Wire.EventError, new GameError(
                "The game server is unavailable. Try again in a moment."));
            return null;
        }
    }

    // ------------------------------------------------------------------
    // Playing
    // ------------------------------------------------------------------

    /// <summary>Forwards one client intent to the room's engine.</summary>
    private Task OnActionAsync(SocketIoConnection connection, JsonElement data)
    {
        if (connection.UserState is not PlayerSession session)
        {
            connection.Emit(Wire.EventError, new GameError("Join a room before acting"));
            return Task.CompletedTask;
        }

        if (session.Room.IsDisposed)
        {
            connection.Emit(Wire.EventError, new GameError("This match is no longer running"));
            return Task.CompletedTask;
        }

        if (!session.Intents.TryConsume())
        {
            logger.LogWarning("Throttling {Sid} in room {RoomId}", connection.Sid, session.Room.RoomId);
            connection.Emit(Wire.EventError, new GameError("Slow down — too many actions"));
            return Task.CompletedTask;
        }

        if (data.ValueKind != JsonValueKind.Object ||
            JsonNode.Parse(data.GetRawText()) is not JsonObject intent)
        {
            connection.Emit(Wire.EventError, new GameError("Malformed action"));
            return Task.CompletedTask;
        }

        if (intent["version"]?.GetValue<int>() is { } version && version != Wire.Version)
        {
            // Fail loudly rather than let a stale client desync quietly.
            connection.Emit(Wire.EventError, new GameError(
                $"This client speaks protocol v{version}; the server speaks v{Wire.Version}. Reload the page."));
            return Task.CompletedTask;
        }

        // Identity comes from the seat, never from the client.
        intent["version"] = Wire.Version;
        intent["room_id"] = session.Room.RoomId;
        intent["actor_id"] = session.Seat.PlayerId;

        session.Room.Engine.SendIntent(intent);
        return Task.CompletedTask;
    }

    // ------------------------------------------------------------------
    // Leaving
    // ------------------------------------------------------------------

    /// <summary>Vacates a seat, leaving it reserved for the grace period.</summary>
    private Task OnDisconnectedAsync(SocketIoConnection connection)
    {
        if (matchmaker.Remove(connection))
        {
            ReportQueue();
        }

        if (connection.UserState is not PlayerSession session)
        {
            return Task.CompletedTask;
        }

        connection.UserState = null;

        // Only clear the seat if this socket is still the one sitting in it; a
        // fast reconnect may already have claimed it.
        if (ReferenceEquals(session.Seat.Connection, connection))
        {
            session.Seat.Connection = null;
            session.Seat.VacatedAt = DateTimeOffset.UtcNow;
            session.Room.BroadcastStatus();
        }

        logger.LogInformation(
            "Seat {Seat} in room {RoomId} vacated; held for {Grace}s",
            session.Seat.Index, session.Room.RoomId, _options.ReconnectGraceSeconds);

        return Task.CompletedTask;
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    /// <summary>Sends the seat assignment that decides the client's board orientation.</summary>
    private static void SendAssignment(SocketIoConnection connection, Room room, Seat seat) =>
        connection.Emit(Wire.EventAssign, new Assignment(
            room.RoomId,
            seat.PlayerId,
            seat.Index,
            room.OpponentOf(seat),
            room.Mode));

    /// <summary>Reads a request payload, tolerating a missing or malformed body.</summary>
    /// <typeparam name="T">The expected payload shape.</typeparam>
    /// <param name="data">The event's first argument.</param>
    /// <returns>The decoded payload, or null.</returns>
    private static T? Read<T>(JsonElement data) where T : class
    {
        if (data.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        try
        {
            return data.Deserialize<T>(JsonDefaults.Options);
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
