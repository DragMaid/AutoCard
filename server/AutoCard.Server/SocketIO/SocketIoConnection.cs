using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;

namespace AutoCard.Server.SocketIO;

/// <summary>
/// One connected browser, from the handshake until the socket closes.
/// </summary>
/// <remarks>
/// Writes go through a channel drained by a single pump task, because a
/// <see cref="WebSocket"/> tolerates only one concurrent send and patches are
/// broadcast from whichever thread the engine reader happens to be on.
/// </remarks>
public sealed class SocketIoConnection
{
    private readonly WebSocket _socket;
    private readonly Channel<string> _outbound;
    private readonly ILogger _logger;
    private readonly CancellationTokenSource _closing = new();

    /// <summary>Session id, also reported to the client as <c>socket.id</c>.</summary>
    public string Sid { get; }

    /// <summary>Auth payload the client passed to <c>io(url, { auth })</c>, if any.</summary>
    public JsonElement Auth { get; internal set; }

    /// <summary>Per-connection state owned by the application layer.</summary>
    public object? UserState { get; set; }

    /// <summary>True until the socket has begun closing.</summary>
    public bool IsOpen => _socket.State == WebSocketState.Open && !_closing.IsCancellationRequested;

    internal SocketIoConnection(string sid, WebSocket socket, ILogger logger)
    {
        Sid = sid;
        _socket = socket;
        _logger = logger;
        _outbound = Channel.CreateBounded<string>(new BoundedChannelOptions(256)
        {
            // A client too slow to keep up would otherwise grow this unboundedly.
            // Dropping the oldest frame leaves a sequence gap, which the client
            // detects from the patch seq and repairs with REQUEST_SYNC.
            FullMode = BoundedChannelFullMode.DropOldest,
            SingleReader = true,
        });
    }

    /// <summary>Queues a Socket.IO event for this client.</summary>
    /// <param name="name">Event name, e.g. <c>patch</c>.</param>
    /// <param name="payload">Single event argument.</param>
    public void Emit(string name, object? payload) =>
        Send(SocketIoCodec.Event(name, payload));

    /// <summary>Queues a pre-encoded frame.</summary>
    /// <param name="frame">A complete Engine.IO text frame.</param>
    internal void Send(string frame)
    {
        if (!_outbound.Writer.TryWrite(frame))
        {
            _logger.LogWarning("Dropped frame for {Sid}: outbound channel closed", Sid);
        }
    }

    /// <summary>Drains queued frames onto the socket until the connection ends.</summary>
    /// <param name="cancellationToken">Fires when the host is shutting down.</param>
    internal async Task PumpAsync(CancellationToken cancellationToken)
    {
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, _closing.Token);

        try
        {
            await foreach (var frame in _outbound.Reader.ReadAllAsync(linked.Token))
            {
                await _socket.SendAsync(
                    Encoding.UTF8.GetBytes(frame),
                    WebSocketMessageType.Text,
                    endOfMessage: true,
                    linked.Token);
            }
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown.
        }
        catch (WebSocketException ex)
        {
            _logger.LogDebug(ex, "Send failed for {Sid}", Sid);
        }
    }

    /// <summary>Stops the pump and closes the underlying socket.</summary>
    internal async Task CloseAsync()
    {
        if (_closing.IsCancellationRequested)
        {
            return;
        }

        _outbound.Writer.TryComplete();
        await _closing.CancelAsync();

        if (_socket.State == WebSocketState.Open)
        {
            try
            {
                await _socket.CloseAsync(
                    WebSocketCloseStatus.NormalClosure, "closed", CancellationToken.None);
            }
            catch (WebSocketException)
            {
                // The peer may already be gone; nothing useful left to do.
            }
        }
    }
}
