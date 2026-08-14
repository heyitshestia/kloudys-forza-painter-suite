using System;
using System.Collections.Generic;
using Syroot.BinaryData;
using ForzaTools.Shared;

namespace ForzaTools.Bundles.Blobs;

// Header for vertex buffer (VerB) and index buffer (IndB) blobs.
// v1.0+: 16-byte header with SubElementCount and Format. v0.x: 12-byte header, Format defaults to UNKNOWN.
public class BufferHeader
{
    public int Length { get; set; }      // element count
    public int Size { get; set; }         // total data byte size
    public ushort Stride { get; set; }    // bytes per element

    // v1.0+ only
    // Number of sub-elements per element. Defaults to 1 for v0.x.
    public byte SubElementCount { get; set; }
    // DXGI_FORMAT of the first sub-element. Defaults to UNKNOWN for v0.x.
    public DXGI_FORMAT Format { get; set; }

    [Obsolete("Use SubElementCount")]
    public byte NumElements
    {
        get => SubElementCount;
        set => SubElementCount = value;
    }

    // Raw contiguous vertex data
    private byte[] _rawData;

    // Legacy per-vertex accessor. Splits the contiguous raw buffer into per-element arrays.
    // Prefer GetRawData() for performance.
    public byte[][] Data
    {
        get
        {
            if (_rawData == null || Length == 0 || Stride == 0)
                return Array.Empty<byte[]>();

            var result = new byte[Length][];
            for (int i = 0; i < Length; i++)
            {
                result[i] = new byte[Stride];
                Buffer.BlockCopy(_rawData, i * Stride, result[i], 0, Stride);
            }
            return result;
        }
        set
        {
            if (value == null || value.Length == 0)
            {
                _rawData = null;
                Length = 0;
                return;
            }

            Length = value.Length;

            ushort effectiveStride = Stride;
            if (effectiveStride == 0 && value[0] != null)
            {
                effectiveStride = (ushort)value[0].Length;
                Stride = effectiveStride;
            }

            if (effectiveStride == 0)
            {
                _rawData = Array.Empty<byte>();
                return;
            }

            _rawData = new byte[Length * effectiveStride];
            for (int i = 0; i < Length; i++)
            {
                if (value[i] != null)
                {
                    int copyLen = Math.Min(value[i].Length, effectiveStride);
                    Buffer.BlockCopy(value[i], 0, _rawData, i * effectiveStride, copyLen);
                }
            }

            Size = _rawData.Length;
        }
    }

    // Gets the raw buffer data as a single contiguous array.
    public byte[] GetRawData() => _rawData;

    // Sets the raw buffer data directly.
    public void SetRawData(byte[] data, int length, ushort stride)
    {
        _rawData = data;
        Length = length;
        Stride = stride;
        Size = data?.Length ?? 0;
    }

    // Reads the buffer header and data. v1.0+ uses 16-byte header; v0.x uses 12-byte.
    public void Read(BinaryStream bs, byte versionMajor, byte versionMinor)
    {
        Length = bs.ReadInt32();
        Size = bs.ReadInt32();
        Stride = bs.ReadUInt16();

        bool isV1 = versionMajor >= 1;

        if (isV1)
        {
            // v1.0+: 16-byte header
            SubElementCount = bs.Read1Byte();
            bs.Read1Byte(); // padding byte at +0x0B
            Format = (DXGI_FORMAT)bs.ReadInt32();
        }
        else
        {
            // v0.x: 12-byte header — 2 padding bytes fill the remaining space after m_Stride
            bs.ReadBytes(2); // 2 padding bytes
            SubElementCount = 1;
            Format = DXGI_FORMAT.DXGI_FORMAT_UNKNOWN;
        }

        if (Size > 0)
            _rawData = bs.ReadBytes(Size);
        else if (Length > 0 && Stride > 0)
            _rawData = bs.ReadBytes(Length * Stride);
        else
            _rawData = Array.Empty<byte>();
    }

    public void Serialize(BinaryStream bs, byte versionMajor, byte versionMinor)
    {
        int count = _rawData != null && Stride > 0 ? _rawData.Length / Stride : 0;
        bs.WriteInt32(count);
        bs.WriteInt32(_rawData?.Length ?? 0);
        bs.WriteUInt16(Stride);

        bool isV1 = versionMajor >= 1;

        if (isV1)
        {
            bs.WriteByte(SubElementCount);
            bs.WriteByte(0); // padding
            bs.WriteInt32((int)Format);
        }
        else
        {
            bs.WriteBytes(new byte[2]); // 2 padding bytes for v0.x
        }

        if (_rawData != null && _rawData.Length > 0)
            bs.WriteBytes(_rawData);
    }

    public void CreateModelBin(BinaryStream bs, byte versionMajor, byte versionMinor)
    {
        int count = _rawData != null && Stride > 0 ? _rawData.Length / Stride : 0;
        int size = _rawData?.Length ?? 0;

        bs.WriteInt32(count);
        bs.WriteInt32(size);
        bs.WriteUInt16(Stride);

        bool isV1 = versionMajor >= 1;

        if (isV1)
        {
            bs.WriteByte(SubElementCount);
            bs.WriteByte(0); // padding
            bs.WriteInt32((int)Format);
        }
        else
        {
            bs.WriteBytes(new byte[2]); // 2 padding bytes for v0.x
        }

        if (_rawData != null && _rawData.Length > 0)
            bs.WriteBytes(_rawData);
    }
}
