#pragma once
// Every OpenGL function past 1.1 the client calls, loaded through SDL once a
// context exists (load_gl). Windows' opengl32 exports only 1.1, so nothing here
// may be called by its prototype: each name is a macro for its pointer, and no
// file defines GL_GLEXT_PROTOTYPES, so a function missing from this list does
// not compile on Linux either.
#include "platform/gl.h"
#include <GL/glcorearb.h>
#include <SDL3/SDL.h>
#include <stdexcept>
#include <string>
#define N3E_GL_FUNCTIONS(X) \
  X(ActiveTexture, PFNGLACTIVETEXTUREPROC) \
  X(AttachShader, PFNGLATTACHSHADERPROC) \
  X(BindBuffer, PFNGLBINDBUFFERPROC) \
  X(BindFramebuffer, PFNGLBINDFRAMEBUFFERPROC) \
  X(BindRenderbuffer, PFNGLBINDRENDERBUFFERPROC) \
  X(BindSampler, PFNGLBINDSAMPLERPROC) \
  X(BindVertexArray, PFNGLBINDVERTEXARRAYPROC) \
  X(BlendFuncSeparate, PFNGLBLENDFUNCSEPARATEPROC) \
  X(BufferData, PFNGLBUFFERDATAPROC) \
  X(BufferSubData, PFNGLBUFFERSUBDATAPROC) \
  X(CheckFramebufferStatus, PFNGLCHECKFRAMEBUFFERSTATUSPROC) \
  X(ClientWaitSync, PFNGLCLIENTWAITSYNCPROC) \
  X(CompileShader, PFNGLCOMPILESHADERPROC) \
  X(CreateProgram, PFNGLCREATEPROGRAMPROC) \
  X(CreateShader, PFNGLCREATESHADERPROC) \
  X(DeleteBuffers, PFNGLDELETEBUFFERSPROC) \
  X(DeleteFramebuffers, PFNGLDELETEFRAMEBUFFERSPROC) \
  X(DeleteProgram, PFNGLDELETEPROGRAMPROC) \
  X(DeleteRenderbuffers, PFNGLDELETERENDERBUFFERSPROC) \
  X(DeleteSamplers, PFNGLDELETESAMPLERSPROC) \
  X(DeleteShader, PFNGLDELETESHADERPROC) \
  X(DeleteSync, PFNGLDELETESYNCPROC) \
  X(DeleteVertexArrays, PFNGLDELETEVERTEXARRAYSPROC) \
  X(DisableVertexAttribArray, PFNGLDISABLEVERTEXATTRIBARRAYPROC) \
  X(EnableVertexAttribArray, PFNGLENABLEVERTEXATTRIBARRAYPROC) \
  X(FenceSync, PFNGLFENCESYNCPROC) \
  X(FramebufferRenderbuffer, PFNGLFRAMEBUFFERRENDERBUFFERPROC) \
  X(FramebufferTexture2D, PFNGLFRAMEBUFFERTEXTURE2DPROC) \
  X(GenBuffers, PFNGLGENBUFFERSPROC) \
  X(GenerateMipmap, PFNGLGENERATEMIPMAPPROC) \
  X(GenFramebuffers, PFNGLGENFRAMEBUFFERSPROC) \
  X(GenRenderbuffers, PFNGLGENRENDERBUFFERSPROC) \
  X(GenSamplers, PFNGLGENSAMPLERSPROC) \
  X(GenVertexArrays, PFNGLGENVERTEXARRAYSPROC) \
  X(GetProgramInfoLog, PFNGLGETPROGRAMINFOLOGPROC) \
  X(GetProgramiv, PFNGLGETPROGRAMIVPROC) \
  X(GetShaderInfoLog, PFNGLGETSHADERINFOLOGPROC) \
  X(GetShaderiv, PFNGLGETSHADERIVPROC) \
  X(GetUniformLocation, PFNGLGETUNIFORMLOCATIONPROC) \
  X(LinkProgram, PFNGLLINKPROGRAMPROC) \
  X(MapBufferRange, PFNGLMAPBUFFERRANGEPROC) \
  X(RenderbufferStorage, PFNGLRENDERBUFFERSTORAGEPROC) \
  X(SamplerParameteri, PFNGLSAMPLERPARAMETERIPROC) \
  X(ShaderSource, PFNGLSHADERSOURCEPROC) \
  X(TexImage3D, PFNGLTEXIMAGE3DPROC) \
  X(TexSubImage3D, PFNGLTEXSUBIMAGE3DPROC) \
  X(Uniform1f, PFNGLUNIFORM1FPROC) \
  X(Uniform1fv, PFNGLUNIFORM1FVPROC) \
  X(Uniform1i, PFNGLUNIFORM1IPROC) \
  X(Uniform1iv, PFNGLUNIFORM1IVPROC) \
  X(Uniform2f, PFNGLUNIFORM2FPROC) \
  X(Uniform3f, PFNGLUNIFORM3FPROC) \
  X(Uniform3fv, PFNGLUNIFORM3FVPROC) \
  X(Uniform4f, PFNGLUNIFORM4FPROC) \
  X(Uniform4fv, PFNGLUNIFORM4FVPROC) \
  X(UniformMatrix4fv, PFNGLUNIFORMMATRIX4FVPROC) \
  X(UnmapBuffer, PFNGLUNMAPBUFFERPROC) \
  X(UseProgram, PFNGLUSEPROGRAMPROC) \
  X(VertexAttribPointer, PFNGLVERTEXATTRIBPOINTERPROC)
#define N3E_GL_POINTER(name, type) inline type p##name;
N3E_GL_FUNCTIONS(N3E_GL_POINTER)
#undef N3E_GL_POINTER
#define glActiveTexture pActiveTexture
#define glAttachShader pAttachShader
#define glBindBuffer pBindBuffer
#define glBindFramebuffer pBindFramebuffer
#define glBindRenderbuffer pBindRenderbuffer
#define glBindSampler pBindSampler
#define glBindVertexArray pBindVertexArray
#define glBlendFuncSeparate pBlendFuncSeparate
#define glBufferData pBufferData
#define glBufferSubData pBufferSubData
#define glCheckFramebufferStatus pCheckFramebufferStatus
#define glClientWaitSync pClientWaitSync
#define glCompileShader pCompileShader
#define glCreateProgram pCreateProgram
#define glCreateShader pCreateShader
#define glDeleteBuffers pDeleteBuffers
#define glDeleteFramebuffers pDeleteFramebuffers
#define glDeleteProgram pDeleteProgram
#define glDeleteRenderbuffers pDeleteRenderbuffers
#define glDeleteSamplers pDeleteSamplers
#define glDeleteShader pDeleteShader
#define glDeleteSync pDeleteSync
#define glDeleteVertexArrays pDeleteVertexArrays
#define glDisableVertexAttribArray pDisableVertexAttribArray
#define glEnableVertexAttribArray pEnableVertexAttribArray
#define glFenceSync pFenceSync
#define glFramebufferRenderbuffer pFramebufferRenderbuffer
#define glFramebufferTexture2D pFramebufferTexture2D
#define glGenBuffers pGenBuffers
#define glGenerateMipmap pGenerateMipmap
#define glGenFramebuffers pGenFramebuffers
#define glGenRenderbuffers pGenRenderbuffers
#define glGenSamplers pGenSamplers
#define glGenVertexArrays pGenVertexArrays
#define glGetProgramInfoLog pGetProgramInfoLog
#define glGetProgramiv pGetProgramiv
#define glGetShaderInfoLog pGetShaderInfoLog
#define glGetShaderiv pGetShaderiv
#define glGetUniformLocation pGetUniformLocation
#define glLinkProgram pLinkProgram
#define glMapBufferRange pMapBufferRange
#define glRenderbufferStorage pRenderbufferStorage
#define glSamplerParameteri pSamplerParameteri
#define glShaderSource pShaderSource
#define glTexImage3D pTexImage3D
#define glTexSubImage3D pTexSubImage3D
#define glUniform1f pUniform1f
#define glUniform1fv pUniform1fv
#define glUniform1i pUniform1i
#define glUniform1iv pUniform1iv
#define glUniform2f pUniform2f
#define glUniform3f pUniform3f
#define glUniform3fv pUniform3fv
#define glUniform4f pUniform4f
#define glUniform4fv pUniform4fv
#define glUniformMatrix4fv pUniformMatrix4fv
#define glUnmapBuffer pUnmapBuffer
#define glUseProgram pUseProgram
#define glVertexAttribPointer pVertexAttribPointer
inline void load_gl() {
#define N3E_GL_LOAD(name, type)                                                       \
  p##name = reinterpret_cast<type>(SDL_GL_GetProcAddress("gl" #name));                 \
  if (!p##name)                                                                        \
    throw std::runtime_error(std::string("missing gl") + #name);
  N3E_GL_FUNCTIONS(N3E_GL_LOAD)
#undef N3E_GL_LOAD
}
