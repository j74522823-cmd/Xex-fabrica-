"""ctypes front end of the native helper (host/): the game's own MotionSetCore / MotionMove.

`Player(model, motion)` hosts a cModel built from the .bin's parts records (rest pose, parent
links, bind matrices as cModel::initJoint does), starts the motion with MotionSetCore (flags 0:
no root movement, linear sequence over maxFrame + 1 frames, IK chains initialised from the joint
table) and plays frames with MotionMove: MotionMoveCore decodes the keys into the parts'
ang/pos/scale, partsMatCalc/partsWorldCalc build the matrices, InverseKinematics bends the
IK chains to the effector keys (no floor collision on the host), the blend table slerps the
double joints. `frame(f)` returns the parts state after that.
"""
import ctypes
import os
import subprocess

from . import fcv

HOST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'host')
LIB_NAMES = {'plain': 'libmotion_host.so', 'fma': 'libmotion_host_fma.so'}

F32P = ctypes.POINTER(ctypes.c_float)
U8P = ctypes.POINTER(ctypes.c_uint8)
U16P = ctypes.POINTER(ctypes.c_uint16)
U32P = ctypes.POINTER(ctypes.c_uint32)
I32P = ctypes.POINTER(ctypes.c_int)


def build(variant='plain'):
    target = 'all' if variant == 'plain' else 'fma'
    r = subprocess.run(['make', '-s', target], cwd=HOST_DIR, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'host helper build failed:\n{r.stderr}')
    return os.path.join(HOST_DIR, 'build', LIB_NAMES[variant])


_libs = {}


def load(variant='plain'):
    if variant not in _libs:
        lib = ctypes.CDLL(build(variant))
        lib.mot_model_create.argtypes = [ctypes.c_int, I32P, F32P]
        lib.mot_model_create.restype = ctypes.c_void_p
        lib.mot_model_destroy.argtypes = [ctypes.c_void_p]
        lib.mot_model_blend_table.argtypes = [ctypes.c_void_p, U16P]
        lib.mot_model_set.argtypes = [ctypes.c_void_p, U8P, ctypes.c_size_t, ctypes.c_int, ctypes.c_int]
        lib.mot_model_frame.argtypes = [ctypes.c_void_p, ctypes.c_float]
        lib.mot_model_place.argtypes = [ctypes.c_void_p, F32P, F32P, F32P]
        lib.mot_model_frame.restype = ctypes.c_uint16
        lib.mot_model_root.argtypes = [ctypes.c_void_p, F32P, F32P]
        lib.mot_model_read.argtypes = [ctypes.c_void_p, F32P, F32P, F32P, F32P, F32P, F32P, U32P]
        lib.mot_model_max_frame.argtypes = [ctypes.c_void_p]
        lib.mot_model_max_frame.restype = ctypes.c_float
        lib.mot_rot_matrix.argtypes = [F32P, F32P]
        lib.mot_quat_from_matrix.argtypes = [F32P, F32P]
        lib.mot_hermite.argtypes = [F32P, F32P, ctypes.c_float]
        lib.mot_hermite.restype = ctypes.c_float
        _libs[variant] = lib
    return _libs[variant]


class GameLogError(RuntimeError):
    pass


class Pose:
    """Parts state of one frame (lists indexed by parts number)."""

    def __init__(self, n, pos, ang, scale, l_mat, mat, world, flags, root_pos, root_rot, player):
        self.n = n
        self.quat = player.quat_from_matrix   # rotation part of a 3x4 matrix -> (x, y, z, w), C_QUATMtx
        self.root_mat = player.rot_matrix(root_rot)   # RotMatrix of the root rotation keys
        self.pos = [tuple(pos[3 * i:3 * i + 3]) for i in range(n)]
        self.ang = [tuple(ang[3 * i:3 * i + 3]) for i in range(n)]
        self.scale = [tuple(scale[3 * i:3 * i + 3]) for i in range(n)]
        self.l_mat = [tuple(l_mat[12 * i:12 * i + 12]) for i in range(n)]
        self.mat = [tuple(mat[12 * i:12 * i + 12]) for i in range(n)]
        self.world = [tuple(world[3 * i:3 * i + 3]) for i in range(n)]
        self.flags = list(flags)
        self.root_pos = root_pos
        self.root_rot = root_rot


class Player:
    def __init__(self, model, motion: fcv.Motion, variant='plain', loop=False, ik=True, blend_table=None):
        """blend_table: overrides the model's (None: the .bin's, [] : none)."""
        self.lib = load(variant)
        self.model = model
        self.motion = motion
        n = model.n_parts
        self.n = n
        for j in motion.joints:
            if j.target() is not None and j.parts_no >= n:
                raise ValueError(f'motion joint targets parts {j.parts_no}, model has {n} parts')
        parent = (ctypes.c_int * n)(*(p.parent for p in model.parts))
        rest = (ctypes.c_float * (3 * n))(*[c for p in model.parts for c in p.pos])
        self.handle = self.lib.mot_model_create(n, parent, rest)
        self.blend_tbl = None
        if blend_table is None:
            blend_table = model.blend_table
        if blend_table:
            # MotionMove: s32 count (host order, as two u16 words) then u16 (dst, a, c, percent)
            words = [len(blend_table) & 0xFFFF, len(blend_table) >> 16] + [w for e in blend_table for w in e]
            self.blend_tbl = (ctypes.c_uint16 * len(words))(*words)
            self.lib.mot_model_blend_table(self.handle, self.blend_tbl)
        image = fcv.serialise(motion, '<')
        buf = (ctypes.c_uint8 * len(image)).from_buffer_copy(image)
        self.lib.mot_host_clear_errors()
        flags = 4 if loop else 0   # Mot_attr bit2: loop
        cnt = self.lib.mot_model_set(self.handle, buf, len(image), flags, 1 if ik else 0)
        if cnt != len(motion.joints):
            raise RuntimeError('MotionSetCore joint count mismatch')
        if self.lib.mot_host_errors():
            raise GameLogError('MotionSetCore logged an error')
        self.ik = ik

    def __del__(self):
        if getattr(self, 'handle', None):
            self.lib.mot_model_destroy(self.handle)
            self.handle = None

    def place(self, pos, ang, scale):
        """Model position / rotation / scale (default: the origin, unit scale)."""
        self.lib.mot_model_place(self.handle, (ctypes.c_float * 3)(*pos), (ctypes.c_float * 3)(*ang), (ctypes.c_float * 3)(*scale))

    def frame(self, f):
        n = self.n
        self.lib.mot_host_clear_errors()
        self.lib.mot_model_frame(self.handle, float(f))
        if self.lib.mot_host_errors():
            raise GameLogError(f'frame {f}: the game logged an error')
        pos = (ctypes.c_float * (3 * n))()
        ang = (ctypes.c_float * (3 * n))()
        scale = (ctypes.c_float * (3 * n))()
        l_mat = (ctypes.c_float * (12 * n))()
        mat = (ctypes.c_float * (12 * n))()
        world = (ctypes.c_float * (3 * n))()
        flags = (ctypes.c_uint32 * n)()
        self.lib.mot_model_read(self.handle, pos, ang, scale, l_mat, mat, world, flags)
        rp = (ctypes.c_float * 3)()
        rr = (ctypes.c_float * 3)()
        self.lib.mot_model_root(self.handle, rp, rr)
        return Pose(n, pos, ang, scale, l_mat, mat, world, flags, tuple(rp), tuple(rr), self)

    def rot_matrix(self, ang):
        """The game's RotMatrix (Rz * Ry * Rx) as a 3x4 row-major list."""
        a = (ctypes.c_float * 3)(*ang)
        m = (ctypes.c_float * 12)()
        self.lib.mot_rot_matrix(a, m)
        return list(m)

    def quat_from_matrix(self, m):
        """(x, y, z, w) of a 3x4 row-major matrix's rotation part (C_QUATMtx; columns unit length)."""
        mm = (ctypes.c_float * 12)(*m)
        q = (ctypes.c_float * 4)()
        self.lib.mot_quat_from_matrix(mm, q)
        return tuple(q)
