#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

// Screen post-process: bloom and tone map (PQ-316, D-185; package
// postprocess.bin, N3PF). The chain is the 2233 client's CN3PostProcess, a
// 2233/2145 addition (the pinned 1298 client has none and stays the source of
// truth). 2233 image (static analysis of the unpacked 2233 client, PQ-314;
// binary for that image only), with the pass bodies
// read from the 2145 SHC/pp.fx bytecode (local-asset, PQ-312); n3e's GLSL below
// is written from that reading, no shader bytes are used:
//
// - The main render (00537030) points the scene at an A8R8G8B8 target
//   (00474b30, created by 00474660) and, after the world, runs 00476b40 before
//   the HUD; 00476b40 sets technique HDR and runs, in order, 00475000 (P0),
//   00475350 (P1, then P2 five times, then the read-back), 00475860 (P3),
//   00475ca0 (P4, P5) and 00476690 (P6, into the back buffer). Every target is
//   8-bit RGBA, sampled with linear filtering and clamped addressing.
// - P0, half size: four taps at +-0.5 scene texel (00474ef0); keeps the
//   average when its luminance (0.299, 0.587, 0.114) is at least the
//   threshold, else (0, 0, 0, 1).
// - P1, half size: four taps at +-0.5 scene texel (004751a0); x the geometric
//   mean of luminance + 1e-5, y the maximum, z the minimum. P2: 3x3 taps at
//   -1/0/+1 source texel (00475290); x the mean, y the maximum, z the minimum;
//   into 81, 27, 9, 3 and 1 texel squares (00474660).
// - Read-back (00475350): GetRenderTargetData of the 1x1 target and a lock;
//   R/255, G/255, B/255 are the measured average, maximum and minimum
//   (00b8fac8, the double 255.0).
// - P3, an eighth of the size: 16 taps at -1.5..1.5 half texel (00475760),
//   the mean. P4 then P5: nine taps at -4..4 texels, across then down
//   (004759f0), weighted exp(-i^2 / (2 v)) normalised to 1 and then times the
//   bloom scale (+0x8c) in each pass; v is +0x80, 1.0 from the constructor
//   (00477bd0).
// - P6 (00476690): the adapted values move toward the measured ones by at most
//   0.3 x the frame time per frame (00b905a8, the double 0.3), else snap; they
//   snap on the first frame after the targets are built (+0x73, 00477bd0 and
//   004744f0). Then 00474b50 sets exposure, lift, 1/size, bloom scale,
//   saturation and the three adapted values, and P6 draws c = scene + bloom,
//   Lm = L(c) / average x exposure, k = Lm (1 + Lm / W^2) / (1 + Lm) + lift with
//   W = maximum x (1 + bloom scale), c' = c k, and saturation around L(c').
//
// n3e differences, each recorded in D-185: the read-back is asynchronous
// (a ring of three pixel-pack buffers with fences, never waited on; only the
// first frame after the targets are built reads synchronously, so the snap
// matches 2233's), so the measured values are one to three frames old; and the
// average and maximum are floored at 1/255 before the division, where 2233
// divides by zero on a read-back of 0 (the correction record in
// docs/ko/BINARY-POLICY.md).
namespace n3e::post {
constexpr std::array<float, 3> LUMINANCE{.299f, .587f, .114f};
// The smallest non-zero 8-bit read-back (D-185 correction).
constexpr float FLOOR = 1.f / 255;
constexpr int TAPS = 9;
constexpr std::array<int, 5> CHAIN{81, 27, 9, 3, 1};

// 004759f0's weights for one blur pass.
inline std::array<float, TAPS> blur_weights(float variance, float bloom) {
  std::array<float, TAPS> w{};
  float sum = 0;
  for (int i = 0; i < TAPS; ++i) {
    float x = float(i - TAPS / 2);
    w[i] = std::exp(x * x * -.5f / variance);
    sum += w[i];
  }
  for (auto &x : w) x = x / sum * bloom;
  return w;
}
// 00476690: one adapted value toward the measured one by at most `step`.
inline float adapt(float adapted, float measured, float step) {
  if (step <= std::abs(adapted - measured)) return adapted + (measured <= adapted ? -step : step);
  return measured;
}
// The D-185 correction: the adapted average and maximum the composite divides
// by, floored at the smallest non-zero read-back. Both the drawn composite
// (PostProcessView::finish) and its CPU reference (tone_map) take them here.
inline std::array<float, 2> floored(float average, float maximum) {
  return {std::max(average, FLOOR), std::max(maximum, FLOOR)};
}
// P6 on one pixel, the CPU reference of the composite shader below.
inline std::array<float, 3> tone_map(std::array<float, 3> c, float average, float maximum, const PostProcess &s) {
  auto f = floored(average, maximum);
  average = f[0];
  maximum = f[1];
  float white = maximum * s.bloom + maximum, c1 = 1 / (white * white);
  float l = c[0] * LUMINANCE[0] + c[1] * LUMINANCE[1] + c[2] * LUMINANCE[2];
  float lm = l * (1 / average) * s.exposure;
  float k = lm * (lm * c1 + 1) * (1 / (lm + 1)) + s.lift;
  std::array<float, 3> t{c[0] * k, c[1] * k, c[2] * k};
  float g = t[0] * LUMINANCE[0] + t[1] * LUMINANCE[1] + t[2] * LUMINANCE[2];
  for (auto &x : t) x = s.saturation * (x - g) + g;
  return t;
}
}  // namespace n3e::post

#ifndef N3E_POSTPROCESS_NO_GL
#include "platform/gl.h"
#include <stdexcept>

GLuint shader(GLenum type, const char *source);

struct PostProcessView {
  struct Target {
    GLuint texture = 0, fbo = 0;
    int width = 0, height = 0;
  };
  enum Stage { scene, bright, luminance, down, blur, bloom, stages };
  n3e::PostProcess settings;
  std::array<Target, stages> targets;
  std::array<Target, n3e::post::CHAIN.size()> chain;
  GLuint depth = 0, vao = 0;
  std::array<GLuint, 7> programs{};
  std::array<GLuint, 3> pack{};
  std::array<GLsync, 3> fences{};
  int width = 0, height = 0;
  bool snap = true, ready = false;
  // Harness only: read this frame's measurement synchronously (a stage dump
  // compares the read-back with the frame's own scene).
  bool sync_once = false;
  // Measured and adapted (average, maximum, minimum); `used` is what the last
  // composite drew with, after the floor.
  std::array<float, 3> measured{}, adapted{};
  float used_average = 0, used_maximum = 0;
  // How the last frame's measurement arrived: "sync" (the first frame after
  // the targets were built), "async" (a completed pixel-pack read), "pending"
  // (none completed this frame; the last value stands).
  const char *read = "none";

  static constexpr const char *VS = R"(#version 330 core
out vec2 uv;
void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));uv=p;gl_Position=vec4(p*2.-1.,0.,1.);})";
  // The fragment programs, in pass order: P0, P1, P2, P3, P4 (across), P5
  // (down), P6.
  static constexpr const char *HEAD = R"(#version 330 core
in vec2 uv;out vec4 color;uniform sampler2D s0;uniform sampler2D s1;uniform vec2 texel;
const vec3 LUM=vec3(.299,.587,.114);
)";
  static constexpr std::array<const char *, 7> FS{
      R"(uniform float threshold;
void main(){vec4 c=(texture(s0,uv+vec2(-.5,-.5)*texel)+texture(s0,uv+vec2(.5,-.5)*texel)
 +texture(s0,uv+vec2(-.5,.5)*texel)+texture(s0,uv+vec2(.5,.5)*texel))*.25;
 color=dot(c.rgb,LUM)-threshold>=0.?c:vec4(0,0,0,1);})",
      R"(void main(){vec2 o[4]=vec2[4](vec2(-.5,.5),vec2(.5,.5),vec2(-.5,-.5),vec2(.5,-.5));
 float s=0.,hi=-1e20,lo=10.;
 for(int i=0;i<4;++i){float l=dot(texture(s0,uv+o[i]*texel).rgb,LUM);s+=log2(l+1e-5)*.173287;hi=max(hi,l);lo=min(lo,l);}
 color=vec4(exp2(s*1.4427),hi,lo,1);})",
      R"(void main(){float s=0.,hi=-1e20,lo=10.;
 for(int y=-1;y<=1;++y)for(int x=-1;x<=1;++x){vec4 t=texture(s0,uv+vec2(x,y)*texel);s+=t.x;hi=max(hi,t.y);lo=min(lo,t.z);}
 color=vec4(s*.111111,hi,lo,1);})",
      R"(void main(){vec4 s=vec4(0);
 for(int y=0;y<4;++y)for(int x=0;x<4;++x)s+=texture(s0,uv+(vec2(x,y)-1.5)*texel);
 color=s*.0625;})",
      R"(uniform float weights[9];
void main(){vec3 s=vec3(0);for(int i=0;i<9;++i)s+=texture(s0,uv+vec2(float(i-4)*texel.x,0)).rgb*weights[i];color=vec4(s,1);})",
      R"(uniform float weights[9];
void main(){vec3 s=vec3(0);for(int i=0;i<9;++i)s+=texture(s0,uv+vec2(0,float(i-4)*texel.y)).rgb*weights[i];color=vec4(s,1);})",
      R"(uniform float average,maximum,bloom,exposure,lift,saturation;
void main(){vec3 c=texture(s0,uv).rgb+texture(s1,uv).rgb;
 float l=dot(c,LUM)*(1./average);float lm=l*exposure;float w=maximum*bloom+maximum;
 float k=lm*(lm*(1./(w*w))+1.)*(1./(exposure*l+1.))+lift;
 vec3 t=c*k;float g=dot(t,LUM);color=vec4(saturation*(t-g)+g,1);})"};

  // Compiles the passes; false (with `error`) if the driver refuses one.
  bool create(const n3e::PostProcess &s, std::string &error) {
    settings = s;
    try {
      for (size_t i = 0; i < FS.size(); ++i) {
        std::string source = std::string(HEAD) + FS[i];
        GLuint v = shader(GL_VERTEX_SHADER, VS), f = shader(GL_FRAGMENT_SHADER, source.c_str());
        programs[i] = glCreateProgram();
        glAttachShader(programs[i], v);
        glAttachShader(programs[i], f);
        glLinkProgram(programs[i]);
        GLint ok = 0;
        glGetProgramiv(programs[i], GL_LINK_STATUS, &ok);
        glDeleteShader(v);
        glDeleteShader(f);
        if (!ok) throw std::runtime_error("post-process link");
        glUseProgram(programs[i]);
        glUniform1i(glGetUniformLocation(programs[i], "s0"), 0);
        glUniform1i(glGetUniformLocation(programs[i], "s1"), 1);
      }
      glUseProgram(0);
    } catch (const std::exception &e) {
      error = e.what();
      destroy();
      return false;
    }
    glGenVertexArrays(1, &vao);
    glGenBuffers(GLsizei(pack.size()), pack.data());
    for (auto b : pack) {
      glBindBuffer(GL_PIXEL_PACK_BUFFER, b);
      glBufferData(GL_PIXEL_PACK_BUFFER, 4, nullptr, GL_STREAM_READ);
    }
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    ready = true;
    return true;
  }
  void release_targets() {
    auto drop = [](Target &t) {
      if (t.fbo) glDeleteFramebuffers(1, &t.fbo);
      if (t.texture) glDeleteTextures(1, &t.texture);
      t = {};
    };
    for (auto &t : targets) drop(t);
    for (auto &t : chain) drop(t);
    if (depth) glDeleteRenderbuffers(1, &depth);
    depth = 0;
    for (auto &f : fences)
      if (f) glDeleteSync(f), f = nullptr;
    width = height = 0;
    snap = true;  // 004744f0 sets +0x73: the next composite snaps again
  }
  void destroy() {
    release_targets();
    for (auto &p : programs)
      if (p) glDeleteProgram(p), p = 0;
    if (vao) glDeleteVertexArrays(1, &vao), vao = 0;
    if (pack[0]) glDeleteBuffers(GLsizei(pack.size()), pack.data()), pack = {};
    ready = false;
  }
  // The targets for a w x h scene (00474660's sizes); false if the window is
  // too small for the chain or the driver refuses a target.
  bool resize(int w, int h) {
    if (w == width && h == height) return true;
    release_targets();
    if (w < 8 || h < 8) return false;
    GLint old_texture = 0, old_fbo = 0, old_rb = 0;
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &old_texture);
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &old_fbo);
    glGetIntegerv(GL_RENDERBUFFER_BINDING, &old_rb);
    bool ok = true;
    auto make = [&](Target &t, int tw, int th) {
      t.width = tw;
      t.height = th;
      glGenTextures(1, &t.texture);
      glBindTexture(GL_TEXTURE_2D, t.texture);
      glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, tw, th, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
      glGenFramebuffers(1, &t.fbo);
      glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
      glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t.texture, 0);
      if (&t == &targets[scene]) {
        glGenRenderbuffers(1, &depth);
        glBindRenderbuffer(GL_RENDERBUFFER, depth);
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, tw, th);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth);
      }
      ok = ok && glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
    };
    make(targets[scene], w, h);
    make(targets[bright], w / 2, h / 2);
    make(targets[luminance], w / 2, h / 2);
    for (size_t i = 0; i < chain.size(); ++i) make(chain[i], n3e::post::CHAIN[i], n3e::post::CHAIN[i]);
    for (auto stage : {down, blur, bloom}) make(targets[stage], w / 8, h / 8);
    glBindTexture(GL_TEXTURE_2D, GLuint(old_texture));
    glBindFramebuffer(GL_FRAMEBUFFER, GLuint(old_fbo));
    glBindRenderbuffer(GL_RENDERBUFFER, GLuint(old_rb));
    if (!ok) {
      release_targets();
      return false;
    }
    width = w;
    height = h;
    return true;
  }
  // Points the frame's scene at the scene target; false (draw straight to the
  // window) when the targets cannot be built for this size.
  bool begin(int w, int h) {
    if (!ready || !resize(w, h)) return false;
    glBindFramebuffer(GL_FRAMEBUFFER, targets[scene].fbo);
    return true;
  }
  // The newest completed asynchronous read, then a new one into a free buffer.
  void measure() {
    const Target &one = chain.back();
    unsigned char rgba[4] = {};
    glBindFramebuffer(GL_READ_FRAMEBUFFER, one.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    auto take = [&](const unsigned char *p) {
      for (int i = 0; i < 3; ++i) measured[i] = float(p[i]) / 255.f;
    };
    if (snap || sync_once) {
      sync_once = false;
      glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
      glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
      take(rgba);
      read = "sync";
      return;
    }
    read = "pending";
    // Fences complete in order: take every completed one, oldest first, so the
    // newest completed measurement wins.
    for (int n = 0; n < int(fences.size()); ++n) {
      int i = (next + n) % int(fences.size());
      if (!fences[i]) continue;
      GLenum state = glClientWaitSync(fences[i], 0, 0);
      if (state != GL_ALREADY_SIGNALED && state != GL_CONDITION_SATISFIED) break;
      glDeleteSync(fences[i]);
      fences[i] = nullptr;
      glBindBuffer(GL_PIXEL_PACK_BUFFER, pack[i]);
      if (auto *p = (const unsigned char *)glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, 4, GL_MAP_READ_BIT)) {
        take(p);
        read = "async";
      }
      glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
    }
    // A new read into the next buffer if it is free; with all three still in
    // flight none is issued this frame (bounded, never waited on).
    if (!fences[next]) {
      glBindBuffer(GL_PIXEL_PACK_BUFFER, pack[next]);
      glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
      fences[next] = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
      next = (next + 1) % int(fences.size());
    }
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
  }
  // Runs the chain over the scene target and composites into the window
  // framebuffer; `dt` is the frame time in seconds. Restores the GL state the
  // HUD draws with.
  void finish(double dt) {
    GLint program, vao_old, active, tex0, tex1, sampler0, sampler1, pack_old, viewport[4];
    GLboolean blend = glIsEnabled(GL_BLEND), depth_test = glIsEnabled(GL_DEPTH_TEST), cull = glIsEnabled(GL_CULL_FACE),
              scissor = glIsEnabled(GL_SCISSOR_TEST), stencil = glIsEnabled(GL_STENCIL_TEST), depth_mask, mask[4];
    glGetIntegerv(GL_CURRENT_PROGRAM, &program);
    glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao_old);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &pack_old);
    glGetIntegerv(GL_VIEWPORT, viewport);
    glGetBooleanv(GL_DEPTH_WRITEMASK, &depth_mask);
    glGetBooleanv(GL_COLOR_WRITEMASK, mask);
    glActiveTexture(GL_TEXTURE1);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &tex1);
    glGetIntegerv(GL_SAMPLER_BINDING, &sampler1);
    glActiveTexture(GL_TEXTURE0);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &tex0);
    glGetIntegerv(GL_SAMPLER_BINDING, &sampler0);
    glDisable(GL_BLEND);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_STENCIL_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glBindSampler(0, 0);
    glBindSampler(1, 0);
    glBindVertexArray(vao);
    auto pass = [&](int index, const Target *into, const Target &from) {
      glUseProgram(programs[index]);
      glBindFramebuffer(GL_FRAMEBUFFER, into ? into->fbo : 0);
      glViewport(0, 0, into ? into->width : width, into ? into->height : height);
      glActiveTexture(GL_TEXTURE0);
      glBindTexture(GL_TEXTURE_2D, from.texture);
      glUniform2f(glGetUniformLocation(programs[index], "texel"), 1.f / from.width, 1.f / from.height);
      return programs[index];
    };
    auto draw = [] { glDrawArrays(GL_TRIANGLES, 0, 3); };
    // P0: the bright pass, from the scene into half size.
    glUniform1f(glGetUniformLocation(pass(0, &targets[bright], targets[scene]), "threshold"), settings.threshold);
    draw();
    // P1, then P2 five times: the luminance reduction down to one texel.
    pass(1, &targets[luminance], targets[scene]);
    draw();
    const Target *from = &targets[luminance];
    for (auto &t : chain) {
      pass(2, &t, *from);
      draw();
      from = &t;
    }
    measure();
    // P3: the 4x4 downscale of the bright pass; P4 and P5: the blur.
    pass(3, &targets[down], targets[bright]);
    draw();
    auto weights = n3e::post::blur_weights(settings.blur_variance, settings.bloom);
    glUniform1fv(glGetUniformLocation(pass(4, &targets[blur], targets[down]), "weights"), 9, weights.data());
    draw();
    glUniform1fv(glGetUniformLocation(pass(5, &targets[bloom], targets[blur]), "weights"), 9, weights.data());
    draw();
    // P6: adapt (00476690), then the composite into the window.
    float step = float(settings.adapt_rate * std::max(0.0, dt));
    for (int i = 0; i < 3; ++i) adapted[i] = snap ? measured[i] : n3e::post::adapt(adapted[i], measured[i], step);
    snap = false;
    const auto used = n3e::post::floored(adapted[0], adapted[1]);
    used_average = used[0];
    used_maximum = used[1];
    GLuint p6 = pass(6, nullptr, targets[scene]);
    glActiveTexture(GL_TEXTURE1);
    glBindTexture(GL_TEXTURE_2D, targets[bloom].texture);
    glUniform1f(glGetUniformLocation(p6, "average"), used_average);
    glUniform1f(glGetUniformLocation(p6, "maximum"), used_maximum);
    glUniform1f(glGetUniformLocation(p6, "bloom"), settings.bloom);
    glUniform1f(glGetUniformLocation(p6, "exposure"), settings.exposure);
    glUniform1f(glGetUniformLocation(p6, "lift"), settings.lift);
    glUniform1f(glGetUniformLocation(p6, "saturation"), settings.saturation);
    draw();
    glBindTexture(GL_TEXTURE_2D, GLuint(tex1));
    glBindSampler(1, GLuint(sampler1));
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, GLuint(tex0));
    glBindSampler(0, GLuint(sampler0));
    glActiveTexture(GLenum(active));
    glBindBuffer(GL_PIXEL_PACK_BUFFER, GLuint(pack_old));
    glBindVertexArray(GLuint(vao_old));
    glUseProgram(GLuint(program));
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
    glDepthMask(depth_mask);
    glColorMask(mask[0], mask[1], mask[2], mask[3]);
    if (blend) glEnable(GL_BLEND);
    if (depth_test) glEnable(GL_DEPTH_TEST);
    if (cull) glEnable(GL_CULL_FACE);
    if (scissor) glEnable(GL_SCISSOR_TEST);
    if (stencil) glEnable(GL_STENCIL_TEST);
  }
  // One target's pixels, top row first (harness stage dumps).
  std::vector<unsigned char> pixels(const Target &t) const {
    std::vector<unsigned char> p(size_t(t.width) * t.height * 3);
    GLint old = 0;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &old);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, t.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, t.width, t.height, GL_RGB, GL_UNSIGNED_BYTE, p.data());
    glBindFramebuffer(GL_READ_FRAMEBUFFER, GLuint(old));
    std::vector<unsigned char> flipped(p.size());
    for (int y = 0; y < t.height; ++y)
      std::memcpy(flipped.data() + size_t(y) * t.width * 3, p.data() + size_t(t.height - 1 - y) * t.width * 3, size_t(t.width) * 3);
    return flipped;
  }

 private:
  int next = 0;
};
#endif
