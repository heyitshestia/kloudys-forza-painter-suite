using System.Buffers.Binary;
using System.Numerics;
using System.Text;
using System.Text.Json;

namespace Kfps.ChassisConverter;

internal static class GlbWriter
{
    private const uint JsonChunk = 0x4E4F534A;
    private const uint BinChunk = 0x004E4942;

    public static void Write(
        string path,
        IReadOnlyList<ChassisMesh> meshes,
        IReadOnlyList<PartOptionDescriptor> partOptions)
    {
        using var binary = new MemoryStream();
        var bufferViews = new List<object>();
        var accessors = new List<object>();
        var meshRecords = new List<object>();
        var nodes = new List<object>();

        foreach (var mesh in meshes)
        {
            var attributes = new Dictionary<string, int>
            {
                ["POSITION"] = AddVector3Accessor(binary, bufferViews, accessors, mesh.Positions, target: 34962, bounds: true),
                ["NORMAL"] = AddVector3Accessor(binary, bufferViews, accessors, mesh.Normals, target: 34962, bounds: false),
            };
            foreach (var (channel, values) in mesh.UvChannels.OrderBy(item => item.Key))
                attributes[$"TEXCOORD_{channel}"] = AddVector2Accessor(binary, bufferViews, accessors, values, 34962);
            var indexAccessor = AddIndexAccessor(binary, bufferViews, accessors, mesh.Indices);
            var extras = new Dictionary<string, object>
            {
                ["kfps_role"] = mesh.Role,
                ["kfps_source_entry"] = mesh.SourceEntry,
                ["kfps_material_name"] = mesh.MaterialName,
                ["kfps_part_type"] = mesh.PartType,
                ["kfps_instance_identity"] = mesh.InstanceIdentity,
                ["kfps_stock_part"] = mesh.StockPart,
                ["kfps_part_option_ids"] = mesh.PartOptionIds,
                ["kfps_draw_groups"] = mesh.DrawGroups,
                ["kfps_allowed_sides"] = mesh.AllowedSides,
            };
            meshRecords.Add(new
            {
                name = mesh.Name,
                primitives = new[] { new { attributes, indices = indexAccessor, mode = 4 } },
                extras,
            });
            nodes.Add(new { name = mesh.Name, mesh = meshRecords.Count - 1, extras });
        }

        var document = new
        {
            asset = new { version = "2.0", generator = "KFPS local chassis converter" },
            scene = 0,
            scenes = new[]
            {
                new
                {
                    nodes = Enumerable.Range(0, nodes.Count).ToArray(),
                    extras = new
                    {
                        kfps_format = "kfps_local_chassis_scene_v2",
                        kfps_part_options = partOptions.Select(option => new
                        {
                            part_type = option.PartType,
                            part_type_value = option.PartTypeValue,
                            id = option.Id,
                            level = option.Level,
                            car_body_id = option.CarBodyId,
                            parent_is_stock = option.ParentIsStock,
                            stock = option.Stock,
                        }).ToArray(),
                    },
                },
            },
            nodes,
            meshes = meshRecords,
            accessors,
            bufferViews,
            buffers = new[] { new { byteLength = checked((int)binary.Length) } },
        };
        var json = JsonSerializer.SerializeToUtf8Bytes(document, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        });
        var paddedJson = Pad(json, 0x20);
        var paddedBinary = Pad(binary.ToArray(), 0x00);
        var totalLength = checked(12 + 8 + paddedJson.Length + 8 + paddedBinary.Length);

        using var output = File.Create(path);
        using var writer = new BinaryWriter(output, Encoding.UTF8, leaveOpen: false);
        writer.Write(0x46546C67u);
        writer.Write(2u);
        writer.Write((uint)totalLength);
        writer.Write((uint)paddedJson.Length);
        writer.Write(JsonChunk);
        writer.Write(paddedJson);
        writer.Write((uint)paddedBinary.Length);
        writer.Write(BinChunk);
        writer.Write(paddedBinary);
    }

    private static int AddVector3Accessor(
        MemoryStream binary,
        List<object> views,
        List<object> accessors,
        IReadOnlyList<Vector3> values,
        int target,
        bool bounds)
    {
        Align(binary);
        var offset = checked((int)binary.Position);
        foreach (var value in values)
        {
            WriteFloat(binary, value.X);
            WriteFloat(binary, value.Y);
            WriteFloat(binary, value.Z);
        }
        var view = views.Count;
        views.Add(new { buffer = 0, byteOffset = offset, byteLength = values.Count * 12, target });
        object accessor;
        if (bounds)
        {
            var min = new[] { values.Min(value => value.X), values.Min(value => value.Y), values.Min(value => value.Z) };
            var max = new[] { values.Max(value => value.X), values.Max(value => value.Y), values.Max(value => value.Z) };
            accessor = new { bufferView = view, componentType = 5126, count = values.Count, type = "VEC3", min, max };
        }
        else
        {
            accessor = new { bufferView = view, componentType = 5126, count = values.Count, type = "VEC3" };
        }
        accessors.Add(accessor);
        return accessors.Count - 1;
    }

    private static int AddVector2Accessor(
        MemoryStream binary,
        List<object> views,
        List<object> accessors,
        IReadOnlyList<Vector2> values,
        int target)
    {
        Align(binary);
        var offset = checked((int)binary.Position);
        foreach (var value in values)
        {
            WriteFloat(binary, value.X);
            WriteFloat(binary, value.Y);
        }
        var view = views.Count;
        views.Add(new { buffer = 0, byteOffset = offset, byteLength = values.Count * 8, target });
        accessors.Add(new { bufferView = view, componentType = 5126, count = values.Count, type = "VEC2" });
        return accessors.Count - 1;
    }

    private static int AddIndexAccessor(
        MemoryStream binary,
        List<object> views,
        List<object> accessors,
        IReadOnlyList<int> values)
    {
        Align(binary);
        var offset = checked((int)binary.Position);
        Span<byte> encoded = stackalloc byte[4];
        foreach (var value in values)
        {
            if (value < 0) throw new InvalidDataException("A chassis mesh contains a negative index.");
            BinaryPrimitives.WriteUInt32LittleEndian(encoded, checked((uint)value));
            binary.Write(encoded);
        }
        var view = views.Count;
        views.Add(new { buffer = 0, byteOffset = offset, byteLength = values.Count * 4, target = 34963 });
        accessors.Add(new
        {
            bufferView = view,
            componentType = 5125,
            count = values.Count,
            type = "SCALAR",
            min = new[] { values.Min() },
            max = new[] { values.Max() },
        });
        return accessors.Count - 1;
    }

    private static void Align(MemoryStream stream)
    {
        while (stream.Position % 4 != 0) stream.WriteByte(0);
    }

    private static void WriteFloat(Stream stream, float value)
    {
        Span<byte> encoded = stackalloc byte[4];
        BinaryPrimitives.WriteSingleLittleEndian(encoded, value);
        stream.Write(encoded);
    }

    private static byte[] Pad(byte[] source, byte padding)
    {
        var length = (source.Length + 3) & ~3;
        if (length == source.Length) return source;
        var result = new byte[length];
        source.CopyTo(result, 0);
        result.AsSpan(source.Length).Fill(padding);
        return result;
    }
}
