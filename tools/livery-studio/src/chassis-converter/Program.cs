using System.IO.Compression;
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Numerics;
using System.Text.Json;
using System.Xml;
using System.Xml.Linq;
using ForzaTechStudio.Services;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.Bundles.Metadata;
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
    int[] PartOptionIds,
    int DrawGroups,
    int AllowedSides,
    int ProjectionSides,
    ulong MaterialBindingHash,
    Vector3[] Positions,
    Vector3[] Normals,
    Dictionary<int, Vector2[]> UvChannels,
    int[] Indices,
    Dictionary<string, object> Diagnostics);

internal sealed record ModelInstance(
    string Path,
    Matrix4x4 Transform,
    string BoneName,
    short BoneId,
    CCarParts PartType,
    bool WindowHint,
    string Identity,
    bool StockPart,
    int[] PartOptionIds,
    int DrawGroups,
    IReadOnlyDictionary<string, ulong> MaterialBindings,
    ushort SceneLodFlags = 0,
    bool SnapToParent = false,
    IReadOnlyDictionary<string, byte[]> MaterialOverrides = null);

internal sealed record PartOptionDescriptor(
    string PartType,
    int PartTypeValue,
    int Id,
    int Level,
    int CarBodyId,
    bool ParentIsStock,
    bool Stock,
    bool Baseline = false,
    bool Supported = true,
    bool Empty = false,
    int DeclaredInstances = 0,
    string[] Issues = null);

internal sealed record ImportedModel(Bundle Bundle, ImporterResult Imported, Dictionary<int, object> Materials);
internal sealed record NativeMaskPolicy(int ValidSides, Dictionary<string, object> Evidence);

internal sealed record ChassisExtraction(
    List<ChassisMesh> Meshes,
    int RequestedInstances,
    int ResolvedInstances,
    string[] UnresolvedRequiredPaths,
    string[] SkippedOptionalPaths,
    List<PartOptionDescriptor> PartOptions,
    Dictionary<string, object> Coverage = null);

internal static class Program
{
    private const int MaxEntries = 256;
    private const long MaxModelBytes = 512L * 1024 * 1024;
    private const long MaxOutputBinaryBytes = 256L * 1024 * 1024;
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
    private const ulong WindowGlassBinding = 0x9582FD1BA2FFF9A4UL;
    private static readonly HashSet<ulong> LiveryPanelBindings =
    [
        0x4FF3746D9B055F1DUL,
        0xE00E033E6A20B977UL,
        0xE00E023E6A20B7C4UL,
        0xE00E053E6A20BCDDUL,
        0xE00E043E6A20BB2AUL,
        0xE00DFF3E6A20B2ABUL,
        0xE00DFE3E6A20B0F8UL,
        0xE00E013E6A20B611UL,
        0xE00E003E6A20B45EUL,
        0xE00DFB3E6A20ABDFUL,
        0xE00DFA3E6A20AA2CUL,
    ];
    private static readonly HashSet<ulong> CarPaintBindings =
    [
        0xF7DBE8A7C839A675UL,
        0x48E5B27611922B17UL,
        0x496F92FA5A6AAA57UL,
        0xE3AEF60D5E234B88UL,
        0xE3AEF90D5E2350A1UL,
        0xBF98CB3AA93337A4UL,
        0xBF98CE3AA9333CBDUL,
        0xBF98CD3AA9333B0AUL,
        0xBF98C83AA933328BUL,
        0xBF98C73AA93330D8UL,
        0xBF98CA3AA93335F1UL,
        0xBF98C93AA933343EUL,
        0xBF98C43AA9332BBFUL,
        0xBF98C33AA9332A0CUL,
        0x471A5FA481625396UL,
        0x6AC1E9D87FE5D953UL,
        0x4FD95FB5F29A1C11UL,
        0x78D434B9676BAFE1UL,
        0x1E5FF0F50C741122UL,
        0x115F3B8D0531FAE2UL,
        0x23E6ED8FEF16F8E0UL,
        0xCD48110253EE319AUL,
        0x06506BFF10D8BBBAUL,
        0x9A883D636B6F3798UL,
        0xBCEA13C28AA26965UL,
        0x6E3810972EA4DBF4UL,
        0xB0C163FF8ADE48FDUL,
    ];

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
            if (!meshes.Any(mesh => mesh.Role == "paint"))
            {
                var detail = Environment.GetEnvironmentVariable("KFPS_CHASSIS_DIAGNOSTICS") == "1"
                    ? " UV3 materials: " + string.Join(", ", meshes
                        .Where(mesh => mesh.UvChannels.ContainsKey(3))
                        .Select(mesh => string.IsNullOrWhiteSpace(mesh.MaterialName) ? "<unnamed>" : mesh.MaterialName)
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .OrderBy(value => value)
                        .Take(40))
                    : "";
                throw new InvalidDataException("The converted chassis has no livery-bearing paint geometry." + detail);
            }

            Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
            var temporary = outputPath + $".{Environment.ProcessId}.tmp";
            try
            {
                GlbWriter.Write(temporary, meshes, extraction.PartOptions, extraction.Coverage);
                File.Move(temporary, outputPath, true);
            }
            finally
            {
                if (File.Exists(temporary)) File.Delete(temporary);
            }

            Console.WriteLine(JsonSerializer.Serialize(new
            {
                format = "kfps_local_chassis_conversion_v5",
                output = outputPath,
                mesh_count = meshes.Count,
                paint_meshes = meshes.Count(mesh => mesh.Role == "paint"),
                glass_meshes = meshes.Count(mesh => mesh.Role == "glass"),
                direct_uv3_meshes = meshes.Count(mesh => (mesh.Role is "paint" or "glass") && mesh.UvChannels.ContainsKey(3)),
                projected_livery_meshes = meshes.Count(mesh => (mesh.Role is "paint" or "glass") && !mesh.UvChannels.ContainsKey(3)),
                part_option_count = extraction.PartOptions.Count,
                triangle_count = meshes.Sum(mesh => mesh.Indices.Length / 3),
                source_entry_count = meshes.Select(mesh => mesh.SourceEntry)
                    .Distinct(StringComparer.OrdinalIgnoreCase).Count(),
                scene_assembled = sceneAssembled,
                requested_instance_count = extraction.RequestedInstances,
                resolved_instance_count = extraction.ResolvedInstances,
                unresolved_instance_count = extraction.UnresolvedRequiredPaths.Length,
                unresolved_paths = extraction.UnresolvedRequiredPaths,
                skipped_optional_instance_count = extraction.SkippedOptionalPaths.Length,
                skipped_optional_paths = extraction.SkippedOptionalPaths,
                conversion_coverage = extraction.Coverage,
            }, JsonOptions()));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(
                Environment.GetEnvironmentVariable("KFPS_CHASSIS_DIAGNOSTICS") == "1"
                    ? error.ToString()
                    : error.Message);
            return 1;
        }
    }

    private static ChassisExtraction ExtractSceneMeshes(string archivePath, string requestedCarbin)
    {
        using var archive = ZipFile.OpenRead(archivePath);
        var available = archive.Entries.ToDictionary(entry => entry.FullName, StringComparer.OrdinalIgnoreCase);
        var masks = ReadNativeMaskPolicy(available);
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

        var instances = SceneModelInstances(carbin.Scene, out var partOptions, out var referenceIssues);
        if (instances.Count == 0)
            throw new InvalidDataException("The selected car scene contains no model instances.");

        var mediaName = string.IsNullOrWhiteSpace(carbin.Scene.MediaName)
            ? Path.GetFileNameWithoutExtension(requestedCarbin)
            : carbin.Scene.MediaName;
        var sceneLods = carbin.Scene.LODDetails.Value;
        if (sceneLods == 0) sceneLods = (ushort)instances.Aggregate(0, (mask, item) => mask | item.SceneLodFlags);
        var selectedLod = HighestDetailLod(sceneLods);
        var sceneSkeletonEntry = ResolveModelEntry(carbin.Scene.SkeletonPath ?? "", mediaName, available);
        Bundle sceneSkeleton = sceneSkeletonEntry == null ? null : LoadBundle(available[sceneSkeletonEntry], sceneSkeletonEntry);
        var cache = new Dictionary<string, ImportedModel>(StringComparer.OrdinalIgnoreCase);
        var result = new List<ChassisMesh>();
        long estimatedBinaryBytes = 0;
        var resolved = 0;
        var unresolvedRequired = new List<ModelInstance>();
        var skippedOptional = new List<ModelInstance>();
        var failures = new List<object>();
        var attachmentIssues = new List<object>();
        var excludedLod = new List<string>();
        void RecordUnresolved(ModelInstance instance, string reason)
        {
            if (instance.StockPart) unresolvedRequired.Add(instance);
            else skippedOptional.Add(instance);
            failures.Add(new { path=instance.Path, part_type=instance.PartType.ToString(),
                option_ids=instance.PartOptionIds, baseline=instance.StockPart, reason });
        }
        foreach (var instance in instances.OrderByDescending(item => item.StockPart))
        {
            if (instance.SceneLodFlags != 0 && (instance.SceneLodFlags & selectedLod) == 0)
            {
                excludedLod.Add(instance.Path);
                continue;
            }
            var entryName = ResolveModelEntry(instance.Path, mediaName, available);
            if (entryName is null)
            {
                RecordUnresolved(instance, "No exact archive entry for scene path.");
                continue;
            }
            try
            {
                if (!cache.TryGetValue(entryName, out var model))
                {
                    model = LoadModel(available[entryName], entryName);
                    cache[entryName] = model;
                }
                var instanceTransform = instance.Transform;
                var resolvedBone = FindBoneWorld(model.Bundle, instance.BoneName, instance.BoneId);
                var sceneBone = sceneSkeleton == null ? null : FindBoneWorld(sceneSkeleton, instance.BoneName, instance.BoneId);
                var nonRootAttachment = instance.SnapToParent || (instance.BoneId > 1
                    || (!string.IsNullOrWhiteSpace(instance.BoneName) && instance.BoneName is not "<root>" and not "root"));
                if (nonRootAttachment)
                    attachmentIssues.Add(new { path=instance.Path, bone_name=instance.BoneName, bone_id=instance.BoneId,
                        model_bone_resolved=resolvedBone.HasValue, scene_bone_resolved=sceneBone.HasValue,
                        snap_to_parent=instance.SnapToParent,
                        reason="Native bind/snap semantics unverified; authored instance plus model-local rigid transforms retained; scene bind transform not guessed." });
                if (resolvedBone is Matrix4x4 boneWorld)
                    instanceTransform = instance.Transform * boneWorld;
                var before = result.Count;
                AppendMeshes(result, model.Imported, entryName, instance, instanceTransform, ref estimatedBinaryBytes, selectedLod, model.Materials);
                foreach (var item in result.Skip(before))
                {
                    item.Diagnostics["kfps_instance_bone_requested"] = instance.BoneId >= 0 || !string.IsNullOrWhiteSpace(instance.BoneName);
                    item.Diagnostics["kfps_instance_bone_resolved"] = resolvedBone.HasValue;
                    item.Diagnostics["kfps_instance_bone_fallback"] = !resolvedBone.HasValue && (instance.BoneId >= 0 || !string.IsNullOrWhiteSpace(instance.BoneName));
                    item.Diagnostics["kfps_scene_bone_resolved"] = sceneBone.HasValue;
                    item.Diagnostics["kfps_attachment_semantics_verified"] = false;
                }
                if (result.Count > before) resolved++;
                else RecordUnresolved(instance, "No renderable geometry survived mesh selection.");
            }
            catch (Exception error) when (error is not OutOfMemoryException and not OperationCanceledException)
            {
                RecordUnresolved(instance, error.Message);
            }
        }

        if (unresolvedRequired.Count > 0)
            throw new InvalidDataException("Baseline scene is incomplete; no GLB written. " + JsonSerializer.Serialize(failures));

        var invalidOptions = skippedOptional
            .Where(instance => !instance.StockPart)
            .SelectMany(instance => instance.PartOptionIds.Select(id => (instance.PartType.ToString(), id)))
            .ToHashSet();
        if (invalidOptions.Count > 0)
        {
            var filtered = new List<ChassisMesh>(result.Count);
            foreach (var mesh in result)
            {
                var optionIds = mesh.PartOptionIds
                    .Where(id => !invalidOptions.Contains((mesh.PartType, id)))
                    .ToArray();
                if (mesh.PartOptionIds.Length > 0 && optionIds.Length == 0 && !mesh.StockPart)
                    continue;
                filtered.Add(mesh with { PartOptionIds = optionIds });
            }
            result = filtered;
        }
        var declaredOptions = partOptions
            .Select(option => (option.PartType, option.Id))
            .ToHashSet();
        var declaredMeshes = new List<ChassisMesh>(result.Count);
        foreach (var mesh in result)
        {
            var optionIds = mesh.PartOptionIds
                .Where(id => declaredOptions.Contains((mesh.PartType, id)))
                .ToArray();
            if (mesh.PartOptionIds.Length > 0 && optionIds.Length == 0 && !mesh.StockPart)
                continue;
            declaredMeshes.Add(mesh with { PartOptionIds = optionIds });
        }
        result = declaredMeshes;
        var representedOptions = result
            .SelectMany(mesh => mesh.PartOptionIds.Select(id => (mesh.PartType, id)))
            .ToHashSet();
        partOptions = partOptions.Select(option =>
        {
            var key = (option.PartType, option.Id);
            var declared = instances.Count(item => item.PartType.ToString() == option.PartType && item.PartOptionIds.Contains(option.Id));
            var blocked = invalidOptions.Contains(key) || (declared > 0 && !representedOptions.Contains(key));
            var issues = blocked ? new[] { "One or more declared model instances are unavailable or excluded; selection is blocked." } : Array.Empty<string>();
            return option with { Supported = !blocked, Empty = declared == 0, DeclaredInstances = declared, Issues = issues };
        }).ToList();
        var coverage = new Dictionary<string,object>
        {
            ["format"] = "kfps_component_conversion_coverage_v1",
            ["scene_entry"] = requestedCarbin,
            ["scene_skeleton_path"] = carbin.Scene.SkeletonPath ?? "",
            ["scene_skeleton_entry"] = sceneSkeletonEntry ?? "",
            ["attachment_issues"] = attachmentIssues,
            ["requested_instances"] = instances.Count,
            ["resolved_instances"] = resolved,
            ["unresolved_instances"] = failures,
            ["scene_reference_issues"] = referenceIssues,
            ["excluded_lod_paths"] = excludedLod.Distinct(StringComparer.OrdinalIgnoreCase).Order().ToArray(),
            ["option_count"] = partOptions.Count,
            ["blocked_option_count"] = partOptions.Count(item => !item.Supported),
            ["native_wheel_geometry"] = NativeWheelEvidence(result),
            ["empty_option_count"] = partOptions.Count(item => item.Empty),
            ["uv_hash_contract"] = "SHA256 of little-endian float32 Vector2 streams before GLB writing; importer/effective streams, not raw encoded bytes or game parity",
            ["lod_policy"] = "one highest-detail raw bit from scene mask; intersect instance and mesh masks; no filename exclusion or all-mesh fallback",
            ["selected_lod_bit"] = selectedLod,
            ["selected_lod_name"] = LodName(selectedLod),
            ["fitment_policy"] = "CarBodyId/ParentIsStock preserved verbatim; no inferred cross-part compatibility",
            ["native_parser_parity_verified"] = false,
            ["native_livery_masks"] = masks.Evidence,
            ["surface_policy"] = "native UV3 plus car-declared valid mask resource; generic projection disabled; source shader eligibility still unverified",
        };
        return new ChassisExtraction(
            ApplyNativeMaskPolicy(result, masks),
            instances.Count,
            resolved,
            unresolvedRequired.Select(instance => instance.Path)
                .Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(value => value).ToArray(),
            skippedOptional.Select(instance => instance.Path)
                .Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(value => value).ToArray(),
            partOptions, coverage);
    }

    private static ChassisExtraction ExtractLooseMeshes(string archivePath, IReadOnlyList<string> requested)
    {
        using var archive = ZipFile.OpenRead(archivePath);
        var available = archive.Entries.ToDictionary(entry => entry.FullName, StringComparer.OrdinalIgnoreCase);
        var masks = ReadNativeMaskPolicy(available);
        var result = new List<ChassisMesh>();
        long estimatedBinaryBytes = 0;
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
                $"legacy:{requestedName}",
                true,
                [],
                1,
                new Dictionary<string, ulong>(StringComparer.OrdinalIgnoreCase));
            AppendMeshes(
                result,
                model.Imported,
                requestedName,
                instance,
                Matrix4x4.Identity,
                ref estimatedBinaryBytes, materials: model.Materials);
        }
        return new ChassisExtraction(ApplyNativeMaskPolicy(result, masks), requested.Count, requested.Count, [], [], [],
            new() { ["native_livery_masks"] = masks.Evidence });
    }

    private static ImportedModel LoadModel(ZipArchiveEntry entry, string entryName)
    {
        var bundle = LoadBundle(entry, entryName);
        using var stream = entry.Open();
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        return new ImportedModel(bundle, new ModelImporter().ExtractModels(bundle), ReadMaterials(bundle, memory.ToArray()));
    }

    private static Bundle LoadBundle(ZipArchiveEntry entry, string entryName)
    {
        if (entry.Length <= 0 || entry.Length > MaxModelBytes)
            throw new InvalidDataException($"Model entry {entryName} has an unsupported size.");
        using var source = entry.Open();
        using var memory = new MemoryStream(checked((int)entry.Length));
        source.CopyTo(memory);
        memory.Position = 0;
        var bundle = new Bundle();
        bundle.Load(memory);
        return bundle;
    }

    private static string StaticRenderPurpose(MeshBlob mesh, string name, string material, CCarParts part)
    {
        // Never infer shadow-only from IsShadow alone: ordinary surfaces cast shadows too.
        if (mesh.IsShadow && !mesh.IsNotShadow && mesh.MaterialId < 0) return "shadow-only";
        if (part == CCarParts.WheelStyle && mesh.IsTransparent
            && (name ?? "").StartsWith("blur", StringComparison.OrdinalIgnoreCase)
            && (material ?? "").StartsWith("blur_", StringComparison.OrdinalIgnoreCase)) return "wheel-motion-blur";
        return "surface";
    }

    private static object NativeWheelEvidence(IReadOnlyList<ChassisMesh> meshes)
    {
        var native=meshes.Where(m=>m.PartType==nameof(CCarParts.WheelStyle)
            && m.Indices.Length>=3 && (string)m.Diagnostics.GetValueOrDefault("kfps_static_render_purpose")=="surface").ToArray();
        return new {
            has_static_meshes=native.Length>0,
            static_mesh_count=native.Length,
            instance_count=native.Select(m=>m.InstanceIdentity).Distinct(StringComparer.Ordinal).Count(),
            source_entries=native.Select(m=>m.SourceEntry).Distinct(StringComparer.OrdinalIgnoreCase).Order().ToArray(),
            basis="native carbin WheelStyle membership and decoded triangle geometry; excludes identified blur/shadow-only meshes",
            assembly_complete=false,
            tire_geometry_present=false,
            runtime_fitment_applied=false,
            missing_requirements=new[] {
                "Exact car/compound-to-shared-tire model association and tire instances are not loaded.",
                "Native rim diameter/width/offset and tire-profile deformation plus suspension attachment are unresolved."
            },
            fitment_verified=false,
            materials_verified=false,
            substitute_geometry=false
        };
    }

    private static object ParameterValue(object value) => value switch
    {
        Vector4 v when float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z) && float.IsFinite(v.W) => new[] {v.X,v.Y,v.Z,v.W},
        Vector2 v when float.IsFinite(v.X) && float.IsFinite(v.Y) => new[] {v.X,v.Y},
        float f when float.IsFinite(f) => f,
        int i => i,
        bool b => b,
        TextureParameter t => new { path=t.Path, path_hash=t.PathHash.ToString("X8") },
        SamplerParameter s => new { address_u=s.AddressU,address_v=s.AddressV,unknown=s.UnkType },
        _ => null,
    };

    private static Dictionary<int, object> ReadMaterials(Bundle bundle, byte[] source)
    {
        var output=new Dictionary<int,object>();
        foreach (var blob in bundle.Blobs.Where(b=>b is MaterialBlob or MaterialResourceBlob))
        {
            var ids=blob.Metadatas.OfType<IdentifierMetadata>().Select(m=>(int)m.Id).ToArray();
            var size=blob.UncompressedSize > 0 ? blob.UncompressedSize : blob.CompressedSize;
            if (blob.FileOffset < 0 || blob.FileOffset > source.LongLength-size)
                throw new InvalidDataException("Material source range exceeds model bytes.");
            var nested=(blob as MaterialBlob)?.Bundle;
            var record=new {
                name=blob.Metadatas.OfType<NameMetadata>().FirstOrDefault()?.Name ?? "",
                tag=blob.Tag.ToString("X8"), source_blob_offset=blob.FileOffset, source_blob_bytes=size,
                source_blob_sha256=Convert.ToHexString(SHA256.HashData(source.AsSpan((int)blob.FileOffset,(int)size))).ToLowerInvariant(),
                resource_path=(blob as MaterialResourceBlob)?.Path,
                nested_resources=nested?.Blobs.OfType<MaterialResourceBlob>().Select(b=>b.Path).ToArray() ?? Array.Empty<string>(),
                parameters=nested?.Blobs.OfType<MaterialShaderParameterBlob>().SelectMany(b=>b.Parameters)
                    .Select(p=>new { name_hash=p.NameHash.ToString("X8"), type=p.Type.ToString(),
                        value=ParameterValue(p.Value), parser_placeholder=p.NameHash==0xDEADBEEF }).ToArray(),
                decoded_parameters_verified=false,
                assurance="Native source blob hash/reference and parser values only; no PBR/shader equivalence or guessed textures."
            };
            foreach (var id in ids)
                if (!output.TryAdd(id,record)) throw new InvalidDataException("Duplicate native material identifier.");
        }
        return output;
    }

    private static void AppendMeshes(
        List<ChassisMesh> result,
        ImporterResult imported,
        string sourceEntry,
        ModelInstance instance,
        Matrix4x4 instanceTransform,
        ref long estimatedBinaryBytes,
        ushort selectedLod = 0,
        Dictionary<int, object> materials = null)
    {
        if (selectedLod == 0) selectedLod = HighestDetailLod((ushort)imported.Meshes.Aggregate(0, (mask, geometry) => mask | geometry.SourceMesh.LODFlags));
        var selected = SelectLodMeshes(imported, selectedLod);
        foreach (var geometry in selected)
        {
            if (geometry.RawPositions is not { Length: > 0 } || geometry.Indices is not { Length: >= 3 })
                continue;
            if (geometry.Indices.Length % 3 != 0 || geometry.SourceMesh.Topology != 4)
                throw new InvalidDataException($"Mesh {geometry.Name} does not use a triangle-list topology.");

            var vertexCount = geometry.RawPositions.Length;
            var uvChannelCount = geometry.UvChannels.Count(item =>
                item.Key >= 0 && item.Value.Length == vertexCount);
            var upperBound = checked(
                (long)vertexCount * (24L + 8L * uvChannelCount)
                + (long)geometry.Indices.Length * 4L);
            if (upperBound > MaxOutputBinaryBytes
                || estimatedBinaryBytes > MaxOutputBinaryBytes - upperBound)
            {
                throw new InvalidDataException(
                    "The selected car's default chassis exceeds KFPS's safe 256 MiB geometry limit.");
            }

            var positions = TransformPositions(geometry, instanceTransform);
            var normals = TransformNormals(geometry, instanceTransform);
            var finalMatrix = Matrix4x4.CreateScale(new Vector3(geometry.SourceMesh.PositionScale.X,geometry.SourceMesh.PositionScale.Y,geometry.SourceMesh.PositionScale.Z))
                * Matrix4x4.CreateTranslation(new Vector3(geometry.SourceMesh.PositionTranslate.X,geometry.SourceMesh.PositionTranslate.Y,geometry.SourceMesh.PositionTranslate.Z))
                * geometry.BoneTransform * instanceTransform * Matrix4x4.CreateScale(-1,1,1);
            var reverseWinding = ReverseWinding(geometry.BoneTransform, instanceTransform);
            var indices = CleanTriangleIndices(geometry.Indices, reverseWinding);
            if (indices.Length == 0)
                continue;
            ValidateGeometry(geometry.Name, positions, normals, indices);
            var uvs = TransformUvChannels(geometry, positions.Length);
            var diagnostics = new Dictionary<string, object>
            {
                ["kfps_source_mesh_name"] = geometry.Name,
                ["kfps_source_mesh_index"] = geometry.SourceMesh.SourceMeshIndex,
                ["kfps_source_mesh_blob_offset"] = geometry.SourceMesh.FileOffset,
                ["kfps_source_material_id"] = geometry.SourceMesh.MaterialId,
                ["kfps_source_material_ids"] = geometry.SourceMesh.MaterialIds ?? Array.Empty<short>(),
                ["kfps_source_material_groups"] = geometry.SourceMesh.MaterialGroups,
                ["kfps_native_render_bucket"] = new { opaque=geometry.SourceMesh.IsOpaque,
                    decal=geometry.SourceMesh.IsDecal, transparent=geometry.SourceMesh.IsTransparent,
                    shadow=geometry.SourceMesh.IsShadow, alpha_to_coverage=geometry.SourceMesh.IsAlphaToCoverage,
                    not_shadow=geometry.SourceMesh.IsNotShadow,
                    order=geometry.SourceMesh.BucketOrder },
                ["kfps_static_render_purpose"] = StaticRenderPurpose(geometry.SourceMesh, geometry.Name, geometry.MaterialName, instance.PartType),
                ["kfps_native_material"] = materials?.GetValueOrDefault(geometry.SourceMesh.MaterialId),
                ["kfps_material_instance_overrides"] = instance.MaterialOverrides?.Select(item => new {
                    name=item.Key, bytes=item.Value.Length,
                    sha256=Convert.ToHexString(SHA256.HashData(item.Value)).ToLowerInvariant(),
                    applied=false }).ToArray(),
                ["kfps_native_surface_eligibility_verified"] = false,
                ["kfps_source_vertex_count"] = positions.Length,
                ["kfps_source_vertex_base"] = geometry.MinVertexIndex,
                ["kfps_source_index_count"] = geometry.Indices.Length,
                ["kfps_source_index_buffer_reference"] = geometry.SourceMesh.IndexBufferIndex,
                ["kfps_winding_reversed"] = reverseWinding,
                ["kfps_source_lod_flags"] = geometry.SourceMesh.LODFlags,
                ["kfps_scene_lod_flags"] = instance.SceneLodFlags,
                ["kfps_final_lod_policy"] = "single-raw-bit-intersection",
                ["kfps_selected_lod_bit"] = selectedLod,
                ["kfps_selected_lod_name"] = LodName(selectedLod),
                ["kfps_skinning_elements"] = geometry.SourceMesh.SkinningElementsCount,
                ["kfps_skinning_applied"] = false,
                ["kfps_source_position_scale"] = new[] {geometry.SourceMesh.PositionScale.X,geometry.SourceMesh.PositionScale.Y,geometry.SourceMesh.PositionScale.Z},
                ["kfps_source_position_translate"] = new[] {geometry.SourceMesh.PositionTranslate.X,geometry.SourceMesh.PositionTranslate.Y,geometry.SourceMesh.PositionTranslate.Z},
                ["kfps_native_morph_target_count"] = geometry.SourceMesh.MorphTargetCount,
                ["kfps_native_morph_is_damage"] = geometry.SourceMesh.IsMorphDamage,
                ["kfps_native_morph_buffer_index"] = geometry.SourceMesh.MorphDataBufferIndex,
                ["kfps_native_morph_applied"] = false,
                ["kfps_position_pipeline"] = "raw * source-scale + source-translate; rigid-bone; instance; reflect-X",
                ["kfps_final_vertex_transform"] = MatrixValues(finalMatrix),
                ["kfps_snap_to_parent"] = instance.SnapToParent,
                ["kfps_source_rigid_bone"] = geometry.BoneIndex,
                ["kfps_bone_transform"] = MatrixValues(geometry.BoneTransform),
                ["kfps_instance_bone_name"] = instance.BoneName ?? "",
                ["kfps_instance_bone_id"] = instance.BoneId,
                ["kfps_authored_instance_transform"] = MatrixValues(instance.Transform),
                ["kfps_instance_transform"] = MatrixValues(instanceTransform),
                ["kfps_imported_uv_sha256"] = geometry.UvChannels.ToDictionary(item => item.Key.ToString(), item => HashUv(item.Value)),
                ["kfps_uv_sha256"] = uvs.ToDictionary(item => item.Key.ToString(), item => HashUv(item.Value)),
                ["kfps_uv_hash_stage"] = "decoded-importer / effective-before-GLB; not encoded-source parity",
                ["kfps_native_texcoord_transforms"] = NativeTexCoordTransforms(geometry.SourceMesh),
                ["kfps_native_uv_pipeline"] = "native-unflipped-then-native-scale-offset-v1",
            };
            var identity = $"{sourceEntry} {geometry.Name} {geometry.MaterialName}";
            var hasUv3 = uvs.ContainsKey(3);
            var materialBindingHash = ResolveMaterialBindingHash(
                geometry.MaterialName ?? "",
                instance.MaterialBindings);
            var role = ClassifyRole(
                identity,
                hasUv3,
                instance.WindowHint,
                geometry.Name,
                geometry.MaterialName ?? "",
                materialBindingHash);
            var actualBytes = checked(
                (long)positions.Length * 24L
                + uvs.Values.Sum(values => (long)values.Length * 8L)
                + (long)indices.Length * 4L);
            if (estimatedBinaryBytes > MaxOutputBinaryBytes - actualBytes)
            {
                throw new InvalidDataException(
                    "The selected car's default chassis exceeds KFPS's safe 256 MiB geometry limit.");
            }
            estimatedBinaryBytes += actualBytes;
            result.Add(new ChassisMesh(
                $"{Path.GetFileNameWithoutExtension(sourceEntry)} :: {geometry.Name}",
                sourceEntry,
                geometry.MaterialName ?? "",
                role,
                instance.PartType.ToString(),
                instance.Identity,
                instance.StockPart,
                instance.PartOptionIds,
                instance.DrawGroups,
                RenderedLiverySides(role, geometry.Name, instance.PartType),
                ProjectionLiverySides(role, geometry.Name, instance.PartType),
                materialBindingHash,
                positions,
                normals,
                uvs,
                indices, diagnostics));
        }
    }

    private static List<ModelInstance> SceneModelInstances(
        Scene scene,
        out List<PartOptionDescriptor> partOptions,
        out List<object> referenceIssues)
    {
        var output = new List<ModelInstance>();
        var byIdentity = new Dictionary<string, int>(StringComparer.Ordinal);
        partOptions = [];
        referenceIssues = [];

        void Add(CarRenderModel model, CCarParts partType, bool stock, IEnumerable<int>? optionIds = null)
        {
            if (string.IsNullOrWhiteSpace(model.Path)) return;
            var key = InstanceKey(model, partType);
            var ids = (optionIds ?? []).Distinct().OrderBy(value => value).ToArray();
            if (byIdentity.TryGetValue(key, out var existingIndex))
            {
                var existing = output[existingIndex];
                output[existingIndex] = existing with
                {
                    StockPart = existing.StockPart || stock,
                    PartOptionIds = existing.PartOptionIds.Concat(ids).Distinct().OrderBy(value => value).ToArray(),
                };
                return;
            }
            byIdentity[key] = output.Count;
            output.Add(new ModelInstance(
                model.Path,
                model.Transform,
                model.BoneName ?? "",
                model.BoneId,
                partType,
                model.IsInteriorWindshield || model.IsLeftSideWindow != 0 || model.IsRightSideWindow != 0,
                key,
                stock,
                ids,
                model.RawDrawGroupsValue,
                model.MaterialIndexes
                    .Where(item => !string.IsNullOrWhiteSpace(item.Key))
                    .GroupBy(item => MaterialToken(item.Key), StringComparer.OrdinalIgnoreCase)
                    .Where(group => !string.IsNullOrWhiteSpace(group.Key))
                    .ToDictionary(group => group.Key, group => group.First().Value, StringComparer.OrdinalIgnoreCase),
                model.LODDetails.Value, model.SnapToParent, model.MaterialOverrides));
        }

        foreach (var entry in scene.NonUpgradableParts)
            foreach (var model in entry.Part.Models)
                Add(model, entry.Type, true);

        foreach (var part in scene.UpgradableParts)
        {
            if (part.Upgrades.Select(item => item.Id).Distinct().Count() != part.Upgrades.Count)
                throw new InvalidDataException($"Duplicate upgrade IDs in {part.Type}.");
            var selected = part.Upgrades
                .OrderBy(upgrade => upgrade.IsStock ? 0 : 1)
                .ThenBy(upgrade => upgrade.Level)
                .ThenBy(upgrade => upgrade.Id)
                .FirstOrDefault();
            if (selected is null) continue;
            foreach (var upgrade in part.Upgrades)
            {
                partOptions.Add(new PartOptionDescriptor(part.Type.ToString(), (int)part.Type,
                    upgrade.Id, upgrade.Level, upgrade.CarBodyId, upgrade.ParentIsStock,
                    upgrade.IsStock, upgrade.Id == selected.Id));
                foreach (var model in upgrade.Models)
                    Add(model, part.Type, upgrade.Id == selected.Id, new[] { upgrade.Id });
            }
            var allIds = part.Upgrades.Select(item => item.Id).ToArray();
            foreach (var shared in part.SharedModels)
            {
                var ids = shared.UpgradeIds.Count == 0 ? allIds : shared.UpgradeIds.ToArray();
                var unknown = ids.Where(id => !allIds.Contains(id)).Distinct().ToArray();
                if (unknown.Length > 0)
                    referenceIssues.Add(new { part_type=part.Type.ToString(), path=shared.Model.Path,
                        unknown_option_ids=unknown, reason="Shared model references option IDs absent from this scene's upgrade table; no options were invented." });
                ids = ids.Where(allIds.Contains).ToArray();
                if (ids.Length == 0) continue;
                Add(shared.Model, part.Type, ids.Contains(selected.Id), ids);
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
            model.RawDrawGroupsValue.ToString(), model.LODDetails.Value.ToString(), model.SnapToParent.ToString(),
            model.IsInteriorWindshield.ToString(), model.IsLeftSideWindow.ToString(), model.IsRightSideWindow.ToString(),
            string.Join(",", model.MaterialIndexes.OrderBy(item => item.Key, StringComparer.Ordinal).Select(item => $"{item.Key}:{item.Value:X16}")),
            string.Join(",", model.MaterialOverrides.OrderBy(item => item.Key, StringComparer.Ordinal).Select(item => $"{item.Key}:{Convert.ToHexString(SHA256.HashData(item.Value))}")),
        });
    }

    private static string? ResolveModelEntry(
        string gamePath,
        string mediaName,
        IReadOnlyDictionary<string, ZipArchiveEntry> available)
    {
        var normalized = gamePath.Replace('\\', '/').Trim();
        var prefix = $"game:/media/cars/{mediaName}/";
        if (normalized.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) normalized = normalized[prefix.Length..];
        else if (normalized.Contains(':') || normalized.StartsWith('/')) return null;
        if (normalized.Split('/').Any(segment => segment is ".." or "." or "")) return null;
        return available.TryGetValue(normalized, out var exact) ? exact.FullName : null;
    }

    private static float[] MatrixValues(Matrix4x4 m) => new[] { m.M11,m.M12,m.M13,m.M14,m.M21,m.M22,m.M23,m.M24,m.M31,m.M32,m.M33,m.M34,m.M41,m.M42,m.M43,m.M44 };

    private static string HashUv(IEnumerable<Vector2> values)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        Span<byte> bytes = stackalloc byte[8];
        foreach(var uv in values)
        {
            BinaryPrimitives.WriteSingleLittleEndian(bytes,uv.X);
            BinaryPrimitives.WriteSingleLittleEndian(bytes[4..],uv.Y);
            hash.AppendData(bytes);
        }
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    private static Matrix4x4? FindBoneWorld(Bundle bundle, string name, short id)
    {
        var skeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();
        if (skeleton is null || skeleton.Bones.Count == 0) return null;
        var target = -1;
        if (!string.IsNullOrWhiteSpace(name))
            target = skeleton.Bones.FindIndex(bone => string.Equals(bone.Name, name, StringComparison.OrdinalIgnoreCase));
        if (string.IsNullOrWhiteSpace(name) && id >= 0 && id < skeleton.Bones.Count) target = id;
        if (target < 0) return null;
        return ModelImporter.ResolveBoneMatrices(skeleton)[target];
    }

    private static float[][] NativeTexCoordTransforms(MeshBlob mesh)
    {
        var source = mesh.TexCoordTransforms;
        if (source is not { Length: > 0 }) return null;
        // Missing/invalid source metadata must not qualify a guessed texture transform.
        return source.Select(value =>
            float.IsFinite(value.X) && float.IsFinite(value.Y) && float.IsFinite(value.Z) && float.IsFinite(value.W)
                ? new[] { value.X, value.Y, value.Z, value.W }
                : null).ToArray();
    }

    private static Dictionary<int, Vector2[]> TransformUvChannels(ForzaGeometryData geometry, int vertexCount)
    {
        var output = new Dictionary<int, Vector2[]>();
        var transforms = geometry.SourceMesh.TexCoordTransforms;
        foreach (var (channel, source) in geometry.UvChannels)
        {
            if (channel < 0)
                continue;
            if (source.Length != vertexCount)
            {
                if (channel >= 4)
                    throw new InvalidDataException($"Mesh {geometry.Name} UV{channel} has an invalid vertex count.");
                continue;
            }
            if (channel >= 4 && (transforms == null || channel >= transforms.Length))
                throw new InvalidDataException($"Mesh {geometry.Name} UV{channel} has no explicit native affine.");
            var transform = transforms is { Length: > 0 } && channel < transforms.Length
                ? transforms[channel]
                : new Vector4(0.0f, 1.0f, 0.0f, 1.0f);
            var values = new Vector2[source.Length];
            for (var index = 0; index < source.Length; index++)
            {
                var value = source[index];
                values[index] = new Vector2(
                    value.X * transform.Y + transform.X,
                    value.Y * transform.W + transform.Z);
            }
            if (values.Any(value => !float.IsFinite(value.X) || !float.IsFinite(value.Y)))
                throw new InvalidDataException($"Mesh {geometry.Name} contains a non-finite UV coordinate.");
            output[channel] = values;
        }
        return output;
    }

    private static ushort HighestDetailLod(ushort mask)
    {
        for (ushort bit = 1; bit <= 64; bit <<= 1)
            if ((mask & bit) != 0) return bit;
        throw new InvalidDataException("No supported native LOD bit is declared.");
    }

    private static string LodName(ushort bit) => bit == 1 ? "LODS" : "LOD" + ((int)Math.Log2(bit) - 1);

    private static List<ForzaGeometryData> SelectLodMeshes(ImporterResult imported, ushort bit)
    {
        if (bit == 0 || bit > 64 || (bit & (bit - 1)) != 0)
            throw new InvalidDataException("Exactly one supported LOD bit is required.");
        return imported.Meshes.Where(geometry => (geometry.SourceMesh.LODFlags & bit) != 0).ToList();
    }

    private static int[] CleanTriangleIndices(IReadOnlyList<int> source, bool reverseWinding)
    {
        if (source.Count % 3 != 0) throw new InvalidDataException("Triangle list index count is not divisible by three.");
        var output = new List<int>(source.Count);
        for (var index = 0; index < source.Count; index += 3)
        {
            var a = source[index];
            var b = source[index + 1];
            var c = source[index + 2];
            if (a == b || b == c || a == c)
                continue;
            output.Add(a);
            output.Add(reverseWinding ? c : b);
            output.Add(reverseWinding ? b : c);
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
        for (var index = 0; index < count; index++)
        {
            var normal = input is { Length: > 0 } && index < input.Length ? input[index] : Vector3.UnitY;
            // PositionScale decodes positions; normals have independent encoding.
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

    private static bool ReverseWinding(Matrix4x4 bone, Matrix4x4 instance)
    {
        // Index winding is authored for decoded positions, not quantized bounds.
        var determinant = (bone * instance * Matrix4x4.CreateScale(-1,1,1)).GetDeterminant();
        if (!float.IsFinite(determinant) || determinant == 0)
            throw new InvalidDataException("Spatial transform is singular or non-finite.");
        return determinant < 0;
    }

    internal static string ClassifyRole(
        string identity,
        bool hasUv3,
        bool windowHint = false,
        string meshName = "",
        string materialName = "",
        ulong materialBindingHash = 0)
    {
        var value = identity.ToLowerInvariant();
        var sourceName = string.IsNullOrWhiteSpace(meshName) ? identity : meshName;
        var windowSide = AllowedWindowSide(sourceName);
        if (IsInteriorWindowShell(sourceName)) return "hidden";
        if (windowSide != 0
            && !IsRejectedWindowMaterial(materialName)
            && (materialBindingHash == WindowGlassBinding
                || windowHint
                || IsWindowGlassMaterial(materialName)
                || value.Contains("/windows/")
                || value.Contains("\\windows\\")))
            return "glass";
        if (IsBodyPaintMaterial(materialName)
            || LiveryPanelBindings.Contains(materialBindingHash)
            || (hasUv3
                && value.Contains("livery", StringComparison.Ordinal)
                && CarPaintBindings.Contains(materialBindingHash)))
            return "paint";
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
            || name.StartsWith("car_paint", StringComparison.Ordinal)
            || name.StartsWith("paint_", StringComparison.Ordinal)
            || name.EndsWith("_paint", StringComparison.Ordinal)
            || name.Contains("_paint_", StringComparison.Ordinal);
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
        if (name.StartsWith("glassrf", StringComparison.Ordinal)
            || name.StartsWith("glassrr", StringComparison.Ordinal)
            || name.StartsWith("glassrm", StringComparison.Ordinal)) return SideGlassRight;
        if (name.StartsWith("glasslf", StringComparison.Ordinal)
            || name.StartsWith("glasslr", StringComparison.Ordinal)
            || name.StartsWith("glasslm", StringComparison.Ordinal)) return SideGlassLeft;
        if (name.StartsWith("glassf_", StringComparison.Ordinal)
            || name.StartsWith("glassflivery", StringComparison.Ordinal)
            || name.Contains("windshield", StringComparison.Ordinal)
            || name.Contains("windsheild", StringComparison.Ordinal)) return SideGlassFront;
        if (name.StartsWith("glassr_", StringComparison.Ordinal)
            || name.StartsWith("glassrlivery", StringComparison.Ordinal)
            || name.Contains("backglass", StringComparison.Ordinal)
            || name.Contains("rearglass", StringComparison.Ordinal)) return SideGlassBack;
        if (name.StartsWith("glasstop_", StringComparison.Ordinal)
            || name.StartsWith("glassroof_", StringComparison.Ordinal)) return SideGlassTop;
        return 0;
    }

    private static bool IsSpoilerMesh(string name)
    {
        var value = name.ToLowerInvariant();
        return !value.Contains("mirror") && (value.Contains("spoiler") || value.Contains("wing"));
    }

    private static bool IsTrunkPanelMesh(string name) =>
        name.StartsWith("trunk", StringComparison.OrdinalIgnoreCase) && !IsSpoilerMesh(name);

    private static int RenderedLiverySides(string role, string meshName, CCarParts partType)
    {
        if (role == "glass") return AllGlassSides;
        if (role != "paint") return 0;
        if (IsSpoilerMesh(meshName)) return SideSpoiler;
        if (IsTrunkPanelMesh(meshName)) return SideBack | SideTop;
        return AllBodySides;
    }

    private static int NativeAllowedSides(string role, string meshName, CCarParts partType, bool uv3, int validSides)
    {
        if (!uv3) return 0;
        // Assembly names do not own sections: a "trunk" can include side panels
        // and wing endplates. Native UV3 masks, not projection heuristics, decide
        // which pixels accept artwork. Keep body and glass domains separate.
        var domain = role == "paint" ? AllBodySides | SideSpoiler : role == "glass" ? AllGlassSides : 0;
        return domain & validSides;
    }

    private static string LiveryRoleAfterMaskPolicy(string role, int allowedSides) =>
        allowedSides == 0 && role is "paint" or "glass" ? "trim" : role;

    private static List<ChassisMesh> ApplyNativeMaskPolicy(List<ChassisMesh> meshes, NativeMaskPolicy masks)
    {
        return meshes.Select(mesh =>
        {
            var sides = NativeAllowedSides(mesh.Role, (string)mesh.Diagnostics["kfps_source_mesh_name"],
                Enum.Parse<CCarParts>(mesh.PartType), mesh.UvChannels.ContainsKey(3), masks.ValidSides);
            mesh.Diagnostics["kfps_native_mask_valid_sides"] = masks.ValidSides;
            mesh.Diagnostics["kfps_livery_mapping"] = sides != 0 ? "native-uv3-car-mask" : "unavailable-native-uv3-or-mask";
            mesh.Diagnostics["kfps_generic_projection_enabled"] = false;
            var role = LiveryRoleAfterMaskPolicy(mesh.Role, sides);
            // Keep the visible material while excluding surfaces without native livery mapping.
            if (role != mesh.Role) mesh.Diagnostics["kfps_unpaintable_surface_role"] = mesh.Role;
            return mesh with { Role = role, AllowedSides = sides, ProjectionSides = 0 };
        }).ToList();
    }

    private static NativeMaskPolicy ReadNativeMaskPolicy(IReadOnlyDictionary<string, ZipArchiveEntry> entries)
    {
        var bits = new Dictionary<string,int>(StringComparer.Ordinal) {
            ["Front"]=SideFront,["Back"]=SideBack,["Top"]=SideTop,["Left"]=SideLeft,["Right"]=SideRight,["Wing"]=SideSpoiler,
            ["Glass_Front"]=SideGlassFront,["Glass_Back"]=SideGlassBack,["Glass_Top"]=SideGlassTop,["Glass_Left"]=SideGlassLeft,["Glass_Right"]=SideGlassRight };
        var sections = new List<object>();
        var evidence = new Dictionary<string,object> { ["format"]="kfps_native_mask_evidence_v1",
            ["sections"]=sections,["valid_sides"]=0,["xml_path"]="",["xml_sha256"]="",
            ["assurance"]="Exact native declarations and resource byte hashes; no regenerated mask, projection or shader-parity claim." };
        if (!entries.TryGetValue("LiveryMasks/Masks.xml", out var xml)) return new(0, evidence);
        if (xml.Length <= 0 || xml.Length > 1024 * 1024) throw new InvalidDataException("Native mask XML size is unsupported.");
        byte[] bytes;
        using (var source=xml.Open()) { using var memory=new MemoryStream(); source.CopyTo(memory); bytes=memory.ToArray(); }
        evidence["xml_path"]=xml.FullName;
        evidence["xml_sha256"]=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        using var reader=XmlReader.Create(new MemoryStream(bytes), new XmlReaderSettings {
            DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=1024*1024 });
        var document=XDocument.Load(reader);
        if (document.Root?.Name != "LiveryMasks") throw new InvalidDataException("Unexpected native mask XML root.");
        var seen=new HashSet<string>();
        var allowed=0;
        foreach (var element in document.Root.Elements())
        {
            var name=element.Name.LocalName;
            if (!seen.Add(name)) throw new InvalidDataException("Duplicate native mask section.");
            if (!bool.TryParse((string)element.Attribute("valid"), out var valid))
                throw new InvalidDataException("Invalid native mask valid flag.");
            var resource="LiveryMasks/"+name.ToLowerInvariant()+".swatchbin";
            var present=entries.TryGetValue(resource, out var entry);
            var resourceHash="";
            if (present)
            {
                if (entry.Length <= 0 || entry.Length > 32L*1024*1024) throw new InvalidDataException("Native mask resource size is unsupported.");
                using var source=entry.Open();
                resourceHash=Convert.ToHexString(SHA256.HashData(source)).ToLowerInvariant();
            }
            var bit=bits.GetValueOrDefault(name);
            if (valid && present) allowed |= bit;
            sections.Add(new { section=name, declared_valid=valid, side_bit=bit, resource_present=present,
                path=present ? entry.FullName : resource, sha256=resourceHash, bytes=present ? entry.Length : 0,
                attributes=element.Attributes().ToDictionary(a=>a.Name.ToString(),a=>a.Value) });
        }
        evidence["valid_sides"]=allowed;
        return new(allowed,evidence);
    }

    private static int ProjectionLiverySides(string role, string meshName, CCarParts partType)
    {
        if (role == "glass") return AllowedWindowSide(meshName);
        if (role != "paint") return 0;
        if (IsSpoilerMesh(meshName)) return SideSpoiler;
        if (IsTrunkPanelMesh(meshName)) return SideBack | SideTop;
        if (partType == CCarParts.FrontBumper) return SideFront | SideLeft | SideRight;
        if (partType == CCarParts.RearBumper) return SideBack | SideLeft | SideRight;
        if (partType == CCarParts.Hood) return SideTop;
        if (partType == CCarParts.SideSkirts) return SideLeft | SideRight;
        if (partType == CCarParts.RearWing) return SideSpoiler;
        return AllBodySides;
    }

    private static string MaterialToken(string value)
    {
        var normalized = value.Replace('\\', '/');
        var separator = normalized.LastIndexOf('/');
        if (separator >= 0) normalized = normalized[(separator + 1)..];
        var pipe = normalized.IndexOf('|');
        if (pipe >= 0) normalized = normalized[..pipe];
        if (normalized.EndsWith(".materialbin", StringComparison.OrdinalIgnoreCase))
            normalized = normalized[..^12];
        return normalized.Trim().ToLowerInvariant();
    }

    private static ulong ResolveMaterialBindingHash(
        string materialName,
        IReadOnlyDictionary<string, ulong> bindings)
    {
        var candidate = MaterialToken(materialName);
        if (string.IsNullOrWhiteSpace(candidate)) return 0;
        if (bindings.TryGetValue(candidate, out var exact)) return exact;
        return 0;
    }

    private static JsonSerializerOptions JsonOptions() => new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
    };
}
