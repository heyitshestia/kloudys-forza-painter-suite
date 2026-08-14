using System;
using System.Collections.Generic;
using Syroot.BinaryData;

namespace ForzaTools.Bundles.Metadata;

public class TextureReferencesMetadata : BundleMetadata
{
    // List of CRC32 hashes of the .swatchbin paths
    public List<uint> TexturePathHashes { get; set; } = new();

    public override void ReadMetadataData(BinaryStream bs)
    {

        int count = Size / 4;
        for (int i = 0; i < count; i++)
        {
            TexturePathHashes.Add(bs.ReadUInt32());
        }
    }

    public override void SerializeMetadataData(BinaryStream bs)
    {
        foreach (var hash in TexturePathHashes)
        {
            bs.WriteUInt32(hash);
        }
    }

    public override void CreateModelBinMetadataData(BinaryStream bs)
    {
        var safeHashes = TexturePathHashes ?? new List<uint>();
        foreach (var hash in safeHashes)
        {
            bs.WriteUInt32(hash);
        }
    }
}