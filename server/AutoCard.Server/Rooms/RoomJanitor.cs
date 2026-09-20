using AutoCard.Server.Configuration;

using Microsoft.Extensions.Options;

namespace AutoCard.Server.Rooms;

/// <summary>
/// Disposes rooms whose players have all been gone past the reconnect grace.
/// </summary>
/// <remarks>
/// Each room holds a Python <c>GameEngine</c> open, so an unswept relay leaks one
/// engine per abandoned match until the process restarts.
/// </remarks>
public sealed class RoomJanitor(
    RoomRegistry rooms,
    IOptions<ServerOptions> options,
    ILogger<RoomJanitor> logger) : BackgroundService
{
    /// <inheritdoc/>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var period = TimeSpan.FromSeconds(Math.Max(1, options.Value.SweepIntervalSeconds));
        using var timer = new PeriodicTimer(period);

        try
        {
            while (await timer.WaitForNextTickAsync(stoppingToken))
            {
                var disposed = await rooms.SweepIdleAsync();
                if (disposed > 0)
                {
                    logger.LogDebug("Swept {Count} idle rooms; {Live} remain", disposed, rooms.Count);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Host shutdown.
        }
        finally
        {
            await rooms.DisposeAllAsync();
        }
    }
}
