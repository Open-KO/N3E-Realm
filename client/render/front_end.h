#pragma once
// Spec 11's KO front end: login (the 1098 intro scene), the realm list, the
// Karus character select hall, create, loading and the OK message box, drawn
// from front-end.bin (content/front-end.md). The screens are a state machine
// here; the viewer turns each Command into the protocol message it already
// sends for the legacy panels, and tells this module what the server said.
#include "assets/assets.h"
#include "platform/gl.h"
#include "platform/gl_load.h"
#include "render/animation.h"
#include "render/select_turn.h"
#include "wire.pb.h"
#include <SDL3/SDL.h>
#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace n3e::front {

enum class Screen { login, realms, select, create, loading };
enum class Command { none, login, exit, enter_realm, select, create, back };
struct Output {
  Command command = Command::none;
  uint64_t character = 0;  // select
  std::string name;        // create
};
// What the viewer knows this frame.
struct Context {
  std::string realm;         // realm.json's name
  std::string notice;        // the login line (spec 02's flow status)
  std::string version;       // shown by the loading screen's `version` text
  const Characters *characters = nullptr;
  float progress = 0;        // loading: 0..1
};
// The select hall's character in front as the last frame showed it (a test
// hook): its clip (0 hover, 1 start, 2 rest), that clip's time and length
// (seconds), how far the blend into it has run (1: none or done), the spot's
// theta and whether the spot is on, and whether the info text shows.
struct FrontPose {
  uint32_t clip = 0;
  float time = 0, length = 0, blend = 1, theta = 0;
  bool spot = false, info = false;
};
// The select camera as the last frame showed it (a test hook): the slot it is
// at, the slot in focus (they differ while it turns) and its turn from the
// scene camera's eye (radians, positive to the left; select_turn).
struct FrontTurn {
  int slot = 0, focus = 0;
  float angle = 0;
};

namespace detail {
using Mat = std::array<float, 16>;  // column-major
inline Mat mul(const Mat &a, const Mat &b) {
  Mat r{};
  for (int c = 0; c < 4; ++c)
    for (int i = 0; i < 4; ++i)
      for (int k = 0; k < 4; ++k) r[c * 4 + i] += a[k * 4 + i] * b[c * 4 + k];
  return r;
}
inline Mat identity() { return {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}; }
inline Mat translate_yaw(const V &p, float yaw) {
  const float c = std::cos(yaw), s = std::sin(yaw);
  return {c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, p[0], p[1], p[2], 1};
}
inline V sub(V a, V b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
inline V cross(V a, V b) { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
inline V unit(V a) {
  const float l = std::sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
  return l > 0 ? V{a[0] / l, a[1] / l, a[2] / l} : V{0, 0, 1};
}
inline float dot(V a, V b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
inline Mat look_at(V eye, V at, V up) {
  const V f = unit(sub(at, eye)), s = unit(cross(f, up)), u = cross(s, f);
  return {s[0], u[0], -f[0], 0, s[1], u[1], -f[1], 0, s[2], u[2], -f[2], 0,
          -dot(s, eye), -dot(u, eye), dot(f, eye), 1};
}
inline Mat perspective(float fov, float aspect, float n, float f) {
  const float t = 1 / std::tan(fov / 2);
  return {t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) / (n - f), -1, 0, 0, 2 * f * n / (n - f), 0};
}
inline GLuint compile(GLenum type, const char *src) {
  auto s = glCreateShader(type);
  glShaderSource(s, 1, &src, nullptr);
  glCompileShader(s);
  int ok = 0;
  glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
  if (!ok) {
    char b[2048];
    glGetShaderInfoLog(s, sizeof b, nullptr, b);
    throw std::runtime_error(std::string("front end shader: ") + b);
  }
  return s;
}
inline GLuint program(const char *vs, const char *fs) {
  auto v = compile(GL_VERTEX_SHADER, vs), f = compile(GL_FRAGMENT_SHADER, fs), p = glCreateProgram();
  glAttachShader(p, v);
  glAttachShader(p, f);
  glLinkProgram(p);
  int ok = 0;
  glGetProgramiv(p, GL_LINK_STATUS, &ok);
  glDeleteShader(v);
  glDeleteShader(f);
  if (!ok) throw std::runtime_error("front end program link");
  return p;
}
inline GLuint texture(uint32_t w, uint32_t h, const unsigned char *pixels, bool rgb = false) {
  GLuint t;
  glGenTextures(1, &t);
  glBindTexture(GL_TEXTURE_2D, t);
  glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
  glTexImage2D(GL_TEXTURE_2D, 0, rgb ? GL_RGB8 : GL_RGBA8, w, h, 0, rgb ? GL_RGB : GL_RGBA, GL_UNSIGNED_BYTE, pixels);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
  return t;
}
// KO's string styles (CN3UIString).
inline constexpr uint32_t SINGLELINE = 0x00100000, ALIGNRIGHT = 0x00400000, ALIGNCENTER = 0x00800000,
                          VCENTER = 0x04000000, PASSWORD = 0x10000000;
inline std::string replace(std::string s, const std::string &key, const std::string &value) {
  for (size_t at = s.find(key); at != std::string::npos; at = s.find(key, at + value.size()))
    s.replace(at, key.size(), value);
  return s;
}
}  // namespace detail

class View {
 public:
  explicit View(FrontEnd data) : fe(std::move(data)) {
    using namespace detail;
    for (const auto &t : fe.textures) textures.push_back(texture(t.width, t.height, t.pixels.data()));
    // Samplers as KO sets them. UIF images: CUIManager::RenderStateSet's
    // point sampling (KO's atlases border each tile with black texels that
    // a linear filter blends in). Scene meshes and plugs: CN3Eng's trilinear
    // filter, mip LOD bias -1, and D3D's default wrap (hall UVs run past
    // 0..1). The font atlases (not KO art) and the moon stay linear.
    std::vector<int> use(textures.size(), 0);  // 0 UI, 1 linear, 2 scene
    for (const auto &f : fe.fonts) use[f.texture] = 1;
    use[fe.backdrop] = 1;
    for (const auto &m : fe.hall) use[m.texture] = 2;
    for (const auto *scene : {&fe.intro, &fe.select, &fe.create})
      for (const auto &plug : scene->plugs) use[plug.mesh.texture] = 2;
    for (size_t i = 0; i < textures.size(); ++i) {
      glBindTexture(GL_TEXTURE_2D, textures[i]);
      if (use[i] == 0) {
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
      } else if (use[i] == 2) {
        glGenerateMipmap(GL_TEXTURE_2D);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_LOD_BIAS, -1.f);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
      }
    }
    for (auto *scene : {&fe.intro, &fe.select, &fe.create})
      models.push_back(texture(scene->model.width, scene->model.height, scene->model.texture.data(),
                               scene->model.channels == 3));
    lit = program(R"(#version 330 core
layout(location=0) in vec3 p;layout(location=1) in vec3 n;layout(location=2) in vec2 t;
uniform mat4 mvp,model;out vec3 wp,wn;out vec2 uv;
void main(){vec4 w=model*vec4(p,1);wp=w.xyz;wn=mat3(model)*n;uv=t;gl_Position=mvp*vec4(p,1);})",
                  R"(#version 330 core
in vec3 wp,wn;in vec2 uv;out vec4 o;uniform sampler2D tex;uniform int count;uniform int kind[9];
uniform vec3 ld[9],la[9],lp[9],ldir[9],latt[9];uniform vec4 lr[9];uniform vec3 md,ma,ga;uniform float unlit,cut;
void main(){vec4 c=texture(tex,uv);if(c.a<=cut)discard;if(unlit>.5){o=c;return;}
vec3 N=normalize(wn);vec3 col=ma*ga;
for(int i=0;i<count;i++){vec3 L;float a=1.,s=1.;
if(kind[i]==3)L=normalize(-ldir[i]);else{vec3 d=lp[i]-wp;float r=length(d);if(r>lr[i].x)continue;L=d/max(r,1e-5);
a=1./max(latt[i].x+latt[i].y*r+latt[i].z*r*r,1e-5);
if(kind[i]==2){float rho=dot(normalize(ldir[i]),-L),ct=cos(lr[i].z*.5),cp=cos(lr[i].w*.5);
if(rho<=cp)s=0.;else if(rho<ct)s=pow((rho-cp)/max(ct-cp,1e-5),lr[i].y);}}
col+=a*s*(ma*la[i]+md*ld[i]*max(dot(N,L),0.));}
o=vec4(c.rgb*clamp(col,0.,1.),c.a);})");
    flat = program(R"(#version 330 core
layout(location=0) in vec2 p;layout(location=1) in vec2 t;layout(location=2) in vec4 c;uniform vec2 screen;
out vec2 uv;out vec4 tint;void main(){uv=t;tint=c;gl_Position=vec4(p.x/screen.x*2.-1.,1.-p.y/screen.y*2.,0,1);})",
                   R"(#version 330 core
in vec2 uv;in vec4 tint;out vec4 o;uniform sampler2D tex;uniform float solid;
void main(){o=(solid>.5?vec4(1):texture(tex,uv))*tint;})");
    glGenVertexArrays(1, &vao);
    glGenBuffers(1, &vbo);
    for (auto &mesh : fe.hall) statics.push_back(upload(mesh));
    for (auto &plug : fe.intro.plugs) intro_plugs.push_back(upload(plug.mesh));
    for (auto &plug : fe.select.plugs) select_plugs.push_back(upload(plug.mesh));
    for (auto &plug : fe.create.plugs) create_plugs.push_back(upload(plug.mesh));
    // A further clip poses the model's own nodes (load_front_end checked them).
    for (auto *scene : {&fe.intro, &fe.select, &fe.create}) {
      std::vector<Scene> poses;
      for (const auto &clip : scene->clips) {
        Scene s;
        s.nodes = scene->model.nodes;
        s.tracks = clip;
        poses.push_back(std::move(s));
      }
      clips.push_back(std::move(poses));
    }
    for (const auto &node : fe.screens[size_t(FrontScreen::login)])
      if (node.action == FrontAction::realm_group) realm_height = node.rect[3] - node.rect[1];
    fe.intro.model.texture.clear();
    fe.select.model.texture.clear();
    fe.create.model.texture.clear();
  }
  ~View() {
    glDeleteTextures(GLsizei(textures.size()), textures.data());
    glDeleteTextures(GLsizei(models.size()), models.data());
    for (auto *set : {&statics, &intro_plugs, &select_plugs, &create_plugs})
      for (auto &m : *set) {
        glDeleteBuffers(1, &m.vbo);
        glDeleteBuffers(1, &m.ebo);
        glDeleteVertexArrays(1, &m.vao);
      }
    glDeleteBuffers(1, &vbo);
    glDeleteVertexArrays(1, &vao);
    glDeleteProgram(lit);
    glDeleteProgram(flat);
  }
  View(const View &) = delete;
  View &operator=(const View &) = delete;

  Screen screen() const { return state; }
  bool wants_text() const { return state == Screen::create && !message; }
  // RQ-018 (Q57): the track this screen plays (null for silence). The
  // viewer hands it to the mixer every frame, which keeps a track already
  // playing, so it runs on across the screens that share it.
  std::shared_ptr<const MusicTrack> music() const {
    const auto index = fe.screen_music[size_t(layout())];
    return index == FrontEnd::kNoMusic ? nullptr : fe.music[index];
  }
  bool has_music() const { return !fe.music.empty(); }
  // The Discord login finished: KO's OpenServerList.
  void logged_in() {
    // A message box (a kick, a drop) stays over the login screen until OK.
    if (state != Screen::login || message) return;
    state = Screen::realms;
    slide = 0;
  }
  // Back to the login screen (a dropped or reset connection).
  void reset() {
    state = Screen::login;
    choosing = -1;
    pending_create = false;
  }
  void show_message(std::string text) { message = std::move(text); }
  bool showing_message() const { return message.has_value(); }
  bool creating() const { return pending_create; }
  // The character in front as the last select frame showed it; the test
  // client checks the hover, its blends, the spot and the info text.
  FrontPose front_pose() const { return front_shown; }
  FrontTurn front_turn() const { return turn_shown; }
  const std::string &message_text() const { static const std::string none; return message ? *message : none; }
  // The server answered CreateCharacter: a longer list is a success (the
  // new character takes its slot), a refusal is shown in a message box.
  void characters(const Characters &list) {
    if (pending_create && list.characters_size() > known) {
      pending_create = false;
      enter_select();
      focus = std::min<int>(list.characters_size() - 1, int(fe.slots.size()) - 1);
      face(focus);
    }
    known = list.characters_size();
  }
  // A refused create, or a refused select (the character is online
  // elsewhere): back to the screen with the server's wording.
  void refused(const std::string &detail) {
    if (pending_create) {
      pending_create = false;
      show_message(detail);
    } else if (state == Screen::loading || choosing >= 0) {
      state = Screen::select;
      choosing = -1;
      // Back at rest (1097: state 2) the character in front leaves the start
      // clip now, for the clip DoProcPreselect sets, so a start right after
      // the refusal plays the start clip again rather than finding it ended.
      if (focus < characters_shown()) set_clip(players.at(size_t(focus)), in_front() ? kHover : kRest, -1);
      show_message(detail);
    }
  }
  // Loading: the selection animation has played and the screen shows.
  void loading() { state = Screen::loading; }

  // Test hooks (spec 11's captures): a screen at rest, the characters the
  // last frame drew (their boxes in normalised device coordinates of the
  // viewport they were drawn in), and a bound node's rect in pixels.
  void jump(Screen to) {
    state = to;
    message.reset();
    choosing = -1;
    pending_create = false;
    slide = realm_height;
    reset_hall();
    face(0);
  }
  struct Drawn {
    size_t which;                  // 0 intro, 1 select, 2 create
    std::array<float, 4> box;      // x0 y0 x1 y1 in the viewport's NDC, y up
    std::array<int, 4> viewport;   // GL viewport: x, y (from the bottom), w, h
  };
  const std::vector<Drawn> &drawn() const { return drawn_boxes; }
  std::optional<std::array<float, 4>> action_rect(FrontAction action, int width, int height) const {
    const auto screen = action == FrontAction::message || action == FrontAction::ok ? FrontScreen::message : layout();
    const auto &nodes = fe.screens[size_t(screen)];
    for (size_t i = 0; i < nodes.size(); ++i)
      if (nodes[i].action == action) {
        const float s = scale(width, height), ox = (width - fe.canvas_width * s) / 2,
                    oy = (height - fe.canvas_height * s) / 2;
        const auto r = rect(screen, i);
        return std::array<float, 4>{ox + r[0] * s, oy + r[1] * s, ox + r[2] * s, oy + r[3] * s};
      }
    return std::nullopt;
  }

  Output event(const SDL_Event &e, float x, float y, int width, int height) {
    Output out;
    const float s = scale(width, height), ox = (width - fe.canvas_width * s) / 2,
                oy = (height - fe.canvas_height * s) / 2;
    const float cx = (x - ox) / s, cy = (y - oy) / s;
    if (e.type == SDL_EVENT_MOUSE_MOTION) {
      pointer = {cx, cy};
      screen_pointer = {x, y};
      screen_size = {width, height};
      return out;
    }
    if (message) {
      const bool ok = (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat &&
                       (e.key.key == SDLK_RETURN || e.key.key == SDLK_KP_ENTER || e.key.key == SDLK_ESCAPE)) ||
                      (e.type == SDL_EVENT_MOUSE_BUTTON_UP && e.button.button == SDL_BUTTON_LEFT &&
                       hit(FrontScreen::message, cx, cy) == FrontAction::ok);
      if (e.type == SDL_EVENT_MOUSE_BUTTON_DOWN) pressed = hit(FrontScreen::message, cx, cy);
      if (ok) message.reset(), pressed = FrontAction::none;
      return out;
    }
    if (state == Screen::loading) return out;
    const auto ui = layout();
    if (e.type == SDL_EVENT_TEXT_INPUT && state == Screen::create) {
      for (const char *c = e.text.text; *c; ++c)
        if (name.size() < 24 && (std::isalnum((unsigned char)*c) || *c == '_' || *c == '-')) name += *c;
      return out;
    }
    if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat) {
      const auto key = e.key.key;
      const bool enter = key == SDLK_RETURN || key == SDLK_KP_ENTER;
      if (key == SDLK_BACKSPACE && state == Screen::create && !name.empty()) name.pop_back();
      if (key == SDLK_ESCAPE) return escape();
      if (enter) return primary();
      if (state == Screen::select && key == SDLK_LEFT) return act(FrontAction::select_prev);
      if (state == Screen::select && key == SDLK_RIGHT) return act(FrontAction::select_next);
      return out;
    }
    if (e.type == SDL_EVENT_MOUSE_BUTTON_DOWN && e.button.button == SDL_BUTTON_LEFT) {
      pressed = hit(ui, cx, cy);
      if (pressed == FrontAction::realm_list && e.button.clicks >= 2) return act(FrontAction::realm_connect);
      // CGameProcCharacterSelect: a click in the centre of the screen
      // chooses the character in front (ENTER does the same); primary()
      // takes it only at rest.
      screen_pointer = {x, y};
      screen_size = {width, height};
      if (state == Screen::select && pressed == FrontAction::none && clicked_front()) return primary();
      return out;
    }
    if (e.type == SDL_EVENT_MOUSE_BUTTON_UP && e.button.button == SDL_BUTTON_LEFT) {
      const auto was = pressed;
      pressed = FrontAction::none;
      if (was != FrontAction::none && hit(ui, cx, cy) == was) return act(was);
    }
    return out;
  }

  // The frame: the screen's scene, then its UI on the canvas, then the
  // message box. Called with the default framebuffer bound.
  void draw(int width, int height, double now, const Context &context) {
    using namespace detail;
    const double dt = last_frame < 0 ? 0 : std::clamp(now - last_frame, 0.0, 0.25);
    last_frame = now;
    drawn_boxes.clear();
    glViewport(0, 0, width, height);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    if (context.characters) {
      characters(*context.characters);
      list = context.characters;
    }
    if (state == Screen::realms && realm_height > 0) {
      // CUILogIn_1098::Tick: the server group drops in from above the screen.
      float delta = float(5000 * dt) * (realm_height - slide) / realm_height;
      slide = std::min(realm_height, slide + std::max(delta, dt > 0 ? 2.f : 0.f));
    }
    if (state == Screen::login || state == Screen::realms) intro(width, height, now);
    if (state == Screen::select) hall(width, height, dt);
    // IsAnimEnd: the start clip has played once, after its blend (1097:
    // 0043ed20 reads the loop count, which 00445bb0 counts only past the
    // clip's end, and the frame stays on the start during the blend).
    if (state == Screen::select && choosing >= 0 && ended(players.at(size_t(choosing)))) {
      choosing = -1;
      state = Screen::loading;
    }
    begin_ui(width, height);
    ui(layout(), context, now);
    if (state == Screen::create) {
      flush();
      character_view(width, height, now);
      begin_ui(width, height);
    }
    if (message) ui(FrontScreen::message, context, now);
    flush();
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
    glDisable(GL_BLEND);
  }

 private:
  struct Buffer { GLuint vao = 0, vbo = 0, ebo = 0; GLsizei count = 0; };
  FrontEnd fe;
  std::vector<GLuint> textures, models;
  GLuint lit = 0, flat = 0, vao = 0, vbo = 0;
  std::vector<Buffer> statics, intro_plugs, select_plugs, create_plugs;
  std::vector<std::vector<Scene>> clips;  // per scene: each clip's poses
  Screen state = Screen::login;
  std::optional<std::string> message;
  std::array<float, 2> pointer{-1, -1};
  FrontAction pressed = FrontAction::none;
  float realm_height = 0, slide = 0;
  // The select camera: the slot it is at and the slot in focus, which is the
  // one it turns to from the press on (1097: CGameProcCharacterSelect's
  // positions +0x2c4 and +0x2c8, the selected index 006e04d0), and its turn
  // from the scene camera's eye (select_turn).
  int focus = 0, at_slot = 0, choosing = -1, known = 0;
  float angle = 0;
  FrontTurn turn_shown;
  double last_frame = -1;
  // The select hall as CGameProcCharacterSelect keeps it (1097 binary,
  // specs/KO-FINDINGS.md 8.1): each slot's clip player, the spot's theta
  // (+0x2d0) and whether it is on, the slot whose info text shows (-1 none).
  // The select model's clips by role.
  static constexpr size_t kHover = 0, kStart = 1, kRest = 2;
  struct Player {
    size_t clip = kHover, from = kHover;  // the clip, the clip blended from
    float elapsed = 0, blend = 0, from_time = 0;  // ticked time since set; blend time; from's time
  };
  std::array<Player, 3> players{};
  float theta = 0;
  bool spot_on = false;
  int info_slot = -1;
  FrontPose front_shown;
  std::array<float, 2> screen_pointer{-1, -1};  // the pointer in window pixels
  std::array<int, 2> screen_size{0, 0};          // the window those pixels are of
  bool pending_create = false;
  std::string name;
  const Characters *list = nullptr;
  // UI batch: x, y, u, v, r, g, b, a per vertex, flushed per texture.
  std::vector<float> batch;
  GLuint batch_texture = 0;
  bool batch_solid = false;
  float ui_scale = 1, ui_x = 0, ui_y = 0;
  std::vector<Drawn> drawn_boxes;

  Buffer upload(const FrontMesh &mesh) {
    Buffer b;
    glGenVertexArrays(1, &b.vao);
    glGenBuffers(1, &b.vbo);
    glGenBuffers(1, &b.ebo);
    glBindVertexArray(b.vao);
    glBindBuffer(GL_ARRAY_BUFFER, b.vbo);
    glBufferData(GL_ARRAY_BUFFER, mesh.vertices.size() * sizeof(float), mesh.vertices.data(), GL_STATIC_DRAW);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, b.ebo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, mesh.indices.size() * sizeof(uint32_t), mesh.indices.data(), GL_STATIC_DRAW);
    for (unsigned a = 0; a < 3; ++a) {
      glEnableVertexAttribArray(a);
      glVertexAttribPointer(a, a == 2 ? 2 : 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void *)(a * 3 * sizeof(float)));
    }
    b.count = GLsizei(mesh.indices.size());
    glBindVertexArray(0);
    return b;
  }
  float scale(int width, int height) const {
    return std::min(width / float(fe.canvas_width), height / float(fe.canvas_height));
  }
  FrontScreen layout() const {
    return state == Screen::select ? FrontScreen::select
           : state == Screen::create ? FrontScreen::create
           : state == Screen::loading ? FrontScreen::loading
                                      : FrontScreen::login;
  }
  int characters_shown() const {
    return list ? std::min<int>(list->characters_size(), int(fe.slots.size())) : 0;
  }
  // The slots from left to right: 1, 0, 2 (CheckRotateLeft/Right).
  std::vector<int> slot_order() const {
    std::vector<int> order;
    for (int s : {1, 0, 2})
      if (s < int(fe.slots.size())) order.push_back(s);
    return order;
  }
  float slot_angle(int slot) const {
    const auto &c = fe.select.camera;
    return select_turn(c.eye, c.at, fe.slots[size_t(slot)].eye);
  }
  // The camera at rest on the slot, which is in focus.
  void face(int slot) {
    focus = at_slot = slot;
    angle = slot_angle(slot);
  }
  // Whether node i draws in this state: its group's state, its parent.
  std::vector<bool> visible(FrontScreen screen) const {
    const auto &nodes = fe.screens[size_t(screen)];
    std::vector<bool> shown(nodes.size());
    for (size_t i = 0; i < nodes.size(); ++i) {
      bool on = i == 0 || shown[nodes[i].parent];
      if (nodes[i].action == FrontAction::login_group) on = on && state == Screen::login;
      if (nodes[i].action == FrontAction::realm_group) on = on && state == Screen::realms;
      if (nodes[i].kind == FrontNode::BUTTON && on) {
        // Prev and next only where there is a neighbour to turn to.
        const auto order = slot_order();
        if (nodes[i].action == FrontAction::select_prev) on = focus != order.front();
        if (nodes[i].action == FrontAction::select_next) on = focus != order.back();
      }
      shown[i] = on;
    }
    return shown;
  }
  // The node rect on the canvas; the server group slides.
  std::array<float, 4> rect(FrontScreen screen, size_t i) const {
    auto r = fe.screens[size_t(screen)][i].rect;
    if (screen == FrontScreen::login && state == Screen::realms && in_realm_group(i)) {
      const float dy = slide - realm_height;
      r[1] += dy, r[3] += dy;
    }
    return r;
  }
  bool in_realm_group(size_t i) const {
    const auto &nodes = fe.screens[size_t(FrontScreen::login)];
    for (size_t j = i;; j = nodes[j].parent) {
      if (nodes[j].action == FrontAction::realm_group) return true;
      if (j == 0) return false;
    }
  }
  FrontAction hit(FrontScreen screen, float x, float y) const {
    const auto &nodes = fe.screens[size_t(screen)];
    const auto shown = visible(screen);
    for (size_t i = nodes.size(); i-- > 0;) {
      const auto &n = nodes[i];
      if (!shown[i] || n.action == FrontAction::none || (n.flags & FrontNode::FIXED_DISABLED)) continue;
      if (n.kind != FrontNode::BUTTON && n.kind != FrontNode::LIST) continue;
      const auto r = rect(screen, i);
      if (x >= r[0] && x < r[2] && y >= r[1] && y < r[3]) return n.action;
    }
    return FrontAction::none;
  }
  FrontAction hit(FrontScreen screen, std::array<float, 2> p) const { return hit(screen, p[0], p[1]); }
  int button_state(FrontScreen screen, size_t i) const {
    const auto &n = fe.screens[size_t(screen)][i];
    if (n.flags & FrontNode::FIXED_DISABLED) return 3;
    const bool over = n.action != FrontAction::none && hit(screen, pointer) == n.action;
    if (over && pressed == n.action) return 1;
    if (over || (n.flags & FrontNode::FIXED_ON)) return 2;
    return 0;
  }
  Output primary() {
    if (state == Screen::login) return act(FrontAction::login);
    if (state == Screen::realms) return act(FrontAction::realm_connect);
    if (state == Screen::create) return act(FrontAction::create_confirm);
    // Only at rest: 1097 takes the click outside the turn (0043b550) and
    // starts the clip only in state 2 (Select 0043ea30); nothing while the
    // camera turns or the start clip plays.
    if (state == Screen::select && choosing < 0 && !turning()) {
      Output out;
      if (focus < characters_shown()) {
        // GameProcCharacterSelect: the chosen character plays its "selected"
        // clip; the loading screen follows when it ends.
        // The select (1097: 0043ea30) sets it once with its own 0.6 s blend
        // (the package's start blend) and widens the spot to its theta.
        choosing = focus;
        set_clip(players.at(size_t(focus)), kStart, -1);
        theta = fe.slots[focus].spot.theta;
        spot_on = true;
        out.command = Command::select;
        out.character = list->characters(focus).id();
      } else {
        state = Screen::create;
        name.clear();
      }
      return out;
    }
    return {};
  }
  Output escape() {
    if (state == Screen::create) {
      enter_select();
      return {};
    }
    if (state == Screen::select) return act(FrontAction::back);
    return act(FrontAction::exit);
  }
  Output act(FrontAction action) {
    Output out;
    switch (action) {
    case FrontAction::login:
      if (state == Screen::login) out.command = Command::login;
      break;
    case FrontAction::exit: out.command = Command::exit; break;
    case FrontAction::realm_list: break;
    case FrontAction::realm_connect:
      if (state == Screen::realms && slide >= realm_height) {
        enter_select();
        face(0);
        out.command = Command::enter_realm;
      }
      break;
    case FrontAction::select_prev:
    case FrontAction::select_next: {
      // DoJobLeft/DojobRight (1097: 0043e310, 0043e380, reached from the
      // arrow buttons and DIK_LEFT/DIK_RIGHT, 00440690): nothing while the
      // camera turns or at the end of the row; otherwise the neighbour is in
      // focus at once and the camera turns to it (state 1).
      if (choosing >= 0 || turning()) break;
      const auto order = slot_order();
      int at = int(std::find(order.begin(), order.end(), focus) - order.begin());
      at = std::clamp(at + (action == FrontAction::select_next ? 1 : -1), 0, int(order.size()) - 1);
      // The turn keeps the spot's theta (1097: only the proc's init, the
      // select 0043ea30 and 0043f280 write +0x2d0).
      focus = order[at];
      break;
    }
    case FrontAction::back:
      if (state == Screen::create) enter_select();
      else if (state == Screen::select && choosing < 0) out.command = Command::back;
      break;
    case FrontAction::create_confirm:
      if (state == Screen::create && !pending_create) {
        if (name.empty()) {
          show_message("Enter a name: 1 to 24 letters, digits, _ or -.");
          break;
        }
        pending_create = true;
        known = list ? list->characters_size() : 0;
        out.command = Command::create;
        out.name = name;
      }
      break;
    default: break;
    }
    return out;
  }

  // --- 3D ------------------------------------------------------------------
  void lights(const FrontScene &scene, const std::vector<FrontLight> &extra) {
    std::vector<FrontLight> all = scene.lights;
    all.insert(all.end(), extra.begin(), extra.end());
    const int n = std::min<int>(int(all.size()), 9);
    glUniform1i(glGetUniformLocation(lit, "count"), n);
    for (int i = 0; i < n; ++i) {
      const auto &l = all[i];
      auto at = [&](const char *name) { return glGetUniformLocation(lit, (std::string(name) + "[" + std::to_string(i) + "]").c_str()); };
      glUniform1i(at("kind"), int(l.kind));
      glUniform3fv(at("ld"), 1, l.diffuse.data());
      glUniform3fv(at("la"), 1, l.ambient.data());
      glUniform3fv(at("lp"), 1, l.position.data());
      glUniform3fv(at("ldir"), 1, l.direction.data());
      glUniform3fv(at("latt"), 1, l.attenuation.data());
      glUniform4f(at("lr"), l.range, l.falloff, l.theta, l.phi);
    }
    glUniform3fv(glGetUniformLocation(lit, "ga"), 1, scene.ambient.data());
  }
  void material(V diffuse, V ambient, bool unlit, float cut) {
    glUniform3fv(glGetUniformLocation(lit, "md"), 1, diffuse.data());
    glUniform3fv(glGetUniformLocation(lit, "ma"), 1, ambient.data());
    glUniform1f(glGetUniformLocation(lit, "unlit"), unlit ? 1.f : 0.f);
    glUniform1f(glGetUniformLocation(lit, "cut"), cut);
  }
  void transform(const detail::Mat &view_projection, const detail::Mat &model) {
    const auto mvp = detail::mul(view_projection, model);
    glUniformMatrix4fv(glGetUniformLocation(lit, "mvp"), 1, GL_FALSE, mvp.data());
    glUniformMatrix4fv(glGetUniformLocation(lit, "model"), 1, GL_FALSE, model.data());
  }
  void draw_mesh(const Buffer &b, const FrontMesh &m, const detail::Mat &vp, const detail::Mat &model) {
    transform(vp, model);
    material(m.diffuse, m.ambient, false, (m.flags & FrontMesh::ALPHA_TEST) ? .5f : -1.f);
    if (m.flags & FrontMesh::DOUBLE_SIDED) glDisable(GL_CULL_FACE);
    else glEnable(GL_CULL_FACE);
    glBindTexture(GL_TEXTURE_2D, textures[m.texture]);
    glBindVertexArray(b.vao);
    glDrawElements(GL_TRIANGLES, b.count, GL_UNSIGNED_INT, nullptr);
  }
  // A posed character: skinned on the CPU (Scene::skin), drawn by its render
  // runs (N3SM) or as one opaque draw; KO's parts keep alpha test on.
  void draw_character(size_t which, const std::vector<Node> &pose, const detail::Mat &vp, const detail::Mat &model) {
    static const GLenum factors[] = {GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_SRC_ALPHA,
                                     GL_ONE_MINUS_SRC_ALPHA, GL_DST_ALPHA, GL_ONE_MINUS_DST_ALPHA,
                                     GL_DST_COLOR, GL_ONE_MINUS_DST_COLOR};
    const auto &scene = which == 0 ? fe.intro : which == 1 ? fe.select : fe.create;
    const auto vertices = scene.model.skin(pose);
    const auto mvp = detail::mul(vp, model);
    std::array<float, 4> box{1e9f, 1e9f, -1e9f, -1e9f};
    for (size_t v = 0; v + 2 < vertices.size(); v += 8) {
      float c[4];
      for (int i = 0; i < 4; ++i)
        c[i] = mvp[i] * vertices[v] + mvp[4 + i] * vertices[v + 1] + mvp[8 + i] * vertices[v + 2] + mvp[12 + i];
      if (c[3] <= 0) continue;
      box = {std::min(box[0], c[0] / c[3]), std::min(box[1], c[1] / c[3]), std::max(box[2], c[0] / c[3]),
             std::max(box[3], c[1] / c[3])};
    }
    std::array<int, 4> viewport{};
    glGetIntegerv(GL_VIEWPORT, viewport.data());
    drawn_boxes.push_back({which, box, viewport});
    glBindVertexArray(vao);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(float), vertices.data(), GL_STREAM_DRAW);
    for (unsigned a = 0; a < 3; ++a) {
      glEnableVertexAttribArray(a);
      glVertexAttribPointer(a, a == 2 ? 2 : 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void *)(a * 3 * sizeof(float)));
    }
    glDisableVertexAttribArray(3);
    transform(vp, model);
    glBindTexture(GL_TEXTURE_2D, models[which]);
    const V white{1, 1, 1};
    if (scene.model.runs.empty()) {
      glEnable(GL_CULL_FACE);
      material(white, white, false, 0);
      glDrawArrays(GL_TRIANGLES, 0, GLsizei(scene.model.indices.size()));
    }
    for (const auto &run : scene.model.runs) {
      if (run.flags & MaterialRun::BLEND) {
        glEnable(GL_BLEND);
        glBlendFunc(factors[run.source], factors[run.destination]);
      } else
        glDisable(GL_BLEND);
      if (run.flags & MaterialRun::DOUBLE_SIDED) glDisable(GL_CULL_FACE);
      else glEnable(GL_CULL_FACE);
      material(white, white, run.flags & MaterialRun::UNLIT, run.alpha_reference);
      glDrawArrays(GL_TRIANGLES, GLint(run.first), GLsizei(run.count));
    }
    glDisable(GL_BLEND);
    const auto &plugs = which == 0 ? intro_plugs : which == 1 ? select_plugs : create_plugs;
    for (size_t i = 0; i < plugs.size(); ++i) {
      const auto &plug = scene.plugs[i];
      const auto joint = scene.model.joint_matrix(pose, plug.joint);
      detail::Mat j;
      std::copy(joint.begin(), joint.end(), j.begin());
      draw_mesh(plugs[i], plug.mesh, vp, detail::mul(model, j));
    }
  }
  // CGameProcCharacterSelect's centre rect, 0.36-0.64 of the viewport's
  // width by 0.44-0.86 of its height, on the pointer's whole pixel. The hover
  // (1097: DoProcPreselect 0043f280) wants the pointer strictly inside the
  // scaled reals; the click (the tick 0043b550) uses PtInRect on the rect
  // truncated to whole pixels, so its left and top edges count.
  static constexpr double kFrontRect[4] = {double(.36f), double(.44f), double(.64f), double(.86f)};
  bool in_front() const {
    const double w = screen_size[0], h = screen_size[1];
    const double x = std::floor(screen_pointer[0]), y = std::floor(screen_pointer[1]);
    return w * kFrontRect[0] < x && x < w * kFrontRect[2] && h * kFrontRect[1] < y && y < h * kFrontRect[3];
  }
  bool clicked_front() const {
    const double w = screen_size[0], h = screen_size[1];
    const double x = std::floor(screen_pointer[0]), y = std::floor(screen_pointer[1]);
    return x >= std::trunc(w * kFrontRect[0]) && x < std::trunc(w * kFrontRect[2]) &&
           y >= std::trunc(h * kFrontRect[1]) && y < std::trunc(h * kFrontRect[3]);
  }
  // The camera still turning to the slot in focus (1097: state 1).
  bool turning() const { return at_slot != focus; }
  const Scene &clip_scene(size_t scene, size_t clip) const {
    return clips[scene][std::min(clip, clips[scene].size() - 1)];
  }
  float clip_length(size_t scene, size_t clip) const {
    float duration = .001f;
    for (const auto &track : clip_scene(scene, clip).tracks) duration = std::max(duration, track.keys.back().time);
    return duration;
  }
  // A clip's time at t: looping, or (KO's once-and-freeze) held on its last
  // frame once it has played.
  float clip_time(size_t scene, size_t clip, double t, bool loop) const {
    const float duration = clip_length(scene, clip);
    return loop ? float(std::fmod(t, double(duration))) : std::min(float(t), duration);
  }
  std::vector<Node> pose(size_t scene, size_t clip, double t, bool loop) {
    return clip_scene(scene, clip).sample(clip_time(scene, clip, t, loop));
  }
  // The select hall's clip player, as CN3Chr's (1097 binary: the setter
  // 00447e30, the frame tick 00445bb0). Selecting the clip already set
  // changes nothing; a negative blend is the clip's own blend time (FLT_MIN);
  // a blend starts from the frame the previous clip had reached and keeps
  // the new clip on its first frame until it ends; a clip played once holds
  // its last frame. A blend set during another starts from the frame that
  // one's clip was held on (its first): KO keeps only the frame, not the
  // blended pose (00447e30 stores +0x1c8 as the previous frame, +0x1d4, and
  // the joints blend those two frames, 00445e90), so its pose jumps there.
  void set_clip(Player &p, size_t clip, float blend) {
    if (clip == p.clip) return;
    p.from_time = played(p);
    p.from = p.clip;
    p.clip = clip;
    p.elapsed = 0;
    p.blend = blend < 0 ? fe.select.blends[clip] : blend;
  }
  float played(const Player &p) const { return std::clamp(p.elapsed - p.blend, 0.f, clip_length(1, p.clip)); }
  bool ended(const Player &p) const { return p.elapsed - p.blend >= clip_length(1, p.clip); }
  std::vector<Node> posed(const Player &p) const {
    auto now = clip_scene(1, p.clip).sample(played(p));
    if (p.elapsed >= p.blend) return now;
    return blend_pose(clip_scene(1, p.from).sample(p.from_time), std::move(now), p.elapsed / p.blend);
  }
  // CGameProcCharacterSelect::Init: AddChr sets the hover clip once with no
  // blend on every character (1097: 0043cee1-0043cf0b), the spot is off and
  // the info text hidden.
  void reset_hall() {
    players = {};
    theta = 0;
    spot_on = false;
    info_slot = -1;
  }
  void enter_select() {
    state = Screen::select;
    reset_hall();
  }
  detail::Mat view_projection(const FrontCamera &c, V eye, int width, int height) const {
    return detail::mul(detail::perspective(c.fov, width / float(std::max(height, 1)), c.near_plane, c.far_plane),
                       detail::look_at(eye, c.at, c.up));
  }
  // CGameProcLogIn_1098::Render: the moon as a screen quad (lighting off),
  // then the looping character under lights 0-2.
  void intro(int width, int height, double now) {
    const auto &r = fe.backdrop_rect;
    begin_ui(width, height);
    ui_scale = 1, ui_x = 0, ui_y = 0;
    quad(textures[fe.backdrop], {r[0] * width / 1024, r[1] * height / 768, r[2] * width / 1024, r[3] * height / 768},
         {0, 0, 1, 1}, 0xffffffff);
    flush();
    glEnable(GL_DEPTH_TEST);
    glUseProgram(lit);
    glUniform1i(glGetUniformLocation(lit, "tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    lights(fe.intro, {});
    const auto vp = view_projection(fe.intro.camera, fe.intro.camera.eye, width, height);
    draw_character(0, pose(0, 0, now, true), vp, detail::identity());
  }
  // CGameProcCharacterSelect: the hall, then each slot's character, the
  // camera turning about `at` to the slot in focus (select_turn_tick; the
  // tick the turn ends is still a turning tick, as 0043e4e0 runs no state-2
  // proc on it). At rest (1097: state 2,
  // DoProcPreselect 0043f280, every tick) the character in front plays the
  // hover clip once while the pointer is in the centre rect and the rest clip
  // (dummy, the hover clip's first frame) otherwise, each with its own blend
  // time, and is the only one ticked; the spot widens by spot_rate while the
  // pointer is there, up to its theta, narrows when it leaves and is off at 0;
  // the info text shows only while the pointer is there. While the camera
  // turns (state 1) nothing is ticked and the spot is off (0043b550 turns
  // every light off each tick). Starting (state 3, 0043ed20) ticks the
  // chosen character's start clip under the full spot: its blend first, on
  // the clip's first frame, then the clip, whose end (IsAnimEnd) comes after
  // both.
  void hall(int width, int height, double dt) {
    const bool rest = !turning();
    if (!rest && select_turn_tick(angle, slot_angle(at_slot), slot_angle(focus), float(dt))) at_slot = focus;
    const float widest = fe.slots[focus].spot.theta;
    if (choosing >= 0)
      players.at(size_t(choosing)).elapsed += float(dt);
    else if (rest) {
      const bool over = in_front();
      if (focus < characters_shown()) {
        set_clip(players.at(size_t(focus)), over ? kHover : kRest, -1);
        players.at(size_t(focus)).elapsed += float(dt);
      }
      theta = std::clamp(theta + (over ? 1 : -1) * fe.spot_rate * float(dt), 0.f, widest);
      spot_on = theta > 0;
      info_slot = over ? focus : -1;
    } else
      spot_on = false;
    const auto &c = fe.select.camera;
    turn_shown = {at_slot, focus, angle};
    const auto vp = view_projection(c, select_eye(c.eye, c.at, angle), width, height);
    glEnable(GL_DEPTH_TEST);
    glUseProgram(lit);
    glUniform1i(glGetUniformLocation(lit, "tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    auto spot = fe.slots[focus].spot;
    spot.theta = theta;
    lights(fe.select, spot_on ? std::vector<FrontLight>{spot} : std::vector<FrontLight>{});
    for (size_t i = 0; i < statics.size(); ++i) draw_mesh(statics[i], fe.hall[i], vp, detail::identity());
    const auto &front = players.at(size_t(focus));
    front_shown = {uint32_t(front.clip), played(front), clip_length(1, front.clip),
                   front.blend > 0 ? std::min(1.f, front.elapsed / front.blend) : 1.f, theta, spot_on, info_slot >= 0};
    for (int i = 0; i < characters_shown(); ++i) {
      const auto &slot = fe.slots[i];
      draw_character(1, posed(players.at(size_t(i))), vp, detail::translate_yaw(slot.position, slot.yaw));
    }
  }
  // Create: the player's own model breathing in `char_view`, as KO's
  // InventoryChrRender draws it in area_character.
  void character_view(int width, int height, double now) {
    const auto &nodes = fe.screens[size_t(FrontScreen::create)];
    auto it = std::find_if(nodes.begin(), nodes.end(), [](const auto &n) { return n.action == FrontAction::char_view; });
    const auto r = it->rect;
    const int x0 = int(ui_x + r[0] * ui_scale), y0 = int(ui_y + r[1] * ui_scale);
    const int w = std::max(1, int((r[2] - r[0]) * ui_scale)), h = std::max(1, int((r[3] - r[1]) * ui_scale));
    glViewport(x0, height - y0 - h, w, h);
    glEnable(GL_SCISSOR_TEST);
    glScissor(x0, height - y0 - h, w, h);
    glClear(GL_DEPTH_BUFFER_BIT);
    FrontCamera camera = fe.select.camera;
    camera.at = {0, .95f, 0};
    camera.fov = .75f;
    const V eye{0, 1.1f, -3.4f};
    glEnable(GL_DEPTH_TEST);
    glUseProgram(lit);
    glUniform1i(glGetUniformLocation(lit, "tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    FrontScene scene = {};
    scene.lights = {FrontLight{FrontLight::DIRECTIONAL, {1, 1, 1}, {.5f, .5f, .5f}, {}, {.3f, -.4f, 1}, 1, 0, {1, 0, 0}, 0, 0}};
    scene.ambient = {.3f, .3f, .3f};
    lights(scene, {});
    draw_character(2, pose(2, 0, now, true), view_projection(camera, eye, w, h), detail::translate_yaw({0, 0, 0}, 0));
    glDisable(GL_SCISSOR_TEST);
    glViewport(0, 0, width, height);
  }

  // --- UI ------------------------------------------------------------------
  void begin_ui(int width, int height) {
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(flat);
    glUniform2f(glGetUniformLocation(flat, "screen"), float(width), float(height));
    glUniform1i(glGetUniformLocation(flat, "tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    ui_scale = scale(width, height);
    ui_x = (width - fe.canvas_width * ui_scale) / 2;
    ui_y = (height - fe.canvas_height * ui_scale) / 2;
  }
  void flush() {
    if (batch.empty()) return;
    glUseProgram(flat);
    glBindVertexArray(vao);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, batch.size() * sizeof(float), batch.data(), GL_STREAM_DRAW);
    for (unsigned a = 0; a < 3; ++a) {
      glEnableVertexAttribArray(a);
      glVertexAttribPointer(a, a == 2 ? 4 : 2, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void *)((a == 0 ? 0 : a == 1 ? 2 : 4) * sizeof(float)));
    }
    glUniform1f(glGetUniformLocation(flat, "solid"), batch_solid ? 1.f : 0.f);
    glBindTexture(GL_TEXTURE_2D, batch_texture);
    glDrawArrays(GL_TRIANGLES, 0, GLsizei(batch.size() / 8));
    batch.clear();
  }
  // A quad in canvas units (or pixels with ui_scale 1); colour ARGB.
  void quad(GLuint texture, std::array<float, 4> r, std::array<float, 4> uv, uint32_t argb, bool solid = false) {
    if (texture != batch_texture || solid != batch_solid) {
      flush();
      batch_texture = texture;
      batch_solid = solid;
    }
    const float a = (argb >> 24) / 255.f, red = ((argb >> 16) & 255) / 255.f, g = ((argb >> 8) & 255) / 255.f,
                b = (argb & 255) / 255.f;
    // Whole screen pixels, as CN3UIImage::SetVB's integer rects: no pixel
    // centre on an edge, adjacent tiles meet without a gap or overlap.
    const float x0 = std::round(ui_x + r[0] * ui_scale), y0 = std::round(ui_y + r[1] * ui_scale),
                x1 = std::round(ui_x + r[2] * ui_scale), y1 = std::round(ui_y + r[3] * ui_scale);
    const float v[6][4] = {{x0, y0, uv[0], uv[1]}, {x1, y0, uv[2], uv[1]}, {x1, y1, uv[2], uv[3]},
                           {x0, y0, uv[0], uv[1]}, {x1, y1, uv[2], uv[3]}, {x0, y1, uv[0], uv[3]}};
    for (const auto &p : v) batch.insert(batch.end(), {p[0], p[1], p[2], p[3], red, g, b, a});
  }
  float advance(const FrontFont &f, char c) const { return c >= 32 && c < 127 ? f.advances[c - 32] : 0; }
  float width_of(const FrontFont &f, const std::string &s) const {
    float w = 0;
    for (char c : s) w += advance(f, c);
    return w;
  }
  // DrawText as CN3UIString lays it out: lines (split and, unless
  // SINGLELINE, wrapped at words), aligned by the style, the block centred
  // vertically with VCENTER. Glyphs are at (x - 2, y - top), y the cap top.
  void text(const std::string &value, uint32_t font_index, uint32_t color, uint32_t style, std::array<float, 4> r) {
    const auto &f = fe.fonts[font_index];
    const float line = std::round(f.pixels * 1.15f), cap = std::round(f.pixels * .905f) - f.height;
    std::vector<std::string> lines;
    std::string rest = value;
    for (;;) {
      const auto nl = rest.find('\n');
      std::string part = rest.substr(0, nl);
      while (!(style & detail::SINGLELINE) && width_of(f, part) > r[2] - r[0]) {
        size_t cut = std::string::npos;
        for (size_t at = part.find(' '); at != std::string::npos; at = part.find(' ', at + 1)) {
          if (width_of(f, part.substr(0, at)) > r[2] - r[0]) break;
          cut = at;
        }
        if (cut == std::string::npos) break;
        lines.push_back(part.substr(0, cut));
        part = part.substr(cut + 1);
      }
      lines.push_back(part);
      if (nl == std::string::npos) break;
      rest = rest.substr(nl + 1);
    }
    float y = r[1] + ((style & detail::VCENTER) ? std::round((r[3] - r[1] - line * lines.size()) / 2) : 0);
    for (const auto &l : lines) {
      const float w = width_of(f, l);
      float x = (style & detail::ALIGNCENTER) ? std::round(r[0] + (r[2] - r[0] - w) / 2)
                : (style & detail::ALIGNRIGHT) ? r[2] - w
                                               : r[0];
      for (char c : l) {
        if (c > 32 && c < 127) {
          const float u = ((c - 32) % 16) * 32 / 512.f, v = ((c - 32) / 16) * 32 / 192.f;
          quad(textures[f.texture], {x - 2, y + cap - f.top, x + 30, y + cap - f.top + 32},
               {u, v, u + 32 / 512.f, v + 32 / 192.f}, color);
        }
        x += advance(f, c);
      }
      y += line;
    }
  }
  std::string filled(FrontString key, const Context &context, const Character *c) const {
    auto s = fe.strings[size_t(key)];
    s = detail::replace(s, "{version}", context.version);
    s = detail::replace(s, "{class}", fe.strings[size_t(FrontString::class_name)]);
    if (c) {
      s = detail::replace(s, "{level}", std::to_string(std::max<uint32_t>(1, c->level())));
      s = detail::replace(s, "{name}", c->name());
    }
    return s;
  }
  void ui(FrontScreen screen, const Context &context, double now) {
    const auto &nodes = fe.screens[size_t(screen)];
    const auto shown = visible(screen);
    std::vector<int> state(nodes.size(), 0);
    for (size_t i = 0; i < nodes.size(); ++i) {
      if (!shown[i]) continue;
      const auto &n = nodes[i];
      const auto r = rect(screen, i);
      if (n.kind == FrontNode::BUTTON) state[i] = button_state(screen, i);
      if (i > 0 && nodes[n.parent].kind == FrontNode::BUTTON && !(n.mask & (1u << state[n.parent]))) continue;
      switch (n.kind) {
      case FrontNode::IMAGE:
        if (n.flags & FrontNode::FOREGROUND) {
          // CN3UIProgress: the foreground cut to the value.
          const float v = std::clamp(context.progress, 0.f, 1.f);
          quad(textures[n.texture], {r[0], r[1], r[0] + (r[2] - r[0]) * v, r[3]},
               {n.uv[0], n.uv[1], n.uv[0] + (n.uv[2] - n.uv[0]) * v, n.uv[3]}, 0xffffffff);
        } else
          quad(textures[n.texture], r, n.uv, 0xffffffff);
        break;
      case FrontNode::TEXT: {
        std::string value = n.text;
        switch (n.action) {
        case FrontAction::notice: value = context.notice; break;
        case FrontAction::char_info:
          // DisplayChrInfo (1097: 004402a0, text00, string 1201, or 1202 for
          // an empty slot) while the pointer is on the character in front;
          // DontDisplayInfo (004405a0) hides it otherwise.
          if (info_slot < 0) value.clear();
          else if (list && info_slot < characters_shown())
            value = filled(FrontString::select_info, context, &list->characters(info_slot));
          else
            value = filled(FrontString::select_hint, context, nullptr);
          break;
        case FrontAction::class_desc: value = filled(FrontString::class_desc, context, nullptr); break;
        case FrontAction::version: value = filled(FrontString::version, context, nullptr); break;
        case FrontAction::info: value = filled(FrontString::loading_info, context, nullptr); break;
        case FrontAction::message: value = message.value_or(""); break;
        default: break;
        }
        text(value, n.font, n.color, n.style, r);
        break;
      }
      case FrontNode::EDIT:
        if (n.action == FrontAction::name_field) {
          std::string shown_name = (n.style & detail::PASSWORD) ? std::string(name.size(), '*') : name;
          if (wants_text() && std::fmod(now, 1.0) < .5) shown_name += '_';
          text(shown_name, n.font, n.color, (n.style & ~detail::ALIGNCENTER) | detail::VCENTER | detail::SINGLELINE,
               {r[0] + 4, r[1], r[2] - 4, r[3]});
        }
        break;
      case FrontNode::LIST:
        if (n.action == FrontAction::realm_list) {
          const auto &f = fe.fonts[n.font];
          const float line = std::round(f.pixels * 1.3f);
          const std::array<float, 4> row{r[0] + 2, r[1] + 2, r[2] - 2, r[1] + 2 + line};
          quad(textures[n.texture], row, {0, 0, 1, 1}, 0x60406080, true);
          text(context.realm, n.font, n.color, detail::SINGLELINE | detail::VCENTER, {row[0] + 4, row[1], row[2], row[3]});
        }
        break;
      default: break;
      }
    }
  }
};

}  // namespace n3e::front
