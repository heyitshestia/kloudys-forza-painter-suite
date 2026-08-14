using ForzaTools.Bundles.Metadata;
using ForzaTools.Shared;
using Syroot.BinaryData;
using System.Collections.Generic;

namespace ForzaTools.Bundles.Blobs;

// VLay/ILay blob. Defines the vertex input layout: semantic names, element descriptors, and optional packed formats.
// v1.0+ includes per-element packed format values; v1.1+ adds a flags field.
public class VertexLayoutBlob : BundleBlob
{
    public List<string> SemanticNames { get; set; } = new();
    public List<D3D12_INPUT_LAYOUT_DESC> Elements { get; set; } = new();
    public List<DXGI_FORMAT> PackedFormats { get; set; } = new();
    public uint Flags { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        ushort semanticCount = bs.ReadUInt16();
        for (int i = 0; i < semanticCount; i++)
            SemanticNames.Add(bs.ReadString(StringCoding.Int32CharCount));

        ushort elementCount = bs.ReadUInt16();
        for (int i = 0; i < elementCount; i++)
        {
            var desc = new D3D12_INPUT_LAYOUT_DESC();
            desc.Read(bs);
            Elements.Add(desc);
        }

        // v1.0+: packed formats present (one per element)
        if (VersionMajor >= 1)
        {
            for (int i = 0; i < elementCount; i++)
                PackedFormats.Add((DXGI_FORMAT)bs.ReadInt32());
        }
        else
        {
            // v0.x: no packed formats in file; caller infers from DXGI_FORMAT lookup table.
            // Populate with UNKNOWN placeholders so the list stays in sync with Elements.
            for (int i = 0; i < elementCount; i++)
                PackedFormats.Add(DXGI_FORMAT.DXGI_FORMAT_UNKNOWN);
        }

        // v1.1+: material system usage flags
        if (IsAtLeastVersion(1, 1))
            Flags = bs.ReadUInt32();
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        WriteSemanticNames(bs);
        WriteElements(bs);

        if (VersionMajor >= 1)
            WritePackedFormats(bs);

        if (IsAtLeastVersion(1, 1))
            bs.WriteUInt32(Flags);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        WriteSemanticNames(bs);
        WriteElements(bs);
        WritePackedFormats(bs);
        bs.WriteUInt32(Flags);
    }

    // Helpers

    private void WriteSemanticNames(BinaryStream bs)
    {
        bs.WriteUInt16((ushort)SemanticNames.Count);
        foreach (string name in SemanticNames)
            bs.WriteString(name, StringCoding.Int32CharCount);
    }

    private void WriteElements(BinaryStream bs)
    {
        bs.WriteUInt16((ushort)Elements.Count);
        foreach (var elem in Elements)
            elem.Serialize(bs);
    }

    private void WritePackedFormats(BinaryStream bs)
    {
        // No count prefix — reader uses elementCount from the Elements list
        foreach (DXGI_FORMAT fmt in PackedFormats)
            bs.WriteInt32((int)fmt);
    }
}

// One element in a vertex input layout. 20 bytes on the wire.
// Describes semantic name/index, input slot, format, byte offset, and instance step rate.
public class D3D12_INPUT_LAYOUT_DESC
{
    public short SemanticNameIndex;
    public short SemanticIndex;
    public short InputSlot;
    public short InputSlotClass;
    public DXGI_FORMAT Format;
    public int AlignedByteOffset;
    public int InstanceDataStepRate;

    public void Read(BinaryStream bs)
    {
        SemanticNameIndex   = bs.ReadInt16();
        SemanticIndex       = bs.ReadInt16();
        InputSlot           = bs.ReadInt16();
        InputSlotClass      = bs.ReadInt16();
        Format              = (DXGI_FORMAT)bs.ReadInt32();
        AlignedByteOffset   = bs.ReadInt32();
        InstanceDataStepRate = bs.ReadInt32();
    }

    public void Serialize(BinaryStream bs)
    {
        bs.WriteInt16(SemanticNameIndex);
        bs.WriteInt16(SemanticIndex);
        bs.WriteInt16(InputSlot);
        bs.WriteInt16(InputSlotClass);
        bs.WriteInt32((int)Format);
        bs.WriteInt32(AlignedByteOffset);
        bs.WriteInt32(InstanceDataStepRate);
    }
}
