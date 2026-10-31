#pragma once
#include <stdexcept>
#include <GL/glcorearb.h>
#include <SDL3/SDL.h>
inline PFNGLCREATESHADERPROC pCreateShader;
#define glCreateShader pCreateShader
inline PFNGLSHADERSOURCEPROC pShaderSource;
#define glShaderSource pShaderSource
inline PFNGLCOMPILESHADERPROC pCompileShader;
#define glCompileShader pCompileShader
inline PFNGLGETSHADERIVPROC pGetShaderiv;
#define glGetShaderiv pGetShaderiv
inline PFNGLGETSHADERINFOLOGPROC pGetShaderInfoLog;
#define glGetShaderInfoLog pGetShaderInfoLog
inline PFNGLCREATEPROGRAMPROC pCreateProgram;
#define glCreateProgram pCreateProgram
inline PFNGLATTACHSHADERPROC pAttachShader;
#define glAttachShader pAttachShader
inline PFNGLLINKPROGRAMPROC pLinkProgram;
#define glLinkProgram pLinkProgram
inline PFNGLGETPROGRAMIVPROC pGetProgramiv;
#define glGetProgramiv pGetProgramiv
inline PFNGLGETPROGRAMINFOLOGPROC pGetProgramInfoLog;
#define glGetProgramInfoLog pGetProgramInfoLog
inline PFNGLUSEPROGRAMPROC pUseProgram;
#define glUseProgram pUseProgram
inline PFNGLGENVERTEXARRAYSPROC pGenVertexArrays;
#define glGenVertexArrays pGenVertexArrays
inline PFNGLBINDVERTEXARRAYPROC pBindVertexArray;
#define glBindVertexArray pBindVertexArray
inline PFNGLGENBUFFERSPROC pGenBuffers;
#define glGenBuffers pGenBuffers
inline PFNGLBINDBUFFERPROC pBindBuffer;
#define glBindBuffer pBindBuffer
inline PFNGLBUFFERDATAPROC pBufferData;
#define glBufferData pBufferData
inline PFNGLENABLEVERTEXATTRIBARRAYPROC pEnableVertexAttribArray;
#define glEnableVertexAttribArray pEnableVertexAttribArray
inline PFNGLVERTEXATTRIBPOINTERPROC pVertexAttribPointer;
#define glVertexAttribPointer pVertexAttribPointer
inline PFNGLGETUNIFORMLOCATIONPROC pGetUniformLocation;
#define glGetUniformLocation pGetUniformLocation
inline PFNGLUNIFORM1FPROC pUniform1f;
#define glUniform1f pUniform1f
inline PFNGLUNIFORM2FPROC pUniform2f;
#define glUniform2f pUniform2f
inline PFNGLDELETEBUFFERSPROC pDeleteBuffers;
#define glDeleteBuffers pDeleteBuffers
inline PFNGLDELETEVERTEXARRAYSPROC pDeleteVertexArrays;
#define glDeleteVertexArrays pDeleteVertexArrays
inline PFNGLDELETEPROGRAMPROC pDeleteProgram;
#define glDeleteProgram pDeleteProgram
inline PFNGLDELETESHADERPROC pDeleteShader;
#define glDeleteShader pDeleteShader
inline PFNGLUNIFORM3FPROC pUniform3f;
#define glUniform3f pUniform3f
inline void load_gl() {
  pUniform3f = reinterpret_cast<PFNGLUNIFORM3FPROC>(SDL_GL_GetProcAddress("glUniform3f"));
  if (!pUniform3f) throw std::runtime_error("missing glUniform3f");
  pCreateShader = reinterpret_cast<PFNGLCREATESHADERPROC>(
      SDL_GL_GetProcAddress("glCreateShader"));
  if (!pCreateShader)
    throw std::runtime_error("missing glCreateShader");
  pShaderSource = reinterpret_cast<PFNGLSHADERSOURCEPROC>(
      SDL_GL_GetProcAddress("glShaderSource"));
  if (!pShaderSource)
    throw std::runtime_error("missing glShaderSource");
  pCompileShader = reinterpret_cast<PFNGLCOMPILESHADERPROC>(
      SDL_GL_GetProcAddress("glCompileShader"));
  if (!pCompileShader)
    throw std::runtime_error("missing glCompileShader");
  pGetShaderiv = reinterpret_cast<PFNGLGETSHADERIVPROC>(
      SDL_GL_GetProcAddress("glGetShaderiv"));
  if (!pGetShaderiv)
    throw std::runtime_error("missing glGetShaderiv");
  pGetShaderInfoLog = reinterpret_cast<PFNGLGETSHADERINFOLOGPROC>(
      SDL_GL_GetProcAddress("glGetShaderInfoLog"));
  if (!pGetShaderInfoLog)
    throw std::runtime_error("missing glGetShaderInfoLog");
  pCreateProgram = reinterpret_cast<PFNGLCREATEPROGRAMPROC>(
      SDL_GL_GetProcAddress("glCreateProgram"));
  if (!pCreateProgram)
    throw std::runtime_error("missing glCreateProgram");
  pAttachShader = reinterpret_cast<PFNGLATTACHSHADERPROC>(
      SDL_GL_GetProcAddress("glAttachShader"));
  if (!pAttachShader)
    throw std::runtime_error("missing glAttachShader");
  pLinkProgram = reinterpret_cast<PFNGLLINKPROGRAMPROC>(
      SDL_GL_GetProcAddress("glLinkProgram"));
  if (!pLinkProgram)
    throw std::runtime_error("missing glLinkProgram");
  pGetProgramiv = reinterpret_cast<PFNGLGETPROGRAMIVPROC>(
      SDL_GL_GetProcAddress("glGetProgramiv"));
  if (!pGetProgramiv)
    throw std::runtime_error("missing glGetProgramiv");
  pGetProgramInfoLog = reinterpret_cast<PFNGLGETPROGRAMINFOLOGPROC>(
      SDL_GL_GetProcAddress("glGetProgramInfoLog"));
  if (!pGetProgramInfoLog)
    throw std::runtime_error("missing glGetProgramInfoLog");
  pUseProgram = reinterpret_cast<PFNGLUSEPROGRAMPROC>(
      SDL_GL_GetProcAddress("glUseProgram"));
  if (!pUseProgram)
    throw std::runtime_error("missing glUseProgram");
  pGenVertexArrays = reinterpret_cast<PFNGLGENVERTEXARRAYSPROC>(
      SDL_GL_GetProcAddress("glGenVertexArrays"));
  if (!pGenVertexArrays)
    throw std::runtime_error("missing glGenVertexArrays");
  pBindVertexArray = reinterpret_cast<PFNGLBINDVERTEXARRAYPROC>(
      SDL_GL_GetProcAddress("glBindVertexArray"));
  if (!pBindVertexArray)
    throw std::runtime_error("missing glBindVertexArray");
  pGenBuffers = reinterpret_cast<PFNGLGENBUFFERSPROC>(
      SDL_GL_GetProcAddress("glGenBuffers"));
  if (!pGenBuffers)
    throw std::runtime_error("missing glGenBuffers");
  pBindBuffer = reinterpret_cast<PFNGLBINDBUFFERPROC>(
      SDL_GL_GetProcAddress("glBindBuffer"));
  if (!pBindBuffer)
    throw std::runtime_error("missing glBindBuffer");
  pBufferData = reinterpret_cast<PFNGLBUFFERDATAPROC>(
      SDL_GL_GetProcAddress("glBufferData"));
  if (!pBufferData)
    throw std::runtime_error("missing glBufferData");
  pEnableVertexAttribArray = reinterpret_cast<PFNGLENABLEVERTEXATTRIBARRAYPROC>(
      SDL_GL_GetProcAddress("glEnableVertexAttribArray"));
  if (!pEnableVertexAttribArray)
    throw std::runtime_error("missing glEnableVertexAttribArray");
  pVertexAttribPointer = reinterpret_cast<PFNGLVERTEXATTRIBPOINTERPROC>(
      SDL_GL_GetProcAddress("glVertexAttribPointer"));
  if (!pVertexAttribPointer)
    throw std::runtime_error("missing glVertexAttribPointer");
  pGetUniformLocation = reinterpret_cast<PFNGLGETUNIFORMLOCATIONPROC>(
      SDL_GL_GetProcAddress("glGetUniformLocation"));
  if (!pGetUniformLocation)
    throw std::runtime_error("missing glGetUniformLocation");
  pUniform1f = reinterpret_cast<PFNGLUNIFORM1FPROC>(
      SDL_GL_GetProcAddress("glUniform1f"));
  if (!pUniform1f)
    throw std::runtime_error("missing glUniform1f");
  pUniform2f = reinterpret_cast<PFNGLUNIFORM2FPROC>(
      SDL_GL_GetProcAddress("glUniform2f"));
  if (!pUniform2f)
    throw std::runtime_error("missing glUniform2f");
  pDeleteBuffers = reinterpret_cast<PFNGLDELETEBUFFERSPROC>(
      SDL_GL_GetProcAddress("glDeleteBuffers"));
  if (!pDeleteBuffers)
    throw std::runtime_error("missing glDeleteBuffers");
  pDeleteVertexArrays = reinterpret_cast<PFNGLDELETEVERTEXARRAYSPROC>(
      SDL_GL_GetProcAddress("glDeleteVertexArrays"));
  if (!pDeleteVertexArrays)
    throw std::runtime_error("missing glDeleteVertexArrays");
  pDeleteProgram = reinterpret_cast<PFNGLDELETEPROGRAMPROC>(
      SDL_GL_GetProcAddress("glDeleteProgram"));
  if (!pDeleteProgram)
    throw std::runtime_error("missing glDeleteProgram");
  pDeleteShader = reinterpret_cast<PFNGLDELETESHADERPROC>(
      SDL_GL_GetProcAddress("glDeleteShader"));
  if (!pDeleteShader)
    throw std::runtime_error("missing glDeleteShader");
}
