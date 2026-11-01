# Host build of the game's motion evaluation code (see ../README.md).
#
#   make            -> build/libmotion_host.so       (plain x86-64 SSE float arithmetic)
#   make fma        -> build/libmotion_host_fma.so   (-mfma -ffp-contract=fast: fused multiply-adds
#                                                     like the PowerPC fmadds the game uses)
#
# Sources (nothing in the game tree is edited; prepare.py writes host copies into build/):
#   motion_prep.cpp   src/game/motion.cpp with the PowerPC register pins stripped and the u32
#                     pointer casts widened (MotionSetCore, MotionMove, HermiteInterpolation, ...)
#   ik_prep.cpp       src/game/ik.cpp (IKInit, InverseKinematics, ikCalc)
#   game_extract.cpp  functions copied verbatim from src/game/math_sub.cpp (hermite, RotMatrix,
#                     TransMatrix, ScaleMatrix, VecRadLimit, SetOrientationZX/ZY, VecAngle,
#                     VecLinearCombination), sub2.cpp (RootSumSquare3, GetDistance3) and
#                     model.cpp (cModel::partsMatCalc, partsWorldCalc, getPartsPtr, matBlend)
#   sdk_extract.cpp   the SDK's C matrix/vector/quaternion routines (src/lib mtx.c, mtxvec.c, vec.c, quat.c)
#                     under the PS* names the game links (paired-single assembly on the GameCube)
#   fdlibm            the game's libm sinf/cosf/acosf (src/lib sf_sin.cpp ..., renamed re4_*)
#   motion_host.cpp   the driver: the hosted cModel, stubs, C versions of SQRTF / LIMIT_ANGLE
# Unused functions are dropped by --gc-sections.

ROOT   := $(abspath ../../..)
BUILD  := build
CXX    ?= g++
PY     ?= python3

CXXFLAGS := -O2 -g -std=gnu++14 -fno-strict-aliasing -fno-fast-math \
            -fPIC -fvisibility=hidden -ffunction-sections -fdata-sections \
            -Wno-register -Wno-unused-variable -Wno-unused-but-set-variable -Wno-int-to-pointer-cast \
            -Wno-unused-function
LDFLAGS  := -shared -Wl,--gc-sections -Wl,-Bsymbolic

FDLIBM_DEFS := -Dsinf=re4_sinf -Dcosf=re4_cosf -Dacosf=re4_acosf -Dfabsf=re4_fabsf -Dfloorf=re4_floorf -Dscalbnf=re4_scalbnf
FDLIBM_SRCS := sf_sin sf_cos kf_sin kf_cos ef_rem_pio2 kf_rem_pio2 sf_scalbn sf_floor sf_fabs ef_acos ef_sqrt

MATH_FUNCS  := hermite RotMatrix TransMatrix ScaleMatrix VecRadLimit SetOrientationZX SetOrientationZY VecAngle VecLinearCombination
SUB2_FUNCS  := RootSumSquare3 GetDistance3
MODEL_FUNCS := cModel::partsMatCalc cModel::partsWorldCalc cModel::getPartsPtr cModel::matBlend
MTX_FUNCS   := C_MTXIdentity C_MTXCopy C_MTXConcat C_MTXInverse C_MTXTranspose C_MTXTrans C_MTXScale \
               C_MTXRotTrig C_MTXRotRad C_MTXRotAxisRad C_MTXQuat
MTXVEC_FUNCS := C_MTXMultVec C_MTXMultVecSR
VEC_FUNCS   := C_VECAdd C_VECSubtract C_VECScale C_VECNormalize C_VECSquareMag C_VECMag C_VECDotProduct C_VECCrossProduct
QUAT_FUNCS  := C_QUATMtx C_QUATSlerp

GAME_SRCS := $(BUILD)/motion_prep.cpp $(BUILD)/ik_prep.cpp $(BUILD)/game_extract.cpp $(BUILD)/sdk_extract.cpp motion_host.cpp

all: $(BUILD)/libmotion_host.so
fma: $(BUILD)/libmotion_host_fma.so

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/motion_prep.cpp: $(ROOT)/src/game/motion.cpp prepare.py | $(BUILD)
	$(PY) prepare.py motion $< $@

$(BUILD)/ik_prep.cpp: $(ROOT)/src/game/ik.cpp prepare.py | $(BUILD)
	$(PY) prepare.py motion $< $@

$(BUILD)/game_extract.cpp: $(ROOT)/src/game/math_sub.cpp $(ROOT)/src/game/sub2.cpp $(ROOT)/src/game/model.cpp prepare.py | $(BUILD)
	$(PY) prepare.py extract $(ROOT)/src/game/math_sub.cpp $(BUILD)/x_math.cpp $(MATH_FUNCS)
	$(PY) prepare.py extract $(ROOT)/src/game/sub2.cpp $(BUILD)/x_sub2.cpp $(SUB2_FUNCS)
	$(PY) prepare.py extract $(ROOT)/src/game/model.cpp $(BUILD)/x_model.cpp $(MODEL_FUNCS)
	cat $(BUILD)/x_math.cpp $(BUILD)/x_sub2.cpp $(BUILD)/x_model.cpp > $@

$(BUILD)/sdk_extract.cpp: $(ROOT)/src/lib/mtx.c $(ROOT)/src/lib/mtxvec.c $(ROOT)/src/lib/vec.c $(ROOT)/src/lib/quat.c prepare.py | $(BUILD)
	$(PY) prepare.py extract $(ROOT)/src/lib/mtx.c $(BUILD)/x_mtx.cpp $(MTX_FUNCS)
	$(PY) prepare.py extract $(ROOT)/src/lib/mtxvec.c $(BUILD)/x_mtxvec.cpp $(MTXVEC_FUNCS)
	$(PY) prepare.py extract $(ROOT)/src/lib/vec.c $(BUILD)/x_vec.cpp $(VEC_FUNCS)
	$(PY) prepare.py extract $(ROOT)/src/lib/quat.c $(BUILD)/x_quat.cpp $(QUAT_FUNCS)
	cat $(BUILD)/x_mtx.cpp $(BUILD)/x_mtxvec.cpp $(BUILD)/x_vec.cpp $(BUILD)/x_quat.cpp > $@

# $(1): library name, $(2): variant suffix for objects, $(3): extra flags
define BUILD_LIB
$(BUILD)/$(1).so: $(GAME_SRCS) stub/re4_host_stub.h
	for f in $(FDLIBM_SRCS); do \
	    $(CXX) $(CXXFLAGS) $(3) -I $(ROOT)/include $(FDLIBM_DEFS) -c $(ROOT)/src/lib/$$$${f}.cpp -o $(BUILD)/$$$${f}$(2).o || exit 1; \
	done
	$(CXX) $(CXXFLAGS) $(3) -I stub -o $$@ $(GAME_SRCS) $(BUILD)/*$(2).o $(LDFLAGS)
endef

$(eval $(call BUILD_LIB,libmotion_host,_plain,-ffp-contract=off))
$(eval $(call BUILD_LIB,libmotion_host_fma,_fma,-mfma -ffp-contract=fast))

clean:
	rm -rf $(BUILD)

.PHONY: all fma clean
