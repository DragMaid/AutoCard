using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;

using AutoCard.Server.SocketIO;

namespace AutoCard.Server.Engine;

/// <summary>
/// The relay's WebSocket connection to one room's Python engine.
/// </summary>
/// <remarks>
/// One socket per room, because the engine keeps one <c>GameEngine</c> per room
/// and serialises intents through a single task. Nothing on this class inspects
/// gameplay: intents go out as the client sent them, and patches come back
/// unread, addressed to a seat by the engine that decided what that seat may
/// see.
/// </remarks>
public sealed class EngineSocket : IAsyncDisposable
{
    private readonly ClientWebSocket _socket = new();
    private readonly Channel<string> _outbound =
        Channel.CreateUnbounded<string>(new UnboundedChannelOptions { SingleReader = true });
    private readonly TaskCompletionSource<RoomReady> _ready =
        new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly CancellationTokenSource _closing = new();
    private readonly ILogger _logger;

    private Task _reader = Task.CompletedTask;
    private Task _writer = Task.CompletedTask;

    /// <summary>
    /// Raised for every patch the engine emits, with the raw JSON body and the
    /// player it is addressed to, or null for one meant for the whole room.
    /// </summary>
    public Func<JsonNode, string?, Task>? PatchReceived { get; set; }

    /// <summary>Raised when the engine refuses an intent.</summary>
    public Func<IntentRejected, Task>? Refused { get; set; }

    /// <summary>Raised once the engine connection has ended, for any reason.</summary>
    public Func<string, Task>? Closed { get; set; }

    /// <summary>Creates an unconnected socket.</summary>
    /// <param name="logger">Logger for transport-level diagnostics.</param>
    public EngineSocket(ILogger logger) => _logger = logger;

    /// <summary>
    /// Opens the room's engine connection and waits for its handshake.
    /// </summary>
    /// <param name="baseUri">Engine service base address, e.g. <c>ws://localhost:9000</c>.</param>
    /// <param name="roomId">Room to open; it becomes the request path.</param>
    /// <param name="mode">Requested mode, <c>pvp</c> or <c>ai</c>.</param>
    /// <param name="timeout">How long to wait for the handshake.</param>
    /// <param name="cancellationToken">Fires when the host shuts down.</param>
    /// <returns>The engine's room description, including its player ids.</returns>
    public async Task<RoomReady> ConnectAsync(
        Uri baseUri,
        string roomId,
        string mode,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var target = new UriBuilder(baseUri)
        {
            Path = $"/{Uri.EscapeDataString(roomId)}",
            Query = $"mode={Uri.EscapeDataString(mode)}",
        }.Uri;

        await _socket.ConnectAsync(target, cancellationToken);

        _reader = ReadLoopAsync();
        _writer = WriteLoopAsync();

        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(timeout);
        return await _ready.Task.WaitAsync(deadline.Token);
    }

    /// <summary>Forwards one intent to the engine, verbatim.</summary>
    /// <param name="intent">The intent object, already stamped with room and actor.</param>
    public void SendIntent(JsonObject intent)
    {
        var envelope = new JsonObject
        {
            ["type"] = EngineMessage.Intent,
            ["intent"] = intent,
        };
        _outbound.Writer.TryWrite(envelope.ToJsonString(JsonDefaults.Options));
    }

    /// <summary>Asks the engine to discard this room's state.</summary>
    public void SendDispose() =>
        _outbound.Writer.TryWrite($"{{\"type\":\"{EngineMessage.Dispose}\"}}");

    /// <summary>Reads engine messages until the socket ends.</summary>
    private async Task ReadLoopAsync()
    {
        var buffer = new byte[64 * 1024];
        var message = new MemoryStream();
        var reason = "engine closed";

        try
        {
            while (_socket.State == WebSocketState.Open && !_closing.IsCancellationRequested)
            {
                var result = await _socket.ReceiveAsync(buffer, _closing.Token);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    break;
                }

                message.Write(buffer, 0, result.Count);
                if (!result.EndOfMessage)
                {
                    continue;
                }

                var text = Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length);
                message.SetLength(0);
                await HandleAsync(text);
            }
        }
        catch (OperationCanceledException)
        {
            reason = "relay closed the engine connection";
        }
        catch (Exception ex)
        {
            reason = $"engine connection failed: {ex.Message}";
            _logger.LogWarning(ex, "Engine socket failed");
        }
        finally
        {
            await message.DisposeAsync();
            _ready.TrySetException(new InvalidOperationException(reason));

            if (Closed is not null)
            {
                await Closed(reason);
            }
        }
    }

    /// <summary>Dispatches one engine message.</summary>
    private async Task HandleAsync(string text)
    {
        JsonNode? node;
        try
        {
            node = JsonNode.Parse(text);
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Unparseable engine message");
            return;
        }

        if (node is not JsonObject envelope ||
            envelope["type"]?.GetValue<string>() is not { } type)
        {
            return;
        }

        switch (type)
        {
            case EngineMessage.RoomReady:
                var ready = envelope.Deserialize<RoomReady>(JsonDefaults.Options);
                if (ready is not null)
                {
                    _ready.TrySetResult(ready);
                }
                return;

            case EngineMessage.Patch:
                if (envelope["patch"] is { } patch && PatchReceived is not null)
                {
                    await PatchReceived(patch, envelope["player_id"]?.GetValue<string>());
                }
                return;

            case EngineMessage.Rejected:
                var refused = envelope.Deserialize<IntentRejected>(JsonDefaults.Options);
                if (refused is not null && Refused is not null)
                {
                    await Refused(refused);
                }
                return;

            default:
                _logger.LogDebug("Ignoring engine message {Type}", type);
                return;
        }
    }

    /// <summary>Drains queued messages onto the engine socket.</summary>
    private async Task WriteLoopAsync()
    {
        try
        {
            await foreach (var text in _outbound.Reader.ReadAllAsync(_closing.Token))
            {
                await _socket.SendAsync(
                    Encoding.UTF8.GetBytes(text),
                    WebSocketMessageType.Text,
                    endOfMessage: true,
                    _closing.Token);
            }
        }
        catch (OperationCanceledException)
        {
            // Room disposed.
        }
        catch (WebSocketException ex)
        {
            _logger.LogDebug(ex, "Engine send failed");
        }
    }

    /// <inheritdoc/>
    /// <remarks>
    /// The writer is drained before anything is cancelled. A room's final
    /// message is its <c>dispose</c>, and cancelling first would discard it —
    /// leaving the engine holding a <c>GameEngine</c> for a match that no longer
    /// exists until its own idle TTL eventually expires.
    /// </remarks>
    public async ValueTask DisposeAsync()
    {
        _outbound.Writer.TryComplete();
        await AwaitLoopAsync(_writer, "writer");

        await _closing.CancelAsync();

        if (_socket.State == WebSocketState.Open)
        {
            try
            {
                await _socket.CloseAsync(
                    WebSocketCloseStatus.NormalClosure, "dispose", CancellationToken.None);
            }
            catch (WebSocketException)
            {
                // Already gone.
            }
        }

        await AwaitLoopAsync(_reader, "reader");

        _socket.Dispose();
        _closing.Dispose();
    }

    /// <summary>Waits for one loop to finish, bounded so a wedged socket cannot block disposal.</summary>
    /// <param name="loop">The loop task.</param>
    /// <param name="name">Which loop, for the log line.</param>
    private async Task AwaitLoopAsync(Task loop, string name)
    {
        try
        {
            await loop.WaitAsync(TimeSpan.FromSeconds(2));
        }
        catch (Exception ex) when (ex is TimeoutException or OperationCanceledException)
        {
            _logger.LogDebug("Engine {Loop} did not finish cleanly", name);
        }
    }
}
