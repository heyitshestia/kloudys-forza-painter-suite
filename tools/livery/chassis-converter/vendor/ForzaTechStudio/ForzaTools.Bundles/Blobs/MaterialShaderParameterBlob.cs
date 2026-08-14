using Syroot.BinaryData;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Numerics;
using ForzaTools.Bundles.Metadata;

namespace ForzaTools.Bundles.Blobs;

public class MaterialShaderParameterBlob : BundleBlob
{
    public ObservableCollection<ShaderParameter> Parameters { get; set; } = new();

    // Extra data at end of v2.0+
    public uint Unk1 { get; set; }
    public uint Unk2 { get; set; }
    public uint Unk3 { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        ushort count = 0;
        if (IsAtLeastVersion(2, 1))
            count = bs.ReadUInt16();
        else
            count = bs.Read1Byte();

        System.Diagnostics.Debug.WriteLine($"MaterialShaderParameterBlob: Reading {count} parameters (Version {VersionMajor}.{VersionMinor}, Tag: 0x{Tag:X8})");
        System.Diagnostics.Debug.WriteLine($"  Stream position: {bs.Position}, Length: {bs.Length}, Available: {bs.Length - bs.Position}");

        for (int i = 0; i < count; i++)
        {
            long paramStartPos = bs.Position;
            try
            {
                var param = new ShaderParameter();
                param.Read(bs, this);
                Parameters.Add(param);
                long bytesRead = bs.Position - paramStartPos;
                System.Diagnostics.Debug.WriteLine($"  Parameter {i}: Hash=0x{param.NameHash:X8}, Type={param.Type}, Version={param.VersionMajor}.{param.VersionMinor}, BytesRead={bytesRead}");
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"  ERROR reading parameter {i} at position {paramStartPos}: {ex.Message}");
                System.Diagnostics.Debug.WriteLine($"    Current position: {bs.Position}, Remaining: {bs.Length - bs.Position}");
                // Add a placeholder parameter so we don't lose track of the count
                var errorParam = new ShaderParameter
                {
                    NameHash = 0xDEADBEEF,
                    Type = ShaderParameterType.Float,
                    Value = 0f,
                    VersionMajor = VersionMajor,
                    VersionMinor = VersionMinor
                };
                Parameters.Add(errorParam);
            }
        }

        // Check if we have enough bytes left for the unknown data
        long remainingBytes = bs.Length - bs.Position;
        System.Diagnostics.Debug.WriteLine($"After reading parameters: Position={bs.Position}, Remaining={remainingBytes}");

        if (IsAtLeastVersion(2, 0) && Tag == Bundle.TAG_BLOB_MaterialShaderParameter)
        {
            if (remainingBytes >= 12)
            {
                Unk1 = bs.ReadUInt32();
                Unk2 = bs.ReadUInt32();
                Unk3 = bs.ReadUInt32();
                System.Diagnostics.Debug.WriteLine($"  Read unknown data: Unk1=0x{Unk1:X8}, Unk2=0x{Unk2:X8}, Unk3=0x{Unk3:X8}");
            }
            else
            {
                System.Diagnostics.Debug.WriteLine($"  WARNING: Not enough bytes for unknown data (need 12, have {remainingBytes})");
            }
        }
        
        System.Diagnostics.Debug.WriteLine($"MaterialShaderParameterBlob: Successfully loaded {Parameters.Count} parameters");
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(2, 1))
            bs.WriteUInt16((ushort)Parameters.Count);
        else
            bs.WriteByte((byte)Parameters.Count);

        foreach (var param in Parameters)
            param.Serialize(bs, this);

        if (IsAtLeastVersion(2, 0) && Tag == Bundle.TAG_BLOB_MaterialShaderParameter)
        {
            bs.WriteUInt32(Unk1);
            bs.WriteUInt32(Unk2);
            bs.WriteUInt32(Unk3);
        }
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        var safeParams = Parameters ?? new ObservableCollection<ShaderParameter>();

        if (IsAtLeastVersion(2, 1))
            bs.WriteUInt16((ushort)safeParams.Count);
        else
            bs.WriteByte((byte)safeParams.Count);

        foreach (var param in safeParams)
            param.Serialize(bs, this); // Reusing existing Serialize as it handles values well

        if (IsAtLeastVersion(2, 0) && Tag == Bundle.TAG_BLOB_MaterialShaderParameter)
        {
            bs.WriteUInt32(Unk1);
            bs.WriteUInt32(Unk2);
            bs.WriteUInt32(Unk3);
        }
    }
}

public class ShaderParameter
{
    public byte VersionMajor { get; set; }
    public byte VersionMinor { get; set; }
    public uint NameHash { get; set; }
    public uint UnkV3_1 { get; set; }
    public ShaderParameterType Type { get; set; }
    public Guid Guid { get; set; }

    public object Value { get; set; }

    public void Read(BinaryStream bs, BundleBlob blob)
    {
        VersionMajor = bs.Read1Byte();
        VersionMinor = bs.Read1Byte();
        NameHash = bs.ReadUInt32();

        if (VersionMajor > 3 || (VersionMajor == 3 && VersionMinor >= 1))
        {
            bool hasUnk = bs.ReadBoolean();
            if (hasUnk) UnkV3_1 = bs.ReadUInt32();
        }

        Type = (ShaderParameterType)bs.Read1Byte();

        if (VersionMajor >= 3)
            Guid = new Guid(bs.ReadBytes(16));

        try
        {
            switch (Type)
            {
                case ShaderParameterType.Vector:
                case ShaderParameterType.Color:
                case ShaderParameterType.Swizzle:
                case ShaderParameterType.FunctionRange:
                    // Read 4 floats
                    Value = new Vector4(bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle());
                    break;
                case ShaderParameterType.Float:
                    Value = bs.ReadSingle();
                    break;
                case ShaderParameterType.Bool:
                    Value = bs.ReadInt32() != 0;
                    break;
                case ShaderParameterType.Int:
                    Value = bs.ReadInt32();
                    break;
                case ShaderParameterType.Texture2D:
                    Value = ReadTextureParam(bs);
                    break;
                case ShaderParameterType.Sampler:
                    Value = ReadSamplerParam(bs);
                    break;
                case ShaderParameterType.ColorGradient:
                    // Color gradient - read the gradient data
                    Value = ReadColorGradientParam(bs);
                    break;
                case ShaderParameterType.Vector2:
                    Value = new Vector2(bs.ReadSingle(), bs.ReadSingle());
                    // v1 only: legacy 8-byte dummy
                    if (VersionMajor == 1) bs.ReadBytes(8);
                    break;
                default:
                    // Unknown type - log and skip
                    System.Diagnostics.Debug.WriteLine($"Warning: Unsupported shader parameter type {Type} (0x{(byte)Type:X2}) for hash {NameHash:X8}");
                    Value = $"<Unsupported Type: {Type}>";
                    break;
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error reading shader parameter: {ex.Message}");
            Value = $"<Error: {ex.Message}>";
        }
    }

    private TextureParameter ReadTextureParam(BinaryStream bs)
    {
        var tp = new TextureParameter();
        tp.Path = bs.ReadString(StringCoding.VariableByteCount); // Use 7-bit encoding, not Int32CharCount
        if (VersionMajor >= 2)
            tp.PathHash = bs.ReadUInt32();
        return tp;
    }

    private SamplerParameter ReadSamplerParam(BinaryStream bs)
    {
        var sp = new SamplerParameter();
        // Default filter mode is 1 (Linear); overwritten in v1.1+
        sp.UnkType = 1;
        sp.AddressU = bs.ReadInt32();
        sp.AddressV = bs.ReadInt32();
        if (VersionMajor >= 1 && VersionMinor >= 1)
            sp.UnkType = bs.ReadInt32();
        return sp;
    }

    private ColorGradientParameter ReadColorGradientParam(BinaryStream bs)
    {
        var cgp = new ColorGradientParameter();
        uint length = bs.ReadUInt32();
        cgp.Values = new List<Vector4>();
        for (int i = 0; i < length; i++)
        {
            cgp.Values.Add(new Vector4(
                bs.ReadSingle(),
                bs.ReadSingle(),
                bs.ReadSingle(),
                bs.ReadSingle()
            ));
        }
        return cgp;
    }

    public void Serialize(BinaryStream bs, BundleBlob blob)
    {
        bs.WriteByte(VersionMajor);
        bs.WriteByte(VersionMinor);
        bs.WriteUInt32(NameHash);

        if (VersionMajor > 3 || (VersionMajor == 3 && VersionMinor >= 1))
        {
            bs.WriteBoolean(UnkV3_1 != 0);
            if (UnkV3_1 != 0) bs.WriteUInt32(UnkV3_1);
        }

        bs.WriteByte((byte)Type);

        if (VersionMajor >= 3)
            bs.WriteBytes(Guid.ToByteArray());

        try
        {
            switch (Type)
            {
                case ShaderParameterType.Vector:
                case ShaderParameterType.Color:
                case ShaderParameterType.Swizzle:
                case ShaderParameterType.FunctionRange:
                    if (Value is Vector4 v)
                    {
                        bs.WriteSingle(v.X); bs.WriteSingle(v.Y); bs.WriteSingle(v.Z); bs.WriteSingle(v.W);
                    }
                    break;
                case ShaderParameterType.Float:
                    if (Value is float f)
                        bs.WriteSingle(f);
                    break;
                case ShaderParameterType.Bool:
                    if (Value is bool b)
                        bs.WriteInt32(b ? 1 : 0);
                    break;
                case ShaderParameterType.Int:
                    if (Value is int i)
                        bs.WriteInt32(i);
                    break;
                case ShaderParameterType.Texture2D:
                    if (Value is TextureParameter tp)
                    {
                        bs.WriteString(tp.Path ?? "", StringCoding.VariableByteCount); // Use 7-bit encoding
                        if (VersionMajor >= 2) bs.WriteUInt32(tp.PathHash);
                    }
                    break;
                case ShaderParameterType.Sampler:
                    if (Value is SamplerParameter sp)
                    {
                        bs.WriteInt32(sp.AddressU);
                        bs.WriteInt32(sp.AddressV);
                        if (VersionMajor >= 1 && VersionMinor >= 1) bs.WriteInt32(sp.UnkType);
                    }
                    break;
                case ShaderParameterType.ColorGradient:
                    if (Value is ColorGradientParameter cgp)
                    {
                        bs.WriteUInt32((uint)cgp.Values.Count);
                        foreach (var val in cgp.Values)
                        {
                            bs.WriteSingle(val.X); bs.WriteSingle(val.Y);
                            bs.WriteSingle(val.Z); bs.WriteSingle(val.W);
                        }
                    }
                    break;
                case ShaderParameterType.Vector2:
                    if (Value is Vector2 v2)
                    {
                        bs.WriteSingle(v2.X); bs.WriteSingle(v2.Y);
                        if (VersionMajor == 1) bs.WriteBytes(new byte[8]);
                    }
                    break;
                default:
                    // Unsupported type - don't write anything
                    System.Diagnostics.Debug.WriteLine($"Warning: Cannot serialize unsupported shader parameter type {Type}");
                    break;
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error serializing shader parameter: {ex.Message}");
        }
    }



}

public class TextureParameter
{
    public string Path { get; set; }
    public uint PathHash { get; set; }
}

public class SamplerParameter
{
    public int AddressU { get; set; }
    public int AddressV { get; set; }
    public int UnkType { get; set; }
}

public class ColorGradientParameter
{
    public List<Vector4> Values { get; set; } = new();
}

public enum ShaderParameterType : byte
{
    Vector = 0,
    Color = 1,
    Float = 2,
    Bool = 3,
    Int = 4,
    Swizzle = 5,
    Texture2D = 6,
    Sampler = 7,
    ColorGradient = 8,
    FunctionRange = 9,
    Vector2 = 11
}