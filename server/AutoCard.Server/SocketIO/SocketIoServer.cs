using System.Buffers;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace AutoCard.Server.SocketIO;

/// <summary>Tuning for the Socket.IO endpoint.</summary>
public sealed class SocketIoOptions
{
    /// <summary>How often the server pings an idle client, in milliseconds.</summary>
    public int PingIntervalMs { get; set; } = 25_000;

    /// <summary>How long the client may take to pong before it is dropped, in milliseconds.</summary>
    public int PingTimeoutMs { get; set; } = 20_000;

    /// <summary>Largest inbound frame accepted, in bytes. Intents are a few hundred bytes.</summary>
    public int MaxPayloadBytes { get; set; } = 64 * 1024;
}

/// <summary>
/// A minimal Socket.IO v5 server speaking only the WebSocket transport.
/// </summary>
/// <remarks>
/// Written by hand rather than taken from a library because the surface actually
/// used is tiny — a handshake, named events in one namespace, and heartbeats —
/// and because no maintained .NET Socket.IO <em>server</em> tracks the v4 protocol
/// that <c>socket.io-client</c> 4.x speaks.
/// </remarks>
public sealed class SocketIoServer(ILogger<SocketIoServer> logger, SocketIoOptions options)
{
    private readonly ConcurrentDictionary<string, SocketIoConnection> _connections = new();
    private readonly Dictionary<string, Func<SocketIoConnection, JsonElement, Task>> _handlers = [];

    /// <summary>Raised once a client has completed the Socket.IO handshake.</summary>
    public Func<SocketIoConnection, Task>? Connected { get; set; }

    /// <summary>Raised once a client's socket has gone away, for any reason.</summary>
    public Func<SocketIoConnection, Task>? Disconnected { get; set; }

    /// <summary>Registers the handler for one event name.</summary>
    /// <param name="name">Event name the client emits.</param>
    /// <param name="handler">Callback receiving the connection and the first argument.</param>
    public void On(string name, Func<SocketIoConnection, JsonElement, Task> handler) =>
        _handlers[name] = handler;

    /// <summary>All currently connected clients.</summary>
    public IEnumerable<SocketIoConnection> Connections => _connections.Values;

    /// <summary>
    /// Serves one accepted WebSocket for its whole lifetime.
    /// </summary>
    /// <param name="socket">The accepted socket.</param>
    /// <param name="cancellationToken">Fires when the host shuts down.</param>
    public async Task ServeAsync(WebSocket socket, CancellationToken cancellationToken)
    {
        var sid = Guid.NewGuid().ToString("N");
        var connection = new SocketIoConnection(sid, socket, logger);
        _connections[sid] = connection;

        var pump = connection.PumpAsync(cancellationToken);
        connection.Send(SocketIoCodec.Open(
            sid, options.PingIntervalMs, options.PingTimeoutMs, options.MaxPayloadBytes));

        var lastSeen = DateTimeOffset.UtcNow;
        using var heartbeat = new CancellationTokenSource();
        var pinger = PingAsync(connection, () => lastSeen, heartbeat.Token);

        try
        {
            await ReadLoopAsync(connection, socket, () => lastSeen = DateTimeOffset.UtcNow, cancellationToken);
        }
        catch (OperationCanceledException)
        {
            // Host shutdown.
        }
        catch (WebSocketException ex)
        {
            logger.LogDebug(ex, "Socket {Sid} ended abnormally", sid);
        }
        finally
        {
            _connections.TryRemove(sid, out _);
            await heartbeat.CancelAsync();
            await connection.CloseAsync();

            if (Disconnected is not null)
            {
                await Disconnected(connection);
            }

            await Task.WhenAll(pump, pinger);
        }
    }

    /// <summary>Reads frames until the client goes away.</summary>
    private async Task ReadLoopAsync(
        SocketIoConnection connection,
        WebSocket socket,
        Action markSeen,
        CancellationToken cancellationToken)
    {
        var buffer = ArrayPool<byte>.Shared.Rent(8 * 1024);
        var message = new MemoryStream();

        try
        {
            while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                var result = await socket.ReceiveAsync(buffer, cancellationToken);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    return;
                }

                message.Write(buffer, 0, result.Count);
                if (message.Length > options.MaxPayloadBytes)
                {
                    logger.LogWarning("Frame from {Sid} exceeded the payload cap", connection.Sid);
                    return;
                }

                if (!result.EndOfMessage)
                {
                    continue;
                }

                var frame = Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length);
                message.SetLength(0);

                markSeen();
                await HandleFrameAsync(connection, frame);
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
            await message.DisposeAsync();
        }
    }

    /// <summary>Routes one decoded Engine.IO frame.</summary>
    private async Task HandleFrameAsync(SocketIoConnection connection, string frame)
    {
        if (frame.Length == 0)
        {
            return;
        }

        switch (frame[0])
        {
            case EngineIoType.Ping:
                // Some clients ping first; answer so they do not time us out.
                connection.Send(EngineIoType.Pong.ToString());
                return;

            case EngineIoType.Pong:
                return;

            case EngineIoType.Close:
                await connection.CloseAsync();
                return;

            case EngineIoType.Message:
                await HandleMessageAsync(connection, frame);
                return;

            default:
                logger.LogDebug("Ignoring unsupported frame type {Type}", frame[0]);
                return;
        }
    }

    /// <summary>Routes one Socket.IO packet carried inside an Engine.IO message.</summary>
    /// <param name="frame">The whole frame, including the Engine.IO message digit.</param>
    private async Task HandleMessageAsync(SocketIoConnection connection, string frame)
    {
        if (frame.Length < 2)
        {
            return;
        }

        var type = frame[1];
        var (ns, ackId, json) = SocketIoCodec.SplitBody(frame.AsSpan(2));

        if (ns != SocketIoCodec.RootNamespace)
        {
            connection.Send(SocketIoCodec.ConnectError("Invalid namespace"));
            return;
        }

        switch (type)
        {
            case SocketIoType.Connect:
                if (!string.IsNullOrEmpty(json))
                {
                    try
                    {
                        connection.Auth = JsonDocument.Parse(json).RootElement.Clone();
                    }
                    catch (JsonException)
                    {
                        // An unparseable auth blob is not fatal; the relay does
                        // not require one.
                    }
                }

                connection.Send(SocketIoCodec.Connect(connection.Sid));
                if (Connected is not null)
                {
                    await Connected(connection);
                }
                return;

            case SocketIoType.Disconnect:
                await connection.CloseAsync();
                return;

            case SocketIoType.Event:
                if (!SocketIoCodec.TryReadEvent(ns, ackId, json, out var parsed))
                {
                    logger.LogDebug("Malformed event from {Sid}", connection.Sid);
                    return;
                }

                if (_handlers.TryGetValue(parsed.Name, out var handler))
                {
                    await handler(connection, parsed.Data);
                }
                return;

            default:
                return;
        }
    }

    /// <summary>Pings the client on an interval and drops it when pongs stop.</summary>
    private async Task PingAsync(
        SocketIoConnection connection,
        Func<DateTimeOffset> lastSeen,
        CancellationToken cancellationToken)
    {
        var period = TimeSpan.FromMilliseconds(options.PingIntervalMs);
        var deadline = period + TimeSpan.FromMilliseconds(options.PingTimeoutMs);

        try
        {
            using var timer = new PeriodicTimer(period);
            while (await timer.WaitForNextTickAsync(cancellationToken))
            {
                if (DateTimeOffset.UtcNow - lastSeen() > deadline)
                {
                    logger.LogInformation("Dropping {Sid}: heartbeat timed out", connection.Sid);
                    await connection.CloseAsync();
                    return;
                }

                connection.Send(SocketIoCodec.Ping());
            }
        }
        catch (OperationCanceledException)
        {
            // The connection ended first.
        }
    }
}
