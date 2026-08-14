using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

public class STexBlob : BundleBlob
{
    public Bundle TextureBundle { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        TextureBundle = new Bundle();
        TextureBundle.Load(bs);
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (TextureBundle != null)
            TextureBundle.Serialize(bs);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        if (TextureBundle != null)
        {
            TextureBundle.CreateModelBin(bs.BaseStream);
        }
        else
        {
            // Empty bundle fallback
            var empty = new Bundle();
            empty.VersionMajor = this.VersionMajor;
            empty.VersionMinor = this.VersionMinor;
            empty.CreateModelBin(bs.BaseStream);
        }
    }
}