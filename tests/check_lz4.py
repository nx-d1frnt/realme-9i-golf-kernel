#!/usr/bin/env python3
"""Cross-decode actual old/new kernel LZ4 sources under AddressSanitizer.

Only kernel headers are shimmed for the host. Codec implementation files remain
unchanged. This validates block compatibility and buffers, not ARM performance.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--old-source', required=True, type=Path)
parser.add_argument('--new-source', required=True, type=Path)
args = parser.parse_args()

common = r'''
#ifndef GC_HOST_COMPAT
#define GC_HOST_COMPAT
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <limits.h>
#ifndef __always_inline
#define __always_inline inline __attribute__((always_inline))
#endif
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)
#define BUILD_BUG_ON(x) ((void)sizeof(char[1 - 2*!!(x)]))
#define EXPORT_SYMBOL(x)
#define MODULE_LICENSE(x)
#define MODULE_DESCRIPTION(x)
#define __ffs(x) __builtin_ctzl(x)
#define __fls(x) (63-__builtin_clzl(x))
#define BITS_PER_LONG 64
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define get_unaligned(p) ({ __typeof__(*(p)) v; memcpy((void*)&v,p,sizeof(v)); v; })
#define put_unaligned(v,p) do { __typeof__(*(p)) t=(v); memcpy(p,&t,sizeof(t)); } while(0)
static inline uint16_t get_unaligned_le16(const void *p) { uint16_t v; memcpy(&v,p,2); return v; }
static inline void put_unaligned_le16(uint16_t v, void *p) { memcpy(p,&v,2); }
#endif
'''

harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int old_LZ4_compress_default(const char*,char*,int,int,void*);
int new_LZ4_compress_default(const char*,char*,int,int,void*);
int old_LZ4_decompress_safe(const char*,char*,int,int);
int new_LZ4_decompress_safe(const char*,char*,int,int);
int new_LZ4_compress_fast(const char*,char*,int,int,int,void*);
int new_LZ4_compress_destSize(const char*,char*,int*,int,void*);
size_t old_worksize(void);
size_t new_worksize(void);
static uint32_t seed = 0x7b18c9a3;
static unsigned rnd(void) { seed^=seed<<13; seed^=seed>>17; seed^=seed<<5; return seed; }
static void fill(char *p, int n, int pattern) {
    for(int i=0;i<n;i++) p[i]=pattern==0?0:pattern==1?'x':pattern==2?(char)i:
        pattern==3?(char)rnd():(i%4096<2000?'a':(char)rnd());
}
int main(void) {
    int sizes[]={0,1,4,12,13,15,16,63,64,255,256,4095,4096,4097,16384,65536,131072};
    int (*compressors[])(const char*,char*,int,int,void*)={old_LZ4_compress_default,new_LZ4_compress_default};
    int (*decoders[])(const char*,char*,int,int)={old_LZ4_decompress_safe,new_LZ4_decompress_safe};
    size_t work_sizes[]={old_worksize(),new_worksize()};
    int rounds=0, bounds=0;
    for(unsigned s=0;s<sizeof(sizes)/sizeof(*sizes);s++) for(int pattern=0;pattern<5;pattern++) {
        int n=sizes[s], cap=n+n/255+16;
        char *src=malloc(n?n:1); fill(src,n,pattern);
        for(int c=0;c<2;c++) {
            void *work=malloc(work_sizes[c]); memset(work,0xa5,work_sizes[c]);
            char *encoded=malloc(cap);
            int size=compressors[c](src,encoded,n,cap,work); assert(size>0 && size<=cap);
            for(int d=0;d<2;d++) {
                char *decoded=malloc(n?n:1);
                assert(decoders[d](encoded,decoded,size,n)==n);
                assert(memcmp(src,decoded,n)==0); rounds++;
                if(n>0) { assert(decoders[d](encoded,decoded,size,n-1)<0); bounds++; }
                assert(decoders[d](encoded,decoded,size-1,n)<0); bounds++;
                free(decoded);
            }
            for(int outcap=0;outcap<16;outcap++) {
                char *small=malloc(outcap?outcap:1); small[0]=0x55;
                int ret=compressors[c](src,small,n,outcap,work);
                assert(ret>=0 && ret<=outcap);
                if(outcap==0) assert(small[0]==0x55);
                if(ret>0) {
                    char *decoded=malloc(n?n:1);
                    assert(new_LZ4_decompress_safe(small,decoded,ret,n)==n);
                    assert(memcmp(src,decoded,n)==0); free(decoded);
                }
                free(small); bounds++;
            }
            free(work); free(encoded);
        }
        void *work=malloc(new_worksize()); char *encoded=malloc(cap); char *decoded=malloc(n?n:1);
        for(int acceleration=1;acceleration<=17;acceleration*=4) {
            int ret=new_LZ4_compress_fast(src,encoded,n,cap,acceleration,work);
            assert(ret>0 && old_LZ4_decompress_safe(encoded,decoded,ret,n)==n);
            assert(memcmp(src,decoded,n)==0); rounds++;
        }
        int consumed=n, limit=cap>32?cap/2:cap;
        int ret=new_LZ4_compress_destSize(src,encoded,&consumed,limit,work);
        assert(ret>0 && ret<=limit && consumed>=0 && consumed<=n);
        assert(old_LZ4_decompress_safe(encoded,decoded,ret,n)==consumed);
        assert(memcmp(src,decoded,consumed)==0); rounds++;
        free(work); free(encoded); free(decoded); free(src);
    }
    for(int i=0;i<5000;i++) {
        int n=1+(rnd()%128), cap=rnd()%8193;
        char *bad=malloc(n), *out=malloc(cap?cap:1); fill(bad,n,3);
        for(int d=0;d<2;d++) assert(decoders[d](bad,out,n,cap)<=cap);
        free(bad); free(out); bounds+=2;
    }
    printf("ASan cross-codec and workspace tests passed: %d round trips, %d buffer/malformed checks; old workspace=%zu new workspace=%zu\n",
           rounds,bounds,old_worksize(),new_worksize());
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='golfcore-lz4-test-') as directory:
    temp = Path(directory)
    include = temp / 'compat'
    for name in ['linux/types.h', 'linux/string.h', 'linux/compiler.h',
                 'linux/kernel.h', 'linux/export.h', 'linux/module.h', 'linux/init.h', 'asm/unaligned.h']:
        path = include / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(common)
    objects = []
    flags = ['-std=gnu99', '-g', '-O1', '-fsanitize=address', '-fno-omit-frame-pointer',
             '-DCONFIG_64BIT', '-D__LITTLE_ENDIAN=1234', '-DLZ4_FREESTANDING=1',
             '-DLZ4_FAST_DEC_LOOP=1', '-I' + str(include)]
    for label, source, files in [
            ('old', args.old_source, ['lz4_compress.c', 'lz4_decompress.c']),
            ('new', args.new_source, ['lz4.c'])]:
        sources = [source / 'lib/lz4' / name for name in files]
        wrapper = temp / (label + '-worksize.c')
        wrapper.write_text('#include <linux/lz4.h>\nsize_t ' + label +
                           '_worksize(void){return LZ4_MEM_COMPRESS;}\n')
        sources.append(wrapper)
        built = []
        for index, path in enumerate(sources):
            obj = temp / f'{label}-{index}.o'
            subprocess.run(['cc', *flags, '-I' + str(source / 'include'),
                            '-c', str(path), '-o', str(obj)], check=True)
            built.append(obj)
        symbols = set()
        for obj in built:
            for line in subprocess.check_output(['nm', '-g', '--defined-only', str(obj)], text=True).splitlines():
                name = line.split()[-1]
                if name.startswith('LZ4'):
                    symbols.add(name)
        mapping = temp / (label + '-symbols')
        mapping.write_text(''.join(name + ' ' + label + '_' + name + '\n' for name in sorted(symbols)))
        for obj in built:
            subprocess.run(['objcopy', '--redefine-syms=' + str(mapping), str(obj)], check=True)
        objects.extend(built)
    (temp / 'test.c').write_text(harness)
    executable = temp / 'test'
    subprocess.run(['cc', *flags, str(temp / 'test.c'), *map(str, objects), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True,
                   env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1'})
