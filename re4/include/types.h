#ifndef TYPES_H
#define TYPES_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#ifdef TARGET_PC
// 360 port: same scalar types as Aurora's dolphin/types.h under TARGET_PC
typedef int8_t s8;
typedef int16_t s16;
typedef int32_t s32;
typedef int64_t s64;
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef signed char s8;
typedef signed short s16;
typedef signed long s32;
typedef signed long long s64;
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned long u32;
typedef unsigned long long u64;
#endif
typedef float f32;
typedef double f64;
typedef int BOOL;

#ifndef NULL
#define NULL 0
#endif

#endif
