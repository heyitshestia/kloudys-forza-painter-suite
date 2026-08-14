using ForzaTools.Bundles.Metadata;
using Syroot.BinaryData;
using System.Text;

namespace ForzaTools.Bundles.Blobs
{
    public class MaterialBlob : BundleBlob
    {
        public Bundle Bundle { get; set; }

        public byte[] CustomBlobData { get; set; }

        public override void ReadBlobData(BinaryStream bs)
        {
            // Capture raw bytes into CustomBlobData for extraction fallback
            if (Data != null && Data.Length > 0)
            {
                CustomBlobData = Data;
            }

            try
            {
                Bundle = new Bundle();
                Bundle.Load(bs.BaseStream);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error loading nested Bundle in MaterialBlob: {ex.Message}");
                System.Diagnostics.Debug.WriteLine($"Stack trace: {ex.StackTrace}");
                // Don't re-throw, keep CustomBlobData as fallback
                Bundle = null;
            }
        }

        public override void SerializeBlobData(BinaryStream bs)
        {
            if (Bundle != null)
            {
                Bundle.Serialize(bs.BaseStream);
            }
        }

        public override void CreateModelBinBlobData(BinaryStream bs)
        {
            // If the bundle has been parsed and possibly modified, serialize it fresh.
            if (Bundle != null)
            {
                // This ensures changes to children (like ShaderParams) are written.
                Bundle.Serialize(bs.BaseStream);
                return;
            }

            // If we have custom data injected from the library, use it.
            if (CustomBlobData != null && CustomBlobData.Length > 0)
            {
                bs.Write(CustomBlobData);
            }
            else
            {
                // Fallback / Error string if no data provided
                string fallback = "scene/library/materials/error.materialbin";
                Write7BitEncodedString(bs, fallback);
            }
        }

        // Override GetContents to return our persisted CustomBlobData or live Bundle data
        public override byte[] GetContents()
        {
            if (Bundle != null)
            {
                using (var ms = new System.IO.MemoryStream())
                {
                    Bundle.Serialize(ms);
                    return ms.ToArray();
                }
            }
            return CustomBlobData ?? base.GetContents();
        }

        // Standard 7-bit string writer for fallback paths
        private void Write7BitEncodedString(BinaryStream bs, string value)
        {
            if (value == null) value = "";
            byte[] bytes = Encoding.UTF8.GetBytes(value);
            Write7BitEncodedInt(bs, bytes.Length);
            bs.Write(bytes);
        }

        private void Write7BitEncodedInt(BinaryStream bs, int value)
        {
            uint v = (uint)value;
            while (v >= 0x80)
            {
                bs.WriteByte((byte)(v | 0x80));
                v >>= 7;
            }
            bs.WriteByte((byte)v);
        }
    }
}