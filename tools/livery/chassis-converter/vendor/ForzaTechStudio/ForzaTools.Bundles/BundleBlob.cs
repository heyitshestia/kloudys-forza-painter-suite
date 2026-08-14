using System;
using System.Collections.Generic;
using System.Diagnostics;
using Syroot.BinaryData;
using ForzaTools.Bundles.Metadata;

namespace ForzaTools.Bundles;

public abstract class BundleBlob
{
    public const int InfoSize = 0x18;

    public uint Tag { get; set; }
    public byte VersionMajor { get; set; }
    public byte VersionMinor { get; set; }

    public uint CompressedSize { get; set; }
    public uint UncompressedSize { get; set; }

    public long FileOffset { get; set; }

    public uint Id { get; set; } = 1;

    public byte[] Data
    {
        get => GetContents() ?? Array.Empty<byte>();
        set => _data = value;
    }

    public List<BundleMetadata> Metadatas { get; set; } = new List<BundleMetadata>();

    private byte[] _data { get; set; }

    public T GetMetadataByTag<T>(uint tag) where T : BundleMetadata
    {
        foreach (var metadata in Metadatas)
        {
            if (metadata.Tag == tag)
                return (T)metadata;
        }
        return null;
    }

    public virtual void Read(BinaryStream bs, long baseBundleOffset)
    {
        Tag = bs.ReadUInt32();
        VersionMajor = bs.Read1Byte();
        VersionMinor = bs.Read1Byte();

        uint metadataCount = bs.ReadUInt16();
        uint metadataOffset = bs.ReadUInt32();
        uint dataOffset = bs.ReadUInt32();

        CompressedSize = bs.ReadUInt32();
        UncompressedSize = bs.ReadUInt32();

        long basePos = bs.Position;

        // 1. Read Metadata
        for (int i = 0; i < metadataCount; i++)
        {
            bs.Position = baseBundleOffset + metadataOffset + (i * BundleMetadata.InfoSize);
            uint metadataTag = bs.ReadUInt32();
            bs.Position -= 4;

            BundleMetadata metadata = GetMetadataObjectByTag(metadataTag);
            metadata.Read(bs);
            Metadatas.Add(metadata);
        }

        // 2. Read Blob Data
        bs.Position = baseBundleOffset + dataOffset;
        this.FileOffset = bs.Position;

        uint sizeToRead = UncompressedSize > 0 ? UncompressedSize : CompressedSize;

        _data = bs.ReadBytes((int)sizeToRead);

        bs.Position = baseBundleOffset + dataOffset;
        ReadBlobData(bs);

        // Release raw bytes after parsing
        _data = null;
    }

    public abstract void ReadBlobData(BinaryStream bs);
    public abstract void SerializeBlobData(BinaryStream bs);

    private BundleMetadata GetMetadataObjectByTag(uint tag)
    {
        return tag switch
        {
            BundleMetadata.TAG_METADATA_Name => new NameMetadata(),
            BundleMetadata.TAG_METADATA_Identifier => new IdentifierMetadata(),
            BundleMetadata.TAG_METADATA_Atlas => new AtlasMetadata(),
            BundleMetadata.TAG_METADATA_ARTX => new ARTXMetadata(),
            BundleMetadata.TAG_METADATA_BBox => new BoundaryBoxMetadata(),
            BundleMetadata.TAG_METADATA_TextureContentHeader => new TextureContentHeaderMetadata(),
            BundleMetadata.TAG_METADATA_TRef => new TextureReferencesMetadata(),
            BundleMetadata.TAG_METADATA_ACMR => new ACMRMetadata(),
            BundleMetadata.TAG_METADATA_VDCL => new VDCLMetadata(),
            BundleMetadata.TAG_METADATA_BLEN => new BlendMetadata(),
            _ => new RawMetadata(),
        };
    }

    public void SerializeMetadatas(BinaryStream bs)
    {
        long headersStartOffset = bs.Position;
        long lastDataPos = bs.Position + (BundleMetadata.InfoSize * Metadatas.Count);
        for (int j = 0; j < Metadatas.Count; j++)
        {
            bs.Position = lastDataPos;
            long headerOffset = headersStartOffset + (BundleMetadata.InfoSize * j);
            long dataStartOffset = lastDataPos;
            BundleMetadata metadata = Metadatas[j];
            metadata.SerializeMetadataData(bs);
            ulong relativeOffset = (ulong)(lastDataPos - headerOffset);
            lastDataPos = bs.Position;
            bs.Position = headerOffset;
            bs.WriteUInt32(metadata.Tag);
            ulong metadataSize = (ulong)(lastDataPos - dataStartOffset);
            ushort flags = (ushort)(metadataSize << 4 | (ushort)(metadata.Version & 0b1111));
            bs.WriteUInt16(flags);
            bs.WriteUInt16((ushort)relativeOffset);
        }
        bs.Position = lastDataPos;
    }

    public virtual void CreateModelBinMetadatas(BinaryStream bs)
    {
        WriteMetadatasInternal(bs, m => m.CreateModelBinMetadataData(bs));
    }

    private void WriteMetadatasInternal(BinaryStream bs, Action<BundleMetadata> writeDataAction)
    {
        long headersStartOffset = bs.Position;
        long lastDataPos = bs.Position + (BundleMetadata.InfoSize * Metadatas.Count);

        for (int j = 0; j < Metadatas.Count; j++)
        {
            bs.Position = lastDataPos;
            long headerOffset = headersStartOffset + (BundleMetadata.InfoSize * j);
            long dataStartOffset = lastDataPos;
            BundleMetadata metadata = Metadatas[j];
            writeDataAction(metadata);
            ulong relativeOffset = (ulong)(lastDataPos - headerOffset);
            lastDataPos = bs.Position;
            bs.Position = headerOffset;
            bs.WriteUInt32(metadata.Tag);
            ulong metadataSize = (ulong)(lastDataPos - dataStartOffset);
            ushort flags = (ushort)(metadataSize << 4 | (ushort)(metadata.Version & 0b1111));
            bs.WriteUInt16(flags);
            bs.WriteUInt16((ushort)relativeOffset);
        }
        bs.Position = lastDataPos;
    }

    public abstract void CreateModelBinBlobData(BinaryStream bs);

    public virtual byte[] GetContents() => _data;

    public bool IsAtMostVersion(byte versionMajor, byte versionMinor)
    {
        return VersionMajor < versionMajor || (VersionMajor == versionMajor && VersionMinor <= versionMinor);
    }

    public bool IsAtLeastVersion(byte versionMajor, byte versionMinor)
    {
        return VersionMajor > versionMajor || (VersionMajor == versionMajor && VersionMinor >= versionMinor);
    }
}