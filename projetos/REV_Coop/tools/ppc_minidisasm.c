/* Minimal PowerPC 32-bit big-endian disassembler.
 * Usage: ppc_minidisasm file.bin offset_hex virtual_address_hex instruction_count
 * Input is a raw code slice, not an XEX container.
 */
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int hexarg(const char *s, unsigned long long *v) {
    char *end = NULL;
    errno = 0;
    *v = strtoull(s, &end, 16);
    return !errno && end != s && *end == '\0';
}
static int32_t sx(uint32_t v, unsigned n) {
    uint32_t m = 1u << (n - 1);
    return (int32_t)((v ^ m) - m);
}
static uint32_t be32(const unsigned char *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}
static void decode(uint32_t w, uint32_t pc, char *s, size_t n) {
    unsigned op=w>>26, rt=(w>>21)&31, ra=(w>>16)&31, rb=(w>>11)&31;
    unsigned xo=(w>>1)&1023;
    int32_t d=sx(w&0xffff,16);
#define OUT(...) snprintf(s,n,__VA_ARGS__)
    switch(op) {
    case 10: OUT("cmpli cr%u,r%u,0x%04X",(w>>23)&7,ra,w&0xffff); break;
    case 11: OUT("cmpwi cr%u,r%u,%d",(w>>23)&7,ra,d); break;
    case 14: if(!ra) OUT("li r%u,%d",rt,d); else OUT("addi r%u,r%u,%d",rt,ra,d); break;
    case 15: if(!ra) OUT("lis r%u,0x%04X",rt,w&0xffff); else OUT("addis r%u,r%u,%d",rt,ra,d); break;
    case 16: { int32_t bd=sx(w&0xfffc,16); uint32_t t=(w&2)?(uint32_t)bd:pc+(uint32_t)bd;
        OUT("bc 0x%X,0x%X,0x%08X%s",(w>>21)&31,(w>>16)&31,t,(w&1)?" (lk)":""); break; }
    case 18: { int32_t bd=sx(w&0x03fffffc,26); uint32_t t=(w&2)?(uint32_t)bd:pc+(uint32_t)bd;
        OUT("b 0x%08X%s",t,(w&1)?" (bl)":""); break; }
    case 19: if(xo==16) OUT("%s",(w&1)?"bclrl":"bclr"); else OUT(".long 0x%08X ; op19 xo=%u",w,xo); break;
    case 20: OUT("rlwimi r%u,r%u,%u,%u,%u",ra,rt,rb,(w>>6)&31,(w>>1)&31); break;
    case 21: OUT("rlwinm r%u,r%u,%u,%u,%u",ra,rt,rb,(w>>6)&31,(w>>1)&31); break;
    case 24: OUT("ori r%u,r%u,0x%04X",ra,rt,w&0xffff); break;
    case 25: OUT("oris r%u,r%u,0x%04X",ra,rt,w&0xffff); break;
    case 26: OUT("xori r%u,r%u,0x%04X",ra,rt,w&0xffff); break;
    case 32: OUT("lwz r%u,%d(r%u)",rt,d,ra); break;
    case 33: OUT("lwzu r%u,%d(r%u)",rt,d,ra); break;
    case 34: OUT("lbz r%u,%d(r%u)",rt,d,ra); break;
    case 36: OUT("stw r%u,%d(r%u)",rt,d,ra); break;
    case 37: OUT("stwu r%u,%d(r%u)",rt,d,ra); break;
    case 38: OUT("stb r%u,%d(r%u)",rt,d,ra); break;
    case 31:
        if(xo==23) OUT("lwzx r%u,r%u,r%u",rt,ra,rb);
        else if(xo==151) OUT("stwx r%u,r%u,r%u",rt,ra,rb);
        else if(xo==266) OUT("add r%u,r%u,r%u",rt,ra,rb);
        else if(xo==444 && ra==rb) OUT("mr r%u,r%u",ra,rt);
        else if(xo==444) OUT("or r%u,r%u,r%u",ra,rt,rb);
        else if(xo==339) OUT("mfspr r%u,%u",rt,((w>>16)&31)|((w>>6)&0x3e0));
        else if(xo==467) OUT("mtspr %u,r%u",((w>>16)&31)|((w>>6)&0x3e0),rt);
        else OUT(".long 0x%08X ; op31 xo=%u",w,xo);
        break;
    default: OUT(".long 0x%08X ; opcode=%u",w,op); break;
    }
#undef OUT
}
int main(int argc,char **argv) {
    FILE *f; unsigned long long off,va,count,i; unsigned char b[4];
    if(argc!=5 || !hexarg(argv[2],&off) || !hexarg(argv[3],&va) || !hexarg(argv[4],&count)) {
        fprintf(stderr,"Usage: %s file.bin offset_hex virtual_address_hex count\n",argv[0]); return 2;
    }
    f=fopen(argv[1],"rb"); if(!f) { perror(argv[1]); return 1; }
    if(off>(unsigned long long)LONG_MAX || fseek(f,(long)off,SEEK_SET)) {
        fprintf(stderr,"Invalid file offset\n"); fclose(f); return 1;
    }
    for(i=0;i<count;i++) {
        uint32_t pc=(uint32_t)(va+i*4), w; char text[128];
        if(fread(b,1,4,f)!=4) { if(ferror(f)) perror("fread"); break; }
        w=be32(b); decode(w,pc,text,sizeof(text));
        printf("%08X: %08X  %s\n",pc,w,text);
    }
    fclose(f); return 0;
}
