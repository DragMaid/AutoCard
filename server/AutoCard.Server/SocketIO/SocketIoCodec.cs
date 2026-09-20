using System.Text.Json;

namespace AutoCard.Server.SocketIO;

/// <summary>
/// Encodes and decodes the textual Socket.IO v5 / Engine.IO v4 framing.
/// </summary>
/// <remarks>
/// Only the WebSocket transport is implemented, because the browser client opens
/// with <c>transports: ["websocket"]</c> and therefore never negotiates polling.
/// That removes the whole session-upgrade dance: a frame is one text message and
/// one packet, with no payload-length separators and no binary attachments.
/// </remarks>
internal static class SocketIoCodec
{
    /// <summary>The only namespace this server serves.</summary>
    public const string RootNamespace = "/";

    /// <summary>Builds the Engine.IO <c>open</c> handshake frame.</summary>
    /// <param name="sid">Session id handed to the client.</param>
    /// <param name="pingInterval">How often the server will send a ping, in milliseconds.</param>
    /// <param name="pingTimeout">How long the client may take to pong, in milliseconds.</param>
    /// <param name="maxPayload">Largest frame the client may send, in bytes.</param>
    /// <returns>The frame to write to the socket.</returns>
    public static string Open(string sid, int pingInterval, int pingTimeout, int maxPayload)
    {
        var handshake = JsonSerializer.Serialize(new
        {
            sid,
            upgrades = Array.Empty<string>(),
            pingInterval,
            pingTimeout,
            maxPayload,
        });
        return EngineIoType.Open + handshake;
    }

    /// <summary>Builds the Socket.IO <c>CONNECT</c> acknowledgement for the root namespace.</summary>
    /// <param name="sid">Socket id the client should report as <c>socket.id</c>.</param>
    /// <returns>The frame to write to the socket.</returns>
    public static string Connect(string sid) =>
        $"{EngineIoType.Message}{SocketIoType.Connect}{{\"sid\":\"{sid}\"}}";

    /// <summary>Builds a Socket.IO <c>CONNECT_ERROR</c> frame.</summary>
    /// <param name="message">Reason shown to the client's <c>connect_error</c> handler.</param>
    /// <returns>The frame to write to the socket.</returns>
    public static string ConnectError(string message)
    {
        var body = JsonSerializer.Serialize(new { message });
        return $"{EngineIoType.Message}{SocketIoType.ConnectError}{body}";
    }

    /// <summary>Builds a Socket.IO <c>EVENT</c> frame carrying one argument.</summary>
    /// <param name="name">Event name the client listens for.</param>
    /// <param name="payload">Single event argument, serialized as JSON.</param>
    /// <returns>The frame to write to the socket.</returns>
    public static string Event(string name, object? payload)
    {
        var args = JsonSerializer.Serialize(new[] { payload }, JsonDefaults.Options);
        // args is a JSON array already, so splice the name in as element zero.
        var inner = args.AsSpan(1, args.Length - 2);
        var nameJson = JsonSerializer.Serialize(name);
        return $"{EngineIoType.Message}{SocketIoType.Event}[{nameJson},{inner}]";
    }

    /// <summary>Builds the Engine.IO ping frame.</summary>
    public static string Ping() => EngineIoType.Ping.ToString();

    /// <summary>Builds the Engine.IO close frame.</summary>
    public static string Close() => EngineIoType.Close.ToString();

    /// <summary>
    /// Splits a Socket.IO message frame into namespace, ack id and JSON body.
    /// </summary>
    /// <param name="body">Frame contents after the Engine.IO and Socket.IO type digits.</param>
    /// <returns>The namespace, the ack id if present, and the remaining JSON text.</returns>
    public static (string Namespace, int? AckId, string Json) SplitBody(ReadOnlySpan<char> body)
    {
        var ns = RootNamespace;

        // A non-root namespace is written as "/name," directly after the type.
        if (body.Length > 0 && body[0] == '/')
        {
            var comma = body.IndexOf(',');
            if (comma < 0)
            {
                return (body.ToString(), null, string.Empty);
            }
            ns = body[..comma].ToString();
            body = body[(comma + 1)..];
        }

        var digits = 0;
        while (digits < body.Length && char.IsAsciiDigit(body[digits]))
        {
            digits++;
        }

        int? ackId = digits > 0 ? int.Parse(body[..digits]) : null;
        return (ns, ackId, body[digits..].ToString());
    }

    /// <summary>
    /// Reads an <c>EVENT</c> body into its name and first argument.
    /// </summary>
    /// <param name="ns">Namespace the frame targeted.</param>
    /// <param name="ackId">Ack id the client expects, if any.</param>
    /// <param name="json">The JSON array text, e.g. <c>["join",{...}]</c>.</param>
    /// <param name="parsed">The decoded event on success.</param>
    /// <returns>True when the body was a well-formed event array with a string name.</returns>
    public static bool TryReadEvent(
        string ns,
        int? ackId,
        string json,
        out SocketIoEvent parsed)
    {
        parsed = default;
        if (string.IsNullOrEmpty(json))
        {
            return false;
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(json);
        }
        catch (JsonException)
        {
            return false;
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Array || root.GetArrayLength() == 0)
            {
                return false;
            }

            var nameElement = root[0];
            if (nameElement.ValueKind != JsonValueKind.String)
            {
                return false;
            }

            // Clone so the argument outlives the JsonDocument being disposed.
            var data = root.GetArrayLength() > 1 ? root[1].Clone() : default;
            parsed = new SocketIoEvent(ns, ackId, nameElement.GetString()!, data);
            return true;
        }
    }
}
