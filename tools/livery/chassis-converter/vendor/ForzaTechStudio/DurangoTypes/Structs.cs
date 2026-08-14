using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace DurangoTypes;

public struct XG_SAMPLE_DESC
{
    public uint Count;
    public uint Quality;
};

public struct XG_TEXTURE2D_DESC
{
    public uint Width;
    public uint Height;
    public uint MipLevels;
    public uint ArraySize;
    public XG_FORMAT Format;
    public XG_SAMPLE_DESC SampleDesc;
    public XG_USAGE Usage;
    public uint BindFlags;                 // Any of XG_BIND_FLAG.
    public uint CPUAccessFlags;            // Any of XG_CPU_ACCESS_FLAG.
    public uint MiscFlags;                 // Any of XG_RESOURCE_MISC_FLAG.
    public uint ESRAMOffsetBytes;
    public uint ESRAMUsageBytes;
    public XG_TILE_MODE TileMode;
    public uint Pitch;
}

[StructLayout(LayoutKind.Sequential)]
public struct XG_RESOURCE_LAYOUT
{
    public ulong SizeBytes;
    public ulong BaseAlignmentBytes;
    public uint MipLevels;
    public uint Planes;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public XG_PLANE_LAYOUT[] Plane;

    public XG_RESOURCE_DIMENSION Dimension;
};

[StructLayout(LayoutKind.Sequential)]
public unsafe struct XG_PLANE_LAYOUT
{
    public XG_PLANE_USAGE Usage;
    public ulong SizeBytes;
    public ulong BaseOffsetBytes;
    public ulong BaseAlignmentBytes;
    public uint BytesPerElement;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 15)]
    public XG_MIPLEVEL_LAYOUT[] MipLayout;
};

[StructLayout(LayoutKind.Sequential)]
public struct XG_MIPLEVEL_LAYOUT
{
    public ulong SizeBytes;
    public ulong OffsetBytes;
    public ulong Slice2DSizeBytes;
    public uint PitchPixels;
    public uint PitchBytes;
    public uint AlignmentBytes;
    public uint PaddedWidthElements;
    public uint PaddedHeightElements;
    public uint PaddedDepthOrArraySize;
    public uint WidthElements;
    public uint HeightElements;
    public uint DepthOrArraySize;
    public uint SampleCount;
    public XG_TILE_MODE TileMode;
    public ulong BankRotationAddressBitMask;
    public ulong BankRotationBytesPerSlice;
    public uint SliceDepthElements;
};

public unsafe struct XGTextureAddressComputer
{
    public XGTextureAddressComputer_vtable* vt;
}

public unsafe struct XGTextureAddressComputer_vtable
{
    public delegate* unmanaged<XGTextureAddressComputer*> AddRef;
    public delegate* unmanaged<XGTextureAddressComputer*> Release;

    /* HRESULT GetResourceLayout(XG_RESOURCE_LAYOUT* pLayout); */
    public delegate* unmanaged<XGTextureAddressComputer*, XG_RESOURCE_LAYOUT*, int> GetResourceLayout;

    /* ulong GetResourceSizeBytes(); */
    public delegate* unmanaged<XGTextureAddressComputer*, ulong> GetResourceSizeBytes;

    /* ulong GetResourceBaseAlignmentBytes(); */
    public delegate* unmanaged<XGTextureAddressComputer*, ulong> GetResourceBaseAlignmentBytes;

    /* ulong GetMipLevelOffsetBytes(uint32 plane, uint32 miplevel) */
    public delegate* unmanaged<XGTextureAddressComputer*, uint, uint, ulong> GetMipLevelOffsetBytes;

    /* ulong CopyFromSubresource(uint plane, uint miplevel, uint64 x, uint y, uint zOrSlice, uint sample) */
    public nint GetTexelElementOffsetBytes;

    /* ulong CopyFromSubresource(uint plane, uint miplevel, uint64 x, uint y, uint zOrSlice, uint sample) */
    public nint GetTexelCoordinate;

    /* HRESULT CopyFromSubresource(void* pTiledResourceBaseAddress, uint plane, uint subresource, void* pLinearData, uint rowPitchBytes, uint slicePitchBytes) */
    public delegate* unmanaged<XGTextureAddressComputer*, byte*, uint, uint, byte*, uint, uint, int> CopyIntoSubresource;

    /* HRESULT CopyFromSubresource(void* pLinearData, uint plane, uint subresource, void* pTiledResourceBaseAddress, uint rowPitchBytes, uint slicePitchBytes) */
    public delegate* unmanaged<XGTextureAddressComputer*, byte*, uint, uint, byte*, uint, uint, int> CopyFromSubresource;

    public nint GetResourceTiling;
    public nint GetTextureViewDescriptor;

    /* bool IsTiledResource() */
    public delegate* unmanaged<XGTextureAddressComputer*, bool> IsTiledResource;
}
