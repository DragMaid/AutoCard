using AutoCard.Server.Rooms;
using AutoCard.Server.Util;

namespace AutoCard.Server.Game;

/// <summary>
/// The identity the relay binds to a socket once it is seated.
/// </summary>
/// <remarks>
/// This, not the client's own message fields, is the authority on who is acting.
/// Every intent's <c>actor_id</c> is overwritten from <see cref="Seat"/> before it
/// reaches the engine, which is the single check that stops a player from acting
/// as their opponent.
/// </remarks>
/// <param name="Room">Room the socket joined.</param>
/// <param name="Seat">Seat the socket holds.</param>
/// <param name="Intents">Rate limiter for this socket.</param>
public sealed record PlayerSession(Room Room, Seat Seat, TokenBucket Intents);
