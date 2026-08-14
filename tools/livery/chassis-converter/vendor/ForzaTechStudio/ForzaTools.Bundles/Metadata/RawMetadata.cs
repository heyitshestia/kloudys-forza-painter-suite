using System;
using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public class RawMetadata : BundleMetadata
{
    public byte[] RawData { get; set; } = Array.Empty<byte>();

    public override void ReadMetadataData(BinaryStream bs)
    {
        RawData = Size == 0 ? Array.Empty<byte>() : bs.ReadBytes(Size);
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        bs.Write(RawData ?? Array.Empty<byte>());
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        bs.Write(RawData ?? Array.Empty<byte>());
    }
}