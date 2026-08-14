using Syroot.BinaryData;
using System.Numerics;
using ForzaTools.Bundles.Metadata;

namespace ForzaTools.Bundles.Blobs;

// Model blob (tag 'Modl'). Holds mesh, buffer, layout, and material counts plus LOD info.
// FH6 keeps the v1.3+ wire layout to 0x12 bytes: a v1.3 buffer-retention flag at +0x10 and,
// for v1.4+, a visibility mask byte at +0x11.

public class ModelBlob : BundleBlob
{
    public ushort MeshCount { get; set; }
    public ushort BuffersCount { get; set; }
    public ushort VertexLayoutCount { get; set; }
    public ushort MaterialCount { get; set; }

    public bool HasLOD { get; set; }
    public sbyte MinLOD { get; set; }
    public sbyte MaxLOD { get; set; }
    public ushort LODFlags { get; set; }
    public byte DecompressFlags { get; set; }
    public bool RetainCpuBufferCopy { get; set; }
    public byte VisibilityFlags { get; set; } = 0x01;

    // Bounding box from metadata (populated during read, used during write)
    public Vector3? BoundingBoxMin { get; set; }
    public Vector3? BoundingBoxMax { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        // Reads the flat 16-byte ModelStats block
        MeshCount         = bs.ReadUInt16();
        BuffersCount      = bs.ReadUInt16();
        VertexLayoutCount = bs.ReadUInt16();
        MaterialCount     = bs.ReadUInt16();

        HasLOD = bs.Read1Byte() != 0;
        MinLOD = bs.ReadSByte();
        MaxLOD = bs.ReadSByte();
        bs.Read1Byte(); // padding at +0x0B

        LODFlags = bs.ReadUInt16();

        // v1.2+: DecompressFlags byte
        if (IsAtLeastVersion(1, 2))
        {
            DecompressFlags = bs.Read1Byte();
            bs.Read1Byte(); // padding at +0x0F
        }
        // v1.3+: keep-CPU-copy flag at +0x10 and one reserved/visibility byte at +0x11.
        if (IsAtLeastVersion(1, 3))
        {
            RetainCpuBufferCopy = bs.Read1Byte() != 0;
            if (IsAtLeastVersion(1, 4))
                VisibilityFlags = bs.Read1Byte();
            else
                bs.Read1Byte();
        }

        var bboxMetadata = GetMetadataByTag<BoundaryBoxMetadata>(BundleMetadata.TAG_METADATA_BBox);
        if (bboxMetadata != null)
        {
            BoundingBoxMin = bboxMetadata.Min;
            BoundingBoxMax = bboxMetadata.Max;
        }
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        bs.WriteUInt16(MeshCount);
        bs.WriteUInt16(BuffersCount);
        bs.WriteUInt16(VertexLayoutCount);
        bs.WriteUInt16(MaterialCount);
        bs.WriteByte((byte)(HasLOD ? 1 : 0));
        bs.WriteSByte(MinLOD);
        bs.WriteSByte(MaxLOD);
        bs.WriteByte(0); // padding
        bs.WriteUInt16(LODFlags);

        if (IsAtLeastVersion(1, 2)) { bs.WriteByte(DecompressFlags); bs.WriteByte(0); }
        if (IsAtLeastVersion(1, 3))
        {
            bs.WriteByte((byte)(RetainCpuBufferCopy ? 1 : 0));
            bs.WriteByte(IsAtLeastVersion(1, 4) ? VisibilityFlags : (byte)0);
        }
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        bs.WriteUInt16(MeshCount);
        bs.WriteUInt16(BuffersCount);
        bs.WriteUInt16(VertexLayoutCount);
        bs.WriteUInt16(MaterialCount);

        bs.WriteByte((byte)(HasLOD ? 1 : 0));

        // Fix: use actual MinLOD/MaxLOD values rather than hardcoded 5/-1
        bs.WriteSByte(MinLOD);
        bs.WriteSByte(MaxLOD);
        bs.WriteByte(0); // padding

        bs.WriteUInt16(LODFlags);

        // DecompressFlags: always write for new files (v1.2+ format)
        bs.WriteByte(DecompressFlags);
        bs.WriteByte(0); // padding

        if (IsAtLeastVersion(1, 3))
        {
            bs.WriteByte((byte)(RetainCpuBufferCopy ? 1 : 0));
            bs.WriteByte(IsAtLeastVersion(1, 4) ? VisibilityFlags : (byte)0);
        }
    }

    public override void CreateModelBinMetadatas(BinaryStream bs)
    {
        Metadatas.Clear();

        Vector3 minBounds = BoundingBoxMin ?? new Vector3(-45.98f, -0.83f, 2.05f);
        Vector3 maxBounds = BoundingBoxMax ?? new Vector3(45.98f, 0.77f, 2.20f);

        Metadatas.Add(new BoundaryBoxMetadata
        {
            Tag = BundleMetadata.TAG_METADATA_BBox,
            Min = minBounds,
            Max = maxBounds
        });

        base.CreateModelBinMetadatas(bs);
    }
}
