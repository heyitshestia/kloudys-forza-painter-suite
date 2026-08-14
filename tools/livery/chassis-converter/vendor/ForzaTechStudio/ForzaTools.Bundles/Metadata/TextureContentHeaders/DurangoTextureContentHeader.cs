using System;
using System.IO;
using Syroot.BinaryData;
using DurangoTypes;
using ForzaTools.Shared;

namespace ForzaTools.Bundles.Metadata.TextureContentHeaders;

public class DurangoTextureContentHeader
{
    public Guid Id { get; set; }
    public ushort Width { get; set; }
    public ushort Height { get; set; }
    public ushort Depth { get; set; }

    public ushort TileRelativeWidth { get; set; }
    public ushort TileRelativeHeight { get; set; }
    public ushort TileRelativeDepth { get; set; }

    public byte NumMips { get; set; }
    public byte TileRelativeMipLevels { get; set; }
    public byte TileRelativeMipOffset { get; set; }

    // Bitfields
    public XG_TILE_MODE TileMode { get; set; }
    public byte Encoding { get; set; }
    public byte Transcoding { get; set; }
    public byte EncodedColorProfile { get; set; }
    public byte TargetColorProfile { get; set; }
    public byte Domain { get; set; }

    public bool IsCubeMap { get; set; }
    public bool Is3DTexture { get; set; }
    public bool IsPremultipliedAlpha { get; set; }
    public byte LogPitchOrLinearSize { get; set; }

    public void Read(byte[] data)
    {
        using var ms = new MemoryStream(data);
        using var bs = new BinaryStream(ms);

        Id = new Guid(bs.ReadBytes(16));
        Width = bs.ReadUInt16();
        Height = bs.ReadUInt16();
        Depth = bs.ReadUInt16();

        TileRelativeWidth = bs.ReadUInt16();
        TileRelativeHeight = bs.ReadUInt16();
        TileRelativeDepth = bs.ReadUInt16();

        NumMips = bs.Read1Byte();
        TileRelativeMipLevels = bs.Read1Byte();
        TileRelativeMipOffset = bs.Read1Byte();

        uint flags = bs.ReadUInt32();

        // 5 bits
        TileMode = (XG_TILE_MODE)(flags & 0x1F);

        // 6 bits
        Encoding = (byte)((flags >> 5) & 0x3F);

        // 6 bits
        Transcoding = (byte)((flags >> 11) & 0x3F);

        // 3 bits
        EncodedColorProfile = (byte)((flags >> 17) & 0x7);

        // 3 bits
        TargetColorProfile = (byte)((flags >> 20) & 0x7);

        // 2 bits
        Domain = (byte)((flags >> 23) & 0x3);

        // Single bits
        IsCubeMap = ((flags >> 25) & 1) != 0;
        Is3DTexture = ((flags >> 26) & 1) != 0;
        IsPremultipliedAlpha = ((flags >> 27) & 1) != 0;

        // 4 bits
        LogPitchOrLinearSize = (byte)((flags >> 28) & 0xF);
    }

    public void Write(BinaryStream bs)
    {
        bs.WriteBytes(Id.ToByteArray());
        bs.WriteUInt16(Width);
        bs.WriteUInt16(Height);
        bs.WriteUInt16(Depth);
        bs.WriteUInt16(TileRelativeWidth);
        bs.WriteUInt16(TileRelativeHeight);
        bs.WriteUInt16(TileRelativeDepth);
        bs.WriteByte(NumMips);
        bs.WriteByte(TileRelativeMipLevels);
        bs.WriteByte(TileRelativeMipOffset);

        uint flags = 0;
        flags |= (uint)((int)TileMode & 0x1F);
        flags |= (uint)((Encoding & 0x3F) << 5);
        flags |= (uint)((Transcoding & 0x3F) << 11);
        flags |= (uint)((EncodedColorProfile & 0x7) << 17);
        flags |= (uint)((TargetColorProfile & 0x7) << 20);
        flags |= (uint)((Domain & 0x3) << 23);
        
        if (IsCubeMap) flags |= (1u << 25);
        if (Is3DTexture) flags |= (1u << 26);
        if (IsPremultipliedAlpha) flags |= (1u << 27);
        flags |= (uint)((LogPitchOrLinearSize & 0xF) << 28);
        
        bs.WriteUInt32(flags);
    }

    public XG_FORMAT DetermineFormat()
    {
        bool useSrgb = TargetColorProfile != 0;

        if (Transcoding <= 1)
        {
            return (XG_FORMAT)EncodingToDxgiFormat(Encoding, useSrgb);
        }
        else
        {
            return (XG_FORMAT)TranscodingToDxgiFormat(Transcoding, useSrgb);
        }
    }

    private DXGI_FORMAT EncodingToDxgiFormat(byte encoding, bool srgb)
    {
        return encoding switch
        {
            0 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM,
            1 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM,
            2 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM,
            3 => DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM,
            4 => DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM,
            5 => DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM,
            6 => DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM,
            7 => DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16,
            8 => DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16,
            9 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
            10 => DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_FLOAT,
            11 => DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_UNORM,
            12 => DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_FLOAT,
            13 => srgb ? DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UNORM,
            14 => DXGI_FORMAT.DXGI_FORMAT_B5G6R5_UNORM,
            15 => DXGI_FORMAT.DXGI_FORMAT_B5G5R5A1_UNORM,
            19 => DXGI_FORMAT.DXGI_FORMAT_R8_UNORM,
            20 => DXGI_FORMAT.DXGI_FORMAT_A8_UNORM,
            21 => DXGI_FORMAT.DXGI_FORMAT_R8G8_UNORM,
            22 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
            _ => DXGI_FORMAT.DXGI_FORMAT_UNKNOWN,
        };
    }

    private DXGI_FORMAT TranscodingToDxgiFormat(byte transcoding, bool srgb)
    {
        return transcoding switch
        {
            2 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM,
            3 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM,
            4 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM,
            5 => DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM,
            6 => DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM,
            7 => DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM,
            8 => DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM,
            9 => DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16,
            10 => DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16,
            11 => srgb ? DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB : DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
            _ => DXGI_FORMAT.DXGI_FORMAT_UNKNOWN,
        };
    }
}