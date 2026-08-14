using Syroot.BinaryData;
using System.Collections.Generic;

namespace ForzaTools.Bundles.Blobs;

public class LightScenarioBlob : BundleBlob
{
    public bool IsInline { get; set; }
    public List<LightScenario> LightScenarios { get; set; } = new();

    public override void ReadBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(1, 1))
            IsInline = bs.ReadBoolean();

        byte count = bs.Read1Byte();
        for (int i = 0; i < count; i++)
        {
            var ls = new LightScenario();
            ls.Name = bs.ReadString(StringCoding.VariableByteCount);
            ls.Version = bs.ReadUInt32();

            // v1.4+: bool HasInstancedData — stored on the model so serializer can round-trip correctly
            if (IsAtLeastVersion(1, 4))
                ls.HasInstancedData = bs.ReadBoolean();

            // v1.2+: animScenarioCount (else 1 anim slot)
            uint animCount = 1;
            if (IsAtLeastVersion(1, 2))
                animCount = bs.ReadUInt32();
            ls.AnimCount = animCount;

            for (int v = 0; v < animCount; v++)
            {
                var vs = new VertexShaderEntry();
                if (IsAtLeastVersion(1, 2))
                    vs.AnimScenarioFlags = bs.Read1Byte();

                vs.Path = bs.ReadString(StringCoding.VariableByteCount);

                // Read and preserve platform hash data for round-trip safety
                if (IsAtLeastVersion(1, 6))
                {
                    byte platformCount = bs.Read1Byte();
                    vs.VSPlatformHashes = new List<VertexShaderPlatformHash>();
                    for (int p = 0; p < platformCount; p++)
                    {
                        byte platform = bs.Read1Byte();
                        byte[] hash = bs.ReadBytes(32);
                        vs.VSPlatformHashes.Add(new VertexShaderPlatformHash { Platform = platform, Hash = hash });
                    }
                }
                else if (IsAtLeastVersion(1, 5))
                {
                    // v1.5: 32-byte dummy + 32-byte actual VS hash
                    vs.VSHashDummy = bs.ReadBytes(32);
                    vs.VSHash = bs.ReadBytes(32);
                }

                // If HasInstancedData: read instanced VS path + hashes after the regular VS
                if (ls.HasInstancedData)
                {
                    vs.InstancedPath = bs.ReadString(StringCoding.VariableByteCount);

                    if (IsAtLeastVersion(1, 6))
                    {
                        byte instPlatformCount = bs.Read1Byte();
                        vs.InstancedPlatformHashes = new List<VertexShaderPlatformHash>();
                        for (int p = 0; p < instPlatformCount; p++)
                        {
                            byte platform = bs.Read1Byte();
                            byte[] hash = bs.ReadBytes(32);
                            vs.InstancedPlatformHashes.Add(new VertexShaderPlatformHash { Platform = platform, Hash = hash });
                        }
                    }
                    else if (IsAtLeastVersion(1, 5))
                    {
                        vs.InstancedVSHashDummy = bs.ReadBytes(32);
                        vs.InstancedVSHash = bs.ReadBytes(32);
                        // v1.5+ instanced PS skip
                        bs.ReadString(StringCoding.VariableByteCount); // instanced PS path (skipped)
                        if (IsAtLeastVersion(1, 6))
                            bs.Read1Byte(); // PS platform count
                    }
                }

                ls.VertexShaders.Add(vs);
            }

            // Shader stage bits. Bits: 0=VS, 3=GS, 4=PS. Engine default = 0x11 (VS|PS).
            ls.ShaderStageBits = 0x11;
            if (IsAtLeastVersion(1, 3))
                ls.ShaderStageBits = bs.ReadInt32();

            // Combined PS/GS path string
            ls.GeometryPixelShader = bs.ReadString(StringCoding.VariableByteCount);

            LightScenarios.Add(ls);
        }
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(1, 1))
            bs.WriteBoolean(IsInline);

        bs.WriteByte((byte)LightScenarios.Count);
        foreach (var ls in LightScenarios)
        {
            bs.WriteString(ls.Name, StringCoding.VariableByteCount);
            bs.WriteUInt32(ls.Version);

            if (IsAtLeastVersion(1, 4))
                bs.WriteBoolean(ls.HasInstancedData);

            if (IsAtLeastVersion(1, 2))
                bs.WriteUInt32((uint)ls.VertexShaders.Count);

            foreach (var vs in ls.VertexShaders)
            {
                if (IsAtLeastVersion(1, 2))
                    bs.WriteByte(vs.AnimScenarioFlags);

                bs.WriteString(vs.Path ?? "", StringCoding.VariableByteCount);

                if (IsAtLeastVersion(1, 6))
                {
                    var hashes = vs.VSPlatformHashes ?? new List<VertexShaderPlatformHash>();
                    bs.WriteByte((byte)hashes.Count);
                    foreach (var ph in hashes)
                    {
                        bs.WriteByte(ph.Platform);
                        bs.WriteBytes(ph.Hash ?? new byte[32]);
                    }
                }
                else if (IsAtLeastVersion(1, 5))
                {
                    bs.WriteBytes(vs.VSHashDummy ?? new byte[32]);
                    bs.WriteBytes(vs.VSHash ?? new byte[32]);
                }

                if (ls.HasInstancedData)
                {
                    bs.WriteString(vs.InstancedPath ?? "", StringCoding.VariableByteCount);

                    if (IsAtLeastVersion(1, 6))
                    {
                        var hashes = vs.InstancedPlatformHashes ?? new List<VertexShaderPlatformHash>();
                        bs.WriteByte((byte)hashes.Count);
                        foreach (var ph in hashes)
                        {
                            bs.WriteByte(ph.Platform);
                            bs.WriteBytes(ph.Hash ?? new byte[32]);
                        }
                    }
                    else if (IsAtLeastVersion(1, 5))
                    {
                        bs.WriteBytes(vs.InstancedVSHashDummy ?? new byte[32]);
                        bs.WriteBytes(vs.InstancedVSHash ?? new byte[32]);
                        bs.WriteString("", StringCoding.VariableByteCount); // instanced PS path placeholder
                    }
                }
            }

            if (IsAtLeastVersion(1, 3))
                bs.WriteInt32(ls.ShaderStageBits);

            bs.WriteString(ls.GeometryPixelShader ?? "", StringCoding.VariableByteCount);
        }
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        //not needed for modelbin
    }
}

public class LightScenario
{
    public string Name { get; set; }
    public uint Version { get; set; }
    // Set for v1.4+. When true, each anim slot also carries an instanced VS path and hashes.
    public bool HasInstancedData { get; set; }
    // Number of anim slots. v1.2+ reads from file; pre-v1.2 always 1.
    public uint AnimCount { get; set; } = 1;
    public List<VertexShaderEntry> VertexShaders { get; set; } = new();
    public string GeometryPixelShader { get; set; }
    // Shader stage bitfield. Bits: 0=VS, 3=GS, 4=PS. Default = 17 (VS|PS). Pre-v1.3 files don't write this field.
    public int ShaderStageBits { get; set; } = 0x11;
}

public class VertexShaderPlatformHash
{
    // Platform ID byte (e.g. 1 = D3D12).
    public byte Platform { get; set; }
    // 32-byte SHA-256 platform shader hash.
    public byte[] Hash { get; set; }
}

public class VertexShaderEntry
{
    // v1.2+ animScenarioFlags byte preceding the VS path.
    public byte AnimScenarioFlags { get; set; }
    public string Path { get; set; }
    // v1.5 only: 32-byte dummy read before the real VS hash.
    public byte[] VSHashDummy { get; set; }
    // v1.5 only: 32-byte actual VS hash.
    public byte[] VSHash { get; set; }
    // v1.6+ platform-tagged VS hashes (preserves all platforms).
    public List<VertexShaderPlatformHash> VSPlatformHashes { get; set; }
    // Instanced VS fields (HasInstancedData == true)
    public string InstancedPath { get; set; }
    public byte[] InstancedVSHashDummy { get; set; }
    public byte[] InstancedVSHash { get; set; }
    public List<VertexShaderPlatformHash> InstancedPlatformHashes { get; set; }

    // Legacy alias kept for any existing callers
    [System.Obsolete("Use AnimScenarioFlags instead")]
    public byte UnkV1_2 { get => AnimScenarioFlags; set => AnimScenarioFlags = value; }
    [System.Obsolete("Use InstancedPath instead")]
    public string PathV1_4 { get => InstancedPath; set => InstancedPath = value; }
}
