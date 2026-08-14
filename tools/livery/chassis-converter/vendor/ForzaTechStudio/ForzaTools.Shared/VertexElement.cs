using System.Runtime.InteropServices;

namespace ForzaTools.Shared
{
    [StructLayout(LayoutKind.Sequential)]
    public struct VertexElement
    {
        public short SemanticNameIndex;
        public short SemanticIndex;
        public int InputSlot;
        public DXGI_FORMAT Format;
        public int AlignedByteOffset;
        public int InstanceDataStepRate;
    }
}
