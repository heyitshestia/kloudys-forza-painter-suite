using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public class BlendMetadata : BundleMetadata
{
    public bool Unk1 { get; set; }
    public bool Unk2 { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        // v1 initial - FH3, FH5
        // Boolean unk;
        // Boolean unk;
        if (Version == 1)
        {
            Unk1 = bs.ReadBoolean();
            Unk2 = bs.ReadBoolean();
        }
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        if (Version == 1)
        {
            bs.WriteBoolean(Unk1);
            bs.WriteBoolean(Unk2);
        }
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        if (Version == 1)
        {
            bs.WriteBoolean(Unk1);
            bs.WriteBoolean(Unk2);
        }
    }
}