using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Numerics;
using Syroot.BinaryData;

namespace ForzaTools.Bundles
{
    public static class StreamExtensions
    {
        public static void WriteMatrix4x4(this Stream stream, Matrix4x4 matrix)
        {
            var data = new float[] { 
                matrix.M11, matrix.M12, matrix.M13, matrix.M14,
                matrix.M21, matrix.M22, matrix.M23, matrix.M24,
                matrix.M31, matrix.M32, matrix.M33, matrix.M34,
                matrix.M41, matrix.M42, matrix.M43, matrix.M44 
            };
            foreach (var f in data)
            {
                byte[] bytes = BitConverter.GetBytes(f);
                stream.Write(bytes, 0, bytes.Length);
            }
        }

        public static void WriteVector4(this Stream stream, Vector4 vec)
        {
            byte[] x = BitConverter.GetBytes(vec.X);
            byte[] y = BitConverter.GetBytes(vec.Y);
            byte[] z = BitConverter.GetBytes(vec.Z);
            byte[] w = BitConverter.GetBytes(vec.W);
            stream.Write(x, 0, 4);
            stream.Write(y, 0, 4);
            stream.Write(z, 0, 4);
            stream.Write(w, 0, 4);
        }

        public static void WriteVector3(this Stream stream, Vector3 vec)
        {
            byte[] x = BitConverter.GetBytes(vec.X);
            byte[] y = BitConverter.GetBytes(vec.Y);
            byte[] z = BitConverter.GetBytes(vec.Z);
            stream.Write(x, 0, 4);
            stream.Write(y, 0, 4);
            stream.Write(z, 0, 4);
        }

        public static Vector4 ReadVector4(this Stream stream)
        {
            byte[] buffer = new byte[16];
            stream.Read(buffer, 0, 16);
            return new Vector4(
                BitConverter.ToSingle(buffer, 0),
                BitConverter.ToSingle(buffer, 4),
                BitConverter.ToSingle(buffer, 8),
                BitConverter.ToSingle(buffer, 12));
        }

        public static Vector3 ReadVector3(this Stream stream)
        {
            byte[] buffer = new byte[12];
            stream.Read(buffer, 0, 12);
            return new Vector3(
                BitConverter.ToSingle(buffer, 0),
                BitConverter.ToSingle(buffer, 4),
                BitConverter.ToSingle(buffer, 8));
        }

        // BinaryStream extensions
        public static void WriteVector4(this BinaryStream bs, Vector4 vec)
        {
            bs.WriteSingle(vec.X);
            bs.WriteSingle(vec.Y);
            bs.WriteSingle(vec.Z);
            bs.WriteSingle(vec.W);
        }

        public static void WriteVector3(this BinaryStream bs, Vector3 vec)
        {
            bs.WriteSingle(vec.X);
            bs.WriteSingle(vec.Y);
            bs.WriteSingle(vec.Z);
        }

        public static Vector4 ReadVector4(this BinaryStream bs)
        {
            return new Vector4(bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle());
        }

        public static Vector3 ReadVector3(this BinaryStream bs)
        {
            return new Vector3(bs.ReadSingle(), bs.ReadSingle(), bs.ReadSingle());
        }
    }
}
