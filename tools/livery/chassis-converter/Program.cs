using System.IO.Compression;
using System.Numerics;
using System.Text.Json;
using ForzaTechStudio.Services;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.CarScene;

namespace Kfps.ChassisConverter;

internal sealed class ConversionRequest
{
    public string Archive { get; set; } = "";
    public string Output { get; set; } = "";
    public string CarbinEntry { get; set; } = "";
    public List<string> Entries { get; set; } = [];
}

internal sealed record ChassisMesh(
    string Name,
    string SourceEntry,
    string MaterialName,
    string Role,
    string PartType,
    string InstanceIdentity,
    bool StockPart,
    int AllowedSides,
    Vector3[] Positions,
    Vector3[] Normals,
    Dictionary<int, Vector2[]> UvChannels,
    int[] Indices);

internal sealed record ModelInstance(
    string Path,
    Matrix4x4 Transform,
    string BoneName,
    short BoneId,
    CCarParts PartType,
    bool WindowHint,
    string Identity);

internal sealed record ImportedModel(Bundle Bundle, ImporterResult Imported);

internal sealed record ChassisExtraction(
    List<ChassisMesh> Meshes,
    int RequestedInstances,
    int ResolvedInstances,
    string[] UnresolvedPaths);

internal static class Program
{
    private const int MaxEntries = 256;
    private const long MaxModelBytes = 512L * 1024 * 1024;
    private const int SideFront = 1 << 0;
    private const int SideBack = 1 << 1;
    private const int SideTop = 1 << 2;
    private const int SideLeft = 1 << 3;
    private const int SideRight = 1 << 4;
    private const int SideSpoiler = 1 << 5;
    private const int SideGlassFront = 1 << 6;
    private const int SideGlassBack = 1 << 7;
    private const int SideGlassTop = 1 << 8;
    private const int SideGlassLeft = 1 << 9;
    private const int SideGlassRight = 1 << 10;
    private const int AllBodySides = 0x1F;
    private const int AllGlassSides = 0x7C0;

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 2 || args[0] != "--request")
                throw new InvalidDataException("Usage: Kfps.ChassisConverter --request <request.json>");

            var requestPath = Path.GetFullPath(args[1]);
            var request = JsonSerializer.Deserialize<ConversionRequest>(File.ReadAllText(requestPath), JsonOptions())
                ?? throw new InvalidDataException("The conversion request is empty.");
            var archivePath = Path.GetFullPath(request.Archive);
            var outputPath = Path.GetFullPath(request.Output);
            if (!File.Exists(archivePath))
                throw new FileNotFoundException("The selected FH6 car archive does not exist.", archivePath);
            if (string.IsNullOrWhiteSpace(request.CarbinEntry)
                && request.Entries.Count is < 1 or > MaxEntries)
                throw new InvalidDataException($"The request must contain between 1 and {MaxEntries} model entries.");
            if (request.Entries.Any(entry => string.IsNullOrWhiteSpace(entry)))
                throw new InvalidDataException("The request contains an empty model entry.");

            var sceneAssembled = !string.IsNullOrWhiteSpace(request.CarbinEntry);
            var extraction = sceneAssembled
                ? ExtractSceneMeshes(archivePath, request.CarbinEntry)
                : ExtractLooseMeshes(archivePath, request.Entries);
            var meshes = extraction.Meshes;
            if (meshes.Count == 0)
                throw new InvalidDataException("The selected car scene contained no renderable triangle meshes.");
            if (!meshes.Any(mesh => mesh.Role == "paint" && mesh.UvChannels.ContainsKey(3)))
                throw new InvalidDataException("The converted chassis has no livery-bearing paint geometry with TEXCOORD_3.");

            Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
            var temporary = outputPath + $".{Environment.ProcessId}.tmp";
            try
            {
                GlbWriter.Write(temporary, meshes);
                File.Move(temporary, outputPath, true);
            }
            finally
            {
                if (File.Exists(temporary)) File.Delete(temporary);
            }

            Console.WriteLine(JsonSerializer.Serialize(new
            {
                format = "kfps_local_chassis_conversion_v3",
                output = outputPath,
                mesh_count = meshes.Count,
                paint_meshes = meshes.Count(mesh => mesh.Role == "paint"),
                glass_meshes = meshes.Count(mesh => mesh.Role == "glass"),
                triangle_count = meshes.Sum(mesh => mesh.Indices.Length / 3),
                source_entry_count = meshes.Select(mesh => mesh.SourceEntry)
                    .Distinct(StringComparer.OrdinalIgnoreCase).Count(),
                scene_assembled = sceneAssembled,
                requested_instance_count = extraction.RequestedInstances,
                resolved_instance_count = extraction.ResolvedInstances,
                unresolved_instance_count = extraction.UnresolvedPaths.Length,
                unresolved_paths = extraction.UnresolvedPaths,
            }, JsonOptions()));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
    }

    private static ChassisExtraction ExtractSceneMeshes(string archivePath, string requestedCarbin)
    {
        using var archive = ZipFile.OpenRead(archivePath);
        var available = archive.Entries.ToDictionary(entry => entry.FullName, StringComparer.OrdinalIgnoreCase);
        if (!available.TryGetValue(requestedCarbin, out var carbinEntry))
            throw new InvalidDataException($"The car archive has no requested car scene: {requestedCarbin}");
        if (carbinEntry.Length <= 0 || carbinEntry.Length > MaxModelBytes)
            throw new InvalidDataException("The selected car scene has an unsupported size.");

        var carbin = new CarbinFile();
        using (var source = carbinEntry.Open())
        using (var stream = new MemoryStream(checked((int)carbinEntry.Length)))
        {
            source.CopyTo(stream);
            stream.Position = 0;
            try
            {
                carbin.Load(stream);
            }
            catch (Exception error)
            {
                throw new InvalidDataException(
                    $"Car scene {requestedCarbin} failed at byte {stream.Position} of {stream.Length}: {error.Message}",
                    error);
            }
        }
        if (carbin.Scene is null)
            throw new InvalidDataException("The selected car scene is empty.");

        var instances = StockModelInstances(carbin.Scene);
        if (instances.Count == 0)
            throw new InvalidDataException("The selected car scene contains no stock model instances.");

        var mediaName = string.IsNullOrWhiteSpace(carbin.Scene.MediaName)
            ? Path.GetFileNameWithoutExtension(requestedCarbin)
            : carbin.Scene.MediaName;
        var cache = new Dictionary<string, ImportedModel>(StringComparer.OrdinalIgnoreCase);
        var result = new List<ChassisMesh>();
        var resolved = 0;
        var unresolved = new List<string>();
        foreach (var instance in instances)
        {
            var entryName = ResolveModelEntry(instance.Path, mediaName, available);
            if (entryName is null)
            {
                unresolved.Add(instance.Path);
                continue;
            }
            if (entryName.Contains("__slod", StringComparison.OrdinalIgnoreCase))
                continue;
            if (!cache.TryGetValue(entryName, out var model))
            {
                model = LoadModel(available[entryName], entryName);
                cache[entryName] = model;
            }
            var instanceTransform = instance.Transform;
            if (FindBoneWorld(model.Bundle, instance.BoneName, instance.BoneId) is Matrix4x4 boneWorld)
                instanceTransform = instance.Transform * boneWorld;
            var before = result.Count;
            AppendMeshes(result, model.Imported, entryName, instance, instanceTransform);
            if (result.Count > before) resolved++;
            else unresolved.Add(instance.Path);
        }
        return new ChassisExtraction(
            result,
            instances.Count,
            resolved,
            unresolved.Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(value => value).ToArray());
    }

    private static ChassisExtraction ExtractLooseMeshes(string archivePath, IReadOnlyList<string> requested)
    {
        using var archive = ZipFile.OpenRead(archivePath);
        var available = archive.Entries.ToDictionary(entry => entry.FullName, StringComparer.OrdinalIgnoreCase);
        var result = new List<ChassisMesh>();
        foreach (var requestedName in requested)
        {
            if (!available.TryGetValue(requestedName, out var entry))
                throw new InvalidDataException($"The car archive has no requested model entry: {requestedName}");
            var model = LoadModel(entry, requestedName);
            var instance = new ModelInstance(
                requestedName,
                Matrix4x4.Identity,
                "",
                -1,
                CCarParts.CarBody,
                false,
                $"legacy:{requestedName}");
            AppendMeshes(result, model.Imported, requestedName, instance, Matrix4x4.Identity);
        }
        return new ChassisExtraction(result, requested.Count, requested.Count, []);
    }

    private static ImportedModel LoadModel(ZipArchiveEntry entry, string entryName)
    {
        if (entry.Length <= 0 || entry.Length > MaxModelBytes)
            throw new InvalidDataException($"Model entry {entryName} has an unsupported size.");
        using var source = entry.Open();
        using var memory = new MemoryStream(checked((int)entry.Length));
        source.CopyTo(memory);
        memory.Position = 0;
        var bundle = new Bundle();
        bundle.Load(memory);
        return new ImportedModel(bundle, new ModelImporter().ExtractModels(bundle));
    }

    private static void AppendMeshes(
        List<ChassisMesh> result,
        ImporterResult imported,
        string sourceEntry,
        ModelInstance instance,
        Matrix4x4 instanceTransform)
    {
        var primaryLod = imported.Meshes.Where(geometry => geometry.SourceMesh.LOD_LODS).ToList();
        var selected = primaryLod.Count > 0 ? primaryLod : imported.Meshes;
        foreach (var geometry in selected)
        {
            if (geometry.RawPositions is not { Length: > 0 } || geometry.Indices is not { Length: >= 3 })
                continue;
            if (geometry.Indices.Length % 3 != 0 || geometry.SourceMesh.Topology != 4)
                throw new InvalidDataException($"Mesh {geometry.Name} does not use a triangle-list topology.");

            var positions = TransformPositions(geometry, instanceTransform);
            var normals = TransformNormals(geometry, instanceTransform);
            var indices = CleanTriangleIndices(geometry.Indices);
            ValidateGeometry(geometry.Name, positions, normals, indices);
            var uvs = TransformUvChannels(geometry, positions.Length);
            var identity = $"{sourceEntry} {geometry.Name} {geometry.MaterialName}";
            var hasUv3 = uvs.ContainsKey(3);
            var role = ClassifyRole(
                identity,
                hasUv3,
                instance.WindowHint,
                geometry.Name,
                geometry.MaterialName ?? "");
            result.Add(new ChassisMesh(
                $"{Path.GetFileNameWithoutExtension(sourceEntry)} :: {geometry.Name}",
                sourceEntry,
                geometry.MaterialName ?? "",
                role,
                instance.PartType.ToString(),
                instance.Identity,
                true,
                RenderedLiverySides(role, geometry.Name, hasUv3),
                positions,
                normals,
                uvs,
                indices));
        }
    }

    private static List<ModelInstance> StockModelInstances(Scene scene)
    {
        var output = new List<ModelInstance>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        void Add(CarRenderModel model, CCarParts partType, bool stock)
        {
            if (!stock || string.IsNullOrWhiteSpace(model.Path)) return;
            var key = InstanceKey(model, partType);
            if (!seen.Add(key)) return;
            output.Add(new ModelInstance(
                model.Path,
                model.Transform,
                model.BoneName ?? "",
                model.BoneId,
                partType,
                model.IsInteriorWindshield || model.IsLeftSideWindow != 0 || model.IsRightSideWindow != 0,
                key));
        }

        foreach (var entry in scene.NonUpgradableParts)
            foreach (var model in entry.Part.Models)
                Add(model, entry.Type, true);

        foreach (var part in scene.UpgradableParts)
        {
            var stock = part.Upgrades.Where(upgrade => upgrade.IsStock).ToList();
            if (stock.Count == 0 && part.Upgrades.Count > 0)
            {
                var lowestLevel = part.Upgrades.Min(upgrade => upgrade.Level);
                stock = part.Upgrades
                    .Where(upgrade => upgrade.Level == lowestLevel)
                    .OrderBy(upgrade => upgrade.Id)
                    .Take(1)
                    .ToList();
            }
            var stockIds = stock.Select(upgrade => upgrade.Id).ToHashSet();
            foreach (var upgrade in stock)
                foreach (var model in upgrade.Models)
                    Add(model, part.Type, true);
            foreach (var shared in part.SharedModels)
            {
                var selected = shared.UpgradeIds.Count == 0 || shared.UpgradeIds.Any(stockIds.Contains);
                Add(shared.Model, part.Type, selected);
            }
        }
        return output;
    }

    private static string InstanceKey(CarRenderModel model, CCarParts partType)
    {
        var matrix = new[]
        {
            model.Transform.M11, model.Transform.M12, model.Transform.M13, model.Transform.M14,
            model.Transform.M21, model.Transform.M22, model.Transform.M23, model.Transform.M24,
            model.Transform.M31, model.Transform.M32, model.Transform.M33, model.Transform.M34,
            model.Transform.M41, model.Transform.M42, model.Transform.M43, model.Transform.M44,
        };
        return string.Join("|", new[]
        {
            model.Path.Replace('\\', '/').ToLowerInvariant(),
            (model.BoneName ?? "").ToLowerInvariant(),
            model.BoneId.ToString(),
            ((uint)partType).ToString(),
            string.Join(",", matrix.Select(value => BitConverter.SingleToInt32Bits(value).ToString("X8"))),
        });
    }

    private static string? ResolveModelEntry(
        string gamePath,
        string mediaName,
        IReadOnlyDictionary<string, ZipArchiveEntry> available)
    {
        var normalized = gamePath.Replace('\\', '/').Trim();
        var candidates = new List<string>();
        var marker = $"/{mediaName}/";
        var modelIndex = normalized.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        if (modelIndex >= 0)
            candidates.Add(normalized[(modelIndex + marker.Length)..].TrimStart('/'));
        var sceneIndex = normalized.IndexOf("/scene/", StringComparison.OrdinalIgnoreCase);
        if (sceneIndex >= 0)
            candidates.Add(normalized[(sceneIndex + 1)..].TrimStart('/'));
        foreach (var candidate in candidates.Distinct(StringComparer.OrdinalIgnoreCase))
            if (available.TryGetValue(candidate, out var exact))
                return exact.FullName;

        var fileName = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries).LastOrDefault() ?? "";
        var matches = available.Keys
            .Where(key => candidates.Any(candidate => key.EndsWith('/' + candidate, StringComparison.OrdinalIgnoreCase))
                || string.Equals(
                    key.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries).LastOrDefault(),
                    fileName,
                    StringComparison.OrdinalIgnoreCase))
            .ToList();
        return matches.Count == 1 ? available[matches[0]].FullName : null;
    }

    private static Matrix4x4? FindBoneWorld(Bundle bundle, string name, short id)
    {
        var skeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();
        if (skeleton is null || skeleton.Bones.Count == 0) return null;
        var target = -1;
        if (!string.IsNullOrWhiteSpace(name))
            target = skeleton.Bones.FindIndex(bone => string.Equals(bone.Name, name, StringComparison.OrdinalIgnoreCase));
        if (target < 0 && id >= 0 && id < skeleton.Bones.Count) target = id;
        if (target < 0) return null;

        var cache = new Matrix4x4?[skeleton.Bones.Count];
        var visiting = new bool[skeleton.Bones.Count];
        Matrix4x4 Resolve(int index)
        {
            if (cache[index] is Matrix4x4 ready) return ready;
            if (visiting[index]) throw new InvalidDataException("A model skeleton contains a parent cycle.");
            visiting[index] = true;
            var bone = skeleton.Bones[index];
            var world = bone.Matrix;
            if (bone.ParentId >= 0 && bone.ParentId < skeleton.Bones.Count)
                world *= Resolve(bone.ParentId);
            visiting[index] = false;
            cache[index] = world;
            return world;
        }
        return Resolve(target);
    }

    private static Dictionary<int, Vector2[]> TransformUvChannels(ForzaGeometryData geometry, int vertexCount)
    {
        var output = new Dictionary<int, Vector2[]>();
        var transforms = geometry.SourceMesh.TexCoordTransforms;
        foreach (var (channel, source) in geometry.UvChannels)
        {
            if (channel is < 0 or > 3 || source.Length != vertexCount)
                continue;
            var transform = transforms is { Length: > 0 } && channel < transforms.Length
                ? transforms[channel]
                : new Vector4(0.0f, 1.0f, 0.0f, 1.0f);
            var values = new Vector2[source.Length];
            for (var index = 0; index < source.Length; index++)
            {
                var value = source[index];
                values[index] = new Vector2(
                    value.X * transform.Y + transform.X,
                    (1.0f - value.Y) * transform.W + transform.Z);
            }
            if (values.Any(value => !float.IsFinite(value.X) || !float.IsFinite(value.Y)))
                throw new InvalidDataException($"Mesh {geometry.Name} contains a non-finite UV coordinate.");
            output[channel] = values;
        }
        return output;
    }

    private static int[] CleanTriangleIndices(IReadOnlyList<int> source)
    {
        var output = new List<int>(source.Count);
        var faces = new HashSet<(int A, int B, int C)>();
        for (var index = 0; index < source.Count; index += 3)
        {
            var a = source[index];
            var b = source[index + 1];
            var c = source[index + 2];
            if (a == b || b == c || a == c)
                continue;
            var sorted = new[] { a, b, c };
            Array.Sort(sorted);
            if (!faces.Add((sorted[0], sorted[1], sorted[2])))
                continue;
            output.Add(a);
            output.Add(c);
            output.Add(b);
        }
        return output.ToArray();
    }

    private static void ValidateGeometry(
        string name,
        IReadOnlyList<Vector3> positions,
        IReadOnlyList<Vector3> normals,
        IReadOnlyList<int> indices)
    {
        if (positions.Count == 0 || normals.Count != positions.Count)
            throw new InvalidDataException($"Mesh {name} has an invalid vertex or normal count.");
        if (positions.Any(value => !float.IsFinite(value.X) || !float.IsFinite(value.Y) || !float.IsFinite(value.Z)))
            throw new InvalidDataException($"Mesh {name} contains a non-finite vertex.");
        if (normals.Any(value => !float.IsFinite(value.X) || !float.IsFinite(value.Y) || !float.IsFinite(value.Z)))
            throw new InvalidDataException($"Mesh {name} contains a non-finite normal.");
        if (indices.Any(index => index < 0 || index >= positions.Count))
            throw new InvalidDataException($"Mesh {name} contains an out-of-range index.");
    }

    private static Vector3[] TransformPositions(ForzaGeometryData geometry, Matrix4x4 instanceTransform)
    {
        var mesh = geometry.SourceMesh;
        var output = new Vector3[geometry.RawPositions.Length];
        for (var index = 0; index < output.Length; index++)
        {
            var raw = geometry.RawPositions[index];
            var local = new Vector3(
                raw.X * mesh.PositionScale.X + mesh.PositionTranslate.X,
                raw.Y * mesh.PositionScale.Y + mesh.PositionTranslate.Y,
                raw.Z * mesh.PositionScale.Z + mesh.PositionTranslate.Z);
            var transformed = geometry.BoneTransform == Matrix4x4.Identity
                ? local
                : Vector3.Transform(local, geometry.BoneTransform);
            if (instanceTransform != Matrix4x4.Identity)
                transformed = Vector3.Transform(transformed, instanceTransform);
            output[index] = new Vector3(-transformed.X, transformed.Y, transformed.Z);
        }
        return output;
    }

    private static Vector3[] TransformNormals(ForzaGeometryData geometry, Matrix4x4 instanceTransform)
    {
        var count = geometry.RawPositions.Length;
        var output = new Vector3[count];
        var input = geometry.Normals;
        var scale = geometry.SourceMesh.PositionScale;
        for (var index = 0; index < count; index++)
        {
            var normal = input is { Length: > 0 } && index < input.Length ? input[index] : Vector3.UnitY;
            if (MathF.Abs(scale.X) > 0.000001f) normal.X /= scale.X;
            if (MathF.Abs(scale.Y) > 0.000001f) normal.Y /= scale.Y;
            if (MathF.Abs(scale.Z) > 0.000001f) normal.Z /= scale.Z;
            if (geometry.BoneTransform != Matrix4x4.Identity)
                normal = TransformNormal(normal, geometry.BoneTransform);
            if (instanceTransform != Matrix4x4.Identity)
                normal = TransformNormal(normal, instanceTransform);
            normal.X = -normal.X;
            output[index] = normal.LengthSquared() > 0.000001f ? Vector3.Normalize(normal) : Vector3.UnitY;
        }
        return output;
    }

    private static Vector3 TransformNormal(Vector3 normal, Matrix4x4 transform)
    {
        if (!Matrix4x4.Invert(transform, out var inverse))
            throw new InvalidDataException("A car scene instance has a non-invertible transform.");
        return Vector3.TransformNormal(normal, Matrix4x4.Transpose(inverse));
    }

    internal static string ClassifyRole(
        string identity,
        bool hasUv3,
        bool windowHint = false,
        string meshName = "",
        string materialName = "")
    {
        var value = identity.ToLowerInvariant();
        var sourceName = string.IsNullOrWhiteSpace(meshName) ? identity : meshName;
        var windowSide = AllowedWindowSide(sourceName);
        if (IsInteriorWindowShell(sourceName)) return "hidden";
        if (hasUv3
            && windowSide != 0
            && !IsRejectedWindowMaterial(materialName)
            && (windowHint || IsWindowGlassMaterial(materialName) || value.Contains("/windows/") || value.Contains("\\windows\\")))
            return "glass";
        if (hasUv3 && IsBodyPaintMaterial(materialName)) return "paint";
        if (value.Contains("shadow")) return "hidden";
        if (value.Contains("blackglass") || value.Contains("gls_clear") || value.Contains("undercarriage") || value.Contains("tire"))
            return "dark";
        return "trim";
    }

    private static bool IsBodyPaintMaterial(string rawName)
    {
        var name = rawName.ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(name) || name.Contains("caliper") || name.Contains("texture"))
            return false;
        return name.StartsWith("carpaint", StringComparison.Ordinal)
            || name.StartsWith("car_paint", StringComparison.Ordinal);
    }

    private static bool IsWindowGlassMaterial(string rawName)
    {
        var name = rawName.ToLowerInvariant();
        if (IsRejectedWindowMaterial(name)) return false;
        return name.Contains("window")
            || name.Contains("windshield")
            || name.Contains("windsheild")
            || name.Contains("blackglass");
    }

    private static bool IsRejectedWindowMaterial(string rawName)
    {
        var name = rawName.ToLowerInvariant();
        return name.Contains("screw")
            || name.Contains("frame")
            || name.Contains("label")
            || name.Contains("bulb")
            || name.Contains("light");
    }

    private static bool IsInteriorWindowShell(string rawName)
    {
        var name = rawName.ToLowerInvariant();
        var separator = name.IndexOf('|');
        if (separator >= 0) name = name[..separator];
        return name.StartsWith("glass", StringComparison.Ordinal) && name.Contains("int");
    }

    private static int AllowedWindowSide(string rawName)
    {
        var name = rawName.ToLowerInvariant();
        var separator = name.IndexOf('|');
        if (separator >= 0) name = name[..separator];
        if (name.Contains("int")) return 0;
        if (name.StartsWith("glassf_", StringComparison.Ordinal)) return SideGlassFront;
        if (name.StartsWith("glassr_", StringComparison.Ordinal)) return SideGlassBack;
        if (name.StartsWith("glasstop_", StringComparison.Ordinal)
            || name.StartsWith("glassroof_", StringComparison.Ordinal)) return SideGlassTop;
        if (name.StartsWith("glasslf_", StringComparison.Ordinal)
            || name.StartsWith("glasslr_", StringComparison.Ordinal)) return SideGlassLeft;
        if (name.StartsWith("glassrf_", StringComparison.Ordinal)
            || name.StartsWith("glassrr_", StringComparison.Ordinal)) return SideGlassRight;
        return 0;
    }

    private static bool IsSpoilerMesh(string name)
    {
        var value = name.ToLowerInvariant();
        return !value.Contains("mirror") && (value.Contains("spoiler") || value.Contains("wing"));
    }

    private static bool IsTrunkPanelMesh(string name) =>
        name.StartsWith("trunk", StringComparison.OrdinalIgnoreCase) && !IsSpoilerMesh(name);

    private static int RenderedLiverySides(string role, string meshName, bool hasUv3)
    {
        if (!hasUv3) return 0;
        if (role == "glass") return AllGlassSides;
        if (role != "paint") return 0;
        if (IsSpoilerMesh(meshName)) return SideSpoiler;
        if (IsTrunkPanelMesh(meshName)) return SideBack | SideTop;
        return AllBodySides;
    }

    private static JsonSerializerOptions JsonOptions() => new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
    };
}
