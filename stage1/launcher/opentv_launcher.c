/*
 * OpenTV Stage-1 PoC launcher.
 *
 * Minimal EGL + GLES2 program that opens a fullscreen framebuffer surface
 * through the TV's STOCK libmali.so (fbdev winsys) and draws a moving
 * colour + a triangle. If this renders on the panel, it proves our own
 * userland can reuse the proprietary GPU blob without aurora.elf or
 * DirectFB — the whole premise of OpenTV Stage 1.
 *
 * Link:  -lEGL -lGLESv2   (both resolve to the stock libmali.so at runtime)
 * Native window: Mali fbdev expects a `struct fbdev_window {u16 w; u16 h;}`
 *                and EGL_DEFAULT_DISPLAY (it opens $FRAMEBUFFER=/dev/fb0).
 *
 * No writes to flash, no device-specific syscalls — pure EGL/GLES.
 */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <math.h>

/* Mali fbdev native window (ARM DDK contract — verify at bring-up). */
typedef struct fbdev_window { unsigned short width; unsigned short height; } fbdev_window;

static int W = 1920, H = 1080;

static const char *VS =
    "attribute vec4 p;void main(){gl_Position=p;}";
static const char *FS =
    "precision mediump float;uniform vec3 c;void main(){gl_FragColor=vec4(c,1.0);}";

static GLuint shader(GLenum t, const char *s){
    GLuint h=glCreateShader(t); glShaderSource(h,1,&s,0); glCompileShader(h);
    GLint ok=0; glGetShaderiv(h,GL_COMPILE_STATUS,&ok);
    if(!ok){char log[512];glGetShaderInfoLog(h,512,0,log);fprintf(stderr,"[opentv] shader: %s\n",log);}
    return h;
}

int main(void){
    if(getenv("PANEL_WIDTH"))  W=atoi(getenv("PANEL_WIDTH"));
    if(getenv("PANEL_HEIGHT")) H=atoi(getenv("PANEL_HEIGHT"));
    fprintf(stderr,"[opentv] launcher start %dx%d\n",W,H);

    EGLDisplay d=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if(d==EGL_NO_DISPLAY){fprintf(stderr,"[opentv] no EGL display\n");return 1;}
    EGLint maj,min; if(!eglInitialize(d,&maj,&min)){fprintf(stderr,"[opentv] eglInitialize failed\n");return 1;}
    fprintf(stderr,"[opentv] EGL %d.%d  vendor=%s\n",maj,min,eglQueryString(d,EGL_VENDOR));

    EGLint cfg_attr[]={EGL_SURFACE_TYPE,EGL_WINDOW_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,
        EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_NONE};
    EGLConfig cfg; EGLint n=0;
    if(!eglChooseConfig(d,cfg_attr,&cfg,1,&n)||n<1){fprintf(stderr,"[opentv] no EGL config\n");return 1;}

    static fbdev_window win; win.width=W; win.height=H;
    EGLSurface surf=eglCreateWindowSurface(d,cfg,(EGLNativeWindowType)&win,0);
    if(surf==EGL_NO_SURFACE){fprintf(stderr,"[opentv] no surface (err 0x%x)\n",eglGetError());return 1;}

    EGLint ctx_attr[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};
    EGLContext ctx=eglCreateContext(d,cfg,EGL_NO_CONTEXT,ctx_attr);
    eglMakeCurrent(d,surf,surf,ctx);
    fprintf(stderr,"[opentv] GL_RENDERER=%s\n",glGetString(GL_RENDERER));

    GLuint prog=glCreateProgram();
    glAttachShader(prog,shader(GL_VERTEX_SHADER,VS));
    glAttachShader(prog,shader(GL_FRAGMENT_SHADER,FS));
    glBindAttribLocation(prog,0,"p"); glLinkProgram(prog); glUseProgram(prog);
    GLint uc=glGetUniformLocation(prog,"c");
    GLfloat tri[]={0,0.6f, -0.6f,-0.6f, 0.6f,-0.6f};
    glViewport(0,0,W,H);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,tri);

    for(int f=0;;f++){
        float t=f*0.02f;
        glClearColor(0.1f,0.1f+0.1f*sinf(t),0.2f,1); glClear(GL_COLOR_BUFFER_BIT);
        glUniform3f(uc,0.9f,0.6f,0.2f);
        glDrawArrays(GL_TRIANGLES,0,3);
        eglSwapBuffers(d,surf);
        usleep(16000); /* ~60 fps */
    }
    return 0;
}
