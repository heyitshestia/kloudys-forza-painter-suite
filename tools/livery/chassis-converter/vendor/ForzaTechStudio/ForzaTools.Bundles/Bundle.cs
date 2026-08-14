using System;
using System.Collections.Generic;
using System.IO;
using Syroot.BinaryData;
using ForzaTools.Bundles.Blobs;

namespace ForzaTools.Bundles
{
    public class Bundle
    {
        public const uint BundleTag = 0x47727562; // "Grub"
        public byte VersionMajor { get; set; }
        public byte VersionMinor { get; set; }

        public List<BundleBlob> Blobs { get; set; } = new List<BundleBlob>();

        // Tags
        public const uint TAG_BLOB_TextureContentBlob = 0x54584342;
        public const uint TAG_BLOB_STex = 0x53546578;
        public const uint TAG_BLOB_Skeleton = 0x536B656C;
        public const uint TAG_BLOB_Morph = 0x4D727068;
        public const uint TAG_BLOB_Mesh = 0x4D657368;
        public const uint TAG_BLOB_IndexBuffer = 0x496E6442;
        public const uint TAG_BLOB_VertexLayout = 0x564C6179;
        public const uint TAG_BLOB_InstancedVertexLayout = 0x494C6179;
        public const uint TAG_BLOB_VertexBuffer = 0x56657242;
        public const uint TAG_BLOB_MorphBuffer = 0x4D427566;
        public const uint TAG_BLOB_Skin = 0x536B696E;
        public const uint TAG_BLOB_Model = 0x4D6F646C;
        public const uint TAG_BLOB_MaterialInstance = 0x4D617449;
        public const uint TAG_BLOB_MaterialResource = 0x4D415449;
        public const uint TAG_BLOB_MATL = 0x4D41544C;
        public const uint TAG_BLOB_MaterialShaderParameter = 0x4D545052;
        public const uint TAG_BLOB_ManufacturerColors = 0x4D4E434C;
        public const uint TAG_BLOB_DefaultShaderParameter = 0x44465052;
        public const uint TAG_BLOB_LightScenario = 0x4C534345;
        public const uint TAG_BLOB_DebugLightScenario = 0x44424C53;
        public const uint TAG_BLOB_CBMP = 0x43424D50;
        public const uint TAG_BLOB_TXMP = 0x54584D50;
        public const uint TAG_BLOB_SPMP = 0x53504D50;
        public const uint TAG_BLOB_TRGT = 0x54524754;
        public const uint TAG_BLOB_VARS = 0x56415253;
        public const uint TAG_BLOB_VERS = 0x56455253;
        public const uint TAG_BLOB_ParticleBlob = 0x50434C42;

        // Shader-specific blob tags (shaderbin format)
        public const uint TAG_BLOB_TREV = 0x56455254; // Vertex shader register permutation table
        public const uint TAG_BLOB_FRXT = 0x54585246; // shader blob (purpose TBD)
        public const uint TAG_BLOB_CBEX = 0x43424558; // Constant buffer extended register data
        public const uint TAG_BLOB_PARM = 0x5041524D; // Shader parameter name/ID table
        public const uint TAG_BLOB_SHUD = 0x53485544; // Shader hint/user-data string pairs

        public void Load(Stream stream)
        {
            long baseBundleOffset = stream.Position;
            var bs = new BinaryStream(stream);

            uint tag = bs.ReadUInt32();
            if (tag != BundleTag) throw new InvalidDataException($"Invalid Bundle Tag: {tag:X8}");

            VersionMajor = bs.Read1Byte();
            VersionMinor = bs.Read1Byte();

            uint blobCount;

            // version check
            if (VersionMajor > 1 || (VersionMajor == 1 && VersionMinor >= 1))
            {
                bs.ReadInt16(); // Padding
                bs.ReadUInt32(); // HeaderSize
                bs.ReadUInt32(); // TotalSize
                blobCount = bs.ReadUInt32();
            }
            else
            {
                blobCount = bs.ReadUInt16();
                bs.Position += 0x08; // Skip to end of header
            }

            long blobHeadersStart = bs.Position;

            for (int i = 0; i < blobCount; i++)
            {
                try
                {
                    bs.Position = blobHeadersStart + (i * BundleBlob.InfoSize);

                    uint blobTag = bs.ReadUInt32();
                    bs.Position -= 4;

                    BundleBlob blob = GetBlobByTag(blobTag);

                    blob.Read(bs, baseBundleOffset);
                    Blobs.Add(blob);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error reading blob at index {i}: {ex.Message}");
                    var errBlob = new GenericBlob { Tag = 0xBAD00000 };
                    Blobs.Add(errBlob);
                }
            }
        }

        public void Serialize(Stream stream)
        {
            CreateModelBin(stream);
        }

        // Serializes using version-aware blob data (use for repacking existing files)
        public void SerializeConverted(Stream stream)
        {
            long baseBundleOffset = stream.Position;
            var bs = new BinaryStream(stream);

            // 1. Write File Header
            bs.WriteUInt32(BundleTag);
            bs.WriteByte(VersionMajor);
            bs.WriteByte(VersionMinor);

            if (VersionMajor > 1 || (VersionMajor == 1 && VersionMinor >= 1))
            {
                bs.WriteInt16(0); // Padding
                bs.WriteUInt32(0); // Header Size (Placeholder)
                bs.WriteUInt32(0); // Total Size (Placeholder)
                bs.WriteUInt32((uint)Blobs.Count);
            }
            else
            {
                bs.WriteUInt16((ushort)Blobs.Count);
                bs.WriteUInt32(0);
                bs.WriteUInt32(0);
            }

            long blobHeadersStart = bs.Position;
            // Reserve space for blob headers
            bs.Position += Blobs.Count * BundleBlob.InfoSize;

            // Write metadata for each blob
            for (int i = 0; i < Blobs.Count; i++)
            {
                BundleBlob blob = Blobs[i];

                long currentMetadataOffset = bs.Position;
                blob.SerializeMetadatas(bs);

                // Update Blob Header (Metadata part)
                long currentPos = bs.Position;
                bs.Position = blobHeadersStart + (i * BundleBlob.InfoSize);

                bs.Position += 6; // Skip Tag(4) + Maj(1) + Min(1)

                // Offset 0x06: Metadata Count (2)
                bs.WriteUInt16((ushort)blob.Metadatas.Count);

                // Offset 0x08: Metadata Offset (4)
                bs.WriteUInt32((uint)(currentMetadataOffset - baseBundleOffset));

                bs.Position = currentPos;
            }

            bs.Align(0x04, true);
            long headerEndPos = bs.Position;
            long headerSize = headerEndPos - baseBundleOffset;

            // Write blob data
            for (int i = 0; i < Blobs.Count; i++)
            {
                BundleBlob blob = Blobs[i];
                long blobDataStart = bs.Position;

                blob.SerializeBlobData(bs);

                long blobDataEnd = bs.Position;
                uint uncompressedSize = (uint)(blobDataEnd - blobDataStart);

                bs.Align(0x04, true);
                long nextBlobStart = bs.Position;

                bs.Position = blobHeadersStart + (i * BundleBlob.InfoSize);
                bs.WriteUInt32(blob.Tag);
                bs.WriteByte(blob.VersionMajor);
                bs.WriteByte(blob.VersionMinor);

                bs.Position += 6; // Skip MetadataCount(2) + MetadataOffset(4)

                bs.WriteUInt32((uint)(blobDataStart - baseBundleOffset));
                // Offset 0x10: CompressedSize (same as uncompressed for raw)
                bs.WriteUInt32(uncompressedSize);
                bs.WriteUInt32(uncompressedSize);

                bs.Position = nextBlobStart;
            }

            long totalSize = bs.Position - baseBundleOffset;

            // Finalize file header sizes
            bs.Position = baseBundleOffset + 6;
            if (VersionMajor > 1 || (VersionMajor == 1 && VersionMinor >= 1))
            {
                bs.Position += 2; // Skip padding
                bs.WriteUInt32((uint)headerSize);
                bs.WriteUInt32((uint)totalSize);
            }
            else
            {
                bs.Position += 2;
                bs.WriteUInt32((uint)headerSize);
                bs.WriteUInt32((uint)totalSize);
            }
            bs.Position = baseBundleOffset + totalSize;
        }

        public void CreateModelBin(Stream stream)
        {
            long baseBundleOffset = stream.Position;
            var bs = new BinaryStream(stream);

            bs.WriteUInt32(BundleTag);
            bs.WriteByte(VersionMajor);
            bs.WriteByte(VersionMinor);

            if (VersionMajor > 1 || (VersionMajor == 1 && VersionMinor >= 1))
            {
                bs.WriteInt16(0); // Padding
                bs.WriteUInt32(0); // Header Size (Placeholder)
                bs.WriteUInt32(0); // Total Size (Placeholder)
                bs.WriteUInt32((uint)Blobs.Count);
            }
            else
            {
                bs.WriteUInt16((ushort)Blobs.Count);
                bs.WriteUInt32(0);
                bs.WriteUInt32(0);
            }

            long blobHeadersStart = bs.Position;
            // Reserve space for blob headers
            bs.Position += Blobs.Count * BundleBlob.InfoSize;

            // Write metadata for each blob
            for (int i = 0; i < Blobs.Count; i++)
            {
                BundleBlob blob = Blobs[i];

                long currentMetadataOffset = bs.Position;
                blob.CreateModelBinMetadatas(bs);

                // Update blob header (metadata part)
                long currentPos = bs.Position;
                bs.Position = blobHeadersStart + (i * BundleBlob.InfoSize);
                bs.Position += 6; // Skip Tag(4)+Maj(1)+Min(1)
                bs.WriteUInt16((ushort)blob.Metadatas.Count);
                bs.WriteUInt32((uint)(currentMetadataOffset - baseBundleOffset));
                bs.Position = currentPos;
            }

            bs.Align(0x04, true);
            long headerEndPos = bs.Position;
            long headerSize = headerEndPos - baseBundleOffset;

            // Write blob data
            for (int i = 0; i < Blobs.Count; i++)
            {
                BundleBlob blob = Blobs[i];
                long blobDataStart = bs.Position;

                blob.CreateModelBinBlobData(bs);

                long blobDataEnd = bs.Position;
                uint uncompressedSize = (uint)(blobDataEnd - blobDataStart);

                bs.Align(0x04, true);
                long nextBlobStart = bs.Position;

                bs.Position = blobHeadersStart + (i * BundleBlob.InfoSize);
                bs.WriteUInt32(blob.Tag);
                bs.WriteByte(blob.VersionMajor);
                bs.WriteByte(blob.VersionMinor);

                // Current offset 0x06 — skip MetadataCount(2)+MetadataOffset(4) to reach DataOffset
                bs.Position += 6;

                bs.WriteUInt32((uint)(blobDataStart - baseBundleOffset));
                // CompressedSize (same as uncompressed for raw)
                bs.WriteUInt32(uncompressedSize);
                bs.WriteUInt32(uncompressedSize);

                bs.Position = nextBlobStart;
            }

            long totalSize = bs.Position - baseBundleOffset;

            // Finalize file header sizes
            bs.Position = baseBundleOffset + 6;
            if (VersionMajor > 1 || (VersionMajor == 1 && VersionMinor >= 1))
            {
                bs.Position += 2; // Skip padding
                bs.WriteUInt32((uint)headerSize);
                bs.WriteUInt32((uint)totalSize);
            }
            else
            {
                bs.Position += 2; // Skip padding
                bs.WriteUInt32((uint)headerSize);
                bs.WriteUInt32((uint)totalSize);
            }
            bs.Position = baseBundleOffset + totalSize;
        }

        public BundleBlob GetBlobByIndex(uint tag, int index)
        {
            int current = 0;
            foreach (var blob in Blobs)
            {
                if (blob.Tag == tag)
                {
                    if (current == index) return blob;
                    current++;
                }
            }
            return null;
        }

        private BundleBlob GetBlobByTag(uint tag)
        {
            return tag switch
            {
                TAG_BLOB_Skeleton => new SkeletonBlob(),
                TAG_BLOB_Morph => new MorphBlob(),
                TAG_BLOB_MaterialInstance => new MaterialBlob(),
                TAG_BLOB_MaterialResource => new MaterialResourceBlob(),
                TAG_BLOB_MATL => new MatLBlob(),
                TAG_BLOB_MaterialShaderParameter => new MaterialShaderParameterBlob(),
                TAG_BLOB_DefaultShaderParameter => new MaterialShaderParameterBlob(),
                TAG_BLOB_Mesh => new MeshBlob(),
                TAG_BLOB_IndexBuffer => new IndexBufferBlob(),
                TAG_BLOB_VertexLayout => new VertexLayoutBlob(),
                TAG_BLOB_InstancedVertexLayout => new VertexLayoutBlob(),
                TAG_BLOB_VertexBuffer => new VertexBufferBlob(),
                TAG_BLOB_MorphBuffer => new MorphBufferBlob(),
                TAG_BLOB_Skin => new SkinBufferBlob(),
                TAG_BLOB_Model => new ModelBlob(),
                TAG_BLOB_TextureContentBlob => new TextureContentBlob(),
                TAG_BLOB_LightScenario => new LightScenarioBlob(),
                TAG_BLOB_DebugLightScenario => new LightScenarioBlob(),
                TAG_BLOB_CBMP => new ShaderParameterMappingBlob(),
                TAG_BLOB_TXMP => new ShaderParameterMappingBlob(),
                TAG_BLOB_SPMP => new ShaderParameterMappingBlob(),
                TAG_BLOB_ManufacturerColors => new ManufacturerColorsBlob(),
                TAG_BLOB_TRGT => new RenderTargetBlob(),
                TAG_BLOB_STex => new STexBlob(),
                TAG_BLOB_ParticleBlob => new ParticleBlob(),
                TAG_BLOB_VERS => new VersBlob(),
                TAG_BLOB_VARS => new VarsBlob(),
                TAG_BLOB_TREV => new TrevBlob(),
                TAG_BLOB_FRXT => new FrxtBlob(),
                TAG_BLOB_CBEX => new CbexBlob(),
                TAG_BLOB_PARM => new ParmBlob(),
                TAG_BLOB_SHUD => new ShudBlob(),
                _ => new GenericBlob()
            };
        }
    }
}