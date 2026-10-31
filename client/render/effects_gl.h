#pragma once
#include "appearance_effects.h"
#include "effects.h"
#include <functional>
#include <span>
#include "orbit.h"
#include <GL/gl.h>
#include <stdexcept>

GLuint shader(GLenum type,const char* source);
struct EffectsView {
  GLuint program=0,vao=0,vbo=0;
  std::vector<GLuint> textures;
  void upload(const n3e::Effects& data){
    const char* vs=R"(#version 330 core
layout(location=0) in vec3 pos;layout(location=1) in vec2 uv;layout(location=2) in vec4 tint;
uniform vec3 eye,rightward,upward,backward;uniform float projection,aspect,nearplane,farplane;
out vec2 texcoord;out vec4 diffuse;
void main(){vec3 d=pos-eye;float z=dot(d,backward);gl_Position=vec4(dot(d,rightward)*projection/aspect,dot(d,upward)*projection,-(farplane+nearplane)/(farplane-nearplane)*z-2*nearplane*farplane/(farplane-nearplane),-z);texcoord=uv;diffuse=tint;})";
    const char* fs=R"(#version 330 core
in vec2 texcoord;in vec4 diffuse;uniform sampler2D chart;out vec4 color;
void main(){color=texture(chart,texcoord)*diffuse;})";
    GLuint v=shader(GL_VERTEX_SHADER,vs),f=shader(GL_FRAGMENT_SHADER,fs);
    program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);
    GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);glDeleteShader(v);glDeleteShader(f);
    if(!ok)throw std::runtime_error("effect shader link");
    glGenVertexArrays(1,&vao);glBindVertexArray(vao);glGenBuffers(1,&vbo);glBindBuffer(GL_ARRAY_BUFFER,vbo);
    for(unsigned i=0;i<3;++i){glEnableVertexAttribArray(i);glVertexAttribPointer(i,i==0?3:i==1?2:4,GL_FLOAT,GL_FALSE,9*sizeof(float),(void*)(uintptr_t)((i==0?0:i==1?3:5)*sizeof(float)));}
    glActiveTexture(GL_TEXTURE0);
    for(const auto&t:data.textures){
      GLuint id;glGenTextures(1,&id);textures.push_back(id);glBindTexture(GL_TEXTURE_2D,id);
      glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,t.width,t.height,0,GL_RGBA,GL_UNSIGNED_BYTE,t.pixels.data());
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT);
    }
  }
  static GLenum blend(unsigned factor){
    constexpr GLenum factors[]={GL_ZERO,GL_ZERO,GL_ONE,GL_SRC_COLOR,GL_ONE_MINUS_SRC_COLOR,GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA,GL_DST_ALPHA,GL_ONE_MINUS_DST_ALPHA,GL_DST_COLOR,GL_ONE_MINUS_DST_COLOR};
    return factors[factor];
  }
  // `instances` and `meshes` (PQ-211: appearance effect tails and glow
  // meshes) join the player's effects in one far-to-near pass. PQ-379
  // (D-201): so do the caller's `external_keys` (the world's alpha parts),
  // each drawn by `external` with its index at its place in the order; the
  // pass then restores its own program and buffers. Without effects.bin
  // (no program) only those are drawn.
  void draw(const n3e::EffectPlayer& player,double now,const Orbit& orbit,const n3e::CameraConfig&camera,float aspect,
            std::span<const n3e::EffectInstance* const> instances={},std::span<const n3e::EffectMesh> meshes={},
            std::span<const float> external_keys={},const std::function<void(size_t)>&external={}){
    if(!external)external_keys={};
    const bool effects=program&&(!player.active.empty()||!instances.empty()||!meshes.empty());
    if(!effects&&external_keys.empty())return;
    GLint old_program,old_vao,old_buffer;glGetIntegerv(GL_CURRENT_PROGRAM,&old_program);glGetIntegerv(GL_VERTEX_ARRAY_BINDING,&old_vao);glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&old_buffer);
    auto use=[&]{if(!program)return;glUseProgram(program);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);glActiveTexture(GL_TEXTURE0);glBindSampler(0,0);};
    use();
    if(program){
      auto vector=[&](const char*name,const n3e::V&v){glUniform3fv(glGetUniformLocation(program,name),1,v.data());};
      vector("eye",orbit.eye);vector("rightward",orbit.right);vector("upward",orbit.up);vector("backward",orbit.back);
      for(const auto&[name,value]:std::initializer_list<std::pair<const char*,float>>{{"aspect",aspect},{"projection",1.f/std::tan(camera.fov/2)},{"nearplane",camera.near_plane},{"farplane",camera.far_plane}})glUniform1f(glGetUniformLocation(program,name),value);
    }
    // PQ-342: every instance of an N3E4-ruled clip decides its particle
    // candidates by the camera's distance to its bundle, the newest point
    // (2233's copy position, set by RenderFX 004304c0 before its tick); a
    // tail chain's links share one live count, a player effect is its own.
    n3e::thin_all(player,instances,now,orbit.eye);
    // PQ-376 (D-200): one far-to-near list, as 1298 flushes its alpha list
    // (0043dd80); consecutive draws of one material share a draw call, in order.
    std::span<const n3e::EffectInstance* const> links=program?instances:std::span<const n3e::EffectInstance* const>{};
    std::span<const n3e::EffectMesh> shown=program?meshes:std::span<const n3e::EffectMesh>{};
    static const n3e::EffectPlayer none;
    auto draws=n3e::effect_draws(program?player:none,links,shown,now,orbit.eye,orbit.right,orbit.up,textures.size(),external_keys);
    std::vector<float> pending;std::array<unsigned,4> material{};
    auto flush=[&]{
      if(pending.empty())return;
      auto [texture,source,destination,flags]=material;
      if(flags&1)glEnable(GL_BLEND);else glDisable(GL_BLEND);
      glBlendFunc(blend(source),blend(destination));
      if(flags&4)glDisable(GL_CULL_FACE);else glEnable(GL_CULL_FACE);
      if(flags&1024)glDisable(GL_DEPTH_TEST);else glEnable(GL_DEPTH_TEST);
      glDepthMask(!(flags&256));glBindTexture(GL_TEXTURE_2D,textures[texture]);
      auto filter=flags&16?GL_NEAREST:GL_LINEAR;glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,filter);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,filter);
      auto wrap=flags&512?GL_CLAMP_TO_EDGE:GL_REPEAT;glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,wrap);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,wrap);
      glBufferData(GL_ARRAY_BUFFER,pending.size()*sizeof(float),pending.data(),GL_STREAM_DRAW);glDrawArrays(GL_TRIANGLES,0,pending.size()/9);
      pending.clear();
    };
    for(const auto&d:draws){
      if(d.external!=SIZE_MAX){flush();external(d.external);use();continue;}
      std::vector<float> made;
      if(!d.mesh)made=n3e::effect_vertices(*d.instance,*d.batch,d.age,orbit.right,orbit.up,d.record,d.records);
      const auto&vertices=d.mesh?d.mesh->vertices:made;
      if(vertices.empty())continue;
      std::array<unsigned,4> next=d.mesh?std::array<unsigned,4>{d.mesh->texture,d.mesh->source_blend,d.mesh->destination_blend,d.mesh->flags}
                                        :std::array<unsigned,4>{d.batch->texture,d.batch->source_blend,d.batch->destination_blend,d.batch->flags};
      if(next!=material)flush();
      material=next;pending.insert(pending.end(),vertices.begin(),vertices.end());
    }
    flush();
    glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE);glEnable(GL_CULL_FACE);glDisable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(old_program);glBindVertexArray(old_vao);glBindBuffer(GL_ARRAY_BUFFER,old_buffer);
  }
  void destroy(){if(!textures.empty())glDeleteTextures(textures.size(),textures.data());textures.clear();if(program)glDeleteProgram(program);if(vbo)glDeleteBuffers(1,&vbo);if(vao)glDeleteVertexArrays(1,&vao);program=vao=vbo=0;}
};
