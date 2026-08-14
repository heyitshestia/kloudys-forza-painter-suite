using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection.PortableExecutable;
using System.Runtime.Intrinsics.X86;
using System.Text;
using System.Threading.Tasks;

namespace ForzaTools.Shared;

public class DxgiUtils
{
    public const int D3D12_TEXTURE_DATA_PITCH_ALIGNMENT = 1024;

    public static uint BitsPerPixel(DXGI_FORMAT fmt)
    {
        switch (fmt)
        {
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_SINT:
                return 128;

            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32B32_SINT:
                return 96;

            case DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G32_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32G8X24_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_D32_FLOAT_S8X24_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32_FLOAT_X8X24_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_X32_TYPELESS_G8X24_UINT:
                return 64;

            case DXGI_FORMAT.DXGI_FORMAT_R10G10B10A2_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R10G10B10A2_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R10G10B10A2_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R11G11B10_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8B8A8_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16G16_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_D32_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R32_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_R32_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R32_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_R24G8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_D24_UNORM_S8_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R24_UNORM_X8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_X24_TYPELESS_G8_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R9G9B9E5_SHAREDEXP:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8_B8G8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_G8R8_G8B8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_B8G8R8A8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_B8G8R8X8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R10G10B10_XR_BIAS_A2_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_B8G8R8A8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_B8G8R8A8_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_B8G8R8X8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_B8G8R8X8_UNORM_SRGB:
                return 32;

            case DXGI_FORMAT.DXGI_FORMAT_R8G8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R8G8_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_R16_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R16_FLOAT:
            case DXGI_FORMAT.DXGI_FORMAT_D16_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R16_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R16_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_B5G6R5_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_B5G5R5A1_UNORM:
                return 16;

            case DXGI_FORMAT.DXGI_FORMAT_R8_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_R8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R8_UINT:
            case DXGI_FORMAT.DXGI_FORMAT_R8_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_R8_SINT:
            case DXGI_FORMAT.DXGI_FORMAT_A8_UNORM:
                return 8;

            case DXGI_FORMAT.DXGI_FORMAT_R1_UNORM:
                return 1;

            case DXGI_FORMAT.DXGI_FORMAT_BC1_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM:
                return 4;

            case DXGI_FORMAT.DXGI_FORMAT_BC2_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB:
                return 8;

            default:
                return 0;
        }
    }

    public static bool IsBCnFormat(DXGI_FORMAT fmt)
    {
        switch (fmt)
        {
            case DXGI_FORMAT.DXGI_FORMAT_BC1_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB:
                return true;
        }

        return false;
    }

    private static uint Align(uint x, uint alignment)
    {
        uint mask = ~(alignment - 1);
        return (x + (alignment - 1)) & mask;
    }

    public static int ComputePitch(DXGI_FORMAT fmt, uint width, uint height,
        out ulong rowPitch, out ulong slicePitch, out ulong alignedSlicePitch)
    {
        rowPitch = 0;
        slicePitch = 0;
        alignedSlicePitch = 0;

        ulong pitch, slice, aSlice;
    
        switch (fmt)
        {
            case DXGI_FORMAT.DXGI_FORMAT_BC1_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC4_SNORM:
                {
                    ulong nbw = Math.Max(1u, ((ulong)(width) + 3u) / 4u);
                    ulong nbh = Math.Max(1u, ((ulong)(height) + 3u) / 4u);
                    pitch = nbw * 8u;
                    slice = pitch * nbh;
                    aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * nbh;
                }
            
                break;
    
            case DXGI_FORMAT.DXGI_FORMAT_BC2_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM_SRGB:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC5_SNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16:
            case DXGI_FORMAT.DXGI_FORMAT_BC6H_SF16:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_TYPELESS:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM_SRGB:
                {
                    ulong nbw = Math.Max(1u, ((ulong)(width) + 3u) / 4u);
                    ulong nbh = Math.Max(1u, ((ulong)(height) + 3u) / 4u);
                    pitch = nbw * 16u;
                    slice = pitch * nbh;
                    aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * nbh;
                }
                break;
    
            case DXGI_FORMAT.DXGI_FORMAT_R8G8_B8G8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_G8R8_G8B8_UNORM:
            case DXGI_FORMAT.DXGI_FORMAT_YUY2:
                pitch = (((ulong)(width) + 1u) >> 1) * 4u;
                slice = pitch * height;
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (ulong)(height);
                break;
            
            case DXGI_FORMAT.DXGI_FORMAT_Y210:
            case DXGI_FORMAT.DXGI_FORMAT_Y216:
                pitch = (((ulong)(width) + 1u) >> 1) * 8u;
                slice = pitch * height;
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (ulong)(height);
                break;
            
            case DXGI_FORMAT.DXGI_FORMAT_NV12:
            case DXGI_FORMAT.DXGI_FORMAT_420_OPAQUE:
                if ((height % 2) != 0)
                {
                    // Requires a height alignment of 2.
                    return -1;
                }

                pitch = (((ulong)(width) + 1u) >> 1) * 2u;
                slice = pitch * (height + (((ulong)(height) + 1u) >> 1));
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (height + (((ulong)(height) + 1u) >> 1));
                break;
            
            case DXGI_FORMAT.DXGI_FORMAT_P010:
            case DXGI_FORMAT.DXGI_FORMAT_P016:
                if ((height % 2) != 0)
                {
                    // Requires a height alignment of 2.
                    return -1;
                }
    
                pitch = (((ulong)(width) + 1u) >> 1) * 4u;
                slice = pitch * (height + (((ulong)(height) + 1u) >> 1));
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (height + (((ulong)(height) + 1u) >> 1));
                break;

            case DXGI_FORMAT.DXGI_FORMAT_NV11:
                pitch = (((ulong)(width) + 3u) >> 2) * 4u;
                slice = pitch * (ulong)(height) * 2u;
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (ulong)(height) * 2u;
                break;
    
            case DXGI_FORMAT.DXGI_FORMAT_P208:
                pitch = (((ulong)(width) + 1u) >> 1) * 2u;
                slice = pitch * (ulong)(height) * 2u;
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (ulong)(height) * 2u;
                break;
            
            case DXGI_FORMAT.DXGI_FORMAT_V208:
                if ((height % 2) != 0)
                {
                    // Requires a height alignment of 2.
                    return -1;
                }
                pitch = width;
                slice = pitch * (height + ((((ulong)(height) + 1u) >> 1) * 2u));
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (height + ((((ulong)(height) + 1u) >> 1) * 2u));
                break;
            
            case DXGI_FORMAT.DXGI_FORMAT_V408:
                pitch = width;
                slice = pitch * (height + ((ulong)(height >> 1) * 4u));
                aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (height + ((ulong)(height >> 1) * 4u));
                break;

            default:
                {
                    uint bpp = BitsPerPixel(fmt);

                    if (bpp == 0)
                        return -1;


                    // Default byte alignment
                    pitch = ((ulong)(width) * bpp + 7u) / 8u;
                    slice = pitch * height;
                    aSlice = Align((uint)pitch, D3D12_TEXTURE_DATA_PITCH_ALIGNMENT) * (ulong)(height);
                }
                break;
    }
    
        rowPitch = pitch;
        slicePitch = slice;
        alignedSlicePitch = aSlice;
        return 0;
    }
}

public enum DXGI_FORMAT : int
{
    DXGI_FORMAT_UNKNOWN = 0,
    DXGI_FORMAT_R32G32B32A32_TYPELESS = 1,
    DXGI_FORMAT_R32G32B32A32_FLOAT = 2,
    DXGI_FORMAT_R32G32B32A32_UINT = 3,
    DXGI_FORMAT_R32G32B32A32_SINT = 4,
    DXGI_FORMAT_R32G32B32_TYPELESS = 5,
    DXGI_FORMAT_R32G32B32_FLOAT = 6,
    DXGI_FORMAT_R32G32B32_UINT = 7,
    DXGI_FORMAT_R32G32B32_SINT = 8,
    DXGI_FORMAT_R16G16B16A16_TYPELESS = 9,
    DXGI_FORMAT_R16G16B16A16_FLOAT = 10,
    DXGI_FORMAT_R16G16B16A16_UNORM = 11,
    DXGI_FORMAT_R16G16B16A16_UINT = 12,
    DXGI_FORMAT_R16G16B16A16_SNORM = 13,
    DXGI_FORMAT_R16G16B16A16_SINT = 14,
    DXGI_FORMAT_R32G32_TYPELESS = 15,
    DXGI_FORMAT_R32G32_FLOAT = 16,
    DXGI_FORMAT_R32G32_UINT = 17,
    DXGI_FORMAT_R32G32_SINT = 18,
    DXGI_FORMAT_R32G8X24_TYPELESS = 19,
    DXGI_FORMAT_D32_FLOAT_S8X24_UINT = 20,
    DXGI_FORMAT_R32_FLOAT_X8X24_TYPELESS = 21,
    DXGI_FORMAT_X32_TYPELESS_G8X24_UINT = 22,
    DXGI_FORMAT_R10G10B10A2_TYPELESS = 23,
    DXGI_FORMAT_R10G10B10A2_UNORM = 24,
    DXGI_FORMAT_R10G10B10A2_UINT = 25,
    DXGI_FORMAT_R11G11B10_FLOAT = 26,
    DXGI_FORMAT_R8G8B8A8_TYPELESS = 27,
    DXGI_FORMAT_R8G8B8A8_UNORM = 28,
    DXGI_FORMAT_R8G8B8A8_UNORM_SRGB = 29,
    DXGI_FORMAT_R8G8B8A8_UINT = 30,
    DXGI_FORMAT_R8G8B8A8_SNORM = 31,
    DXGI_FORMAT_R8G8B8A8_SINT = 32,
    DXGI_FORMAT_R16G16_TYPELESS = 33,
    DXGI_FORMAT_R16G16_FLOAT = 34,
    DXGI_FORMAT_R16G16_UNORM = 35,
    DXGI_FORMAT_R16G16_UINT = 36,
    DXGI_FORMAT_R16G16_SNORM = 37,
    DXGI_FORMAT_R16G16_SINT = 38,
    DXGI_FORMAT_R32_TYPELESS = 39,
    DXGI_FORMAT_D32_FLOAT = 40,
    DXGI_FORMAT_R32_FLOAT = 41,
    DXGI_FORMAT_R32_UINT = 42,
    DXGI_FORMAT_R32_SINT = 43,
    DXGI_FORMAT_R24G8_TYPELESS = 44,
    DXGI_FORMAT_D24_UNORM_S8_UINT = 45,
    DXGI_FORMAT_R24_UNORM_X8_TYPELESS = 46,
    DXGI_FORMAT_X24_TYPELESS_G8_UINT = 47,
    DXGI_FORMAT_R8G8_TYPELESS = 48,
    DXGI_FORMAT_R8G8_UNORM = 49,
    DXGI_FORMAT_R8G8_UINT = 50,
    DXGI_FORMAT_R8G8_SNORM = 51,
    DXGI_FORMAT_R8G8_SINT = 52,
    DXGI_FORMAT_R16_TYPELESS = 53,
    DXGI_FORMAT_R16_FLOAT = 54,
    DXGI_FORMAT_D16_UNORM = 55,
    DXGI_FORMAT_R16_UNORM = 56,
    DXGI_FORMAT_R16_UINT = 57,
    DXGI_FORMAT_R16_SNORM = 58,
    DXGI_FORMAT_R16_SINT = 59,
    DXGI_FORMAT_R8_TYPELESS = 60,
    DXGI_FORMAT_R8_UNORM = 61,
    DXGI_FORMAT_R8_UINT = 62,
    DXGI_FORMAT_R8_SNORM = 63,
    DXGI_FORMAT_R8_SINT = 64,
    DXGI_FORMAT_A8_UNORM = 65,
    DXGI_FORMAT_R1_UNORM = 66,
    DXGI_FORMAT_R9G9B9E5_SHAREDEXP = 67,
    DXGI_FORMAT_R8G8_B8G8_UNORM = 68,
    DXGI_FORMAT_G8R8_G8B8_UNORM = 69,
    DXGI_FORMAT_BC1_TYPELESS = 70,
    DXGI_FORMAT_BC1_UNORM = 71,
    DXGI_FORMAT_BC1_UNORM_SRGB = 72,
    DXGI_FORMAT_BC2_TYPELESS = 73,
    DXGI_FORMAT_BC2_UNORM = 74,
    DXGI_FORMAT_BC2_UNORM_SRGB = 75,
    DXGI_FORMAT_BC3_TYPELESS = 76,
    DXGI_FORMAT_BC3_UNORM = 77,
    DXGI_FORMAT_BC3_UNORM_SRGB = 78,
    DXGI_FORMAT_BC4_TYPELESS = 79,
    DXGI_FORMAT_BC4_UNORM = 80,
    DXGI_FORMAT_BC4_SNORM = 81,
    DXGI_FORMAT_BC5_TYPELESS = 82,
    DXGI_FORMAT_BC5_UNORM = 83,
    DXGI_FORMAT_BC5_SNORM = 84,
    DXGI_FORMAT_B5G6R5_UNORM = 85,
    DXGI_FORMAT_B5G5R5A1_UNORM = 86,
    DXGI_FORMAT_B8G8R8A8_UNORM = 87,
    DXGI_FORMAT_B8G8R8X8_UNORM = 88,
    DXGI_FORMAT_R10G10B10_XR_BIAS_A2_UNORM = 89,
    DXGI_FORMAT_B8G8R8A8_TYPELESS = 90,
    DXGI_FORMAT_B8G8R8A8_UNORM_SRGB = 91,
    DXGI_FORMAT_B8G8R8X8_TYPELESS = 92,
    DXGI_FORMAT_B8G8R8X8_UNORM_SRGB = 93,
    DXGI_FORMAT_BC6H_TYPELESS = 94,
    DXGI_FORMAT_BC6H_UF16 = 95,
    DXGI_FORMAT_BC6H_SF16 = 96,
    DXGI_FORMAT_BC7_TYPELESS = 97,
    DXGI_FORMAT_BC7_UNORM = 98,
    DXGI_FORMAT_BC7_UNORM_SRGB = 99,
    DXGI_FORMAT_AYUV = 100,
    DXGI_FORMAT_Y410 = 101,
    DXGI_FORMAT_Y416 = 102,
    DXGI_FORMAT_NV12 = 103,
    DXGI_FORMAT_P010 = 104,
    DXGI_FORMAT_P016 = 105,
    DXGI_FORMAT_420_OPAQUE = 106,
    DXGI_FORMAT_YUY2 = 107,
    DXGI_FORMAT_Y210 = 108,
    DXGI_FORMAT_Y216 = 109,
    DXGI_FORMAT_NV11 = 110,
    DXGI_FORMAT_AI44 = 111,
    DXGI_FORMAT_IA44 = 112,
    DXGI_FORMAT_P8 = 113,
    DXGI_FORMAT_A8P8 = 114,
    DXGI_FORMAT_B4G4R4A4_UNORM = 115,
    DXGI_FORMAT_P208 = 130,
    DXGI_FORMAT_V208 = 131,
    DXGI_FORMAT_V408 = 132,
    DXGI_FORMAT_SAMPLER_FEEDBACK_MIN_MIP_OPAQUE,
    DXGI_FORMAT_SAMPLER_FEEDBACK_MIP_REGION_USED_OPAQUE,
    DXGI_FORMAT_FORCE_UINT = -1
}

