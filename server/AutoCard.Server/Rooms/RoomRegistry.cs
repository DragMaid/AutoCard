using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;

using AutoCard.Server.Configuration;
using AutoCard.Server.Engine;

using Microsoft.Extensions.Options;

namespace AutoCard.Server.Rooms;

/// <summary>
/// Owns every live room and the engine connection behind each one.
/// </summary>
public sealed class RoomRegistry(
    IOptions<ServerOptions> options,
    ILogger<RoomRegistry> logger,
    ILoggerFactory loggerFactory)
{
    private readonly ConcurrentDictionary<string, Lazy<Task<Room>>> _rooms = new();
    private readonly ConcurrentDictionary<string, byte> _reserved = new();
    private readonly ServerOptions _options = options.Value;

    /// <summary>
    /// Alphabet for generated room codes.
    /// </summary>
    /// <remarks>
    /// <c>I</c>, <c>O</c>, <c>0</c> and <c>1</c> are left out. A room code is
    /// read aloud and typed by hand, so the pairs that get confused are worth
    /// more than the handful of extra combinations they would add.
    /// </remarks>
    private const string CodeAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    /// <summary>Length of a generated room code.</summary>
    private const int CodeLength = 5;

    /// <summary>Longest room code accepted; anything longer is truncated.</summary>
    private const int MaxRoomIdLength = 24;

    /// <summary>Rooms that currently exist, for diagnostics.</summary>
    public int Count => _rooms.Count;

    /// <summary>
    /// Normalizes a client-supplied room code into a safe, stable id.
    /// </summary>
    /// <param name="raw">Whatever the client typed.</param>
    /// <returns>An uppercase alphanumeric code, or <c>LOBBY</c> when nothing usable was given.</returns>
    /// <remarks>
    /// The code becomes a URL path segment on the engine connection, so it is
    /// restricted rather than escaped: an id that cannot express a traversal or
    /// a query cannot be made to mean something else downstream.
    /// </remarks>
    public static string NormalizeRoomId(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return "LOBBY";
        }

        var builder = new StringBuilder(MaxRoomIdLength);
        foreach (var character in raw.Trim().ToUpperInvariant())
        {
            if (char.IsAsciiLetterOrDigit(character) || character is '-' or '_')
            {
                builder.Append(character);
            }

            if (builder.Length == MaxRoomIdLength)
            {
                break;
            }
        }

        return builder.Length == 0 ? "LOBBY" : builder.ToString();
    }

    /// <summary>
    /// Decides whether a room is a versus-AI room.
    /// </summary>
    /// <param name="requested">The <c>mode</c> field of the join request, if the client sent one.</param>
    /// <param name="roomId">The normalized room code.</param>
    /// <returns><see cref="RoomMode.Ai"/> or <see cref="RoomMode.Pvp"/>.</returns>
    /// <remarks>
    /// The room-code prefixes exist so single player works against the current
    /// frontend, which has no mode selector yet: joining <c>AI-anything</c> or
    /// <c>SOLO</c> seats you opposite the agent.
    /// </remarks>
    public static string ResolveMode(string? requested, string roomId)
    {
        if (string.Equals(requested, RoomMode.Ai, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(requested, "solo", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(requested, "single", StringComparison.OrdinalIgnoreCase))
        {
            return RoomMode.Ai;
        }

        if (string.Equals(requested, RoomMode.Pvp, StringComparison.OrdinalIgnoreCase))
        {
            return RoomMode.Pvp;
        }

        return roomId.StartsWith("AI-", StringComparison.Ordinal) || roomId is "AI" or "SOLO"
            ? RoomMode.Ai
            : RoomMode.Pvp;
    }

    /// <summary>
    /// Returns the room for a code, creating it and its engine if needed.
    /// </summary>
    /// <param name="roomId">Normalized room code.</param>
    /// <param name="mode">Mode to use if the room has to be created.</param>
    /// <param name="cancellationToken">Fires when the host shuts down.</param>
    /// <returns>A live room.</returns>
    public async Task<Room> GetOrCreateAsync(
        string roomId,
        string mode,
        CancellationToken cancellationToken)
    {
        while (true)
        {
            if (_rooms.Count >= _options.MaxRooms && !_rooms.ContainsKey(roomId))
            {
                throw new InvalidOperationException("The server is at capacity; try again shortly.");
            }

            // Lazy with ExecutionAndPublication guarantees one engine socket per
            // room even when both players hit join in the same millisecond.
            var entry = _rooms.GetOrAdd(
                roomId,
                id => new Lazy<Task<Room>>(
                    () => CreateAsync(id, mode, cancellationToken),
                    LazyThreadSafetyMode.ExecutionAndPublication));

            Room room;
            try
            {
                room = await entry.Value;
            }
            catch
            {
                // A failed creation must not poison the code forever.
                Remove(roomId, entry);
                throw;
            }

            if (!room.IsDisposed)
            {
                return room;
            }

            // The sweeper disposed it between lookup and use; build a fresh one.
            Remove(roomId, entry);
        }
    }

    /// <summary>
    /// Opens a brand-new room under a code nobody is using.
    /// </summary>
    /// <param name="mode">Mode for the new room.</param>
    /// <param name="cancellationToken">Fires when the host shuts down.</param>
    /// <returns>A room with every seat still free.</returns>
    /// <remarks>
    /// The code is reserved across the creation itself so two simultaneous
    /// creates cannot land two strangers in the same room. Once creation
    /// returns, the code is in <c>_rooms</c> and generation skips it anyway.
    /// </remarks>
    public async Task<Room> CreateFreshAsync(string mode, CancellationToken cancellationToken)
    {
        for (var attempt = 0; attempt < 8; attempt++)
        {
            var code = NewRoomCode();
            if (_rooms.ContainsKey(code) || !_reserved.TryAdd(code, 0))
            {
                continue;
            }

            try
            {
                return await GetOrCreateAsync(code, mode, cancellationToken);
            }
            finally
            {
                _reserved.TryRemove(code, out _);
            }
        }

        throw new InvalidOperationException("Could not allocate a free room code.");
    }

    /// <summary>Generates a random, human-typeable room code.</summary>
    /// <returns>A code of <see cref="CodeLength"/> characters.</returns>
    private static string NewRoomCode() =>
        string.Create(CodeLength, 0, (span, _) =>
        {
            for (var index = 0; index < span.Length; index++)
            {
                span[index] = CodeAlphabet[RandomNumberGenerator.GetInt32(CodeAlphabet.Length)];
            }
        });

    /// <summary>Opens an engine connection and wraps it in a room.</summary>
    /// <remarks>
    /// The engine callbacks are attached before the socket is connected, so a
    /// patch can never arrive with nowhere to go. They capture <c>room</c> by
    /// reference and no-op while it is still null, which is exactly right:
    /// anything the engine emits before its handshake belongs to no room.
    /// </remarks>
    private async Task<Room> CreateAsync(string roomId, string mode, CancellationToken cancellationToken)
    {
        var engine = new EngineSocket(loggerFactory.CreateLogger<EngineSocket>());
        Room? room = null;

        engine.PatchReceived = (patch, playerId) =>
        {
            room?.Deliver(patch, playerId);
            return Task.CompletedTask;
        };

        engine.Refused = refused =>
        {
            room?.NotifyRejected(refused);
            return Task.CompletedTask;
        };

        engine.Closed = async reason =>
        {
            if (room is null || room.IsDisposed)
            {
                return;
            }

            // There is no persistence: when the engine goes, the match goes.
            logger.LogWarning("Engine for room {RoomId} closed: {Reason}", roomId, reason);
            room.BroadcastError("The match ended because the game server connection was lost.");
            await DiscardAsync(roomId);
        };

        try
        {
            var ready = await engine.ConnectAsync(
                new Uri(_options.EngineUri),
                roomId,
                mode,
                _options.EngineHandshakeTimeout,
                cancellationToken);

            logger.LogInformation(
                "Room {RoomId} ready in {Mode} mode with seats {Seats}",
                ready.RoomId, ready.Mode, string.Join(", ", ready.PlayerIds));

            room = new Room(ready, engine);
            return room;
        }
        catch
        {
            await engine.DisposeAsync();
            throw;
        }
    }

    /// <summary>Looks up an already-created room without creating one.</summary>
    /// <param name="roomId">Normalized room code.</param>
    /// <returns>The room, or null when it does not exist or is not ready yet.</returns>
    public Room? Find(string roomId) =>
        _rooms.TryGetValue(roomId, out var entry) &&
        entry.IsValueCreated &&
        entry.Value is { IsCompletedSuccessfully: true, Result: var room } &&
        !room.IsDisposed
            ? room
            : null;

    /// <summary>
    /// Disposes rooms whose players have all been gone past the grace period.
    /// </summary>
    /// <returns>How many rooms were disposed.</returns>
    /// <remarks>
    /// Without this, every abandoned match leaves a Python <c>GameEngine</c>
    /// resident for the lifetime of the process.
    /// </remarks>
    public async Task<int> SweepIdleAsync()
    {
        var cutoff = DateTimeOffset.UtcNow - _options.ReconnectGrace;
        var disposed = 0;

        foreach (var (roomId, entry) in _rooms.ToArray())
        {
            if (!entry.IsValueCreated || !entry.Value.IsCompletedSuccessfully)
            {
                continue;
            }

            var room = entry.Value.Result;
            var emptySince = room.EmptySince;

            // A room nobody ever joined has no VacatedAt, so it is left alone
            // until someone occupies and leaves it.
            if (room.IsDisposed || emptySince is null || emptySince > cutoff)
            {
                continue;
            }

            Remove(roomId, entry);
            await room.DisposeAsync();
            disposed++;
            logger.LogInformation("Disposed idle room {RoomId}", roomId);
        }

        return disposed;
    }

    /// <summary>Drops a room immediately, for example after its engine died.</summary>
    /// <param name="roomId">Normalized room code.</param>
    public async Task DiscardAsync(string roomId)
    {
        if (!_rooms.TryRemove(roomId, out var entry) ||
            !entry.IsValueCreated ||
            !entry.Value.IsCompletedSuccessfully)
        {
            return;
        }

        await entry.Value.Result.DisposeAsync();
    }

    /// <summary>Disposes every room, for host shutdown.</summary>
    public async Task DisposeAllAsync()
    {
        foreach (var (roomId, _) in _rooms.ToArray())
        {
            await DiscardAsync(roomId);
        }
    }

    /// <summary>Removes a specific entry, leaving a newer one in place.</summary>
    private void Remove(string roomId, Lazy<Task<Room>> entry) =>
        ((ICollection<KeyValuePair<string, Lazy<Task<Room>>>>)_rooms).Remove(
            new KeyValuePair<string, Lazy<Task<Room>>>(roomId, entry));
}
