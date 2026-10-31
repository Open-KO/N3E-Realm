#include "render/navigation.h"
#include "render/orbit.h"
#include <iostream>
#include <stdexcept>
using n3e::V;
void require(bool ok) {
  if (!ok)
    throw std::runtime_error("camera numeric assertion");
}
void close(float a, float b) { require(std::abs(a - b) < 1e-4); }
void quad(n3e::Scene &s, V a, V b, V c, V d) {
  auto t = s.collision.all();
  t.insert(t.end(), {a, b, c, a, c, d});
  s.collision = n3e::Collision(std::move(t));
}
int main(int argc, char **argv) {
  try {
    require(argc == 2);
    auto release = n3e::load_release(argv[1]);
    Orbit o(release.camera);
    n3e::Scene s{};
    quad(s, {-20, 0, -20}, {20, 0, -20}, {20, 0, 20}, {-20, 0, 20});
    o.update({0, 0, 0}, s, 1.6);
    close(o.focus[1], 1.28);
    close(o.boom, 7);
    close(o.eye[1], 1.28 + 7 * std::sin(25 * 3.14159265f / 180));
    o.update({0, 0, 0}, s, 2.5);
    close(o.focus[1], 2);
    const auto &c = release.camera;
    if (c.drag_distance) {
      // KO mode 3 (005e3e20 -> 0063e2e0): dragging down moves the camera
      // away, up brings it in, within the distance limits; pitch stays.
      o.drag(0, 10000);
      close(o.distance, c.distance_max);
      close(o.pitch, c.pitch);
      o.drag(0, -10000);
      close(o.distance, c.distance_min);
      o.drag(0, 100);
      close(o.distance, c.distance_min + 100 * c.distance_per_pixel);
      close(o.pitch, c.pitch);
    } else {
      o.drag(0, 10000);
      close(o.pitch, 70 * 3.14159265f / 180);
      o.drag(0, -10000);
      close(o.pitch, 10 * 3.14159265f / 180);
    }
    o.zoom(10000);
    close(o.distance, 2);
    o.zoom(-10000);
    close(o.distance, 10);
    o = Orbit(release.camera);
    o.update({0, 0, 0}, s);
    for(float fov : {1.04719755f,1.1344640255f}) {
    o.config.fov=fov;
    for (auto dimensions :
         {std::pair{800, 600}, std::pair{1920, 1080}, std::pair{2400, 600}}) {
      auto [w, h] = dimensions;
      for (V p : {V{0, 0, 0}, V{2, 0, -4}, V{-3, 0, 2}}) {
        auto screen = o.project(p, w, h);
        V picked{};
        require(o.ground_point(screen[0], screen[1], w, h, s, picked));
        for (int k = 0; k < 3; ++k)
          close(picked[k], p[k]);
      }
    }
    }
    // Thin vertical prop crossing boom: near-plane clearance, reversed winding,
    // distance changes and yaw at 30/60/144 FPS cannot tunnel.
    quad(s, {-10, 0, 2}, {10, 0, 2}, {10, 8, 2}, {-10, 8, 2});
    o.update({0, 0, 0}, s);
    require(o.eye[2] < 1.801 && o.boom < 2.1);
    float obstructed = o.boom;
    o.zoom(-100);
    o.update({0, 0, 0}, s);
    close(o.boom, obstructed);
    {
      auto t = s.collision.all();
      for (size_t i = 0; i < t.size(); i += 3)
        std::swap(t[i], t[i + 2]);
      s.collision = n3e::Collision(std::move(t));
    }
    o.update({0, 0, 0}, s);
    close(o.boom, obstructed);
    // The same drag gives the same turn at any frame rate (D-143 correction:
    // fixed per-pixel rates where KO scales each frame's pixels by its time).
    for (int fps : {30, 60, 144}) {
      o = Orbit(release.camera);
      for (int i = 0; i < fps; ++i) {
        o.drag(100.f / fps, 20.f / fps);
        o.update({0, 0, 0}, s);
        require(o.eye[2] < 1.801);
      }
      close(o.yaw, -100 * c.yaw_per_pixel);
      if (c.drag_distance) {
        close(o.pitch, c.pitch);
        close(o.distance, c.distance + 20 * c.distance_per_pixel);
      } else {
        close(o.pitch, c.pitch + 20 * c.pitch_per_pixel);
        close(o.distance, c.distance);
      }
    }
    // Held pitch keys (KO 005c6990 Home/End, 0063e0e0): a rate per second,
    // the same at any frame rate; raise wins when both are held; the pitch
    // limits hold; a package without the rate does not move.
    for (int fps : {30, 60, 144}) {
      o = Orbit(c);
      for (int i = 0; i < fps / 4; ++i)
        o.key_pitch(true, false, 1.f / fps);
      close(o.pitch, std::min(c.pitch + c.key_pitch_rate * (fps / 4) / fps, c.pitch_max));
      float before = o.pitch;
      o.key_pitch(true, true, 1.f / fps);
      close(o.pitch, std::min(before + c.key_pitch_rate / fps, c.pitch_max));
      for (int i = 0; i < 10 * fps; ++i)
        o.key_pitch(false, true, 1.f / fps);
      close(o.pitch, c.key_pitch_rate > 0 ? c.pitch_min : c.pitch);
      for (int i = 0; i < 10 * fps; ++i)
        o.key_pitch(true, false, 1.f / fps);
      close(o.pitch, c.key_pitch_rate > 0 ? c.pitch_max : c.pitch);
      o.key_pitch(false, false, 1);
      o.key_pitch(true, false, -1);
      o.key_pitch(true, false, std::numeric_limits<float>::quiet_NaN());
      close(o.pitch, c.key_pitch_rate > 0 ? c.pitch_max : c.pitch);
    }
    // Screen edges (KO 005c6990): only the outermost column of the window,
    // never a cursor outside it; the left edge turns as a drag to the left.
    require(Orbit::edge(0, 800) == -1 && Orbit::edge(.5f, 800) == -1 &&
            Orbit::edge(1, 800) == 0 && Orbit::edge(400, 800) == 0 &&
            Orbit::edge(798.9f, 800) == 0 && Orbit::edge(799, 800) == 1 &&
            Orbit::edge(799.5f, 800) == 1 && Orbit::edge(800, 800) == 0 &&
            Orbit::edge(-1, 800) == 0 && Orbit::edge(0, 1) == 0 &&
            Orbit::edge(std::numeric_limits<float>::quiet_NaN(), 800) == 0);
    for (int fps : {30, 60, 144}) {
      o = Orbit(c);
      for (int i = 0; i < fps / 2; ++i)
        o.edge_yaw(Orbit::edge(0, 800), 1.f / fps);
      close(o.yaw, c.edge_yaw_rate * (fps / 2) / fps);
      Orbit dragged(c);
      dragged.drag(-10, 0);
      require(c.edge_yaw_rate == 0 || (o.yaw > 0 && dragged.yaw > 0));
      o.edge_yaw(Orbit::edge(799, 800), 1.f / fps);
      close(o.yaw, c.edge_yaw_rate * ((fps / 2) - 1) / fps);
    }
    // When the keys and edges act (viewer gating, KO 005c6990): a text field
    // stops the pitch keys but not edge yaw; lost window focus and leaving
    // play stop both; a cursor outside the window stops edge yaw only; tools
    // capture stops its own device; a right-drag stops edge yaw but not the
    // keys (n3e gap, D-143/PQ-160: KO still tests the frame's raw cursor).
    {
      using camera_input::Context;
      Context play;
      play.in_world = play.window_focused = play.mouse_in_window = true;
      require(camera_input::pitch_keys(play) && camera_input::edge(play));
      Context typing = play;
      typing.typing = true;
      require(!camera_input::pitch_keys(typing) && camera_input::edge(typing));
      Context unfocused = play;
      unfocused.window_focused = false;
      require(!camera_input::pitch_keys(unfocused) && !camera_input::edge(unfocused));
      Context outside = play;
      outside.mouse_in_window = false;
      require(camera_input::pitch_keys(outside) && !camera_input::edge(outside));
      Context menu = play;
      menu.in_world = false;
      require(!camera_input::pitch_keys(menu) && !camera_input::edge(menu));
      Context tools_keys = play, tools_mouse = play;
      tools_keys.tools_keyboard = true;
      tools_mouse.tools_mouse = true;
      require(!camera_input::pitch_keys(tools_keys) && camera_input::edge(tools_keys));
      require(camera_input::pitch_keys(tools_mouse) && !camera_input::edge(tools_mouse));
      Context dragging = play;
      dragging.dragging = true;
      require(camera_input::pitch_keys(dragging) && !camera_input::edge(dragging));
    }
    // A wall in front of the eye must prevent picking ground behind it.
    o = Orbit(release.camera);
    n3e::Scene floor{};
    quad(floor, {-20, 0, -20}, {20, 0, -20}, {20, 0, 20}, {-20, 0, 20});
    o.update({0, 0, 0}, floor);
    quad(floor, {-10, 0, 2}, {10, 0, 2}, {10, 8, 2}, {-10, 8, 2});
    auto pixel = o.project({0, 0, 0}, 800, 600);
    V point{};
    require(!o.ground_point(pixel[0], pixel[1], 800, 600, floor, point));
    // Sloping supported terrain intersects the boom before its endpoint.
    n3e::Scene ramp{};
    quad(ramp, {-10, 0, 0}, {10, 0, 0}, {10, 10, 10}, {-10, 10, 10});
    o.update({0, 0, 0}, ramp);
    require(o.boom < 3 && o.eye[1] > o.eye[2]);
    // A corner grazing the swept sphere retracts although the centre ray
    // misses.
    n3e::Scene edge{};
    quad(edge, {.1f, 0, 2}, {2, 0, 2}, {2, 8, 2}, {.1f, 8, 2});
    o.update({0, 0, 0}, edge);
    require(o.boom < 2.1);
    o.update({-4, 0, 0}, edge);
    close(o.boom, 7); // recover desired distance
    // Degenerate focus overlap fails closed at zero boom; never enforce zoom
    // min.
    o.update({0, 0, 2}, edge);
    close(o.boom, 0);
    std::cout
        << "PASS camera profile/focus, limits, projection/picking, foreground "
           "wall, terrain/props/edges, overlap/recovery, 30/60/144 FPS, drag "
        << (release.camera.drag_distance ? "yaw+distance" : "yaw+pitch")
        << ", key pitch " << release.camera.key_pitch_rate << " rad/s, edge yaw "
        << release.camera.edge_yaw_rate << " rad/s\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
