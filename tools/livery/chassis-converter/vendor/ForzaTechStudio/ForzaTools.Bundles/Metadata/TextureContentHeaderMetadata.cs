using Syroot.BinaryData;
using ForzaTools.Bundles.Metadata.TextureContentHeaders;
using System.IO;

namespace ForzaTools.Bundles.Metadata;

public class TextureContentHeaderMetadata : BundleMetadata
{
    // Holds the raw data or parsed object
    public PCTextureContentHeader? PCHeader { get; set; }
    public DurangoTextureContentHeader? DurangoHeader { get; set; }
    
    // Store blob version for proper format detection
    public byte BlobVersionMajor { get; set; }
    public byte BlobVersionMinor { get; set; }

    public override void ReadMetadataData(BinaryStream bs)
    {
        // parsing deferred until ParseWithBlobVersion is called
    }
    
    // Parse using blob version to determine PC or Durango format
    public void ParseWithBlobVersion(byte blobVersionMajor, byte blobVersionMinor)
    {
        BlobVersionMajor = blobVersionMajor;
        BlobVersionMinor = blobVersionMinor;
        
        byte[] data = GetContents();
        if (data == null || data.Length == 0) return;

        // blob version 2.0 = Durango format
        bool isDurango = blobVersionMajor == 2 && blobVersionMinor == 0;

        if (isDurango)
        {
            DurangoHeader = new DurangoTextureContentHeader();
            DurangoHeader.Read(data);
        }
        else
        {
            PCHeader = new PCTextureContentHeader();
            PCHeader.Read(data);
        }
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        if (PCHeader != null)
        {
            PCHeader.Write(bs);
        }
        else if (DurangoHeader != null)
        {
            DurangoHeader.Write(bs);
        }
        else
        {
            var contents = GetContents();
            if (contents != null)
                bs.Write(contents);
        }
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        if (PCHeader != null)
        {
            PCHeader.Write(bs);
        }
        else if (DurangoHeader != null)
        {
            DurangoHeader.Write(bs);
        }
        else
        {
            var contents = GetContents();
            if (contents != null)
                bs.Write(contents);
            else
                bs.WriteBytes([]); // Safe default
        }
    }
}