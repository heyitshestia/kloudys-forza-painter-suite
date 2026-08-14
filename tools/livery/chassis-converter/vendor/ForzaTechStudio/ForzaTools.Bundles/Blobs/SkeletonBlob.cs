using Syroot.BinaryData;
using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.Numerics;

namespace ForzaTools.Bundles.Blobs
{
    public class Bone
    {
        public string Name { get; set; }
        public short ParentId { get; set; } = -1;
        public short FirstChildIndex { get; set; } = -1;
        public short NextIndex { get; set; } = -1;
        public Matrix4x4 Matrix { get; set; } = Matrix4x4.Identity;
    }

    public class SkeletonBlob : BundleBlob
    {
        private byte[] _attributeData = Array.Empty<byte>();
        private byte[] _attributeTrailingData = Array.Empty<byte>();
        private bool _hasStructuredAttributeData;

        public List<Bone> Bones { get; set; } = new List<Bone>();

        // v1.0+: length-prefixed skeleton attribute sidecar.
        public uint AttributesHeader { get; set; }
        public ulong[] AttributeEntries { get; set; } = Array.Empty<ulong>();
        public byte[] AttributeData
        {
            get => _attributeData;
            set
            {
                _attributeData = value ?? Array.Empty<byte>();
                _attributeTrailingData = Array.Empty<byte>();
                _hasStructuredAttributeData = false;
            }
        }
        public byte[] UnknownData { get => AttributeData; set => AttributeData = value ?? Array.Empty<byte>(); }

        public SkeletonBlob()
        {
            // Populate default bone list in the specified order
            // Note: <root> in the prompt is interpreted as the container tag, starting list at "root"
            string[] defaultBoneNames = new string[]
            {
                "<root>",
                "root",
                "anchor_butt",
                "controlArm_LF",
                "controlArm_LR",
                "controlArm_RF",
                "controlArm_RR",
                "hubLF",
                "spindleLF",
                "hubLR",
                "spindleLR",
                "hubRF",
                "spindleRF",
                "hubRR",
                "spindleRR",
                "boneDoorLF",
                "boneGlassLF",
                "boneMirrorL_001",
                "boneDoorRF",
                "boneGlassRF",
                "boneMirrorR_001",
                "boneExhaustR_001",
                "boneFuel",
                "boneSpeed",
                "boneTach",
                "boneTemp",
                "boneHandBrake_001",
                "boneMirrorC_001",
                "boneBrake",
                "anchor_brake",
                "boneClutch",
                "anchor_clutch",
                "boneGas",
                "anchor_gas",
                "anchor_shifter",
                "boneSteeringWheelSpindle",
                "anchor_lefthand",
                "anchor_righthand",
                "boneWiperL",
                "boneWiperBladeL",
                "boneWiperR",
                "boneWiperBladeR",
                "rotorLF_center",
                "rotorLR_center",
                "rotorRF_center",
                "rotorRR_center"
            };

            foreach (var name in defaultBoneNames)
            {
                Bones.Add(new Bone { Name = name });
            }
        }

        public override void ReadBlobData(BinaryStream bs)
        {
            ushort boneCount = bs.ReadUInt16();

            Bones.Clear();
            for (int i = 0; i < boneCount; i++)
            {
                var bone = new Bone();

                bone.Name = bs.ReadString(StringCoding.Int32CharCount);

                bone.ParentId = bs.ReadInt16();
                bone.FirstChildIndex = bs.ReadInt16();
                bone.NextIndex = bs.ReadInt16();

                // Read Matrix (16 floats)
                float m11 = bs.ReadSingle(); float m12 = bs.ReadSingle(); float m13 = bs.ReadSingle(); float m14 = bs.ReadSingle();
                float m21 = bs.ReadSingle(); float m22 = bs.ReadSingle(); float m23 = bs.ReadSingle(); float m24 = bs.ReadSingle();
                float m31 = bs.ReadSingle(); float m32 = bs.ReadSingle(); float m33 = bs.ReadSingle(); float m34 = bs.ReadSingle();
                float m41 = bs.ReadSingle(); float m42 = bs.ReadSingle(); float m43 = bs.ReadSingle(); float m44 = bs.ReadSingle();

                bone.Matrix = new Matrix4x4(
                    m11, m12, m13, m14,
                    m21, m22, m23, m24,
                    m31, m32, m33, m34,
                    m41, m42, m43, m44
                );

                Bones.Add(bone);
            }

            if (VersionMajor >= 1)
            {
                AttributeData = Array.Empty<byte>();
                AttributeEntries = Array.Empty<ulong>();

                if (bs.Position + 4 <= bs.Length)
                {
                    uint attributeDataLength = bs.ReadUInt32();
                    long remaining = bs.Length - bs.Position;
                    if (attributeDataLength > 0 && attributeDataLength <= remaining)
                    {
                        AttributeData = bs.ReadBytes((int)attributeDataLength);
                        ParseAttributeData();
                    }
                }
            }
        }

        public override void SerializeBlobData(BinaryStream bs)
        {
            WriteBones(bs);
        }

        public override void CreateModelBinBlobData(BinaryStream bs)
        {
            WriteBones(bs);
        }

        private void WriteBones(BinaryStream bs)
        {
            // 1. Write Bone Count
            bs.WriteUInt16((ushort)Bones.Count);

            // 2. Write Each Bone
            foreach (var bone in Bones)
            {
                bs.WriteString(bone.Name ?? "", StringCoding.Int32CharCount);

                bs.WriteInt16(bone.ParentId);
                bs.WriteInt16(bone.FirstChildIndex);
                bs.WriteInt16(bone.NextIndex);

                // Matrix
                // If the bone has a valid matrix (read from file or modified), write it. 
                // Otherwise the default value of bone.Matrix is Identity, which corresponds to the "placeholder floats".
                bs.WriteSingle(bone.Matrix.M11); bs.WriteSingle(bone.Matrix.M12); bs.WriteSingle(bone.Matrix.M13); bs.WriteSingle(bone.Matrix.M14);
                bs.WriteSingle(bone.Matrix.M21); bs.WriteSingle(bone.Matrix.M22); bs.WriteSingle(bone.Matrix.M23); bs.WriteSingle(bone.Matrix.M24);
                bs.WriteSingle(bone.Matrix.M31); bs.WriteSingle(bone.Matrix.M32); bs.WriteSingle(bone.Matrix.M33); bs.WriteSingle(bone.Matrix.M34);
                bs.WriteSingle(bone.Matrix.M41); bs.WriteSingle(bone.Matrix.M42); bs.WriteSingle(bone.Matrix.M43); bs.WriteSingle(bone.Matrix.M44);
            }

            if (VersionMajor >= 1)
            {
                byte[] attributeData = BuildAttributeData();
                if (attributeData.Length > 0)
                {
                    bs.WriteUInt32((uint)attributeData.Length);
                    bs.Write(attributeData);
                }
                else
                {
                    bs.WriteUInt32(0);
                }
            }
        }

        private void ParseAttributeData()
        {
            _hasStructuredAttributeData = false;
            _attributeTrailingData = Array.Empty<byte>();
            AttributesHeader = 0;
            AttributeEntries = Array.Empty<ulong>();

            if (AttributeData.Length < 8)
                return;

            ReadOnlySpan<byte> data = AttributeData;
            AttributesHeader = BinaryPrimitives.ReadUInt32LittleEndian(data);
            uint entryCount = BinaryPrimitives.ReadUInt32LittleEndian(data.Slice(4, 4));
            int availableEntries = (data.Length - 8) / 8;
            int count = (int)Math.Min(entryCount, (uint)availableEntries);
            int consumedBytes = 8 + (count * 8);

            AttributeEntries = new ulong[count];
            for (int i = 0; i < count; i++)
                AttributeEntries[i] = BinaryPrimitives.ReadUInt64LittleEndian(data.Slice(8 + i * 8, 8));

            if (AttributeData.Length > consumedBytes)
                _attributeTrailingData = data.Slice(consumedBytes).ToArray();

            _hasStructuredAttributeData = true;
        }

        private byte[] BuildAttributeData()
        {
            if (!_hasStructuredAttributeData && AttributeData.Length > 0)
                return AttributeData;

            if (!_hasStructuredAttributeData && AttributesHeader == 0 && AttributeEntries.Length == 0)
                return Array.Empty<byte>();

            byte[] data = new byte[8 + (AttributeEntries.Length * 8) + _attributeTrailingData.Length];
            BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(0, 4), AttributesHeader);
            BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(4, 4), (uint)AttributeEntries.Length);

            for (int i = 0; i < AttributeEntries.Length; i++)
                BinaryPrimitives.WriteUInt64LittleEndian(data.AsSpan(8 + (i * 8), 8), AttributeEntries[i]);

            if (_attributeTrailingData.Length > 0)
                _attributeTrailingData.CopyTo(data, 8 + (AttributeEntries.Length * 8));

            return data;
        }
    }
}