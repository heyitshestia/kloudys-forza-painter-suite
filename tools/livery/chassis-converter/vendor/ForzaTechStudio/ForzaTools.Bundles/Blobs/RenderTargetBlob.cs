using Syroot.BinaryData;
using System.Collections.Generic;

namespace ForzaTools.Bundles.Blobs;

// A single VS/PS pair in a TRGT blob.
// DxbcBytesVS / DxbcBytesPS are populated when IsInline == true so that
// the serializer can write them back verbatim without any data loss.
public sealed record RenderTargetEntry(
    string VertexShaderName,
    string PixelShaderName,
    byte VSPlatformCount,
    byte PSPlatformCount,
    byte[] DxbcBytesVS,
    byte[] DxbcBytesPS)
{
    // Backwards-compat alias so existing code that reads .PlatformCount still compiles
    public byte PlatformCount => VSPlatformCount;
}

public class RenderTargetBlob : BundleBlob
{
    public bool IsInline { get; set; }
    // Number of render target pairs (raw byte read from file).
    public byte UnkLength { get; set; }
    public IReadOnlyList<RenderTargetEntry> Entries { get; private set; } = [];

    public override void ReadBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(1, 1))
            IsInline = bs.ReadBoolean();

        UnkLength = bs.Read1Byte();

        if (UnkLength == 0)
            return;

        try
        {
            var entries = new List<RenderTargetEntry>(UnkLength);
            for (int i = 0; i < UnkLength; i++)
            {
                string vsName = bs.ReadString(StringCoding.VariableByteCount);
                // v1.3+: per-entry VS platform count (initialised to 2 if no blob; read per-entry if v1.3+)
                byte vsPlatformCount = 2;
                if (IsAtLeastVersion(1, 3))
                    vsPlatformCount = bs.Read1Byte();
                byte[] dxbcVS = IsInline ? ReadAndReturnDxbcBlock(bs) : [];

                string psName = bs.ReadString(StringCoding.VariableByteCount);
                byte psPlatformCount = 2;
                if (IsAtLeastVersion(1, 3))
                    psPlatformCount = bs.Read1Byte();
                byte[] dxbcPS = IsInline ? ReadAndReturnDxbcBlock(bs) : [];

                entries.Add(new RenderTargetEntry(vsName, psName, vsPlatformCount, psPlatformCount, dxbcVS, dxbcPS));
            }
            Entries = entries;
        }
        catch
        {
            // Parsing failed; Entries remains partially filled or empty
        }
    }

    // Reads a complete DXBC block from the stream and returns the raw bytes (including header).
    // Throws <see cref="System.IO.InvalidDataException"/> if the magic is wrong.
    private static byte[] ReadAndReturnDxbcBlock(BinaryStream bs)
    {
        // DXBC layout: 4 magic + 16 MD5 + 4 version + 4 totalSize = 28 header bytes
        uint magic = bs.ReadUInt32();
        if (magic != 0x43425844u) // 'DXBC'
            throw new System.IO.InvalidDataException($"Expected DXBC magic, got 0x{magic:X8}");

        byte[] checksum = bs.ReadBytes(16);
        uint version    = bs.ReadUInt32();
        uint totalSize  = bs.ReadUInt32();

        // Reconstruct the full DXBC blob
        int remaining = (int)totalSize - 28;
        byte[] body = remaining > 0 ? bs.ReadBytes(remaining) : [];

        // Pack everything back into a single byte array for lossless storage
        using var ms = new System.IO.MemoryStream((int)totalSize);
        ms.Write(System.BitConverter.GetBytes(magic));
        ms.Write(checksum);
        ms.Write(System.BitConverter.GetBytes(version));
        ms.Write(System.BitConverter.GetBytes(totalSize));
        ms.Write(body);
        return ms.ToArray();
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(1, 1))
            bs.WriteBoolean(IsInline);

        bs.WriteByte((byte)Entries.Count);

        foreach (var entry in Entries)
        {
            bs.WriteString(entry.VertexShaderName, StringCoding.VariableByteCount);
            if (IsAtLeastVersion(1, 3))
                bs.WriteByte(entry.VSPlatformCount);
            if (IsInline && entry.DxbcBytesVS?.Length > 0)
                bs.WriteBytes(entry.DxbcBytesVS);

            bs.WriteString(entry.PixelShaderName, StringCoding.VariableByteCount);
            if (IsAtLeastVersion(1, 3))
                bs.WriteByte(entry.PSPlatformCount);
            if (IsInline && entry.DxbcBytesPS?.Length > 0)
                bs.WriteBytes(entry.DxbcBytesPS);
        }
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        if (IsAtLeastVersion(1, 1))
            bs.WriteBoolean(IsInline);

        bs.WriteByte((byte)Entries.Count);

        foreach (var entry in Entries)
        {
            bs.WriteString(entry.VertexShaderName, StringCoding.VariableByteCount);
            if (IsAtLeastVersion(1, 3))
                bs.WriteByte(entry.VSPlatformCount);
            if (IsInline && entry.DxbcBytesVS?.Length > 0)
                bs.WriteBytes(entry.DxbcBytesVS);

            bs.WriteString(entry.PixelShaderName, StringCoding.VariableByteCount);
            if (IsAtLeastVersion(1, 3))
                bs.WriteByte(entry.PSPlatformCount);
            if (IsInline && entry.DxbcBytesPS?.Length > 0)
                bs.WriteBytes(entry.DxbcBytesPS);
        }
    }
}
