// Test-only replay fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Field replays after the HUD draw: play, movement, controls, camera, melee, life,
// animation and NPC observation, combat captures, and the --world-smoke deadline.
        if (play_smoke && (entry == 4 || entry == 5)) {
          if (!play_start) {
            play_start = SDL_GetTicks();
            test_origin = world.predicted;
          }
          auto elapsed = SDL_GetTicks() - play_start;
          auto click_control = [&](const std::string &binding) {
            for (const auto &q : hud->data.records)
              if (q.kind == 2 && q.binding == binding) {
                auto r = hud->rectangle(q, width, height);
                int lw, lh;
                SDL_GetWindowSize(w, &lw, &lh);
                SDL_Event click{};
                click.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
                click.button.button = SDL_BUTTON_LEFT;
                click.button.which = replay_mouse;
                click.button.x = (r[0] + r[2]) * .5f * lw / width;
                click.button.y = (r[1] + r[3]) * .5f * lh / height;
                SDL_PushEvent(&click);
                return;
              }
            throw std::runtime_error("missing HUD action binding");
          };
          if (play_stage == 0 && elapsed > 400) {
            int lw, lh;
            SDL_GetWindowSize(w, &lw, &lh);
            SDL_Event press{};
            press.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
            press.button.button = SDL_BUTTON_RIGHT;
            press.button.which = replay_mouse;
            press.button.x = lw * .5f;
            press.button.y = lh * .45f;
            SDL_PushEvent(&press);
            SDL_Event motion{};
            motion.type = SDL_EVENT_MOUSE_MOTION;
            motion.motion.state = SDL_BUTTON_RMASK;
            motion.motion.which = replay_mouse;
            motion.motion.xrel = 50;
            motion.motion.yrel = 8;
            pending_camera_motion = motion;
            SDL_Event wheel{};
            wheel.type = SDL_EVENT_MOUSE_WHEEL;
            wheel.wheel.y = 1;
            wheel.wheel.which = replay_mouse;
            wheel.wheel.mouse_x = lw * .5f;
            wheel.wheel.mouse_y = lh * .45f;
            pending_camera_wheel = wheel;
            pending_camera_events = true;
            ++play_stage;
          } else if (play_stage == 1 && elapsed > 800) {
            SDL_Event release_button{};
            release_button.type = SDL_EVENT_MOUSE_BUTTON_UP;
            release_button.button.button = SDL_BUTTON_RIGHT;
            release_button.button.which = replay_mouse;
            SDL_PushEvent(&release_button);
            auto q = orbit.project(
                {test_origin[0] + 3,
                 scene.ground_height(test_origin[0] + 3, test_origin[2]),
                 test_origin[2]},
                width, height);
            int lw, lh;
            SDL_GetWindowSize(w, &lw, &lh);
            SDL_Event click{};
            click.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
            click.button.button = SDL_BUTTON_LEFT;
            click.button.which = replay_mouse;
            click.button.x = q[0] * lw / width;
            click.button.y = q[1] * lh / height;
            SDL_PushEvent(&click);
            ++play_stage;
          } else if (play_stage == 2 && elapsed > 1200) {
            // PQ-238: the desktop's focus loss, pointer leave and cursor
            // motion, as the compositor sends them (the window's own ID, the
            // desktop mouse), mid travel. The replay owns focus and the
            // pointer, so the walk and the later HUD clicks go on; if they did
            // not, the moved/HUD checks below fail every run instead of only
            // when the desktop interferes.
            for (auto type : {SDL_EVENT_WINDOW_FOCUS_LOST, SDL_EVENT_WINDOW_MOUSE_LEAVE}) {
              SDL_Event native{};
              native.type = type;
              native.window.windowID = SDL_GetWindowID(w);
              SDL_PushEvent(&native);
            }
            int lw, lh;
            SDL_GetWindowSize(w, &lw, &lh);
            SDL_Event native{};
            native.type = SDL_EVENT_MOUSE_MOTION;
            native.motion.windowID = SDL_GetWindowID(w);
            native.motion.x = lw * .5f;
            native.motion.y = lh - 2.f;  // over the bottom HUD bar
            SDL_PushEvent(&native);
            ++play_stage;
          } else if (play_stage == 3 && elapsed > 3000) {
            press_action(n3e::input::Action::target_enemy);
            ++play_stage;
          } else if (hud && play_stage == 4 && elapsed > 3200) {
            click_control("strike");
            ++play_stage;
          } else if (hud && play_stage == 5 && elapsed > 3500) {
            play_melee = release.melee && target && melee.target == target;
            click_control("chat");
            SDL_Event input{};
            input.type = SDL_EVENT_TEXT_INPUT;
            input.text.text = "HUD input check";
            SDL_PushEvent(&input);
            ++play_stage;
          } else if (hud && play_stage == 6 && elapsed > 4300) {
            SDL_Event enter{};
            enter.type = SDL_EVENT_KEY_DOWN;
            enter.key.key = SDLK_RETURN;
            SDL_PushEvent(&enter);
            ++play_stage;
          }
        }
        if (!movement_capture.empty()) {
          capture(movement_capture, width, height);
          movement_capture.clear();
        }
        if (controls_smoke && controls_start) {
          auto elapsed = SDL_GetTicks() - controls_start;
          auto require = [&](bool ok) {
            if (!ok) {
              std::cerr << "REPLAY failure stage=" << controls_stage
                        << " drag=" << orbit_drag << " yaw=" << orbit.yaw
                        << " pitch=" << orbit.pitch
                        << " distance=" << orbit.distance << " entry=" << entry
                        << " held=" << held_ground.active
                        << " boom=" << orbit.boom << "\n";
              throw std::runtime_error("controls replay assertion");
            }
          };
          auto cursor = [&](Uint32 type, n3e::V point) {
            auto q = orbit.project(point, width, height);
            int lw, lh;
            SDL_GetWindowSize(w, &lw, &lh);
            SDL_Event event{};
            event.type = type;
            if (type == SDL_EVENT_MOUSE_MOTION) {
              event.motion.x = q[0] * lw / width;
              event.motion.y = q[1] * lh / height;
              event.motion.state = SDL_BUTTON_LMASK;
            } else {
              event.button.button = SDL_BUTTON_LEFT;
              event.button.x = q[0] * lw / width;
              event.button.y = q[1] * lh / height;
            }
            SDL_PushEvent(&event);
          };
          auto camera_events = [&](bool ui, bool press, float dx, float dy,
                                   float wheel) {
            int lw, lh;
            SDL_GetWindowSize(w, &lw, &lh);
            float x = ui ? 24.f : lw * .5f, y = ui ? 24.f : lh * .45f;
            if (press) {
              SDL_Event event{};
              event.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
              event.button.button = SDL_BUTTON_RIGHT;
              event.button.x = x;
              event.button.y = y;
              SDL_PushEvent(&event);
            }
            SDL_Event event{};
            event.type = SDL_EVENT_MOUSE_MOTION;
            event.motion.state = SDL_BUTTON_RMASK;
            event.motion.xrel = dx;
            event.motion.yrel = dy;
            event.motion.x = x;
            event.motion.y = y;
            if (press)
              pending_camera_motion = event;
            else
              SDL_PushEvent(&event);
            event = {};
            event.type = SDL_EVENT_MOUSE_WHEEL;
            event.wheel.y = wheel;
            event.wheel.mouse_x = x;
            event.wheel.mouse_y = y;
            if (press) {
              pending_camera_wheel = event;
              pending_camera_events = true;
            } else
              SDL_PushEvent(&event);
          };
          auto key_event = [&](SDL_Keycode key) {
            SDL_Event event{};
            event.type = SDL_EVENT_KEY_DOWN;
            event.key.key = key;
            SDL_PushEvent(&event);
          };
          unsigned before = controls_stage;
          if (controls_stage == 0 && elapsed >= 1500) {
            require(std::hypot(world.predicted[0], world.predicted[2]) < .25f &&
                    std::abs(heading - 1.5707963f) < .1f && orbit.yaw == 0);
            ++controls_stage;
          } else if (controls_stage == 1 && elapsed >= 3000) {
            require(world.predicted[0] < -5 &&
                    std::abs(world.predicted[2]) < 1 && orbit.yaw == 0);
            controls_before = world.predicted;
            ++controls_stage;
          } else if (controls_stage == 2 && elapsed >= 4000) {
            require(world.predicted[0] > controls_before[0] + 1 &&
                    orbit.yaw == 0);
            ++controls_stage;
          } else if (controls_stage == 3 && elapsed >= 4500) {
            cursor(SDL_EVENT_MOUSE_BUTTON_DOWN,
                   {world.predicted[0] - 2, 0, -5});
            ++controls_stage;
          } else if (controls_stage == 4 && elapsed >= 5400) {
            require(held_ground.active && walking_to);
            controls_destination = destination;
            cursor(SDL_EVENT_MOUSE_MOTION, {world.predicted[0] + 3, 0, -7});
            ++controls_stage;
          } else if (controls_stage == 5 && elapsed >= 6200) {
            require(held_ground.active && walking_to &&
                    std::hypot(destination[0] - controls_destination[0],
                               destination[2] - controls_destination[2]) > 1);
            cursor(SDL_EVENT_MOUSE_BUTTON_UP, destination);
            ++controls_stage;
          } else if (controls_stage == 6 && elapsed >= 6500) {
            require(!held_ground.active);
            SDL_Event event{};
            event.type = SDL_EVENT_WINDOW_FOCUS_LOST;
            SDL_PushEvent(&event);
            ++controls_stage;
          } else if (controls_stage == 7 && elapsed >= 6700) {
            require(!held_ground.active && !walking_to &&
                    movement_intent == n3e::V{});
            SDL_Event event{};
            event.type = SDL_EVENT_WINDOW_FOCUS_GAINED;
            SDL_PushEvent(&event);
            ++controls_stage;
          }
          if (camera_smoke) {
            if (controls_stage == 8 && elapsed >= 7100) {
              camera_events(true, true, 50, 8, 1);
              ++controls_stage;
            } else if (controls_stage == 9 && elapsed >= 7400) {
              require(!orbit_drag && orbit.yaw == 0 && orbit.distance == 7);
              camera_events(false, true, 50, 8, 1);
              ++controls_stage;
            } else if (controls_stage == 10 && elapsed >= 7700) {
              require(orbit_drag && std::abs(orbit.yaw + .3f) < .01f &&
                      std::abs(orbit.distance - 6.3f) < .01f);
              SDL_Event event{};
              event.type = SDL_EVENT_WINDOW_FOCUS_LOST;
              SDL_PushEvent(&event);
              camera_events(false, false, 50, 8, 1);
              ++controls_stage;
            } else if (controls_stage == 11 && elapsed >= 8000) {
              require(!orbit_drag && std::abs(orbit.yaw + .3f) < .01f &&
                      std::abs(orbit.distance - 6.3f) < .01f);
              SDL_Event event{};
              event.type = SDL_EVENT_WINDOW_FOCUS_GAINED;
              SDL_PushEvent(&event);
              camera_events(false, false, 50, 8, 0);
              ++controls_stage;
            } else if (controls_stage == 12 && elapsed >= 8300) {
              require(!orbit_drag && std::abs(orbit.yaw + .3f) < .01f);
              camera_events(false, true, 0, 10000, 10000);
              ++controls_stage;
            } else if (controls_stage == 13 && elapsed >= 8600) {
              require(orbit.pitch == orbit.config.pitch_max &&
                      orbit.distance == orbit.config.distance_min);
              key_event(SDLK_RETURN);
              camera_events(false, false, 50, -10000, -10000);
              ++controls_stage;
            } else if (controls_stage == 14 && elapsed >= 8900) {
              require(entry == 5 && !orbit_drag &&
                      orbit.pitch == orbit.config.pitch_max &&
                      orbit.distance == orbit.config.distance_min);
              key_event(SDLK_ESCAPE);
              ++controls_stage;
            } else if (controls_stage == 15 && elapsed >= 9200) {
              require(entry == 4);
              cursor(SDL_EVENT_MOUSE_BUTTON_DOWN,
                     {world.predicted[0] + .5f, world.predicted[1],
                      world.predicted[2]});
              ++controls_stage;
            } else if (controls_stage == 16 && elapsed >= 9500) {
              require(held_ground.active);
              // Esc is the package's cancel action: it leaves held-cursor
              // movement running (PQ-010); focus loss then stops it.
              press_action(n3e::input::Action::cancel);
              ++controls_stage;
            } else if (controls_stage == 17 && elapsed >= 9600) {
              // The click target is 0.5 m away, so the walk may have arrived;
              // the held cursor (the movement source) must still be live.
              require(held_ground.active);
              SDL_Event event{};
              event.type = SDL_EVENT_WINDOW_FOCUS_LOST;
              SDL_PushEvent(&event);
              event.type = SDL_EVENT_WINDOW_FOCUS_GAINED;
              SDL_PushEvent(&event);
              camera_events(false, true, 0, 0, 0);
              ++controls_stage;
            } else if (controls_stage == 18 && elapsed >= 10100) {
              require(orbit_drag && !held_ground.active && !walking_to &&
                      movement_intent == n3e::V{});
              set_relative_mouse(false);
              camera_events(false, false, 50, -10000, 0);
              ++controls_stage;
            } else if (controls_stage == 19 && elapsed >= 10400) {
              require(!orbit_drag && orbit.pitch == orbit.config.pitch_max &&
                      std::abs(orbit.yaw + .3f) < .01f);
              ++controls_stage;
            } else if (controls_stage == 20 && elapsed >= 10800) {
              require(orbit.eye[0] < 1.801f && orbit.boom < 2.1f);
              ++controls_stage;
            } else if (controls_stage == 21 && elapsed >= 11100) {
              require(orbit.eye[0] < 1.801f && orbit.boom < 2.1f);
              ++controls_stage;
            } else if (controls_stage == 22 && elapsed >= 11400) {
              require(std::abs(orbit.boom - orbit.config.distance_max) < .001f);
              ++controls_stage;
            }
          }
          if (controls_stage != before) {
            std::cout << "CONTROLS stage=" << before
                      << " x=" << world.predicted[0]
                      << " z=" << world.predicted[2] << " heading=" << heading
                      << " camera_yaw=" << orbit.yaw << " pitch=" << orbit.pitch
                      << " zoom=" << orbit.distance << " boom=" << orbit.boom
                      << "\n";
            if (!capture_path.empty())
              capture(capture_path + ".controls-" + std::to_string(before) +
                          ".ppm",
                      width, height);
          }
        }
        if (melee_smoke && entry == 4) {
          if (!melee_start)
            melee_start = SDL_GetTicks();
          static Uint64 melee_trace = 0;
          if (SDL_GetTicks() > melee_trace + 1000) {
            melee_trace = SDL_GetTicks();
            std::cout << "MELEE trace state=" << melee.state
                      << " target=" << melee.target << " selected=" << target
                      << " seq=" << action_seq << " feedback=" << world.combat
                      << " x=" << world.predicted[0]
                      << " z=" << world.predicted[2]
                      << " focus=" << window_focused << "\n";
          }

          auto elapsed = SDL_GetTicks() - melee_start;
          for (const auto &e : world.world.entities())
            if (e.id() == world.world.self() &&
                e.strike_tick() > melee_strike) {
              melee_strike = e.strike_tick();
              ++melee_hits;
            }
          auto key = [](SDL_Keycode k) {
            SDL_Event e{};
            e.type = SDL_EVENT_KEY_DOWN;
            e.key.key = k;
            SDL_PushEvent(&e);
          };
          auto stopped = [&] {
            if (melee.target)
              throw std::runtime_error("melee cancellation failed");
          };
          // Left clicks at a pixel position, pushed as a player's would be.
          auto click_at = [&](std::array<float, 2> px, int times) {
            int lw, lh;
            SDL_GetWindowSize(w, &lw, &lh);
            for (int i = 0; i < times; ++i)
              for (auto type : {SDL_EVENT_MOUSE_BUTTON_DOWN, SDL_EVENT_MOUSE_BUTTON_UP}) {
                SDL_Event m{};
                m.type = type;
                m.button.button = SDL_BUTTON_LEFT;
                m.button.down = type == SDL_EVENT_MOUSE_BUTTON_DOWN;
                m.button.x = px[0] * lw / std::max(1, width);
                m.button.y = px[1] * lh / std::max(1, height);
                SDL_PushEvent(&m);
              }
          };
          auto aim_npc = [&] {
            for (const auto &e : world.world.entities())
              if (e.id() == melee_npc)
                orbit.yaw = std::atan2(world.predicted[0] - e.x(), world.predicted[2] - e.z());
          };
          auto npc_point = [&]() -> std::array<float, 2> {
            for (const auto &e : world.world.entities())
              if (e.id() == melee_npc && e.health()) {
                // The centre of the NPC's drawn pick box (PQ-146).
                auto *volume = n3e::targeting::volume(pick_frame, e.id());
                if (!volume) throw std::runtime_error("mouse stage NPC not drawn");
                auto q = orbit.project(n3e::targeting::box_centre(volume->box), width, height);
                if (q[2] > .1f && q[0] > 50 && q[0] < width - 200 && q[1] > 140 && q[1] < height - 200)
                  return {q[0], q[1]};
                throw std::runtime_error("mouse stage NPC off screen");
              }
            throw std::runtime_error("mouse stage NPC gone");
          };
          bool advanced = true;
          using A = n3e::input::Action;
          if (melee_stage == 0 && elapsed > 500) {
            SDL_RaiseWindow(w);
            press_action(A::target_enemy);
            press_action(A::target_enemy);
          } else if (melee_stage == 1 && elapsed > 1000 && elapsed < 2000 &&
                     !melee.target) {
            if (!target || action_seq)
              throw std::runtime_error("Z must select without attacking");
            for (const auto &candidate : world.world.entities())
              if (candidate.id() == target) {
                float expected = heading;
                n3e::face_target(world.predicted,
                                 {candidate.x(), candidate.y(), candidate.z()},
                                 expected);
                if (std::abs(expected - heading) > .01f)
                  throw std::runtime_error("Z did not face target");
              }
            if (release.ready_pose && poses[world.world.self()].state != 6)
              throw std::runtime_error("Z did not select ready pose");
            std::cout << "MELEE selection=ready no-action heading=" << heading
                      << "\n";
            if (!capture_path.empty())
              capture(capture_path + ".ready.ppm", width, height);
            press_action(A::attack_toggle);
            advanced = false;
          } else if (melee_stage == 1 && elapsed > 3000 && elapsed < 4500 &&
                     melee.target && !melee_cancel_hits) {
            // Esc (cancel) mid-melee: KO's Esc branch (005c6990 at 005c72b8)
            // never stops auto-attack or clears the target (PQ-010).
            melee_cancel_hits = melee_hits;
            press_action(A::cancel);
            std::cout << "MELEE cancel hits=" << melee_hits << " target=" << target << "\n";
            advanced = false;
          } else if (melee_stage == 1 && elapsed > 5000) {
            if (melee_hits < 2)
              throw std::runtime_error("continuous melee did not repeat");
            if (!melee_cancel_hits || !melee.target || !target ||
                melee_hits <= *melee_cancel_hits)
              throw std::runtime_error("cancel stopped melee or cleared the target");
            std::cout << "MELEE cancel-kept hits=" << melee_hits << "\n";
            press_action(A::attack_toggle);
            melee_stopped_seq = action_seq;
          } else if (melee_stage == 2 && elapsed > 6000) {
            stopped();
            if (action_seq != melee_stopped_seq)
              throw std::runtime_error("attack after stop");
            press_action(A::attack_toggle);
          } else if (melee_stage == 3 && elapsed > 6500) {
            if (!melee.target)
              throw std::runtime_error("attack toggle did not restart melee");
            // X with no party selects nothing, which clears the target and
            // stops auto-attack (005d9500 -> 005d9ce0(0)).
            press_action(A::target_party);
          } else if (melee_stage == 4 && elapsed > 7000) {
            stopped();
            if (target)
              throw std::runtime_error("party target without a party kept the target");
            press_action(A::target_enemy);
            press_action(A::attack_toggle);
          } else if (melee_stage == 5 && elapsed > 7300) {
            if (!target || !melee.target)
              throw std::runtime_error("nearest-enemy target and attack did not restart melee");
          } else if (melee_stage == 6 && elapsed > 8000) {
            stopped();
            press_action(A::attack_toggle);
          } else if (melee_stage == 7 && elapsed > 8500) {
            key(SDLK_RETURN);
          } else if (melee_stage == 9 && elapsed > 10000) {
            SDL_Event e{};
            e.type = SDL_EVENT_WINDOW_FOCUS_LOST;
            SDL_PushEvent(&e);
          } else if (melee_stage == 11 && elapsed > 11500) {
            SDL_Event e{};
            e.type = SDL_EVENT_KEY_DOWN;
            e.key.scancode = n3e::input::reconnect_key;
            SDL_PushEvent(&e);
          } else if (melee_stage == 12 && elapsed > 14000) {
            stopped();
            if (action_seq)
              throw std::runtime_error("reconnect resumed melee");
          } else if (melee_stage == 13 && elapsed > 14500) {
            // PQ-011 mouse stages: a plain click selects without attacking,
            // Ctrl+click attacks the picked actor (005e16f0), a click on empty
            // ground stops and clears, a double click attacks the selected
            // target (005e1490). Aim the camera at the nearest NPC first.
            stopped();
            melee_npc = n3e::targeting::enemy(world);
            if (!melee_npc || target)
              throw std::runtime_error("mouse stages need a fresh NPC and no target");
            aim_npc();
          } else if (melee_stage == 14 && elapsed > 15000) {
            click_at(npc_point(), 1);
          } else if (melee_stage == 15 && elapsed > 15500) {
            if (target != melee_npc || melee.target || action_seq)
              throw std::runtime_error("a plain click must select without attacking");
            std::cout << "MELEE click-select target=" << target << "\n";
            SDL_SetModState(SDL_KMOD_LCTRL);
            click_at(npc_point(), 1);
          } else if (melee_stage == 16 && elapsed > 16000) {
            SDL_SetModState(SDL_KMOD_NONE);
            if (target != melee_npc || melee.target != melee_npc || !melee.attack)
              throw std::runtime_error("Ctrl+click did not attack the picked NPC");
            std::cout << "MELEE ctrl-click attack state=" << melee.state << "\n";
            bool sent = false;
            for (float y = height * .55f; y < height - 200 && !sent; y += 25)
              for (float x = width * .3f; x < width * .7f && !sent; x += 25) {
                n3e::V point;
                if (!n3e::targeting::pick(world, pick_frame, orbit.eye, orbit.ray(x, y, width, height), release.pick.mesh_lod) &&
                    orbit.ground_point(x, y, width, height, scene, point)) {
                  click_at({x, y}, 1);
                  sent = true;
                }
              }
            if (!sent)
              throw std::runtime_error("no empty ground for the mouse stages");
          } else if (melee_stage == 17 && elapsed > 16600) {
            stopped();
            if (target)
              throw std::runtime_error("a ground click kept the target");
            std::cout << "MELEE ground-click clear\n";
            aim_npc();
          } else if (melee_stage == 18 && elapsed > 17200) {
            click_at(npc_point(), 2);  // the first click selects, the second release attacks
          } else if (melee_stage == 19 && elapsed > 17700) {
            if (target != melee_npc || melee.target != melee_npc || !melee.attack)
              throw std::runtime_error("double click did not attack the selected NPC");
            std::cout << "MELEE double-click attack state=" << melee.state << "\n";
          } else
            advanced = false;
          if (advanced) {
            std::cout << "MELEE stage=" << melee_stage++
                      << " hits=" << melee_hits << " seq=" << action_seq
                      << "\n";
            if (!capture_path.empty())
              capture(capture_path + ".stage-" + std::to_string(melee_stage) +
                          ".ppm",
                      width, height);
          }
        }
        if (life_smoke && entry == 4) {
          const n3e::Entity *self = nullptr;
          for (const auto &e : world.world.entities()) if (e.id() == world.world.self()) self = &e;
          if (self && life_stage == 0) {
            life_old = self->id(); press_action(n3e::input::Action::target_enemy); press_action(n3e::input::Action::attack_toggle); life_stage = 1;
          } else if (self && life_stage == 1 && !self->health()) {
            if (melee.target || walking_to || target || held_ground.active) throw std::runtime_error("death retained intent");
            life_action = action_seq;
            life_stage = 2;
            if (!capture_path.empty()) capture(capture_path + ".dead.ppm", width, height);
            std::cout << "LIFE death cancels intent id=" << life_old << std::endl;
          } else if (self && life_stage == 2 && self->life_state() == n3e::DEAD_READY) {
            if (!life_ready) life_ready = world.world.tick();
            if (world.world.tick() >= life_ready + 20) {
              if (self->id() != life_old || action_seq != life_action) throw std::runtime_error("automatic revival or attack while dead");
              if (!capture_path.empty()) capture(capture_path + ".ready.ppm", width, height);
              press_action(n3e::input::Action::respawn); life_stage = 3;
            }
          } else if (self && life_stage == 3 && self->id() != life_old) {
            if (self->life_state() != n3e::ALIVE || melee.target || walking_to || target || action_seq != life_action ||
                std::hypot(world.predicted[0], world.predicted[2]) > .05f)
              throw std::runtime_error("respawn retained identity/prediction/intent");
            life_stage = 4;
            if (!capture_path.empty()) capture(capture_path + ".respawn.ppm", width, height);
            std::cout << "LIFE requested replacement clears prediction id=" << self->id() << std::endl;
          }
        }
        if (animation_test && entry == 4 && release.animation) {
          for (const auto &e : world.world.entities()) {
            auto found = poses.find(e.id());
            if (found == poses.end())
              continue;
            auto &pose = found->second;
            auto signature = std::pair{pose.state, pose.strike};
            std::string role = e.npc()                        ? "npc"
                               : e.id() == world.world.self() ? "local"
                                                              : "remote";
            if (!animation_observed.contains(e.id()) ||
                animation_observed[e.id()] != signature) {
              animation_observed[e.id()] = signature;
              std::cout << "ANIMATION role=" << role << " id=" << e.id()
                        << " state=" << pose.state << " strike=" << pose.strike
                        << " hp=" << e.health() << std::endl;
            }
            std::string key = role + "-" + std::to_string(pose.state);
            if (std::chrono::duration<double>(
                    std::chrono::steady_clock::now().time_since_epoch())
                            .count() -
                        pose.since >
                    .3 &&
                animation_captured.insert(key).second && !capture_path.empty())
              capture(capture_path + "." + key + ".ppm", width, height);
          }
        }
        if (npc_observe && entry == 4) {
          for (const auto &entity : world.world.entities()) {
            if (entity.npc() && npc_observed.insert(entity.behavior()).second) {
              std::cout << "NPC state=" << entity.behavior() << " tick=" << world.world.tick()
                        << " x=" << entity.x() << " z=" << entity.z() << " hp=" << entity.health() << std::endl;
              if (!capture_path.empty())
                capture(capture_path + "." + entity.behavior() + ".ppm", width, height);
            }
          }
        }
        if (chat_test && *chat_test && !chat_sent && network && world.connected &&
            SDL_GetTicks() - start > 2000 &&
            std::any_of(world.world.entities().begin(), world.world.entities().end(),
                        [&](const auto &e) { return !e.npc() && e.id() != world.world.self(); })) {
          n3e::Envelope message;
          message.mutable_chat()->set_text(chat_test);
          network->send(message);
          chat_sent = true;
        }
        // Chat/focus stages deliberately run while gameplay input is captured.
        if (melee_smoke && melee_start) {
          auto elapsed = SDL_GetTicks() - melee_start;
          if ((melee_stage == 8 && elapsed > 9000) ||
              (melee_stage == 10 && elapsed > 10500)) {
            if (melee.target)
              throw std::runtime_error("captured input retained melee");
            SDL_Event e{};
            if (melee_stage == 8) {
              e.type = SDL_EVENT_KEY_DOWN;
              e.key.key = SDLK_ESCAPE;
            } else
              e.type = SDL_EVENT_WINDOW_FOCUS_GAINED;
            SDL_PushEvent(&e);
            press_action(n3e::input::Action::attack_toggle);
            std::cout << "MELEE stage=" << melee_stage++ << " captured-stop\n";
          }
        }
        // PQ-199: once a slain NPC's death presentation has finished (at once
        // for the stand-in model, which has no death clip) it is out of the
        // actor pick and B, as KO's corpse map is (00470b25). Aim the click
        // pick straight at its drawn box: it must not come back.
        if (world_smoke && combat_test && std::string(combat_test) == "1" && entry == 4)
          for (const auto &e : world.world.entities()) {
            if (!e.npc() || e.health() || !pick_frame.corpses.contains(e.id()))
              continue;
            auto *volume = n3e::targeting::volume(pick_frame, e.id());
            if (!volume)
              continue;
            auto q = orbit.project(n3e::targeting::box_centre(volume->box), width, height);
            auto picked = n3e::targeting::pick(world, pick_frame, orbit.eye,
                                               orbit.ray(q[0], q[1], width, height), release.pick.mesh_lod);
            auto b = n3e::targeting::npc(world, pick_frame.corpses);
            if (picked == e.id() || b == e.id())
              throw std::runtime_error("a corpse stayed in the actor pick or B");
            static std::set<uint64_t> corpse_checked;
            if (corpse_checked.insert(e.id()).second)
              std::cout << "CORPSE_PICK entity=" << e.id() << " picked=" << picked << " b=" << b << "\n";
          }
        if (world_smoke && combat_test && std::string(combat_test) == "1" &&
            !capture_path.empty()) {
          const bool stages[] = {saw_reward, saw_dead, saw_respawn};
          const char *names[] = {"reward", "death", "respawn"};
          for (unsigned stage = 0; stage < 3; ++stage)
            if (stages[stage] && !(captured_stages & (1u << stage))) {
              captured_stages |= 1u << stage;
              capture(capture_path + "." + names[stage] + ".ppm", width,
                      height);
              std::cout << "COMBAT stage=" << names[stage]
                        << " tick=" << world.world.tick()
                        << " self=" << world.world.self() << "\n";
            }
        }
        if (world_smoke &&
            SDL_GetTicks() - start > unsigned(world_smoke) * 1000) {
          if(layout_test)throw std::runtime_error("UIF layout replay incomplete stage="+std::to_string(layout_stage));
          if(panel_test)throw std::runtime_error("panel replay incomplete stage="+std::to_string(panel_stage)+" focus="+std::to_string(window_focused));
          if(uif_test){if(!capture_path.empty())capture(capture_path+".incomplete.ppm",width,height);throw std::runtime_error("UIF actions incomplete stage="+std::to_string(uif_stage)+" focus="+std::to_string(window_focused)+" entry="+std::to_string(entry)+" pose="+std::to_string(poses[world.world.self()].state)+" names="+std::to_string(hud?hud->names.size():0)+" bag="+world.bag_status+" bank="+world.storage_status+" friends="+world.friend_status);}
          if(feature_test)throw std::runtime_error("integrated HUD incomplete stage="+std::to_string(feature_stage)+" focus="+std::to_string(window_focused)+" entry="+std::to_string(entry)+" due="+std::to_string(feature_due));
          if((bag_test||commerce_test||repair_test||equipment_test||wear_test)&&!world.connected)throw std::runtime_error("inventory/commerce replay disconnected: "+world.status);
          if(friends_test&&friends_stage!=11)throw std::runtime_error("friends SDL incomplete stage="+std::to_string(friends_stage)+" status="+world.friend_status);
          if(party_test&&party_stage!=16)throw std::runtime_error("party SDL incomplete stage="+std::to_string(party_stage)+" status="+world.party_status);
          if(storage_auth_test&&auth_stage!=23)throw std::runtime_error("warehouse password SDL incomplete stage="+std::to_string(auth_stage)+" status="+world.storage_auth_status);
          if(storage_test&&storage_stage!=15)throw std::runtime_error("storage SDL replay incomplete stage="+std::to_string(storage_stage)+" status="+world.storage_status);
          if(wear_test&&wear_stage!=5)throw std::runtime_error("wear SDL replay incomplete stage="+std::to_string(wear_stage)+" target="+std::to_string(melee.target)+" status="+world.combat);
          if(equipment_test&&equipment_stage!=11)throw std::runtime_error("equipment SDL replay incomplete");
          if(repair_test&&repair_stage!=6)throw std::runtime_error("repair SDL replay incomplete");
          if(commerce_test&&commerce_stage!=9)throw std::runtime_error("commerce SDL replay incomplete");
          if(bag_test&&bag_stage!=8)throw std::runtime_error("inventory SDL replay incomplete");
          if(refusal_test&&refusal_stage!=17)throw std::runtime_error("refusal routing replay incomplete stage="+std::to_string(refusal_stage)+" status="+world.status);
          if(edit_test&&edit_stage!=8)throw std::runtime_error("editor publication/input capture incomplete");
          if(npc_info_test){
            bool inspect=std::any_of(world.registry.capabilities().begin(),world.registry.capabilities().end(),[](const auto&c){return c==inspect_capability;});
            std::cout<<"NPC_INFO inspect="<<inspect<<" names="<<npc_info_names<<" lines="<<npc_info_lines<<" traced="<<npc_info_traced<<" text="<<npc_info_text<<" traced_text="<<npc_info_traced_text<<"\n";
          }
          if(chat_test){
            const auto drawn=hud?hud->chat_drawn:std::nullopt;
            char color[16]="none";if(drawn)std::snprintf(color,sizeof color,"%06x",unsigned(*drawn));
            std::cout<<"CHAT_LINE sent="<<chat_sent<<" operator="<<world.chat_operator<<" drawn="<<color<<" text="<<world.chat<<"\n";
          }
          if(edit_test||edit_observe){
            if(world.world.revision().values_size()==0||std::abs(world.world.revision().values(0).value()-.25f)>.001f)throw std::runtime_error("editing observer revision mismatch");
            std::cout<<"EDIT visible revision="<<world.world.revision().revision()<<" lighting="<<world.world.revision().values(0).value()<<"\n";
          }
          if (life_smoke && life_stage != 4) throw std::runtime_error("life replay incomplete");
          if (melee_smoke && melee_stage != 20)
            throw std::runtime_error("melee replay incomplete");
          if (movement_smoke && movement_stage != 7)
            throw std::runtime_error("movement/reconnect replay incomplete");
          if (controls_smoke && controls_stage != (camera_smoke ? 23u : 8u))
            throw std::runtime_error("controls replay incomplete");
          if (play_smoke) {
            float moved = std::hypot(world.predicted[0] - test_origin[0],
                                     world.predicted[2] - test_origin[2]);
            if (world.world.entities_size() < 5 || moved < 2 || !target ||
                std::abs(orbit.yaw + .3f) > .01f ||
                std::abs(orbit.distance - 6.3f) > .01f)
              throw std::runtime_error(
                  "field input replay failed: visible=" +
                  std::to_string(world.world.entities_size()) +
                  " moved=" + std::to_string(moved) +
                  " target=" + std::to_string(target) +
                  " yaw=" + std::to_string(orbit.yaw) +
                  " zoom=" + std::to_string(orbit.distance));
            if (hud) {
              if ((world.combat.empty() && !play_melee) ||
                  world.chat.find("HUD input check") == std::string::npos)
                throw std::runtime_error("HUD click/chat replay failed: combat=" + world.combat +
                                         " melee=" + std::to_string(play_melee) + " chat confirmed=" +
                                         std::to_string(world.chat.find("HUD input check") != std::string::npos));
              std::cout << "HUD attack=" << (world.combat.empty() ? "auto-attack" : world.combat)
                        << " chat=confirmed\n";
            }
            std::cout << "PLAY orbit=" << orbit.yaw
                      << " zoom=" << orbit.distance << " moved=" << moved
                      << " target=" << target << "\n";
          }
          if (world.world.entities_size() < 2)
            throw std::runtime_error("two graphical entities not observed");
          if (combat_test && std::string(combat_test) == "1") {
            std::cout << "COMBAT reward=" << saw_reward << " death=" << saw_dead
                      << " respawn=" << saw_respawn << "\n";
            if (!saw_reward || !saw_dead || !saw_respawn)
              throw std::runtime_error("graphical playable loop incomplete");
          }
          std::cout << "WORLD tick=" << world.world.tick()
                    << " visible=" << world.world.entities_size()
                    << " corrections=" << world.corrections << "\n";
          if (!capture_path.empty())
            capture(capture_path, width, height);
          run = false;
        }
