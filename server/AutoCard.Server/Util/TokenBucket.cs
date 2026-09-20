namespace AutoCard.Server.Util;

/// <summary>
/// A per-session token bucket limiting how fast intents may arrive.
/// </summary>
/// <remarks>
/// A flood cannot corrupt state — the engine re-validates everything — but each
/// room's engine is single-threaded, so an unthrottled client can starve its
/// opponent. This is the cheap fix at the edge.
/// </remarks>
/// <param name="capacity">Burst size, in tokens.</param>
/// <param name="refillPerSecond">Steady-state rate, in tokens per second.</param>
public sealed class TokenBucket(double capacity, double refillPerSecond)
{
    private readonly Lock _gate = new();
    private readonly double _capacity = capacity;
    private double _tokens = capacity;
    private long _lastTicks = Environment.TickCount64;

    /// <summary>
    /// Consumes one token if any remain.
    /// </summary>
    /// <returns>True when the caller may proceed; false when it is being throttled.</returns>
    public bool TryConsume()
    {
        lock (_gate)
        {
            var now = Environment.TickCount64;
            var elapsed = (now - _lastTicks) / 1000.0;
            _lastTicks = now;

            _tokens = Math.Min(_capacity, _tokens + (elapsed * refillPerSecond));
            if (_tokens < 1.0)
            {
                return false;
            }

            _tokens -= 1.0;
            return true;
        }
    }
}
