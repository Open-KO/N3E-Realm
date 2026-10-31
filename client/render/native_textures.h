#pragma once
#include "assets/assets.h"
#include "platform/gl.h"
#include <algorithm>
#include <map>
#include <stdexcept>
#include <string>

// Group equal-sized authored chains into arrays. No resampling or generated
// mipmaps; distinct dimensions and terminal levels get distinct bounded banks.
struct NativeTextures {
  std::vector<GLuint> banks;
  std::vector<float> slots;
  int mirrored=-1;
  void upload(const std::vector<n3e::TextureChain> &textures) {
    std::map<std::array<unsigned,3>,std::vector<unsigned>> groups;
    for(unsigned i=0;i<textures.size();++i) {
      const auto &c=textures[i];groups[{c[0].width,c[0].height,unsigned(c.size())}].push_back(i);
    }
    if(groups.size()>8) throw std::runtime_error("native texture bank bound");
    slots.resize(textures.size());
    GLint maximum=0;glGetIntegerv(GL_MAX_ARRAY_TEXTURE_LAYERS,&maximum);
    for(const auto &[key,ids]:groups) {
      if(ids.size()>unsigned(maximum)) throw std::runtime_error("native texture layer capability");
      GLuint texture;glGenTextures(1,&texture);
      glActiveTexture(GL_TEXTURE1+banks.size());glBindTexture(GL_TEXTURE_2D_ARRAY,texture);
      for(unsigned j=0;j<ids.size();++j)slots[ids[j]]=float(banks.size()*2048+j);
      for(unsigned level=0;level<key[2];++level) {
        const auto &m=textures[ids[0]][level];std::vector<unsigned char> pixels;
        pixels.reserve(m.pixels.size()*ids.size());
        for(auto id:ids){const auto &p=textures[id][level].pixels;pixels.insert(pixels.end(),p.begin(),p.end());}
        glTexImage3D(GL_TEXTURE_2D_ARRAY,level,GL_RGBA8,m.width,m.height,ids.size(),0,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
      }
      glTexParameteri(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_MAX_LEVEL,key[2]-1);
      glTexParameteri(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
      glTexParameteri(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
      banks.push_back(texture);
    }
    glActiveTexture(GL_TEXTURE0);
  }
  // An N3W2 world's textures (N3WT, PQ-233): the same grouping, with a group
  // split into banks of at most min(GPU layer limit, 2048) layers, and a clear
  // refusal when the banks exceed the shader's samplers or a level exceeds the
  // GPU's texture size. `layer_cap` and `size_cap` lower the GPU's limits
  // (test client only).
  void upload_world(const n3e::WorldTextures &textures, GLint layer_cap = 0, GLint size_cap = 0) {
    GLint layers = 0, size = 0;
    glGetIntegerv(GL_MAX_ARRAY_TEXTURE_LAYERS, &layers);
    glGetIntegerv(GL_MAX_TEXTURE_SIZE, &size);
    if (layer_cap > 0) layers = std::min(layers, layer_cap);
    if (size_cap > 0) size = std::min(size, size_cap);
    layers = std::min<GLint>(layers, n3e::WORLD_TEXTURE_BANK_LAYERS);
    if (layers < 1) throw std::runtime_error("world textures: GPU reports no array texture layers");
    auto groups = n3e::world_texture_banks(textures, unsigned(layers));
    if (groups.size() > n3e::WORLD_TEXTURE_BANKS)
      throw std::runtime_error("world textures need " + std::to_string(groups.size()) + " array banks of at most " +
                               std::to_string(layers) + " layers on this GPU; the client binds " +
                               std::to_string(n3e::WORLD_TEXTURE_BANKS));
    for (const auto &g : groups)
      if (g.width > unsigned(size) || g.height > unsigned(size))
        throw std::runtime_error("world texture " + std::to_string(g.width) + "x" + std::to_string(g.height) +
                                 " exceeds the GPU texture size limit " + std::to_string(size));
    slots.assign(textures.chains.size(), 0.f);
    for (const auto &g : groups) {
      GLuint texture;glGenTextures(1,&texture);
      glActiveTexture(GL_TEXTURE1+banks.size());glBindTexture(GL_TEXTURE_2D_ARRAY,texture);
      for(unsigned j=0;j<g.textures.size();++j)slots[g.textures[j]]=float(banks.size()*2048+j);
      std::vector<unsigned char> pixels;
      for(unsigned level=0;level<g.levels;++level) {
        const auto &m=textures.chains[g.textures[0]][level];
        const size_t bytes=size_t(m.width)*m.height*4;
        pixels.resize(bytes*g.textures.size());
        for(size_t k=0;k<g.textures.size();++k)
          std::copy_n(textures.bytes.data()+textures.chains[g.textures[k]][level].offset,bytes,pixels.data()+k*bytes);
        glTexImage3D(GL_TEXTURE_2D_ARRAY,level,GL_RGBA8,m.width,m.height,GLsizei(g.textures.size()),0,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
      }
      glTexParameteri(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_MAX_LEVEL,g.levels-1);
      glTexParameteri(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
      glTexParameteri(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
      banks.push_back(texture);
    }
    glActiveTexture(GL_TEXTURE0);
  }
  void bind() const {
    for(unsigned i=0;i<banks.size();++i){glActiveTexture(GL_TEXTURE1+i);glBindTexture(GL_TEXTURE_2D_ARRAY,banks[i]);}
    glActiveTexture(GL_TEXTURE0);
  }
  void sampling(bool mirror,const GLuint *samplers) {
    if(mirrored==int(mirror))return;
    for(unsigned i=0;i<banks.size();++i)glBindSampler(1+i,samplers[mirror]);
    mirrored=mirror;
  }
  void destroy() {if(!banks.empty())glDeleteTextures(banks.size(),banks.data());banks.clear();}
};
