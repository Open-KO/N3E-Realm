#pragma once
#include "assets/assets.h"
#include "hud.h"
#include "network/world.h"
#include "network/chat.h"
#include <algorithm>
#include <cctype>
#include <cmath>

#include "orbit.h"
inline void panel(int x, int y, int w, int h, int screen, float r = .08f,
                  float g = .09f, float b = .10f) {
  glEnable(GL_SCISSOR_TEST);
  glScissor(x, screen - y - h, std::max(0, w), std::max(0, h));
  glClearColor(.48f, .36f, .17f, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  glScissor(x + 2, screen - y - h + 2, std::max(0, w - 4), std::max(0, h - 4));
  glClearColor(r, g, b, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  glDisable(GL_SCISSOR_TEST);
}
inline void bar(int x, int y, int w, int h, int screen, float fraction, float r,
                float g, float b) {
  panel(x, y, w, h, screen, .025f, .025f, .03f);
  glEnable(GL_SCISSOR_TEST);
  glScissor(x + 3, screen - y - h + 3,
            std::max(0, int((w - 6) * std::clamp(fraction, 0.f, 1.f))), h - 6);
  glClearColor(r, g, b, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  glDisable(GL_SCISSOR_TEST);
}
inline std::string display_name(std::string name) {
  auto slash = name.find_last_of('/');
  if (slash != std::string::npos)
    name = name.substr(slash + 1);
  return name.substr(0, 20);
}
inline std::string upper(std::string s) {
  for (auto &c : s) c = char(std::toupper((unsigned char)c));
  return s;
}
// key_hint: the package map's target/chat keys (PQ-009), drawn under the bag line.
// operator_chat: the package's colour for a line the server marked (PQ-178).
// discord: the login screen is spec 02's "Log in with Discord" (a realm config).
inline void play_hud(const n3e::WorldState &world, uint64_t target, int entry,
                     const std::string &input, int width, int height,
                     const std::string &key_hint,
                     const std::optional<uint32_t> &operator_chat = {},
                     bool discord = false) {
  if (entry < 4) {
    int x = std::max(10, (width - 480) / 2),
        y = std::max(10, (height - 280) / 2);
    panel(x, y, 480, 280, height);
    hud_text("N3E  /  ADVENTURE", x + 24, y + 24, height);
    if (discord && entry == 0) {
      hud_text("LOG IN WITH DISCORD", x + 24, y + 58, height);
      // The flow's line, wrapped at word breaks to the panel's width.
      std::string line, word, text = world.status + " ";
      int row = 0;
      for (char c : text) {
        if (c != ' ') { word += c; continue; }
        if (line.size() + word.size() + 1 > 36 && !line.empty()) {
          if (row < 6) hud_text(line, x + 24, y + 100 + 22 * row++, height);
          line.clear();
        }
        line += (line.empty() ? "" : " ") + word.substr(0, 36);
        word.clear();
      }
      if (!line.empty() && row < 6) hud_text(line, x + 24, y + 100 + 22 * row, height);
      return;
    }
    hud_text(world.status.substr(0, 36), x + 24, y + 58, height);
    std::string label = entry == 0   ? "ACCOUNT"
                        : entry == 1 ? "PASSWORD"
                        : entry == 3 ? "NEW CHARACTER"
                                     : "SELECT CHARACTER";
    hud_text(label, x + 24, y + 100, height);
    if (entry == 2) {
      for (int i = 0; i < world.characters.characters_size(); ++i)
        hud_text(std::to_string(i + 1) + "  " +
                     world.characters.characters(i).name(),
                 x + 24, y + 126 + 18 * i, height);
      hud_text("N  CREATE CHARACTER", x + 24, y + 248, height);
    } else {
      panel(x + 20, y + 126, 440, 38, height, .03f, .035f, .04f);
      hud_text(entry == 1 ? std::string(std::min<size_t>(32, input.size()), '*')
                          : input.substr(0, 32),
               x + 32, y + 138, height);
      hud_text("ENTER  CONTINUE", x + 24, y + 220, height);
    }
    return;
  }
  const n3e::Entity *self = nullptr, *selected = nullptr;
  for (const auto &e : world.world.entities()) {
    if (e.id() == world.world.self())
      self = &e;
    if (e.id() == target)
      selected = &e;
  }
  panel(16, 16, 250, 102, height);
  if (self) {
    hud_text(display_name(self->name()) + "  LV " +
                 std::to_string(world.world.inventory().level()),
             28, 26, height);
    bar(26, 48, 228, 26, height,
        float(self->health()) / std::max(1u, world.world.max_health()), .65f,
        .10f, .08f);
    hud_text("HP " + std::to_string(self->health()) + " / " +
                 std::to_string(world.world.max_health()),
             36, 54, height);
    bar(26, 80, 228, 24, height,
        float(self->resource()) / std::max(1u, world.world.max_resource()),
        .12f, .26f, .63f);
    hud_text("MP " + std::to_string(self->resource()) + " / " +
                 std::to_string(world.world.max_resource()),
             36, 85, height);
    if (!self->health() && self->life_state() == n3e::LEGACY) {
      panel(width / 2 - 170, height / 2 - 35, 340, 70, height);
      hud_text("FALLEN - RESPAWNING", width / 2 - 150, height / 2 - 10, height);
    }
  }
  if (selected) {
    panel(width / 2 - 132, 18, 264, 60, height);
    hud_text(display_name(selected->name()), width / 2 - 116, 28, height);
    hud_text("HP " + std::to_string(selected->health()) + " " + selected->strike_result() + " " + std::to_string(selected->strike_damage()), width / 2 - 116, 52,
             height);
  }

  panel(width - 174, 16, 158, 158, height, .10f, .16f, .11f);
  hud_text("AREA   N", width - 158, 28, height);
  for (const auto &e : world.world.entities()) {
    int x = width - 95 + int((e.x() - world.predicted[0]) * 4),
        y = 96 + int((e.z() - world.predicted[2]) * 4);
    if (x > width - 166 && x < width - 24 && y > 50 && y < 166)
      panel(x - 3, y - 3, 6, 6, height, e.npc() ? .8f : .2f,
            e.npc() ? .2f : .8f, .15f);
  }
  // PQ-406 (D-209): without a package HUD the world's notice (a chat, whisper,
  // rest or admin refusal) has a line of its own above the chat panel.
  if (!world.notice.empty())
    hud_text(world.notice.substr(0, 42), 28, height - 208, height);
  panel(16, height - 160, std::min(550, width - 32), 66, height);
  if (entry != 5 && world.chat_operator && operator_chat) {
    const auto color = n3e::chat_line_color(true, operator_chat, 0);
    hud_text(world.chat.substr(0, 42), 28, height - 148, height,
             float(color >> 16 & 255) / 255, float(color >> 8 & 255) / 255,
             float(color & 255) / 255);
  } else
    hud_text(entry == 5 ? "CHAT: " + input.substr(0, 38)
                        : world.chat.substr(0, 42),
             28, height - 148, height);
  hud_text(world.combat.substr(0, 32) + " " + std::to_string(world.combat_damage), 28, height - 126, height);
  panel(16, height - 84, width - 32, 68, height);
  panel(28, height - 74, 132, 46, height, .22f, .16f, .09f);
  hud_text("R / SPACE / 1", 38, height - 67, height);
  hud_text("STRIKE", 38, height - 47, height);
  const auto &inv = world.world.inventory();
  hud_text(display_name(inv.item()) + " " + std::to_string(inv.count()) +
               " / " + std::to_string(inv.capacity()) + "   XP " +
               std::to_string(inv.xp()),
           180, height - 68, height);
  hud_text(key_hint, 180, height - 46, height);
  hud_text("WASD / CLICK MOVE  RMB CAMERA  WHEEL ZOOM", 28, height - 186,
           height);
  if (!world.connected)
    hud_text("DISCONNECTED - F12 TO LOGIN", width / 2 - 155, 114, height);
  if (inv.pending())
    hud_text("REWARD PENDING", width / 2 - 100, 92, height);
}
// Original block figure distinguishes players from the package's monster
// visual.
inline void player_mesh(std::vector<float> &out, n3e::V p, bool alive,
                        float heading, bool ready = false) {
  auto box = [&](float x, float y, float z, float sx, float sy, float sz,
                 bool head) {
    n3e::V v[8];
    for (int i = 0; i < 8; ++i)
      v[i] = {x + (i & 1 ? sx : -sx), y + (i & 2 ? sy : -sy),
              z + (i & 4 ? sz : -sz)};
    const int faces[6][4] = {{0, 4, 6, 2}, {1, 3, 7, 5}, {0, 1, 5, 4},
                             {2, 6, 7, 3}, {0, 2, 3, 1}, {4, 5, 7, 6}};
    const n3e::V normals[6] = {{-1, 0, 0}, {1, 0, 0},  {0, -1, 0},
                               {0, 1, 0},  {0, 0, -1}, {0, 0, 1}};
    for (int f = 0; f < 6; ++f)
      for (int j : {0, 1, 2, 0, 2, 3}) {
        auto a = v[faces[f][j]], n = normals[f];
        float c = std::cos(heading), s = std::sin(heading);
        out.insert(out.end(),
                   {p[0] + a[0] * c + a[2] * s,
                    p[1] + a[1] * (alive ? 1.f : .2f),
                    p[2] - a[0] * s + a[2] * c, n[0] * c + n[2] * s, n[1],
                    -n[0] * s + n[2] * c, head ? -3.f : -2.f, 0});
      }
  };
  box(0, 1.05f, 0, .22f, .32f, .14f, false);
  box(0, 1.55f, 0, .16f, .17f, .16f, true);
  box(-.12f, .37f, 0, .085f, .37f, .10f, false);
  box(.12f, .37f, 0, .085f, .37f, .10f, false);
  if (ready && alive) {
    box(-.31f, 1.22f, -.15f, .075f, .12f, .22f, false);
    box(.31f, 1.22f, -.15f, .075f, .12f, .22f, false);
  } else {
    box(-.31f, 1.04f, 0, .075f, .30f, .09f, false);
    box(.31f, 1.04f, 0, .075f, .30f, .09f, false);
  }
}

// respawn_key: the key the package binds to respawn (PQ-009); empty when unbound.
inline void life_hud(const n3e::WorldState &world, int width, int height, const std::string &respawn_key) {
  for (const auto &e : world.world.entities()) {
    if (e.id() != world.world.self() || e.health()) continue;
    panel(width / 2 - 210, height / 2 - 45, 420, 90, height);
    auto remaining = e.respawn_tick() > world.world.tick() ? e.respawn_tick() - world.world.tick() : 0;
    std::string ready = respawn_key.empty() ? "FALLEN - READY TO RESPAWN" : "FALLEN - " + upper(respawn_key) + " TO RESPAWN";
    std::string text = e.life_state() == n3e::DEAD_READY ? ready : "FALLEN - READY IN " + std::to_string((remaining + 19) / 20) + "s";
    hud_text(text, width / 2 - 190, height / 2 - 22, height);
    hud_text("Return to spawn with full HP/MP", width / 2 - 190, height / 2, height);
    hud_text(world.respawn, width / 2 - 190, height / 2 + 20, height);
  }
}
