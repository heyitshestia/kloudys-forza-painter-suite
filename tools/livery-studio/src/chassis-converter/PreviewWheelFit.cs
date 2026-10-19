using System.Numerics;

namespace Kfps.ChassisConverter;

internal enum PreviewWheelKind { Rim, Tire }
internal sealed record PreviewWheelDimensions(
    PreviewWheelKind Kind, float InnerRadius, float OuterRadius, float Width, float AxialMinimum);

// Explicit artist-authored preview deformation, NOT a native morph coefficient solver.
// The caller supplies decoded wheel-local geometry with X as the axle and Y/Z radial.
internal sealed class PreviewWheelFit
{
    public const string Mode = "user-configured-native-mesh-preview-v1";
    public PreviewWheelDimensions Target { get; }
    public float SourceAxialMinimum { get; }
    public float SourceAxialMaximum { get; }
    public float SourceInnerRadius { get; }
    public float SourceOuterRadius { get; }
    private readonly float axialScale, radialScale, radialOffset;

    private PreviewWheelFit(PreviewWheelDimensions target, float xmin, float xmax, float rmin, float rmax)
    {
        Target=target; SourceAxialMinimum=xmin; SourceAxialMaximum=xmax;
        SourceInnerRadius=rmin; SourceOuterRadius=rmax;
        axialScale=target.Width/(xmax-xmin);
        radialScale=target.Kind==PreviewWheelKind.Rim ? target.OuterRadius/rmax
            : (target.OuterRadius-target.InnerRadius)/(rmax-rmin);
        radialOffset=target.Kind==PreviewWheelKind.Rim ? 0 : target.InnerRadius-rmin*radialScale;
        if(!SafeScale(axialScale) || !SafeScale(radialScale))
            throw new InvalidDataException("Preview wheel deformation exceeds its bounded scale range.");
    }

    public static PreviewWheelFit Create(IReadOnlyList<Vector3> positions, PreviewWheelDimensions target)
    {
        if(target is null || !Enum.IsDefined(target.Kind) || !float.IsFinite(target.InnerRadius)
            || !float.IsFinite(target.OuterRadius) || !float.IsFinite(target.Width) || !float.IsFinite(target.AxialMinimum)
            || target.OuterRadius<.1f || target.OuterRadius>.8f || target.Width<.04f || target.Width>.8f
            || Math.Abs(target.AxialMinimum)>1 || Math.Abs(target.AxialMinimum+target.Width)>1)
            throw new InvalidDataException("Explicit bounded preview dimensions are required.");
        if((target.Kind==PreviewWheelKind.Rim && target.InnerRadius!=0)
            || (target.Kind==PreviewWheelKind.Tire && (target.InnerRadius<.08f || target.OuterRadius-target.InnerRadius<.01f)))
            throw new InvalidDataException("Invalid preview rim/bead radius.");
        if(positions is null || positions.Count<2 || positions.Count>1_000_000)
            throw new InvalidDataException("Preview source vertex count is invalid.");
        var xmin=float.PositiveInfinity; var xmax=float.NegativeInfinity;
        var rmin=float.PositiveInfinity; var rmax=0f;
        foreach(var p in positions) {
            if(!Finite(p) || p.LengthSquared()>400) throw new InvalidDataException("Invalid wheel-local source geometry.");
            var r=MathF.Sqrt(p.Y*p.Y+p.Z*p.Z);
            xmin=Math.Min(xmin,p.X); xmax=Math.Max(xmax,p.X);
            rmin=Math.Min(rmin,r); rmax=Math.Max(rmax,r);
        }
        if(xmax-xmin<.001f || rmax<.01f || (target.Kind==PreviewWheelKind.Tire && (rmin<.01f || rmax-rmin<.001f)))
            throw new InvalidDataException("Preview source is degenerate or is not an annular tire.");
        return new(target,xmin,xmax,rmin,rmax);
    }

    public NativeMorphedVertex Apply(Vector3 position, Vector3 normal)
    {
        if(!Finite(position) || !Finite(normal) || normal.LengthSquared()<1e-20f)
            throw new InvalidDataException("Invalid preview vertex or normal.");
        var radius=MathF.Sqrt(position.Y*position.Y+position.Z*position.Z);
        const float tolerance=.002f;
        if(position.X<SourceAxialMinimum-tolerance || position.X>SourceAxialMaximum+tolerance
            || radius>SourceOuterRadius+tolerance || (Target.Kind==PreviewWheelKind.Tire && radius<SourceInnerRadius-tolerance))
            throw new InvalidDataException("Preview vertex lies outside its qualified source bounds.");
        var targetRadius=radius*radialScale+radialOffset;
        var tangentialScale=radius>1e-8f ? targetRadius/radius : radialScale;
        if(!SafeScale(tangentialScale) || targetRadius<0)
            throw new InvalidDataException("Preview radial deformation is singular or inverted.");
        var p=new Vector3((position.X-SourceAxialMinimum)*axialScale+Target.AxialMinimum,
            position.Y*tangentialScale,position.Z*tangentialScale);
        var radial=radius>1e-8f ? new Vector2(position.Y,position.Z)/radius : Vector2.UnitX;
        var n=new Vector2(normal.Y,normal.Z);
        var nr=radial*Vector2.Dot(n,radial);
        var yz=nr/radialScale+(n-nr)/tangentialScale;
        var transformed=new Vector3(normal.X/axialScale,yz.X,yz.Y);
        var length=transformed.Length();
        if(!Finite(p) || !Finite(transformed) || !float.IsFinite(length) || length<1e-10f)
            throw new InvalidDataException("Preview deformation produced invalid geometry.");
        return new(p,transformed/length);
    }

    private static bool SafeScale(float value)=>float.IsFinite(value) && value>=.02f && value<=20;
    private static bool Finite(Vector3 v)=>float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z);
}
