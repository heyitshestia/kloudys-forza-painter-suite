using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public class AtlasMetadata : BundleMetadata
{
    public bool Unk { get; set; }
    public bool UnkV2 { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        if (Version >= 1)
            Unk = bs.ReadBoolean();

        if (Version >= 2)
            UnkV2 = bs.ReadBoolean();
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        if (Version >= 1)
            bs.WriteBoolean(Unk);

        if (Version >= 2)
            bs.WriteBoolean(UnkV2);
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        if (Version >= 1)
            bs.WriteBoolean(Unk);

        if (Version >= 2)
            bs.WriteBoolean(UnkV2);
    }
}