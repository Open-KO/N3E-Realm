#pragma once
#include <iostream>
#include <stdexcept>
#include <vector>

// GPU regression using the live production shader. An opaque texture at the
// first slot of bank one must never sample transparent bank zero. Unequal clip
// W values exercise perspective interpolation over a triangle covering the view.
inline void check_texture_bank(GLuint program) {
  GLuint textures[2], vao, vbo;
  glGenTextures(2, textures);
  for (unsigned bank = 0; bank < 2; ++bank) {
    glActiveTexture(GL_TEXTURE1 + bank);
    glBindSampler(1 + bank, 0);
    glBindTexture(GL_TEXTURE_2D_ARRAY, textures[bank]);
    unsigned char pixel[4] = {0, static_cast<unsigned char>(bank * 255), 0,
                             static_cast<unsigned char>(bank * 255)};
    glTexImage3D(GL_TEXTURE_2D_ARRAY, 0, GL_RGBA8, 1, 1, 1, 0, GL_RGBA,
                 GL_UNSIGNED_BYTE, pixel);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAX_LEVEL, 0);
  }
  const float vertices[] = {
      -1,-1,-1, 0,1,0, .5,.5,.5,.5, 2048,0,
       6,-2,-2, 0,1,0, .5,.5,.5,.5, 2048,0,
      -3, 9,-3, 0,1,0, .5,.5,.5,.5, 2048,0};
  glGenVertexArrays(1, &vao);glBindVertexArray(vao);
  glGenBuffers(1, &vbo);glBindBuffer(GL_ARRAY_BUFFER, vbo);
  glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
  const int offsets[] = {0,3,6,8,10}, widths[] = {3,3,2,2,2};
  for (int a=0;a<5;++a) {
    glEnableVertexAttribArray(a);
    glVertexAttribPointer(a,widths[a],GL_FLOAT,GL_FALSE,12*sizeof(float),
                          (void*)(uintptr_t)(offsets[a]*sizeof(float)));
  }
  glUseProgram(program);
  auto scalar=[&](const char *name,float value) {
    glUniform1f(glGetUniformLocation(program,name),value);
  };
  scalar("gui",0);scalar("gameplay",1);scalar("world",1);
  scalar("native_detail",1);scalar("light",0);scalar("nofog",1);
  scalar("aspect",1);scalar("projection",1);
  scalar("nearplane",.05f);scalar("farplane",100);
  glUniform2f(glGetUniformLocation(program,"foglimits"),0,0);
  glUniform3f(glGetUniformLocation(program,"eye"),0,0,0);
  glUniform3f(glGetUniformLocation(program,"rightward"),1,0,0);
  glUniform3f(glGetUniformLocation(program,"upward"),0,1,0);
  glUniform3f(glGetUniformLocation(program,"backward"),0,0,1);
  glDisable(GL_SCISSOR_TEST);glDisable(GL_DEPTH_TEST);
  glDisable(GL_CULL_FACE);glDisable(GL_BLEND);
  glViewport(0,0,128,128);glClearColor(1,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
  glDrawArrays(GL_TRIANGLES,0,3);
  std::vector<unsigned char> pixels(128*128*3);
  glReadPixels(0,0,128,128,GL_RGB,GL_UNSIGNED_BYTE,pixels.data());
  unsigned wrong=0;
  for(size_t i=0;i<pixels.size();i+=3)
    if(pixels[i]!=0 || pixels[i+1]<80 || pixels[i+2]!=0)++wrong;
  glDeleteBuffers(1,&vbo);glDeleteVertexArrays(1,&vao);
  glDeleteTextures(2,textures);
  if(wrong)throw std::runtime_error("texture bank regression: "+std::to_string(wrong)+" incorrect pixels");
  std::cout<<"PASS native texture bank boundary: 16384 opaque pixels, unequal clip W\n";
}
