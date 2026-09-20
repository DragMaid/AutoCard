using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AutoCard.Server.SocketIO;

/// <summary>
/// JSON settings shared by every message this server writes.
/// </summary>
/// <remarks>
/// Property names are left exactly as declared. The wire protocol is defined by
/// <c>core/network/actions.py</c> and uses snake_case, so the C# DTOs spell their
/// members with explicit <see cref="JsonPropertyNameAttribute"/> values rather
/// than relying on a naming policy that could silently drift.
/// </remarks>
internal static class JsonDefaults
{
    /// <summary>Serializer options used for all outbound frames.</summary>
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = null,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        // Frames are already inside a JSON string context, and the payloads are
        // machine-generated ids, so the relaxed encoder keeps them readable.
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };
}
