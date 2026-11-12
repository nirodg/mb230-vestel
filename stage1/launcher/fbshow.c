/*
 * OpenTV Stage-1 T0 proof: write a picture to the framebuffer directly.
 *
 * NO GPU, NO vendor libs — just libc + the standard Linux fbdev ioctls.
 * This is the cheapest "does our userland own the panel?" test: if a
 * colour test pattern (or a raw image) appears, we control display output
 * and the USB-run path works, independent of Mali/EGL.
 *
 *   fbshow                 -> draws a colour-bar/gradient test pattern
 *   fbshow img.raw         -> blits a raw BGRA/RGBA buffer (w*h*4) centred
 *
 * Build: $(CROSS_COMPILE)gcc -O2 fbshow.c -o fbshow   (no extra libs)
 */
#include <linux/fb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv){
    const char *dev = getenv("FRAMEBUFFER"); if(!dev) dev="/dev/fb0";
    int fd = open(dev, O_RDWR);
    if(fd<0){ perror("[opentv] open fb"); return 1; }

    struct fb_var_screeninfo v; struct fb_fix_screeninfo f;
    if(ioctl(fd,FBIOGET_VSCREENINFO,&v)||ioctl(fd,FBIOGET_FSCREENINFO,&f)){
        perror("[opentv] fb ioctl"); return 1; }
    int W=v.xres, H=v.yres, bpp=v.bits_per_pixel/8, stride=f.line_length;
    fprintf(stderr,"[opentv] fb %dx%d %dbpp stride=%d\n",W,H,v.bits_per_pixel,stride);

    unsigned char *fb = mmap(0, f.smem_len, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
    if(fb==MAP_FAILED){ perror("[opentv] mmap"); return 1; }

    if(argc>1){                       /* blit a raw w*h*4 image, centred */
        FILE *fp=fopen(argv[1],"rb");
        if(!fp){ perror("[opentv] open img"); return 1; }
        fseek(fp,0,SEEK_END); long n=ftell(fp); fseek(fp,0,SEEK_SET);
        int iw=W, ih=(n/4)/W;         /* assume full-width raw */
        unsigned char *buf=malloc(n); if(fread(buf,1,n,fp)!=(size_t)n){} fclose(fp);
        for(int y=0;y<ih&&y<H;y++)
            memcpy(fb+(long)y*stride, buf+(long)y*iw*4, (iw<W?iw:W)*bpp);
        (void)ih;
    } else {                          /* colour gradient test pattern */
        for(int y=0;y<H;y++) for(int x=0;x<W;x++){
            unsigned char *p=fb+(long)y*stride+(long)x*bpp;
            if(bpp>=3){ p[0]=x*255/W; p[1]=y*255/H; p[2]=(x^y)&0xff; if(bpp==4)p[3]=0xff; }
        }
    }
    fprintf(stderr,"[opentv] framebuffer written — hold\n");
    for(;;) pause();                  /* keep the image up */
    return 0;
}
