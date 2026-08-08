"""Minimal Vector3D so the ports read like the C# they came from."""
import math


class V:
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(s, o): return V(s.x + o.x, s.y + o.y, s.z + o.z)
    def __sub__(s, o): return V(s.x - o.x, s.y - o.y, s.z - o.z)
    def __mul__(s, k): return V(s.x * k, s.y * k, s.z * k)
    __rmul__ = __mul__
    def __truediv__(s, k): return V(s.x / k, s.y / k, s.z / k)
    def __neg__(s): return V(-s.x, -s.y, -s.z)
    def __repr__(s): return f"V({s.x:.6g},{s.y:.6g},{s.z:.6g})"

    def dot(s, o): return s.x * o.x + s.y * o.y + s.z * o.z
    def length_sq(s): return s.x * s.x + s.y * s.y + s.z * s.z
    def length(s): return math.sqrt(s.length_sq())

    def normalized(s):
        l = s.length()
        return V(0, 0, 0) if l == 0 else V(s.x / l, s.y / l, s.z / l)

    def copy(s): return V(s.x, s.y, s.z)


def rotate_axis_angle(v, axis, angle):
    """Rodrigues rotation — equivalent to Vector3D.Transform(v, QuaternionD.CreateFromAxisAngle)."""
    if angle == 0.0:
        return v.copy()
    k = axis.normalized()
    c, s = math.cos(angle), math.sin(angle)
    cross = V(k.y * v.z - k.z * v.y, k.z * v.x - k.x * v.z, k.x * v.y - k.y * v.x)
    return v * c + cross * s + k * (k.dot(v) * (1.0 - c))
