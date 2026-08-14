using System;
using Syroot.BinaryData;

namespace ForzaTools.Bundles;

public abstract class BundleMetadata
{
    public const int InfoSize = 0x08;

    // Models (modelbin)
    public const uint TAG_METADATA_Name = 0x4E616D65; // "Name"
    public const uint TAG_METADATA_TextureContentHeader = 0x54584348; // "TXCH"
    public const uint TAG_METADATA_Identifier = 0x49642020; // "Id  "
    public const uint TAG_METADATA_BBox = 0x42426F78; // "BBox"
    public const uint TAG_METADATA_TRef = 0x54526566; // "TRef"
    public const uint TAG_METADATA_ACMR = 0x41434D52; // "ACMR"

    // Materials (materialbin)
    public const uint TAG_METADATA_Atlas = 0x41545354; // "ATST"
    public const uint TAG_METADATA_ARTX = 0x58545241; // "ARTX"
    public const uint TAG_METADATA_BLEN = 0x424C454E; // "BLEN"
    public const uint TAG_METADATA_VDCL = 0x5644434C; // "VDCL"

    public uint Tag { get; set; }
    public byte Version { get; set; }
    public ushort Size { get; set; }

    public long FileOffset { get; set; }

    private byte[] _data { get; set; }

    public virtual void Read(BinaryStream bs)
    {
        long basePos = bs.Position;
        Tag = bs.ReadUInt32();

        ushort flags = bs.ReadUInt16();
        Size = (ushort)(flags >> 4); // 12 bits
        Version = (byte)(flags & 0b1111); // 4 bits

        ushort offset = bs.ReadUInt16();

        bs.Position = basePos + offset;
        this.FileOffset = bs.Position;

        _data = bs.ReadBytes(Size);

        bs.Position = basePos + offset;
        ReadMetadataData(bs);
    }

    public abstract void ReadMetadataData(BinaryStream bs);

    public abstract void SerializeMetadataData(BinaryStream bs);

    public abstract void CreateModelBinMetadataData(BinaryStream bs);

    public byte[] GetContents() => _data;
}