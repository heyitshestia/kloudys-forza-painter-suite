using System;
using System.Collections.Generic;
using System.IO;
using Syroot.BinaryData;
using ForzaTools.Shared;

namespace ForzaTools.Bundles.Metadata.TextureContentHeaders;

public class PCTextureContentHeader
{
    public uint MetaDataFixupOffset { get; set; }
    public uint BlobDataFixupOffset { get; set; }

    public Guid Id { get; set; }
    public uint Width { get; set; }
    public uint Height { get; set; }
    public uint Depth { get; set; }

    // Bitfields/Packed
    public ushort NumSlices { get; set; }
    public byte Platform { get; set; }

    public byte NumMips { get; set; }

    public bool IsCubeMap { get; set; }
    public bool IsPremultipliedAlpha { get; set; }

    public TextureTranscoding Transcoding { get; set; }
    public ColorProfile EncodedColorProfile { get; set; }
    public ColorProfile TargetColorProfile { get; set; }
    public TextureDomain Domain { get; set; }

    public List<TextureContentSlice> Slices { get; set; } = new();

    public void Read(byte[] data)
    {
        using var ms = new MemoryStream(data);
        using var bs = new BinaryStream(ms);
        long basePos = 0;

        MetaDataFixupOffset = bs.ReadUInt32();
        BlobDataFixupOffset = bs.ReadUInt32();

        Id = new Guid(bs.ReadBytes(16));
        Width = bs.ReadUInt32();
        Height = bs.ReadUInt32();
        Depth = bs.ReadUInt32();

        ushort packedSlices = bs.ReadUInt16();
        NumSlices = (ushort)(packedSlices & 0x3FFF); // 14 bits
        Platform = (byte)(packedSlices >> 14);       // 2 bits

        NumMips = bs.Read1Byte();

        byte flags = bs.Read1Byte();
        IsCubeMap = (flags & 1) != 0;
        IsPremultipliedAlpha = (flags & 2) != 0;

        Transcoding = (TextureTranscoding)bs.ReadInt32();
        EncodedColorProfile = (ColorProfile)bs.ReadInt32();
        TargetColorProfile = (ColorProfile)bs.ReadInt32();
        Domain = (TextureDomain)bs.ReadInt32();

        // slice pointer fixup
        uint slicesOffset = bs.ReadUInt32();
        uint slicesNext = bs.ReadUInt32();

        if (slicesOffset != 0)
        {
            bs.Position = basePos + slicesOffset;
            for (int i = 0; i < NumSlices; i++)
            {
                var slice = new TextureContentSlice();
                slice.Encoding = (TextureEncoding)bs.ReadInt32();

                uint mipsOffset = bs.ReadUInt32();
                uint mipsNext = bs.ReadUInt32(); // Unused

                long savePos = bs.Position;

                bs.Position = basePos + mipsOffset;
                for (int j = 0; j < NumMips; j++)
                {
                    var mip = new TextureContentMip();
                    mip.BlobSize = bs.ReadUInt32();
                    mip.BlobOffset = bs.ReadUInt32();
                    bs.ReadUInt32(); // Next pointer (unused)
                    slice.Mips.Add(mip);
                }

                bs.Position = savePos;
                Slices.Add(slice);
            }
        }
    }

    public void Write(BinaryStream bs)
    {
        long basePos = bs.Position;

        // update slice count
        NumSlices = (ushort)Slices.Count;

        // fixed layout offsets relative to basePos
        const uint SlicesPointerFieldOffset = 0x38;
        uint firstMipBlobOffsetField = SlicesPointerFieldOffset + 8u + (uint)(NumSlices * 12) + 4u;

        MetaDataFixupOffset = SlicesPointerFieldOffset;  // 0x38 00 00 00
        BlobDataFixupOffset = Slices.Count > 0 ? firstMipBlobOffsetField : 0u; // 0x50 00 00 00 for 1 slice

        bs.WriteUInt32(MetaDataFixupOffset); // 0x00
        bs.WriteUInt32(BlobDataFixupOffset); // 0x04

        bs.WriteBytes(Id.ToByteArray()); // 0x08 - 0x17
        bs.WriteUInt32(Width);           // 0x18
        bs.WriteUInt32(Height);          // 0x1C
        bs.WriteUInt32(Depth);           // 0x20

        // Bitfields
        ushort packedSlices = (ushort)((NumSlices & 0x3FFF) | ((Platform & 0x3) << 14));
        bs.WriteUInt16(packedSlices); // 0x24

        bs.WriteByte(NumMips); // 0x26

        byte flags = 0;
        if (IsCubeMap) flags |= 1;
        if (IsPremultipliedAlpha) flags |= 2;
        bs.WriteByte(flags); // 0x27

        bs.WriteInt32((int)Transcoding);          // 0x28
        bs.WriteInt32((int)EncodedColorProfile);  // 0x2C
        bs.WriteInt32((int)TargetColorProfile);   // 0x30
        bs.WriteInt32((int)Domain);               // 0x34

        // slice pointer fixup
        if (Slices.Count > 0)
        {
            uint slicesStart = SlicesPointerFieldOffset + 8u;
            bs.WriteUInt32(slicesStart);   // 0x38: SlicesOffset

            bs.WriteUInt32(slicesStart + 4u); // 0x3C: SlicesNext

            // Calculate where mip arrays start (after all slice structs, each 12 bytes)
            uint mipsDataStart = slicesStart + (uint)(Slices.Count * 12);

            uint currentMipArrayOffset = mipsDataStart;

            // Write Slices
            for (int i = 0; i < Slices.Count; i++)
            {
                var slice = Slices[i];

                bs.WriteInt32((int)slice.Encoding);            // Encoding (4)
                bs.WriteUInt32(currentMipArrayOffset);         // MipsOffset (4)
                bs.WriteUInt32(0xFFFFFFFF);                    // MipsNext   (4) = sentinel

                currentMipArrayOffset += (uint)(slice.Mips.Count * 12);
            }

            // Write Mip arrays
            foreach (var slice in Slices)
            {
                for (int j = 0; j < slice.Mips.Count; j++)
                {
                    var mip = slice.Mips[j];
                    bool isLastMip = (j == slice.Mips.Count - 1);

                    bs.WriteUInt32(mip.BlobSize);   // BlobSize   (4)
                    bs.WriteUInt32(mip.BlobOffset); // BlobOffset (4)

                    // Next: points to the BlobOffset field (+4) of the next mip entry.
                    // Last mip terminates the chain with 0xFFFFFFFF.
                    if (isLastMip)
                    {
                        bs.WriteUInt32(0xFFFFFFFF);
                    }
                    else
                    {
                        // Next pointer must be TXCH-data-relative (relative to basePos).
                        // Current mip struct starts at (bs.Position - 8 - basePos).
                        // Next mip struct is 12 bytes later; its BlobOffset field is at +4 within that struct.
                        uint nextMipBlobOffsetAddr = (uint)(bs.Position - 8 - basePos) + 12u + 4u;
                        bs.WriteUInt32(nextMipBlobOffsetAddr);
                    }
                }
            }
        }
        else
        {
            bs.WriteUInt32(0); // 0x38: SlicesOffset = 0 (no slices)
            bs.WriteUInt32(0); // 0x3C: SlicesNext   = 0
        }
    }

    public DXGI_FORMAT DetermineFormat()
    {
        if (Slices.Count == 0)
            return DXGI_FORMAT.DXGI_FORMAT_UNKNOWN;

        var encoding = Slices[0].Encoding;

        if (Transcoding <= TextureTranscoding.BcBlockRle)
        {
            return TargetColorProfile == ColorProfile.Rec709Linear 
                ? EncodingToDxgiFormat(encoding, false) 
                : EncodingToDxgiFormat(encoding, true);
        }
        else
        {
            return TargetColorProfile == ColorProfile.Rec709Linear 
                ? TranscodingToDxgiFormat(Transcoding, false) 
                : TranscodingToDxgiFormat(Transcoding, true);
        }
    }

    private DXGI_FORMAT EncodingToDxgiFormat(TextureEncoding encoding, bool srgb)
    {
        return encoding switch
        {
            TextureEncoding.Bc1 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM,
            TextureEncoding.Bc2 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM,
            TextureEncoding.Bc3 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM,
            TextureEncoding.UnsignedBc4 => DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM,
            TextureEncoding.SignedBc4 => DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM,
            TextureEncoding.UnsignedBc5 => DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM,
            TextureEncoding.SignedBc5 => DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM,
            TextureEncoding.UnsignedBc6H => DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16,
            TextureEncoding.SignedBc6H => DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16,
            TextureEncoding.Bc7 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
            TextureEncoding.Bc7_HighQuality => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
            TextureEncoding.R32G32B32A32Float => DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_FLOAT,
            TextureEncoding.R16G16B16A16 => DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_UNORM,
            TextureEncoding.R16G16B16A16Float => DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_FLOAT,
            TextureEncoding.R8G8B8A8 => srgb ? DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UNORM,
            TextureEncoding.B5G6R5 => DXGI_FORMAT.DXGI_FORMAT_B5G6R5_UNORM,
            TextureEncoding.B5G5R5A1 => DXGI_FORMAT.DXGI_FORMAT_B5G5R5A1_UNORM,
            TextureEncoding.R8 => DXGI_FORMAT.DXGI_FORMAT_R8_UNORM,
            TextureEncoding.A8 => DXGI_FORMAT.DXGI_FORMAT_A8_UNORM,
            TextureEncoding.R8G8 => DXGI_FORMAT.DXGI_FORMAT_R8G8_UNORM,
            _ => DXGI_FORMAT.DXGI_FORMAT_UNKNOWN,
        };
    }

    private DXGI_FORMAT TranscodingToDxgiFormat(TextureTranscoding transcoding, bool srgb)
    {
        return transcoding switch
        {
            TextureTranscoding.Bc1 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM,
            TextureTranscoding.Bc2 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM,
            TextureTranscoding.Bc3 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM,
            TextureTranscoding.UnsignedBc4 => DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM,
            TextureTranscoding.SignedBc4 => DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM,
            TextureTranscoding.UnsignedBc5 => DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM,
            TextureTranscoding.SignedBc5 => DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM,
            TextureTranscoding.UnsignedBc6H => DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16,
            TextureTranscoding.SignedBc6H => DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16,
            TextureTranscoding.Bc7 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
            _ => DXGI_FORMAT.DXGI_FORMAT_UNKNOWN,
        };
    }
}

public class TextureContentSlice
{
    public TextureEncoding Encoding { get; set; }
    public List<TextureContentMip> Mips { get; set; } = new();
}

public class TextureContentMip
{
    public uint BlobSize { get; set; }
    public uint BlobOffset { get; set; }
}

// Enums
public enum TextureEncoding : int
{
    Bc1 = 0, Bc2 = 1, Bc3 = 2, UnsignedBc4 = 3, SignedBc4 = 4,
    UnsignedBc5 = 5, SignedBc5 = 6, UnsignedBc6H = 7, SignedBc6H = 8,
    Bc7 = 9, R32G32B32A32Float = 10, R16G16B16A16 = 11, R16G16B16A16Float = 12,
    R8G8B8A8 = 13, B5G6R5 = 14, B5G5R5A1 = 15, Dct = 16, IntegerDct = 17,
    Procedural = 18, R8 = 19, A8 = 20, R8G8 = 21, Bc7_HighQuality = 22
}

public enum TextureTranscoding : int
{
    None = 0, BcBlockRle = 1, Bc1 = 2, Bc2 = 3, Bc3 = 4,
    UnsignedBc4 = 5, SignedBc4 = 6, UnsignedBc5 = 7, SignedBc5 = 8,
    UnsignedBc6H = 9, SignedBc6H = 10, Bc7 = 11
}

public enum ColorProfile : int
{
    Rec709Linear = 0, Rec709SRgb = 1, Rec709Gamma2 = 2, XvYccLinear = 3
}

public enum TextureDomain : int
{
    Wrap = 0, Clamp = 1, Mirror = 2
}