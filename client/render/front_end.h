#pragma once
// Spec 11's KO front end: the logo screen when the package has one (RQ-101,
// 1264's), login (the 1098 intro scene), the realm list, the
// Karus character select hall, create, loading and KO's message box (OK, or
// RQ-111's yes/no for the select's exit), drawn
// from front-end.bin (content/front-end.md). The screens are a state machine
// here; the viewer turns each Command into the protocol message it already
// sends for the legacy panels, and tells this module what the server said.
#include "assets/assets.h"
#include "assets/front_place.h"
#include "platform/gl.h"
#include "platform/gl_load.h"
#include "render/animation.h"
#include "render/create_choice.h"
#include "render/front_logo.h"
#include "render/front_login.h"
#include "render/front_slide.h"
#include "render/message_box.h"
#include "render/scene_clock.h"
#include "render/select_bar.h"
#include "render/select_hall.h"
#include "render/select_path.h"
#include "render/select_turn.h"
#include "render/select_zone.h"
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

// logo (RQ-101) is last so the others keep their numbers.
enum class Screen { login, realms, select, create, loading, logo };
enum class Command { none, login, exit, enter_realm, select, create, back };
struct Output {
  Command command = Command::none;
  uint64_t character = 0;  // select
  std::string name;        // create
  // An audio.bin key the viewer plays once, unpositioned, stopping the
  // previous play of the same key (RQ-077: the select arrows' turn sound).
  const char *sound = nullptr;
};
// RQ-077 (Q70): the key the package binds the select arrows' turn sound to.
inline constexpr const char *kSelectTurnSound = "front:select-turn";
// What the viewer knows this frame.
struct Context {
  std::string realm;         // realm.json's name
  std::string notice;        // the login line (spec 02's flow status)
  std::string version;       // shown by the loading screen's `version` text
  const Characters *characters = nullptr;
  float progress = 0;        // loading: 0..1
};
// The select hall's character in front as the last frame showed it (a test
// hook): its clip (0 front, 1 start, 2 rest), that clip's time and length
// (seconds), how far the blend into it has run (1: none or done), the spot's
// theta and whether the spot is on, and whether the info text shows.
struct FrontPose {
  uint32_t clip = 0;
  float time = 0, length = 0, blend = 1, theta = 0;
  bool spot = false, info = false;
};
// The select camera as the last frame showed it (a test hook): the slot it is
// at (-1 while the entry path flies it in), the slot in focus (they differ
// while it turns) and its turn from the scene camera's eye (radians, positive
// to the left; select_turn). The path mode (RQ-087): the path playing (its
// index in the package, -1 none), its frame and last frame, and whether the
// select UI shows (1298 hides it while the camera moves).
struct FrontTurn {
  int slot = 0, focus = 0;
  float angle = 0;
  int path = -1;
  float frame = 0, frames = 0;
  bool ui = true;
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
    // RQ-101: KO 1264's WinMain makes the logo the first procedure
    // (00602506: ProcActiveSet of the logo, once per process).
    if (fe.logo) state = Screen::logo;
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
    for (const auto &z : fe.zone) use[z.mesh.texture] = 2;
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
uniform vec3 fog,fogcolor,eye;
vec4 fogged(vec4 c){if(fog.x<.5)return c;
float f=clamp((fog.z-length(wp-eye))/(fog.z-fog.y),0.,1.);return vec4(mix(fogcolor,c.rgb,f),c.a);}
void main(){vec4 c=texture(tex,uv);if(c.a<=cut)discard;if(unlit>.5){o=fogged(c);return;}
vec3 N=normalize(wn);vec3 col=ma*ga;
for(int i=0;i<count;i++){vec3 L;float a=1.,s=1.;
if(kind[i]==3)L=normalize(-ldir[i]);else{vec3 d=lp[i]-wp;float r=length(d);if(r>lr[i].x)continue;L=d/max(r,1e-5);
a=1./max(latt[i].x+latt[i].y*r+latt[i].z*r*r,1e-5);
if(kind[i]==2){float rho=dot(normalize(ldir[i]),-L),ct=cos(lr[i].z*.5),cp=cos(lr[i].w*.5);
if(rho<=cp)s=0.;else if(rho<ct)s=pow((rho-cp)/max(ct-cp,1e-5),lr[i].y);}}
col+=a*s*(ma*la[i]+md*ld[i]*max(dot(N,L),0.));}
o=fogged(vec4(c.rgb*clamp(col,0.,1.),c.a));})");
    flat = program(R"(#version 330 core
layout(location=0) in vec2 p;layout(location=1) in vec2 t;layout(location=2) in vec4 c;uniform vec2 screen;
out vec2 uv;out vec4 tint;void main(){uv=t;tint=c;gl_Position=vec4(p.x/screen.x*2.-1.,1.-p.y/screen.y*2.,0,1);})",
                   R"(#version 330 core
in vec2 uv;in vec4 tint;out vec4 o;uniform sampler2D tex;uniform float solid;
void main(){o=(solid>.5?vec4(1):texture(tex,uv))*tint;})");
    glGenVertexArrays(1, &vao);
    glGenBuffers(1, &vbo);
    for (auto &mesh : fe.hall) statics.push_back(upload(mesh));
    for (auto &z : fe.zone) zone_meshes.push_back(upload(z.mesh));
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
    for (const auto &node : fe.screens[size_t(FrontScreen::login)]) {
      if (node.action == FrontAction::realm_group) realm_height = node.rect[3] - node.rect[1];
    }
    seats.mode = fe.front_clip;
    for (size_t i = 0; i < seats.length.size(); ++i) {
      seats.length[i] = clip_length(1, i);
      seats.blends[i] = fe.select.blends[i];
    }
    fe.intro.model.texture.clear();
    fe.select.model.texture.clear();
    fe.create.model.texture.clear();
  }
  ~View() {
    glDeleteTextures(GLsizei(textures.size()), textures.data());
    glDeleteTextures(GLsizei(models.size()), models.data());
    for (auto *set : {&statics, &zone_meshes, &intro_plugs, &select_plugs, &create_plugs})
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
    // RQ-101: the logo's track from its delay until its fade-out has run;
    // the login's Init then releases it (1264: 005bd9b0 at 005bdd80), so a
    // skip cuts it off.
    if (state == Screen::logo)
      return logo_music_on(*fe.logo, logo_time) ? fe.music[fe.logo->music] : nullptr;
    const auto index = fe.screen_music[size_t(layout())];
    return index == FrontEnd::kNoMusic ? nullptr : fe.music[index];
  }
  // The music's gain (1, or the logo track's fade-out).
  float music_gain() const { return state == Screen::logo ? logo_music_gain(*fe.logo, logo_time) : 1.f; }
  // RQ-101: 1264's logo UI hides the system cursor (00601140: SetCursor(NULL)).
  bool cursor_hidden() const { return state == Screen::logo && (fe.logo->flags & FrontLogo::HIDE_CURSOR); }
  const std::optional<FrontLogo> &logo() const { return fe.logo; }
  // The logo screen as the last frame drew it, and its time (a test hook).
  LogoFrame logo_shown() const { return logo_drawn; }
  double logo_seconds() const { return logo_time; }
  bool has_music() const { return !fe.music.empty(); }
  // RQ-104: what the device plays of the music (AudioDevice::heard_music),
  // before each draw; the login scene keeps time by its own track's.
  void heard_music(const HeardMusic &h) { heard = h; }
  // The login scene's clock as the last frame left it (a test hook).
  const SceneClock &scene() const { return scene_clock; }
  // RQ-108: whether a login is under way (the viewer's, each frame): KO hides
  // the login group from a login press until its answer and shows the node
  // bound to login_closed meanwhile (render/front_login.h).
  void login_waiting(bool on) { waiting = on; }
  // RQ-123 (KO-FINDINGS 9.12): a Back's login and the realm list after it
  // (the viewer's BackHold, each frame): the node bound to login_closed stays
  // hidden, as 1264's Back reaches its list without SetVisibleLogInUIs.
  void login_line_hidden(bool on) { line_hidden = on; }
  // Whether the current layout's node bound to `action` draws in this state,
  // the message box's for its own actions (a test hook; false without one).
  bool action_shown(FrontAction action) const {
    const auto screen = message_action(action) ? FrontScreen::message : layout();
    const auto &nodes = fe.screens[size_t(screen)];
    const auto shown = visible(screen);
    for (size_t i = 0; i < nodes.size(); ++i)
      if (nodes[i].action == action) return shown[i];
    return false;
  }
  // The Discord login finished: KO's OpenServerList.
  void logged_in() {
    // A message box (a kick, a drop) stays over the login screen until OK.
    if (state != Screen::login || message) return;
    state = Screen::realms;
    slide = 0;
  }
  // Back to the login screen (a dropped or reset connection). The logo
  // screen plays on: KO 1264 connects only from its login, after it.
  void reset() {
    if (state != Screen::logo) state = Screen::login;
    waiting = line_hidden = false;  // the connection, and any login on it, is gone
    choosing = -1;
    pending_create = false;
    create_flying = false;
  }
  // KO's message box. During the logo screen it waits for the login (Q82):
  // 1264 connects and logs in only from its login procedure, so nothing it
  // reports can show over the logo; the latest waiting message shows then.
  // RQ-102 (Q81): the package words each kind of message: its title (the
  // node bound to `title`), and a text that replaces the client's own; a kind
  // it does not word shows untitled in the client's words. RQ-111: the box
  // takes the message's style (render/message_box.h): exit_confirm's Yes and
  // No, every other message's OK.
  void show_message(FrontMessage kind, std::string text) {
    const auto &worded = fe.messages[size_t(kind)];
    Message m{worded.replaces ? worded.text : std::move(text), worded.title, kind};
    if (state == Screen::logo) deferred = std::move(m);
    else message = std::move(m);
  }
  bool showing_message() const { return message.has_value(); }
  // The message showing, and its box's style (a test hook; none: an OK box).
  std::optional<FrontMessage> message_kind() const {
    return message ? std::optional<FrontMessage>(message->kind) : std::nullopt;
  }
  // RQ-112 (version 17, KO-FINDINGS 9.12): where the select's Back lands, as
  // the package says: the login (the realm's) or, through a login the viewer
  // holds from the click with the bar hidden, the realm list (1298's Back sets
  // its login procedure's +0x21, whose Init connects, asks for the server list
  // and hides the bar, 005f68e0; 1264's +0x35, 005bd9b0, its line hidden too,
  // RQ-123: render/front_login.h BackHold).
  FrontSelectBack back_lands() const { return fe.select_back; }
  bool creating() const { return pending_create; }
  // The character in front as the last select frame showed it; the test
  // client checks the hover, its blends, the spot and the info text.
  FrontPose front_pose() const { return front_shown; }
  FrontTurn front_turn() const { return turn_shown; }
  // RQ-125 (version 19): whether create draws over the hall (a test hook).
  bool create_over_hall() const { return over_hall(); }
  // RQ-126 (version 20): each node of create's slide's top-left in window
  // pixels as the last frame left it, and whether the slide is still under
  // way (a test hook; empty without a slide).
  std::vector<std::array<int, 2>> create_slide_at(int width, int height) {
    std::vector<std::array<int, 2>> at;
    const auto [s, ox, oy] = view(width, height);
    for (const auto &n : fe.create_slide.nodes) {
      const auto r = rect(FrontScreen::create, n.node);
      at.push_back({int(std::lround(ox + r[0] * s)), int(std::lround(oy + r[1] * s))});
    }
    return at;
  }
  bool create_sliding() const { return create_slide.on; }
  // RQ-130 (version 21): whether create waits for a race click, and the slot
  // the new character stands at over the hall (-1: none stands, no race
  // chosen) (test hooks).
  bool create_waits() const { return choice.waits_race || choice.waits_class; }
  int create_figure() const { return choice.stands() ? choice.stands_at(focus) : -1; }
  // RQ-133 (version 22), RQ-145 (version 23): the ids of create's nodes
  // with `flag` (FrontNode::UNTIL_RACE or UNTIL_CLASS) that draw now (a test
  // hook).
  std::vector<std::string> until_drawn(uint32_t flag) const {
    const auto &nodes = fe.screens[size_t(FrontScreen::create)];
    const auto shown = visible(FrontScreen::create);
    std::vector<std::string> out;
    for (size_t i = 0; i < nodes.size(); ++i)
      if ((nodes[i].flags & flag) && shown[i]) out.push_back(nodes[i].id);
    return out;
  }
  // The state the current layout's button bound to `action` draws in (0
  // normal, 1 down, 2 on, 3 disabled), or -1 (a test hook).
  int action_state(FrontAction action) const {
    const auto screen = layout();
    const auto &nodes = fe.screens[size_t(screen)];
    for (size_t i = 0; i < nodes.size(); ++i)
      if (nodes[i].action == action && nodes[i].kind == FrontNode::BUTTON) return button_state(screen, i);
    return -1;
  }
  const std::string &message_text() const { static const std::string none; return message ? message->text : none; }
  const std::string &message_title() const { static const std::string none; return message ? message->title : none; }
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
      show_message(FrontMessage::create_refused, detail);
    } else if (state == Screen::loading || choosing >= 0) {
      state = Screen::select;
      choosing = -1;
      // Back at rest (1097: state 2) the character in front leaves the start
      // clip now, for the clip DoProcPreselect sets (1298: 005fef90), so a
      // start right after the refusal plays the start clip again rather than
      // finding it ended.
      if (focus < characters_shown()) seats.front_at_rest(seats.players.at(size_t(focus)), in_front());
      show_message(FrontMessage::select_refused, detail);
    }
  }
  // Loading: the selection animation has played and the screen shows.
  void loading() { state = Screen::loading; }

  // Test hooks (spec 11's captures): a screen at rest, the characters the
  // last frame drew (their boxes in normalised device coordinates of the
  // viewport they were drawn in), and a bound node's rect in pixels.
  void jump(Screen to) {
    state = to == Screen::logo && !fe.logo ? Screen::login : to;
    logo_time = 0;
    logo_start_ns = 0;
    deferred.reset();
    message.reset();
    choosing = -1;
    pending_create = false;
    create_flying = false;
    waiting = line_hidden = false;
    slide = realm_height;
    slide_rest(create_slide);
    update_slide();
    open_choice();
    reset_hall();
    face(0);
  }
  // RQ-113: the select at rest with the slot `at` places from the left of the
  // row in focus (a test hook; the row's ends are 0 and the slot count - 1).
  void select_at(int at) {
    jump(Screen::select);
    const auto order = slot_order();
    face(order[size_t(std::clamp(at, 0, int(order.size()) - 1))]);
  }
  // The logo screen `t` seconds in (a test hook; nothing without one).
  void logo_at(double t) {
    if (!fe.logo) return;
    jump(Screen::logo);
    logo_time = t;
  }
  struct Drawn {
    size_t which;                  // 0 intro, 1 select, 2 create
    std::array<float, 4> box;      // x0 y0 x1 y1 in the viewport's NDC, y up
    std::array<int, 4> viewport;   // GL viewport: x, y (from the bottom), w, h
  };
  const std::vector<Drawn> &drawn() const { return drawn_boxes; }
  std::optional<std::array<float, 4>> action_rect(FrontAction action, int width, int height) {
    const auto screen = message_action(action) ? FrontScreen::message : layout();
    const auto &nodes = fe.screens[size_t(screen)];
    for (size_t i = 0; i < nodes.size(); ++i)
      if (nodes[i].action == action) {
        const auto [s, ox, oy] = view(width, height);
        const auto r = rect(screen, i);
        return std::array<float, 4>{ox + r[0] * s, oy + r[1] * s, ox + r[2] * s, oy + r[3] * s};
      }
    return std::nullopt;
  }
  // Where the canvas's (0, 0) is in the window as the current layout's root
  // (the logo's on the logo screen) carries it, and the scale (a test hook):
  // KO's placement moves the root to the window's own pixels, scale 1.
  std::array<float, 3> layout_origin(int width, int height) {
    const auto [s, ox, oy] = view(width, height);
    const size_t at = state == Screen::logo ? FrontEnd::kLogoLayout : size_t(layout());
    const auto &nodes = front_layout(fe, at);
    return {ox + (placed[at][0][0] - nodes[0].rect[0]) * s, oy + (placed[at][0][1] - nodes[0].rect[1]) * s, s};
  }
  static bool message_action(FrontAction action) {
    return action == FrontAction::message || action == FrontAction::ok || action == FrontAction::title ||
           action == FrontAction::yes || action == FrontAction::no;
  }
  // Whether the layouts are scaled to the window (fe.scale_to_window, or a
  // window smaller than the canvas) at this size.
  bool scaled_at(int width, int height) {
    place(width, height);
    return scaled;
  }

  Output event(const SDL_Event &e, float x, float y, int width, int height) {
    Output out;
    const auto [s, ox, oy] = view(width, height);
    const float cx = (x - ox) / s, cy = (y - oy) / s;
    if (e.type == SDL_EVENT_MOUSE_MOTION) {
      pointer = {cx, cy};
      screen_pointer = {x, y};
      screen_size = {width, height};
      return out;
    }
    if (message) {
      // KO's box (render/message_box.h): ENTER and the keypad's ENTER press
      // OK or Yes, ESC OK or No (1298's OnKeyPress 00527c60); a click
      // released on a button the box shows presses it. Yes on exit_confirm
      // leaves the game (BEHAVIOR_EXIT); every press closes the box.
      FrontAction button = FrontAction::none;
      if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat) {
        const auto key = e.key.key == SDLK_RETURN || e.key.key == SDLK_KP_ENTER ? BoxKey::enter
                         : e.key.key == SDLK_ESCAPE                             ? BoxKey::escape
                                                                                : BoxKey::none;
        button = box_key(box_style(message->kind), key);
      } else if (e.type == SDL_EVENT_MOUSE_BUTTON_UP && e.button.button == SDL_BUTTON_LEFT)
        button = hit(FrontScreen::message, cx, cy);
      if (e.type == SDL_EVENT_MOUSE_BUTTON_DOWN) pressed = hit(FrontScreen::message, cx, cy);
      const auto answer = box_press(message->kind, button);
      if (answer.exits) out.command = Command::exit;
      if (answer.closes) message.reset(), pressed = FrontAction::none;
      return out;
    }
    if (state == Screen::loading) return out;
    // RQ-101: 1264's logo UI takes every key press (OnKeyPress 00601480,
    // which ProcessUIKeyInput 005f97a0 calls for each DirectInput key down
    // on the focused UI) and starts the login; a click does nothing (it
    // keeps CN3UIBase's MouseProc).
    // Only a press during the screen counts (logo_key_skips, Q82): not one
    // queued before its first frame, nor a modifier reported as held when
    // the window gains focus.
    if (state == Screen::logo) {
      if (e.type == SDL_EVENT_WINDOW_FOCUS_GAINED) focus_ns = e.window.timestamp;
      if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat && (fe.logo->flags & FrontLogo::SKIP_KEY) &&
          logo_key_skips(logo_start_ns, focus_ns, e.key.timestamp, modifier(e.key.key)))
        leave_logo();
      return out;
    }
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
      // RQ-114: neither skips btn_create's fly (state 6: ENTER skips in
      // states 1 and 2 only, the tick's ESC in every state but 6 and 7), and
      // nothing else takes them while it plays.
      if ((enter || key == SDLK_ESCAPE) && create_flying) return out;
      // The path mode (1298): ENTER (005fe280) and ESC (the tick 005faf10,
      // the input's +0x270) while the camera moves put it on its path's last
      // frame and arrive (state 5, the UI shown); the click does nothing then.
      if ((enter || key == SDLK_ESCAPE) && state == Screen::select && paths() && choosing < 0 && turning()) {
        skip = true;
        return out;
      }
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
    hall_camera.reset();
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
    if (state == Screen::logo) {
      // KO's frame time drives the fade (00601360 adds s_fSecPerFrm); the
      // first frame is the screen's start. After the last group the login
      // starts (005f7f30).
      if (logo_start_ns == 0) logo_start_ns = SDL_GetTicksNS();
      logo_time += dt;
      logo_drawn = logo_frame(*fe.logo, logo_time);
      if (logo_drawn.done) leave_logo();
    }
    // RQ-104: the login scene's clock starts at its entry and keeps its
    // track's time (scene_clock.h).
    const bool scene = state == Screen::login || state == Screen::realms;
    const double scene_time = scene_clock.tick(scene, now, scene ? music().get() : nullptr, heard);
    if (scene) intro(width, height, scene_time);
    // RQ-114: btn_create's fly has arrived (1298: 005fe5b0 case 6, on the
    // tick after the one that reached the path's last frame, sets state 7
    // and the slot): the realm's create screen opens, the camera left on the
    // path's last frame behind it.
    if (state == Screen::select && create_flying && path_camera.ended()) {
      at_slot = focus;
      create_flying = false;
      open_create();
    }
    // RQ-125 (version 19): a create over the hall draws the hall behind it,
    // as 1298's Render (005fb1c0) draws it in every state.
    if (state == Screen::select || in_hall_create()) hall(width, height, dt, now);
    // RQ-126 (version 20): create's slide, a step a frame while create shows
    // (1298's UI manager ticks the create window, 00606450, after the click
    // that shows it and before the frame renders; message box or none).
    if (state == Screen::create && create_slide.on) {
      place(width, height);
      slide_tick(fe.create_slide, placed[size_t(FrontScreen::create)], slide_extent(), create_slide, dt);
      update_slide();
    }
    // IsAnimEnd: the start clip has played once, after its blend (1097:
    // 0043ed20 reads the loop count, which 00445bb0 counts only past the
    // clip's end, and the frame stays on the start during the blend).
    if (state == Screen::select && choosing >= 0 && seats.ended(seats.players.at(size_t(choosing)))) {
      choosing = -1;
      state = Screen::loading;
    }
    begin_ui(width, height);
    if (state == Screen::logo)
      logo_ui();
    else
      ui(layout(), context, now);
    if (state == Screen::create && !in_hall_create() && choice.stands()) {
      flush();
      character_view(width, height, now);
      begin_ui(width, height);
    }
    if (message) ui(FrontScreen::message, context, now);
    flush();
    // The zone's alpha parts after the UI, only while the select is the
    // screen (not on the frame the start clip's end turns it to loading), or
    // a create over it (1298: Render's alpha flush after every window).
    if (hall_camera && (state == Screen::select || in_hall_create()))
      zone_alpha(hall_camera->first, hall_camera->second);
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
    glDisable(GL_BLEND);
  }

 private:
  struct Buffer { GLuint vao = 0, vbo = 0, ebo = 0; GLsizei count = 0; };
  FrontEnd fe;
  std::vector<GLuint> textures, models;
  GLuint lit = 0, flat = 0, vao = 0, vbo = 0;
  std::vector<Buffer> statics, zone_meshes, intro_plugs, select_plugs, create_plugs;
  std::vector<std::vector<Scene>> clips;  // per scene: each clip's poses
  Screen state = Screen::login;
  struct Message {
    std::string text, title;
    FrontMessage kind = FrontMessage::disconnected;
  };
  std::optional<Message> message;
  std::array<float, 2> pointer{-1, -1};
  FrontAction pressed = FrontAction::none;
  float realm_height = 0, slide = 0;
  // RQ-126 (version 20): create's slide, and each create node's shift from
  // where the moves put it (empty at rest).
  SlideState create_slide;
  std::vector<std::array<float, 2>> slide_shift;
  // RQ-130 (version 21): create's race and class, when the package waits for them.
  CreateChoice choice;
  bool waiting = false;  // RQ-108: a login under way (login_waiting)
  bool line_hidden = false;  // RQ-123: a Back's login and list (login_line_hidden)
  // The select camera: the slot it is at and the slot in focus, which is the
  // one it turns to from the press on (1097: CGameProcCharacterSelect's
  // positions +0x2c4 and +0x2c8, the selected index 006e04d0), and its turn
  // from the scene camera's eye (select_turn).
  int focus = 0, at_slot = 0, choosing = -1, known = 0;
  float angle = 0;
  // The path mode (version 7, RQ-087): the camera on its path, and an ENTER
  // or ESC that skips to its last frame on the next tick.
  PathCamera path_camera;
  bool skip = false;
  // RQ-114: btn_create's fly to the first empty slot is playing; create
  // opens when it arrives.
  bool create_flying = false;
  // RQ-101: seconds since the logo screen started, and its last frame; its
  // first frame's and the last focus gain's SDL times (0: none yet); a
  // message waiting for the login.
  double logo_time = 0;
  LogoFrame logo_drawn;
  uint64_t logo_start_ns = 0, focus_ns = 0;
  std::optional<Message> deferred;
  void leave_logo() {
    state = Screen::login;
    if (deferred) message = std::move(deferred), deferred.reset();
  }
  // The modifiers SDL reports as held on a focus gain (SDL 3.4, Wayland).
  static bool modifier(SDL_Keycode k) {
    switch (k) {
      case SDLK_LSHIFT: case SDLK_RSHIFT: case SDLK_LCTRL: case SDLK_RCTRL: case SDLK_LALT:
      case SDLK_RALT: case SDLK_LGUI: case SDLK_RGUI: case SDLK_MODE: case SDLK_LEVEL5_SHIFT:
        return true;
      default:
        return false;
    }
  }
  FrontTurn turn_shown;
  double last_frame = -1;
  SceneClock scene_clock;
  HeardMusic heard;
  // The select camera this frame drew the hall with, for the zone's BLEND
  // meshes after the UI (version 8); none on a frame without the hall.
  std::optional<std::pair<detail::Mat, V>> hall_camera;
  // The select hall as CGameProcCharacterSelect keeps it (select_hall.h):
  // each slot's clip player, the spot's theta and whether it is on, the
  // slot whose info text shows, in the package's front-clip mode.
  SelectHall seats;
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
  // RQ-106 (Q82): each layout's rects at the window size they were placed
  // for (the five screens, then the logo), in window pixels as KO places them,
  // or the canvas rects when `scaled`.
  std::array<std::vector<std::array<float, 4>>, size_t(FrontScreen::count) + 1> placed;
  std::array<int, 2> placed_size{-1, -1};
  bool scaled = false;

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
  // RQ-106 (Q82): KO draws its UI unscaled, each layout placed on the
  // window's own pixels by its moves (front_place.h); the realm's scaling of
  // the canvas to fit the window is the package's option, and the fallback
  // for a window smaller than the canvas, so nothing is cut off.
  void place(int width, int height) {
    if (placed_size[0] == width && placed_size[1] == height) return;
    placed_size = {width, height};
    scaled = front_scaled(fe, width, height);
    for (size_t at = 0; at < placed.size(); ++at) placed[at] = front_layout_rects(fe, at, width, height);
    update_slide();
  }
  // RQ-126 (version 20): create's slide. Opening create starts it at 0 (1298's
  // SetVisible 00606650); each node and its subtree are shifted on the node's
  // axis from where the moves put them to where the slide has it.
  void open_create() {
    state = Screen::create;
    name.clear();
    open_choice();
    // No slide (the 1097 choice): create stays at rest, as before version 20.
    if (fe.create_slide.nodes.empty()) slide_rest(create_slide);
    else slide_open(create_slide);
    update_slide();
  }
  // RQ-130 (version 21): each open starts with nothing chosen that the
  // package's create waits for (1298's Init 005fab40 and Cancel 005ffb90).
  void open_choice() {
    bool race = false, klass = false;
    for (const auto &n : fe.screens[size_t(FrontScreen::create)])
      race = race || n.action == FrontAction::create_race, klass = klass || n.action == FrontAction::create_class;
    choice.open(race, klass);
  }
  std::array<int, 2> slide_extent() const {
    return scaled ? std::array<int, 2>{int(fe.canvas_width), int(fe.canvas_height)} : placed_size;
  }
  void update_slide() {
    slide_shift.clear();
    const auto &slide = fe.create_slide;
    const auto &rects = placed[size_t(FrontScreen::create)];
    if (slide.nodes.empty() || create_slide.rest || rects.empty()) return;
    const auto at = slide_coordinates(slide, rects, slide_extent(), create_slide);
    const auto &nodes = fe.screens[size_t(FrontScreen::create)];
    slide_shift.assign(nodes.size(), {0.f, 0.f});
    std::vector<char> inside(nodes.size());
    for (size_t k = 0; k < slide.nodes.size(); ++k) {
      const auto &n = slide.nodes[k];
      const float delta = float(at[k] - rects[n.node][n.axis]);
      std::fill(inside.begin(), inside.end(), 0);
      inside[n.node] = 1;
      for (size_t j = n.node; j < nodes.size(); ++j) {
        if (j > n.node) inside[j] = inside[nodes[j].parent];
        if (inside[j]) slide_shift[j][n.axis] += delta;
      }
    }
  }
  // The transform from the placed rects to window pixels: the scale and the
  // canvas's offset when scaled, none otherwise.
  std::array<float, 3> view(int width, int height) {
    place(width, height);
    return front_view(fe, width, height);
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
  bool paths() const { return fe.turn == FrontTurnMode::path; }
  // RQ-125 (version 19): create is a window of the select, drawn over the
  // hall (1298's +0x388, co_characterCreate_us.uif; KO-FINDINGS 9.15).
  bool over_hall() const { return fe.create_mode == FrontCreateMode::hall; }
  bool in_hall_create() const { return state == Screen::create && over_hall(); }
  // Create's Cancel (and ESC): back to the select. Over the hall the camera
  // that still flies to the slot is put on it, the select at rest there with
  // its UI shown (1298's Cancel 005ffb90 sets state 5 and shows the bar at
  // once; what its camera does after a Cancel mid-flight was not read).
  void leave_create() {
    const bool flying = over_hall() && turning();
    enter_select();
    if (flying) {
      if (paths()) path_camera.finish();
      at_slot = focus;
      if (!paths()) angle = slot_angle(focus);
    }
  }
  // The path from slot `from` (FrontPath::kEntry: the entry path) to `to`;
  // load_front_end checked those the arrows and the entry take are there.
  const FrontPath *path_to(uint32_t from, uint32_t to) const {
    for (const auto &p : fe.paths)
      if (p.from == from && p.to == to) return &p;
    return nullptr;
  }
  // The camera at rest on the slot, which is in focus. The path mode's rest
  // there is the last frame of the path into it: the entry path's for slot 0,
  // the one from slot 0 for the others.
  void face(int slot) {
    focus = at_slot = slot;
    skip = false;
    if (paths()) {
      angle = 0;
      const auto *p = path_to(slot == 0 ? FrontPath::kEntry : 0, uint32_t(slot));
      if (p) path_camera.start(*p), path_camera.finish();
    } else
      angle = slot_angle(slot);
  }
  // The path mode's entry (1298: Init 005f98c0 sets state 1 and loads the
  // entry path, 005fa670(1), the select UI hidden): the camera flies in to
  // slot 0, which is in focus; it has arrived on the path's last frame
  // (005fe5b0 case 1).
  void fly_in() {
    if (!paths()) return;
    focus = 0;
    at_slot = -1;
    skip = false;
    path_camera.start(*path_to(FrontPath::kEntry, 0));
  }
  // 1298 hides the select UI while the camera moves (005fe3c0, 005fe450 and
  // Init call its +0x3c with 0, the arrival 005fe5b0 with 1; Q77).
  bool ui_hidden() const { return paths() && state == Screen::select && turning(); }
  // Whether node i draws in this state: its group's state, its parent.
  std::vector<bool> visible(FrontScreen screen) const {
    const auto &nodes = fe.screens[size_t(screen)];
    std::vector<bool> shown(nodes.size());
    if (screen == FrontScreen::select && ui_hidden()) return shown;
    for (size_t i = 0; i < nodes.size(); ++i) {
      bool on = i == 0 || shown[nodes[i].parent];
      // The login group, the realm group and (RQ-108) the node KO shows while
      // the login group is hidden, each in its states only (RQ-123: the
      // last not after a Back to the realm list).
      on = on && login_state_shows(nodes[i].action, state == Screen::login, state == Screen::realms, waiting,
                                   line_hidden);
      // RQ-111: the message box's buttons by its style (SetBoxStyle 00527a40).
      if (screen == FrontScreen::message && message) on = on && box_shows(nodes[i].action, box_style(message->kind));
      if (nodes[i].kind == FrontNode::BUTTON && on &&
          (nodes[i].action == FrontAction::select_prev || nodes[i].action == FrontAction::select_next)) {
        // RQ-113 (version 18): prev and next only where there is a neighbour
        // to turn to (the realm's), or both always (KO's), as the package says.
        const auto order = slot_order();
        on = select_arrow_shows(fe.select_arrows == FrontSelectArrows::hide,
                                nodes[i].action == FrontAction::select_next, focus, order.front(), order.back());
      }
      // RQ-133 (version 22): create's nodes drawn only until its race is
      // chosen (1298's race click, 006060f0, hides the class buttons the race
      // cannot take and the images of those it can; each open's reset,
      // 006066b0 by 00605950, shows them all again).
      if (screen == FrontScreen::create && (nodes[i].flags & FrontNode::UNTIL_RACE)) on = on && !choice.race;
      // RQ-145 (version 23, Q93 (b)): create's nodes drawn until a class is
      // clicked and again from each open and each race click that builds
      // (1298's 006062d0 hides the clicked class's cream stat labels;
      // 005fd120's 00605950 shows them all; render/create_choice.h).
      if (screen == FrontScreen::create && (nodes[i].flags & FrontNode::UNTIL_CLASS)) on = on && !choice.marked;
      shown[i] = on;
    }
    return shown;
  }
  // The node rect on the canvas; the server group slides.
  std::array<float, 4> rect(FrontScreen screen, size_t i) const {
    auto r = placed[size_t(screen)].empty() ? fe.screens[size_t(screen)][i].rect : placed[size_t(screen)][i];
    if (screen == FrontScreen::login && state == Screen::realms && in_realm_group(i)) {
      const float dy = slide - realm_height;
      r[1] += dy, r[3] += dy;
    }
    if (screen == FrontScreen::create && i < slide_shift.size()) {
      r[0] += slide_shift[i][0], r[2] += slide_shift[i][0];
      r[1] += slide_shift[i][1], r[3] += slide_shift[i][1];
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
    // RQ-130: a chosen race or class draws down, under the pointer too
    // (006060f0 and 006062d0 set UI_STATE_BUTTON_DOWN).
    if (choice.down(n.action)) return 1;
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
        seats.start(focus, fe.slots[focus].spot.theta);
        out.command = Command::select;
        out.character = list->characters(focus).id();
      } else
        open_create();
      return out;
    }
    return {};
  }
  Output escape() {
    if (state == Screen::create) {
      leave_create();
      return {};
    }
    // RQ-116 (version 15): 1264's select presses bt_exit for ESC (OnKeyPress
    // 004454e0 -> ReceiveMessage 00444e60, as a click), so with the package's
    // `exit` ESC asks the exit question; RQ-119 (version 16): 1298's presses
    // no button (its bar's OnKeyPress 00607810 calls 005faad0, which only
    // skips a playing path, as the key handler does before this), so with
    // `none` it does nothing; otherwise it is the realm's back. RQ-121
    // (KO-FINDINGS 9.10): nothing while the start clip plays, as 1264's and
    // 1097's select take no key from the request (004443d0, 0043f7d0) and
    // the answer (CharacterSelect 00443570, 0043ea30) until the main
    // procedure; only the tick's ENTER skips the clip there.
    if (state == Screen::select) {
      if (fe.select_escape == FrontSelectEscape::none || choosing >= 0) return {};
      return act(fe.select_escape == FrontSelectEscape::exit ? FrontAction::exit : FrontAction::back);
    }
    return act(FrontAction::exit);
  }
  Output act(FrontAction action) {
    Output out;
    switch (action) {
    case FrontAction::login:
      if (state == Screen::login) out.command = Command::login;
      break;
    // RQ-111 (version 14, specs/KO-FINDINGS.md 9.7): 1298's select bar's
    // btn_exit (00607160) asks row 1502 in a yes/no box (MB_YESNO,
    // BEHAVIOR_EXIT) and leaves only on Yes; a package that names
    // exit_confirm asks so on the select. Elsewhere, and without it, exit
    // leaves at once (1298's login Cancel quits at once, by the source).
    // RQ-121 (KO-FINDINGS 9.10): on the select, nothing while the start clip
    // plays: 1264's (00444e60), 1097's (0043ff00) and 1298's (00607160)
    // ReceiveMessage do nothing with the UI flag their select request and
    // CharacterSelect clear.
    case FrontAction::exit:
      if (state == Screen::select && choosing >= 0) break;
      if (state == Screen::select && fe.messages[size_t(FrontMessage::exit_confirm)].named)
        show_message(FrontMessage::exit_confirm, "Exit the game?");
      else
        out.command = Command::exit;
      break;
    case FrontAction::realm_list: break;
    case FrontAction::realm_connect:
      if (state == Screen::realms && slide >= realm_height) {
        enter_select();
        face(0);
        fly_in();
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
      // RQ-077: a turn that starts plays the turn sound (1097: the proc's
      // sound object +0x18, which Init 0043a950 creates as sound 2501, played
      // at once by 004327d0); none at the end of the row.
      if (order[at] != focus) out.sound = kSelectTurnSound;
      // The path mode (1298: DoJobLeft 005fe3c0, DojobRight 005fe450): the
      // path from the slot to its neighbour (005fa670: 2 centre-left, 3
      // centre-right, 4 left-centre, 5 right-centre), the UI hidden.
      if (paths() && order[at] != focus) path_camera.start(*path_to(uint32_t(focus), uint32_t(order[at])));
      focus = order[at];
      break;
    }
    // The select's Back drops the connection (the viewer's reset); where it
    // then lands is the package's (back_lands, RQ-112).
    case FrontAction::back:
      if (state == Screen::create) leave_create();
      else if (state == Screen::select && choosing < 0) out.command = Command::back;
      break;
    // Version 13 (RQ-109, specs/KO-FINDINGS.md 9.6): 1298's select bar
    // (ReceiveMessage 00607160). btn_start (005ff870) is the centre click's
    // own start: the character in focus, or create for an empty slot.
    case FrontAction::select_start:
      if (state == Screen::select) return primary();
      break;
    // btn_create (005ff920, render/select_bar.h): create in the slot in
    // focus when it is empty, else in the first empty slot, else KO's
    // "Cannot create additional characters." (row 7675). RQ-114: the path
    // mode flies the camera there by the path from the slot (005fa670 2-7:
    // the turns' four, 6 left-right and 7 right-left), the bar hidden, and
    // create opens on the arrival (1298 shows its in-select create at once,
    // over the hall; the realm's create is a screen of its own, which draws
    // no hall, so it would hide the fly; Q87). The rotate mode, or a package
    // without that path, puts the camera on the slot and opens create.
    // RQ-125 (version 19): a create over the hall opens with the click, as
    // 1298's does (005ff920 shows +0x388 before the camera moves), and the
    // camera flies behind it (005fe5b0 case 6).
    case FrontAction::select_create: {
      if (state != Screen::select || choosing >= 0 || turning()) break;
      const int slot = select_create_slot(focus, characters_shown(), int(fe.slots.size()));
      if (slot < 0) {
        show_message(FrontMessage::create_full, "No more characters can be made in this realm.");
        break;
      }
      if (slot != focus) {
        const auto *fly = paths() ? path_to(uint32_t(focus), uint32_t(slot)) : nullptr;
        if (fly) {
          path_camera.start(*fly);
          focus = slot;
          if (!over_hall()) {
            create_flying = true;
            break;
          }
        } else
          face(slot);
      }
      open_create();
      break;
    }
    // btn_delete: for a character in focus at rest (state 5), KO's
    // "Character deletion has been disabled currently" (row 1501); the realm
    // deletes no character either.
    case FrontAction::select_delete:
      if (state == Screen::select &&
          select_delete_posts(focus, characters_shown(), choosing < 0 && !turning()))
        show_message(FrontMessage::delete_disabled, "Characters cannot be deleted in this realm.");
      break;
    // RQ-130 (version 21, KO-FINDINGS 9.15): 1298's race and class buttons
    // (ReceiveMessage 00604f90): a race click chooses the race and unchooses
    // the class; the click that builds the new character puts it at the slot
    // the camera is at (005fd120 by +0x38c: the slot a flight left).
    case FrontAction::create_race:
      if (state == Screen::create && !pending_create) choice.click_race(at_slot);
      break;
    case FrontAction::create_class:
      if (state == Screen::create && !pending_create) choice.click_class(at_slot);
      break;
    case FrontAction::create_confirm:
      if (state == Screen::create && !pending_create) {
        if (name.empty()) {
          show_message(FrontMessage::create_name, "Enter a name: 1 to 24 letters, digits, _ or -.");
          break;
        }
        // RQ-130: then no race, then no class (005fffd0's codes 7 and 9).
        if (const auto refused = choice.refusal()) {
          show_message(*refused, *refused == FrontMessage::create_no_race ? "Choose a race." : "Choose a class.");
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
  // The select camera's fog (version 8) from `eye`, or none (the intro, create).
  void fog(const FrontFog *f, const V &eye) {
    const bool on = f && f->on;
    glUniform3f(glGetUniformLocation(lit, "fog"), on ? 1.f : 0.f, on ? f->start : 0.f, on ? f->end : 0.f);
    glUniform3fv(glGetUniformLocation(lit, "fogcolor"), 1, on ? f->color.data() : V{}.data());
    glUniform3fv(glGetUniformLocation(lit, "eye"), 1, eye.data());
  }
  // A zone mesh (version 8): its texels of alpha 0 cut (1298's alpha test,
  // GREATER than 0, 0043ade0), lit unless UNLIT; a BLEND mesh blends source
  // alpha over its inverse, writing depth. Its back faces are triangles of
  // their own, so it culls.
  void draw_zone(size_t i, const detail::Mat &vp) {
    const auto &m = fe.zone[i].mesh;
    transform(vp, detail::identity());
    material(m.diffuse, m.ambient, m.flags & FrontMesh::UNLIT, 0.f);
    glEnable(GL_CULL_FACE);
    glBindTexture(GL_TEXTURE_2D, textures[m.texture]);
    glBindVertexArray(zone_meshes[i].vao);
    glDrawElements(GL_TRIANGLES, zone_meshes[i].count, GL_UNSIGNED_INT, nullptr);
  }
  // The alpha flush (1298: 0043dd80, after the select UI and the other
  // windows in Render 005fb1c0): the zone's BLEND meshes far to near, under
  // the hall's lights and fog, tested against the hall's depth.
  void zone_alpha(const detail::Mat &vp, const V &eye) {
    const auto order = far_to_near(fe.zone, eye);
    if (order.empty()) return;
    glEnable(GL_DEPTH_TEST);
    glDepthMask(GL_TRUE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(lit);
    glUniform1i(glGetUniformLocation(lit, "tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    for (size_t i : order) draw_zone(i, vp);
    glDisable(GL_BLEND);
    glBindVertexArray(0);
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
  std::vector<Node> posed(const HallPlayer &p) const {
    auto now = clip_scene(1, p.clip).sample(seats.played(p));
    if (p.elapsed >= p.blend) return now;
    return blend_pose(clip_scene(1, p.from).sample(p.from_time), std::move(now), p.elapsed / p.blend);
  }
  void reset_hall() { seats.reset(); }
  void enter_select() {
    state = Screen::select;
    reset_hall();
  }
  detail::Mat view_projection(const FrontCamera &c, V eye, int width, int height) const {
    return detail::mul(detail::perspective(c.fov, width / float(std::max(height, 1)), c.near_plane, c.far_plane),
                       detail::look_at(eye, c.at, c.up));
  }
  // CGameProcLogIn_1098::Render: the moon as a screen quad (lighting off),
  // then the looping character under lights 0-2, `t` seconds into the
  // scene (RQ-104: SceneClock).
  void intro(int width, int height, double t) {
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
    fog(nullptr, fe.intro.camera.eye);
    const auto vp = view_projection(fe.intro.camera, fe.intro.camera.eye, width, height);
    draw_character(0, pose(0, 0, t, true), vp, detail::identity());
  }
  // CGameProcCharacterSelect: the hall, then each slot's character, the
  // camera turning about `at` to the slot in focus (select_turn_tick; the
  // tick the turn ends is still a turning tick, as 0043e4e0 runs no state-2
  // proc on it). At rest (1097: state 2, DoProcPreselect 0043f280; 1298:
  // state 5, 005fef90), every tick, the characters play as the package's
  // front-clip mode says (SelectHall::rest): the hover mode's character in
  // front plays the front clip once while the pointer is in the centre rect
  // and the rest clip otherwise, the spot and the info text following the
  // pointer; the loop mode's loops the front clip whatever the pointer does.
  // While the camera turns (state 1) the spot is off (0043b550 turns every
  // light off each tick; SelectHall::turning). Starting (state 3, 0043ed20)
  // ticks the chosen character's start clip under the full spot: its blend
  // first, on the clip's first frame, then the clip, whose end (IsAnimEnd)
  // comes after both.
  // The path mode (1298, RQ-087): the camera plays the path the turn (or
  // the entry) started, 30 frames a second; a turn has arrived on the tick
  // after the one that reached the path's last frame (005fe5b0 tests the
  // frame before 005faf10 ticks the camera), and that tick is still a turning
  // one. An ENTER or ESC skip puts it there after this tick's characters.
  // RQ-125 (version 19): under a create over the hall, once the camera is
  // on the slot (1298's state 7), the new character stands there, turned by
  // the slot's create yaw, breathing, under the hall's lights and the slot's
  // spot (Render 005fb1c0 draws the player's character in state 7; 005fd120
  // puts it at the camera's slot). RQ-130 (version 21): a create that waits
  // for its race draws it once the race is clicked, at the slot the camera
  // was at for that click (render/create_choice.h).
  void hall(int width, int height, double dt, double now) {
    const bool rest = !turning();
    if (paths()) {
      if (!rest && path_camera.ended()) at_slot = focus;
    } else if (!rest && select_turn_tick(angle, slot_angle(at_slot), slot_angle(focus), float(dt)))
      at_slot = focus;
    if (choosing >= 0)
      seats.starting(choosing, float(dt));
    else if (rest)
      seats.rest(focus, characters_shown(), in_front(), fe.slots[focus].spot.theta, fe.spot_rate, float(dt));
    else
      seats.turning(characters_shown(), float(dt));
    if (skip) {
      skip = false;
      if (paths() && turning()) path_camera.finish(), at_slot = focus;
    }
    auto c = fe.select.camera;
    V eye = select_eye(c.eye, c.at, angle);
    if (paths()) {
      path_camera.tick(float(dt));
      eye = path_camera.eye;
      c.at = path_camera.at;
    }
    turn_shown = {at_slot, focus, angle, -1, path_camera.frame, path_camera.whole, !ui_hidden()};
    if (paths() && path_camera.path) turn_shown.path = int(path_camera.path - fe.paths.data());
    const auto vp = view_projection(c, eye, width, height);
    glEnable(GL_DEPTH_TEST);
    glUseProgram(lit);
    glUniform1i(glGetUniformLocation(lit, "tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    auto spot = fe.slots[focus].spot;
    spot.theta = seats.theta;
    lights(fe.select, seats.spot_on ? std::vector<FrontLight>{spot} : std::vector<FrontLight>{});
    // Version 8 (RQ-095): the camera's fog on everything the hall draws, and
    // the zone's terrain and shapes before the characters (1298: Render
    // 005fb1c0 draws the world manager's terrain, then its shapes); their
    // alpha parts after the UI (zone_alpha).
    fog(&fe.fog, eye);
    hall_camera.emplace(vp, eye);
    for (size_t i = 0; i < fe.zone.size(); ++i)
      if (!(fe.zone[i].mesh.flags & FrontMesh::BLEND)) draw_zone(i, vp);
    for (size_t i = 0; i < statics.size(); ++i) draw_mesh(statics[i], fe.hall[i], vp, detail::identity());
    const auto &front = seats.players.at(size_t(focus));
    front_shown = {uint32_t(front.clip), seats.played(front), clip_length(1, front.clip),
                   front.blend > 0 ? std::min(1.f, front.elapsed / front.blend) : 1.f, seats.theta, seats.spot_on,
                   seats.info_slot >= 0};
    for (int i = 0; i < characters_shown(); ++i) {
      const auto &slot = fe.slots[i];
      draw_character(1, posed(seats.players.at(size_t(i))), vp, detail::translate_yaw(slot.position, slot.yaw));
    }
    if (in_hall_create() && !turning() && choice.stands()) {
      const auto &slot = fe.slots[size_t(choice.stands_at(focus))];
      draw_character(2, pose(2, 0, now, true), vp, detail::translate_yaw(slot.position, slot.create_yaw));
    }
  }
  // Create: the player's own model breathing in `char_view`, as KO's
  // InventoryChrRender draws it in area_character.
  void character_view(int width, int height, double now) {
    const auto &nodes = fe.screens[size_t(FrontScreen::create)];
    auto it = std::find_if(nodes.begin(), nodes.end(), [](const auto &n) { return n.action == FrontAction::char_view; });
    const auto r = rect(FrontScreen::create, size_t(it - nodes.begin()));
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
    fog(nullptr, eye);
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
    const auto [s, ox, oy] = view(width, height);
    ui_scale = s, ui_x = ox, ui_y = oy;
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
  // RQ-101: the logo screen (1264: 00600ce0), its nodes in draw order with the
  // groups other than the one showing hidden (00601360 shows each alone), all
  // at the frame's alpha over the black clear.
  void logo_ui() {
    const auto &logo = *fe.logo;
    const auto &nodes = logo.nodes;
    if (logo_drawn.group < 0) return;
    const uint32_t alpha = uint32_t(std::lround(logo_drawn.alpha * 255));
    std::vector<char> drew(nodes.size(), 0);
    for (size_t i = 0; i < nodes.size(); ++i) {
      const auto &n = nodes[i];
      if (i > 0 && !drew[n.parent]) continue;
      bool other = false;
      for (size_t g = 0; g < logo.groups.size(); ++g)
        if (logo.groups[g].node == i && int(g) != logo_drawn.group) other = true;
      if (other) continue;
      drew[i] = 1;
      const auto &r = placed[FrontEnd::kLogoLayout][i];
      if (n.kind == FrontNode::IMAGE) quad(textures[n.texture], r, n.uv, alpha << 24 | 0xffffff);
      else if (n.kind == FrontNode::TEXT)
        text(n.text, n.font, (((n.color >> 24) * alpha / 255) << 24) | (n.color & 0xffffff), n.style, r);
    }
  }
  void ui(FrontScreen screen, const Context &context, double now) {
    const auto &nodes = fe.screens[size_t(screen)];
    const auto shown = visible(screen);
    std::vector<int> state(nodes.size(), 0);
    // CN3UIBase::Render draws a node's children only when it draws the node: a
    // button draws the one state image its state names, and that image its own
    // children (1264's El_MessageBox_us labels each state image, RQ-085).
    std::vector<char> drew(nodes.size(), 0);
    for (size_t i = 0; i < nodes.size(); ++i) {
      if (!shown[i]) continue;
      const auto &n = nodes[i];
      if (i > 0 && !drew[n.parent]) continue;
      const auto r = rect(screen, i);
      if (n.kind == FrontNode::BUTTON) state[i] = button_state(screen, i);
      if (i > 0 && nodes[n.parent].kind == FrontNode::BUTTON && !(n.mask & (1u << state[n.parent]))) continue;
      drew[i] = 1;
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
          // 1298 (006074c0, from 005fef90) fills its info texts every tick at
          // rest, empty for an empty slot (the loop mode's select_hint).
          if (seats.info_slot < 0) value.clear();
          else if (list && seats.info_slot < characters_shown())
            value = filled(FrontString::select_info, context, &list->characters(seats.info_slot));
          else
            value = filled(FrontString::select_hint, context, nullptr);
          break;
        case FrontAction::char_name:
        case FrontAction::char_level:
        case FrontAction::char_class:
          // 1298's bar (006074c0, from 005fef90 at rest): str_id the name,
          // str_lev the level ("%d"), str_job the class; all three empty for
          // an empty slot.
          value.clear();
          if (list && seats.info_slot >= 0 && seats.info_slot < characters_shown()) {
            const auto &c = list->characters(seats.info_slot);
            value = n.action == FrontAction::char_name    ? c.name()
                    : n.action == FrontAction::char_level ? std::to_string(std::max<uint32_t>(1, c.level()))
                                                          : fe.strings[size_t(FrontString::class_name)];
          }
          break;
        case FrontAction::class_desc: value = filled(FrontString::class_desc, context, nullptr); break;
        case FrontAction::version: value = filled(FrontString::version, context, nullptr); break;
        case FrontAction::info: value = filled(FrontString::loading_info, context, nullptr); break;
        case FrontAction::message: value = message ? message->text : std::string(); break;
        case FrontAction::title: value = message ? message->title : std::string(); break;
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
