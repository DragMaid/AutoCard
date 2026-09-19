using AutoCard.Server.SocketIO;

namespace AutoCard.Server.Game;

/// <summary>
/// One player waiting to be paired.
/// </summary>
/// <param name="Connection">The waiting socket.</param>
/// <param name="PlayerName">Display name to carry into the room.</param>
/// <param name="Since">When they started waiting.</param>
public sealed record Waiting(
    SocketIoConnection Connection,
    string? PlayerName,
    DateTimeOffset Since);

/// <summary>
/// The quick-match queue: a first-come, first-served list of waiting players.
/// </summary>
/// <remarks>
/// Deliberately not a skill-ranked matchmaker. There is no rating to match on —
/// the relay holds no accounts and no history — so anything cleverer than a
/// queue would be inventing signal it does not have.
/// </remarks>
public sealed class Matchmaker
{
    private readonly Lock _gate = new();
    private readonly List<Waiting> _queue = [];

    /// <summary>How many players are waiting.</summary>
    public int Count
    {
        get
        {
            lock (_gate)
            {
                return _queue.Count;
            }
        }
    }

    /// <summary>
    /// Adds a player to the queue.
    /// </summary>
    /// <param name="connection">The waiting socket.</param>
    /// <param name="playerName">Display name to carry into the room.</param>
    /// <returns>False when this socket was already waiting.</returns>
    public bool Enqueue(SocketIoConnection connection, string? playerName)
    {
        lock (_gate)
        {
            if (_queue.Any(waiting => ReferenceEquals(waiting.Connection, connection)))
            {
                return false;
            }

            _queue.Add(new Waiting(connection, playerName, DateTimeOffset.UtcNow));
            return true;
        }
    }

    /// <summary>
    /// Removes a player from the queue.
    /// </summary>
    /// <param name="connection">The socket to withdraw.</param>
    /// <returns>True when it was waiting.</returns>
    public bool Remove(SocketIoConnection connection)
    {
        lock (_gate)
        {
            return _queue.RemoveAll(
                waiting => ReferenceEquals(waiting.Connection, connection)) > 0;
        }
    }

    /// <summary>
    /// Takes the two longest-waiting live players, if there are two.
    /// </summary>
    /// <returns>A pair to seat together, or null when nobody can be matched yet.</returns>
    public (Waiting First, Waiting Second)? TryTakePair()
    {
        lock (_gate)
        {
            // Sockets that closed without a disconnect event would otherwise be
            // paired with a live player and strand them in an empty room.
            _queue.RemoveAll(waiting => !waiting.Connection.IsOpen);

            if (_queue.Count < 2)
            {
                return null;
            }

            var first = _queue[0];
            var second = _queue[1];
            _queue.RemoveRange(0, 2);
            return (first, second);
        }
    }

    /// <summary>
    /// The current queue, in order, for reporting positions.
    /// </summary>
    /// <returns>A copy safe to iterate outside the lock.</returns>
    public IReadOnlyList<Waiting> Snapshot()
    {
        lock (_gate)
        {
            return [.. _queue];
        }
    }
}
