using AutoCard.Server.Configuration;
using AutoCard.Server.Game;
using AutoCard.Server.Rooms;
using AutoCard.Server.SocketIO;

var builder = WebApplication.CreateBuilder(args);

builder.Services.Configure<ServerOptions>(builder.Configuration.GetSection(ServerOptions.Section));
builder.Services.AddSingleton(new SocketIoOptions());
builder.Services.AddSingleton<SocketIoServer>();
builder.Services.AddSingleton<RoomRegistry>();
builder.Services.AddSingleton<Matchmaker>();
builder.Services.AddSingleton<GameGateway>();
builder.Services.AddHostedService<RoomJanitor>();

var origins = builder.Configuration
    .GetSection($"{ServerOptions.Section}:AllowedOrigins")
    .Get<string[]>() ?? ["*"];

const string CorsPolicy = "autocard-web";
builder.Services.AddCors(cors => cors.AddPolicy(CorsPolicy, policy =>
{
    // The browser opens the WebSocket directly, which is not subject to CORS,
    // but the health endpoint and any future HTTP routes are.
    if (origins.Contains("*"))
    {
        policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod();
    }
    else
    {
        policy.WithOrigins(origins).AllowAnyHeader().AllowAnyMethod().AllowCredentials();
    }
}));

var app = builder.Build();

app.UseCors(CorsPolicy);
app.UseWebSockets(new WebSocketOptions { KeepAliveInterval = TimeSpan.FromSeconds(30) });

var sockets = app.Services.GetRequiredService<SocketIoServer>();
app.Services.GetRequiredService<GameGateway>().Register(sockets);

// socket.io-client appends /socket.io/ to the base URL from VITE_GAME_API.
app.Map("/socket.io/{**rest}", async (HttpContext context) =>
{
    if (!context.WebSockets.IsWebSocketRequest)
    {
        // The frontend connects with transports: ["websocket"], so a polling
        // request means a misconfigured client rather than a fallback to serve.
        context.Response.StatusCode = StatusCodes.Status400BadRequest;
        await context.Response.WriteAsync(
            "This endpoint serves the WebSocket transport only. "
            + "Connect with io(url, { transports: [\"websocket\"] }).");
        return;
    }

    using var socket = await context.WebSockets.AcceptWebSocketAsync();
    await sockets.ServeAsync(socket, context.RequestAborted);
});

app.MapGet("/health", (RoomRegistry rooms) => Results.Ok(new
{
    status = "ok",
    rooms = rooms.Count,
}));

app.Run();
