using System;
using Syroot.BinaryData;
using System.Collections.Generic;
using System.Numerics;

namespace ForzaTools.Bundles.Blobs;

public class ManufacturerColorsBlob : BundleBlob
{
    private const int Fh6GroupTrailerSize = 27;

    public List<ManufacturerColorGroup> Groups { get; set; } = new();
    public byte[] Fh6TrailingBytes { get; set; } = Array.Empty<byte>();

    public override void ReadBlobData(BinaryStream bs)
    {
        Groups.Clear();
        Fh6TrailingBytes = Array.Empty<byte>();

        byte groupCount = bs.Read1Byte();
        long blobEnd = FileOffset + (UncompressedSize > 0 ? UncompressedSize : CompressedSize);

        for (int i = 0; i < groupCount; i++)
        {
            var group = new ManufacturerColorGroup();
            byte matCount = bs.Read1Byte();

            for (int m = 0; m < matCount; m++)
                group.Entries.Add(ReadEntry(bs));

            if (IsAtLeastVersion(2, 0))
                ReadFh6GroupTrailer(bs, group, blobEnd);

            Groups.Add(group);
        }

        if (IsAtLeastVersion(2, 0) && bs.Position < blobEnd)
            Fh6TrailingBytes = bs.ReadBytes((int)(blobEnd - bs.Position));
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        WriteBlobData(bs);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        WriteBlobData(bs);
    }

    private void WriteBlobData(BinaryStream bs)
    {
        bs.WriteByte((byte)Groups.Count);
        foreach (var group in Groups)
        {
            bs.WriteByte((byte)group.Entries.Count);
            foreach (var entry in group.Entries)
            {
                WriteEntry(bs, entry);
            }

            if (IsAtLeastVersion(2, 0))
            {
                WriteFh6GroupTrailer(bs, group);
            }
        }

        if (IsAtLeastVersion(2, 0) && Fh6TrailingBytes.Length > 0)
            bs.Write(Fh6TrailingBytes);
    }

    private ManufacturerColorEntry ReadEntry(BinaryStream bs)
    {
        var entry = new ManufacturerColorEntry();

        if (IsAtLeastVersion(2, 0))
        {
            uint materialNameCount = bs.ReadUInt32();
            entry.MaterialNames = new List<string>((int)materialNameCount);

            for (int i = 0; i < materialNameCount; i++)
                entry.MaterialNames.Add(bs.ReadString(StringCoding.VariableByteCount));
        }
        else if (IsAtLeastVersion(1, 1))
        {
            entry.MaterialIndexMask = bs.ReadUInt32();
        }
        else
        {
            entry.MaterialIndexMask = bs.ReadUInt16();
        }

        entry.PreviewColor = ReadVector3(bs);
        entry.Path = bs.ReadString(StringCoding.VariableByteCount);
        return entry;
    }

    private void WriteEntry(BinaryStream bs, ManufacturerColorEntry entry)
    {
        if (IsAtLeastVersion(2, 0))
        {
            var materialNames = entry.MaterialNames ?? new List<string>();
            bs.WriteUInt32((uint)materialNames.Count);

            foreach (var materialName in materialNames)
                bs.WriteString(materialName ?? string.Empty, StringCoding.VariableByteCount);
        }
        else if (IsAtLeastVersion(1, 1))
        {
            bs.WriteUInt32(entry.MaterialIndexMask);
        }
        else
        {
            bs.WriteUInt16((ushort)entry.MaterialIndexMask);
        }

        WriteVector3(bs, entry.PreviewColor);
        bs.WriteString(entry.Path ?? string.Empty, StringCoding.VariableByteCount);
    }

    private static Vector3 ReadVector3(BinaryStream bs)
    {
        return new Vector3(bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle());
    }

    private static void WriteVector3(BinaryStream bs, Vector3 value)
    {
        bs.WriteSingle(value.X);
        bs.WriteSingle(value.Y);
        bs.WriteSingle(value.Z);
    }

    private static void ReadFh6GroupTrailer(BinaryStream bs, ManufacturerColorGroup group, long blobEnd)
    {
        if (bs.Position + Fh6GroupTrailerSize > blobEnd)
            return;

        group.PrimaryGroupPreviewPresent = bs.Read1Byte();
        group.PrimaryGroupPreviewColor = ReadVector3(bs);
        group.GroupPreviewZero = bs.Read1Byte();
        group.SecondaryGroupPreviewPresent = bs.Read1Byte();
        group.SecondaryGroupPreviewColor = ReadVector3(bs);
    }

    private static void WriteFh6GroupTrailer(BinaryStream bs, ManufacturerColorGroup group)
    {
        bs.WriteByte(group.PrimaryGroupPreviewPresent);
        WriteVector3(bs, group.PrimaryGroupPreviewColor);
        bs.WriteByte(group.GroupPreviewZero);
        bs.WriteByte(group.SecondaryGroupPreviewPresent);
        WriteVector3(bs, group.SecondaryGroupPreviewColor);
    }
}

public class ManufacturerColorGroup
{
    public List<ManufacturerColorEntry> Entries { get; set; } = new();
    public byte PrimaryGroupPreviewPresent { get; set; } = 1;
    public Vector3 PrimaryGroupPreviewColor { get; set; }
    public byte GroupPreviewZero { get; set; }
    public byte SecondaryGroupPreviewPresent { get; set; } = 1;
    public Vector3 SecondaryGroupPreviewColor { get; set; }
}

public class ManufacturerColorEntry
{
    public uint MaterialIndexMask { get; set; }
    public Vector3 PreviewColor { get; set; }
    public List<string> MaterialNames { get; set; } = new();
    public string Path { get; set; } = string.Empty;
}