using System.Text.Json.Serialization;

namespace AutoCard.Server.Engine;

/// <summary>Message kinds on the relay-to-engine WebSocket.</summary>
public static class EngineMessage
{
    /// <summary>Engine to relay: the room exists and these are its player ids.</summary>
    public const string RoomReady = "room_ready";

    /// <summary>Engine to relay: a delta to broadcast.</summary>
    public const string Patch = "patch";

    /// <summary>Engine to relay: an intent broke a rule and changed nothing.</summary>
    public const string Rejected = "rejected";

    /// <summary>Relay to engine: apply this intent.</summary>
    public const string Intent = "intent";

    /// <summary>Relay to engine: tear this room down.</summary>
    public const string Dispose = "dispose";
}

/// <summary>
/// The engine's reply when a room connection opens.
/// </summary>
/// <param name="RoomId">Room the engine created or resumed.</param>
/// <param name="PlayerIds">Player ids by seat index; index 0 is the canonical frame.</param>
/// <param name="AiSeats">Seats driven by the AI module, which no client may claim.</param>
/// <param name="Mode">The mode the engine actually started, <c>pvp</c> or <c>ai</c>.</param>
public sealed record RoomReady(
    [property: JsonPropertyName("room_id")] string RoomId,
    [property: JsonPropertyName("player_ids")] IReadOnlyList<string> PlayerIds,
    [property: JsonPropertyName("ai_seats")] IReadOnlyList<int> AiSeats,
    [property: JsonPropertyName("mode")] string Mode);

/// <summary>
/// The engine's notice that an intent was refused by the rules.
/// </summary>
/// <param name="ActorId">Player whose intent was refused.</param>
/// <param name="IntentType">Which intent it was.</param>
/// <param name="Reason">Short explanation for the player.</param>
public sealed record IntentRejected(
    [property: JsonPropertyName("actor_id")] string? ActorId,
    [property: JsonPropertyName("intent_type")] string? IntentType,
    [property: JsonPropertyName("reason")] string? Reason);
