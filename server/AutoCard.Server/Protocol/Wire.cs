using System.Text.Json.Serialization;

namespace AutoCard.Server.Protocol;

/// <summary>
/// Names and constants shared with <c>core/network/actions.py</c> and
/// <c>web/src/net/actions.ts</c>. The three files are one protocol; changing a
/// value here without changing it there breaks the match silently.
/// </summary>
public static class Wire
{
    /// <summary>Protocol version stamped on every intent and patch.</summary>
    public const int Version = 1;

    /// <summary>Client asks to be seated in a room it names.</summary>
    public const string EventJoin = "join";

    /// <summary>Client asks the server to open a fresh room and name it.</summary>
    public const string EventCreateRoom = "create_room";

    /// <summary>Client asks to be paired with whoever is waiting.</summary>
    public const string EventMatchmake = "matchmake";

    /// <summary>Client withdraws from the matchmaking queue.</summary>
    public const string EventCancelMatchmake = "cancel_matchmake";

    /// <summary>Server reports the client's place in the matchmaking queue.</summary>
    public const string EventQueued = "queued";

    /// <summary>Server reports how many seats in a room are filled.</summary>
    public const string EventRoomStatus = "room_status";

    /// <summary>Server tells a client which seat and player id it holds.</summary>
    public const string EventAssign = "assign";

    /// <summary>Client sends an intent; the relay forwards it to the engine.</summary>
    public const string EventAction = "action";

    /// <summary>Engine sends a patch; the relay broadcasts it to the room.</summary>
    public const string EventPatch = "patch";

    /// <summary>Server reports something the client should surface.</summary>
    public const string EventError = "game_error";

    /// <summary>Intent asking the engine to deal opening hands.</summary>
    public const string IntentStartGame = "START_GAME";

    /// <summary>Intent asking the engine for a full snapshot.</summary>
    public const string IntentRequestSync = "REQUEST_SYNC";

    /// <summary>Intent conceding the match.</summary>
    public const string IntentSurrender = "SURRENDER";
}

/// <summary>
/// The <c>join</c> payload a client sends on connect.
/// </summary>
/// <param name="RoomId">Room code to join. Blank falls back to a lobby room.</param>
/// <param name="PlayerName">Display name, used only for logging and the engine's player label.</param>
/// <param name="Mode">Optional <c>pvp</c> or <c>ai</c>. Omitted means the room code decides.</param>
/// <param name="PlayerId">
/// Player id from a previous <c>assign</c>. Present only on a reconnect, and it
/// grants nothing except the right to reclaim that seat before its grace period
/// expires — the engine still re-validates every action.
/// </param>
public sealed record JoinRequest(
    [property: JsonPropertyName("room_id")] string? RoomId,
    [property: JsonPropertyName("player_name")] string? PlayerName,
    [property: JsonPropertyName("mode")] string? Mode,
    [property: JsonPropertyName("player_id")] string? PlayerId);

/// <summary>
/// The <c>assign</c> payload handed to a client once it is seated.
/// </summary>
/// <param name="RoomId">Room the client was seated in.</param>
/// <param name="PlayerId">The engine's id for this client's player.</param>
/// <param name="PlayerIndex">
/// Seat index. 0 is the canonical frame; any other seat renders the board
/// rotated 180 degrees, so sending the wrong index mirrors the player's board.
/// </param>
/// <param name="OpponentId">The other seat's player id, when one exists.</param>
/// <param name="Mode">Whether this room is <c>pvp</c> or <c>ai</c>.</param>
public sealed record Assignment(
    [property: JsonPropertyName("room_id")] string RoomId,
    [property: JsonPropertyName("player_id")] string PlayerId,
    [property: JsonPropertyName("player_index")] int PlayerIndex,
    [property: JsonPropertyName("opponent_id")] string? OpponentId,
    [property: JsonPropertyName("mode")] string Mode);

/// <summary>
/// The <c>create_room</c> payload. The server picks the code, not the client.
/// </summary>
/// <param name="PlayerName">Display name of the creator.</param>
/// <param name="Mode">Optional <c>pvp</c> or <c>ai</c>; omitted means <c>pvp</c>.</param>
public sealed record CreateRoomRequest(
    [property: JsonPropertyName("player_name")] string? PlayerName,
    [property: JsonPropertyName("mode")] string? Mode);

/// <summary>
/// The <c>matchmake</c> payload.
/// </summary>
/// <param name="PlayerName">Display name to carry into whatever room is opened.</param>
public sealed record MatchmakeRequest(
    [property: JsonPropertyName("player_name")] string? PlayerName);

/// <summary>
/// How full a room is, pushed to its occupants whenever that changes.
/// </summary>
/// <param name="RoomId">Room the status describes; also the code to share.</param>
/// <param name="Mode">Whether this room is <c>pvp</c> or <c>ai</c>.</param>
/// <param name="Seated">Human seats currently occupied.</param>
/// <param name="Capacity">Human seats the room has at all.</param>
/// <param name="Started">True once the opening hands have been dealt.</param>
/// <param name="Waiting">True while the room still needs someone to fill it.</param>
public sealed record RoomStatus(
    [property: JsonPropertyName("room_id")] string RoomId,
    [property: JsonPropertyName("mode")] string Mode,
    [property: JsonPropertyName("seated")] int Seated,
    [property: JsonPropertyName("capacity")] int Capacity,
    [property: JsonPropertyName("started")] bool Started,
    [property: JsonPropertyName("waiting")] bool Waiting);

/// <summary>
/// The client's place in the matchmaking queue.
/// </summary>
/// <param name="Position">1 means next to be paired.</param>
/// <param name="Size">How many players are waiting in total.</param>
public sealed record QueueStatus(
    [property: JsonPropertyName("position")] int Position,
    [property: JsonPropertyName("size")] int Size);

/// <summary>A message surfaced to the player.</summary>
/// <param name="Message">Human-readable text.</param>
public sealed record GameError(
    [property: JsonPropertyName("message")] string Message);
