namespace AutoCard.Server.Configuration;

/// <summary>
/// Relay settings, bound from the <c>AutoCard</c> section of configuration.
/// </summary>
public sealed class ServerOptions
{
    /// <summary>Configuration section these options are bound from.</summary>
    public const string Section = "AutoCard";

    /// <summary>Base address of the Python engine service.</summary>
    public string EngineUri { get; set; } = "ws://127.0.0.1:9000";

    /// <summary>
    /// Browser origins allowed to connect. <c>*</c> allows any, which is fine for
    /// local development and wrong for a public deployment.
    /// </summary>
    public string[] AllowedOrigins { get; set; } = ["*"];

    /// <summary>How long a vacated seat is held for its previous occupant, in seconds.</summary>
    public int ReconnectGraceSeconds { get; set; } = 90;

    /// <summary>How long to wait for the engine's room handshake, in seconds.</summary>
    public int EngineHandshakeTimeoutSeconds { get; set; } = 10;

    /// <summary>Steady-state intent allowance per client, per second.</summary>
    public double IntentsPerSecond { get; set; } = 20;

    /// <summary>Burst allowance per client, in intents.</summary>
    public double IntentBurst { get; set; } = 40;

    /// <summary>Upper bound on concurrent rooms, so engines cannot accumulate without limit.</summary>
    public int MaxRooms { get; set; } = 500;

    /// <summary>How often idle rooms are swept, in seconds.</summary>
    public int SweepIntervalSeconds { get; set; } = 15;

    /// <summary>Reconnect grace as a <see cref="TimeSpan"/>.</summary>
    public TimeSpan ReconnectGrace => TimeSpan.FromSeconds(ReconnectGraceSeconds);

    /// <summary>Engine handshake timeout as a <see cref="TimeSpan"/>.</summary>
    public TimeSpan EngineHandshakeTimeout => TimeSpan.FromSeconds(EngineHandshakeTimeoutSeconds);
}
