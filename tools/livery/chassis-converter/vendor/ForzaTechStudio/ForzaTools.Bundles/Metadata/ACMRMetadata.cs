using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public class ACMRMetadata : BundleMetadata
{
    public float AverageCacheMissRatio { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        AverageCacheMissRatio = bs.ReadSingle();
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        bs.WriteSingle(AverageCacheMissRatio);
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        bs.WriteSingle(AverageCacheMissRatio);
    }
}