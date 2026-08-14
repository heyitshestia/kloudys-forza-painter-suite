using Syroot.BinaryData;

namespace ForzaTools.Bundles.Blobs;

public class TextureContentBlob : BundleBlob
{
    public byte[] Data { get; set; }

    public override void ReadBlobData(BinaryStream bs)
    {
        // Data is already read into _data by BundleBlob.Read; just expose it directly.
        Data = GetContents();
    }

    public override void SerializeBlobData(BinaryStream bs)
    {
        if (Data != null)
            bs.WriteBytes(Data);
    }

    public override void CreateModelBinBlobData(BinaryStream bs)
    {
        if (Data != null)
            bs.WriteBytes(Data);
    }


}