using System.Text.Json;

namespace AutoCard.Server.SocketIO;

/// <summary>Engine.IO v4 packet type prefixes.</summary>
internal static class EngineIoType
{
    public const char Open = '0';
    public const char Close = '1';
    public const char Ping = '2';
    public const char Pong = '3';
    public const char Message = '4';
}

/// <summary>Socket.IO v5 packet type prefixes, which follow an Engine.IO <c>Message</c>.</summary>
internal static class SocketIoType
{
    public const char Connect = '0';
    public const char Disconnect = '1';
    public const char Event = '2';
    public const char Ack = '3';
    public const char ConnectError = '4';
}

/// <summary>
/// One decoded Socket.IO EVENT frame.
/// </summary>
/// <param name="Namespace">Namespace the frame targets; this server only serves <c>/</c>.</param>
/// <param name="AckId">Ack id the client expects back, or null when it wants no ack.</param>
/// <param name="Name">Event name, i.e. the first element of the payload array.</param>
/// <param name="Data">First argument of the event, or <c>default</c> when the event carried none.</param>
internal readonly record struct SocketIoEvent(
    string Namespace,
    int? AckId,
    string Name,
    JsonElement Data);
