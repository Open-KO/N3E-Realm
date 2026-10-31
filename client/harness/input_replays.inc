// Test-only replay fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Scripted movement input before prediction: --world-smoke walk, N3E_TEST_COMBAT,
// N3E_TEST_ANIMATION=actor and the --movement-smoke walk/run/backward/reconnect.
// N3E_TEST_EQUIPMENT_GLOW=1 (PQ-315), N3E_TEST_ATTACHMENTS=1 (PQ-328),
// N3E_TEST_PART_STATES (PQ-356) and N3E_TEST_STAND_STILL (PQ-357) stand still,
// so glow, attachment, part-state and effect captures of separate clients
// compare (the walk's phase at a capture follows the login's wall time, so a
// walking player stands somewhere else each run). N3E_TEST_APPEARANCE_EFFECTS
// alone still walks: moradon_weapon_effects_live's capture needs the walk's
// sideways heading to show both blades.
        if (world_smoke && !play_smoke && !movement_smoke && !controls_smoke &&
            !melee_smoke && !npc_observe && !life_smoke && !animation_test && !loot_test && !bag_test && !commerce_test && !repair_test && !equipment_test && !feature_test && !uif_test && !layout_test && !panel_test && tour.empty() &&
            !std::getenv("N3E_TEST_EQUIPMENT_GLOW") && !std::getenv("N3E_TEST_ATTACHMENTS") && !std::getenv("N3E_TEST_PART_STATES") &&
            !std::getenv("N3E_TEST_STAND_STILL") && entry == 4) {
          if (!combat_test)
            dx = (SDL_GetTicks() - start) / 1500 % 2 ? -.5f : .5f;
          else {
            dx = dz = 0;
            if (!initial_self) {
              initial_self = world.world.self();
              initial_reward = world.world.inventory().last_operation();
            }
            for (const auto &e : world.world.entities()) {
              if (e.id() == world.world.self() && !e.health())
                saw_dead = true;
              if (e.npc() && e.health())
                target = e.id();
            }
            saw_respawn =
                saw_respawn || (saw_dead && world.world.self() != initial_self);
            saw_reward =
                saw_reward ||
                world.world.inventory().last_operation() != initial_reward;
            if (std::string(combat_test) == "1" && !saw_reward && target &&
                world.world.tick() >= next_test_action) {
              next_test_action = world.world.tick() + 11;
              n3e::Envelope message;
              auto *a = message.mutable_action();
              a->set_session(world.world.session());
              a->set_seq(++action_seq);
              a->set_target(target);
              a->set_action(world.world.action());
              network->send(message);
            }
          }
        }
        if (animation_test && entry == 4) {
          dx = dz = 0;
          auto elapsed = (SDL_GetTicks() - start) / 1000.;
          if (std::string(animation_test) == "actor") {
            if (!initial_self) {
              initial_self = world.world.self();
              initial_reward = world.world.inventory().last_operation();
            }
            saw_reward =
                saw_reward ||
                world.world.inventory().last_operation() != initial_reward;
            if (elapsed > 2 && elapsed < 3)
              dx = dz = -.7071068f;
            for (const auto &e : world.world.entities()) {
              if (e.npc() && e.health() && elapsed > 6 && !saw_reward &&
                  world.world.tick() >= next_test_action) {
                next_test_action = world.world.tick() + 20;
                n3e::Envelope message;
                auto *a = message.mutable_action();
                a->set_session(world.world.session());
                a->set_seq(++action_seq);
                a->set_target(e.id());
                a->set_action(world.world.action());
                network->send(message);
              }
              if (e.id() == world.world.self() &&
                  e.life_state() == n3e::DEAD_READY &&
                  world.world.tick() >= next_test_action) {
                next_test_action = world.world.tick() + 20;
                n3e::Envelope message;
                auto *r = message.mutable_respawn();
                r->set_session(world.world.session());
                r->set_seq(++respawn_seq);
                r->set_entity(e.id());
                network->send(message);
              }
            }
          }
        }
        if (movement_smoke && entry == 4) {
          if (!movement_start) {
            movement_start = SDL_GetTicks();
            movement_session = world.world.session();
          }
          auto elapsed = SDL_GetTicks() - movement_start;
          // The scripted walk/run/backward/stop timeline; from 7 s E's
          // continuous movement (the package's auto_move key) drives instead.
          if (movement_stage < 4) {
            dx = 0;
            dz = elapsed < 4000 ? -1 : elapsed < 6000 ? 1 : 0;
            move_mode = dz > 0 ? 2 : running ? 1 : 0;
          }
          unsigned clip_stage = elapsed / 2000;
          if (clip_stage < 3 && elapsed % 2000 >= 1000 &&
              !(movement_pose_captures & (1u << clip_stage))) {
            movement_pose_captures |= 1u << clip_stage;
            if (!capture_path.empty())
              movement_capture =
                  capture_path + ".pose-" + std::to_string(clip_stage) + ".ppm";
          }
          // Esc (the package's cancel action) halfway through E's run must
          // leave it running (PQ-010: 005c6990's Esc branch never calls the
          // movement code); the auto-stop stage and the distance prove it.
          if (movement_stage == 4 && elapsed >= 8000 && !movement_cancel) {
            if (!auto_move.active)
              throw std::runtime_error("continuous movement ended before cancel");
            press_action(n3e::input::Action::cancel);
            movement_cancel = true;
            std::cout << "MOVEMENT cancel z=" << world.predicted[2] << "\n";
          }
          if ((movement_stage == 0 && elapsed >= 2000) ||
              (movement_stage == 1 && elapsed >= 4000) ||
              (movement_stage == 2 && elapsed >= 6000) ||
              (movement_stage == 3 && elapsed >= 7000) ||
              (movement_stage == 4 && elapsed >= 9000) ||
              (movement_stage == 5 && elapsed >= 10000) ||
              (movement_stage == 6 &&
               world.world.session() != movement_session)) {
            const char *names[] = {"walk", "run", "backward", "stop",
                                   "auto", "auto-stop", "reconnect"};
            if (movement_stage == 4 && !auto_move.active)
              throw std::runtime_error("auto_move did not start continuous movement, or cancel stopped it");
            if (movement_stage == 5 && auto_move.active)
              throw std::runtime_error("auto_move did not stop continuous movement");
            std::cout << "MOVEMENT stage=" << names[movement_stage]
                      << " z=" << world.predicted[2]
                      << " session=" << world.world.session() << "\n";
            if (!capture_path.empty())
              movement_capture =
                  capture_path + "." + names[movement_stage] + ".ppm";
            if (movement_stage == 0)
              press_action(n3e::input::Action::run_toggle);
            if (movement_stage == 3 || movement_stage == 4)
              press_action(n3e::input::Action::auto_move);
            if (movement_stage == 5) {
              SDL_Event key{};
              key.type = SDL_EVENT_KEY_DOWN;
              key.key.scancode = n3e::input::reconnect_key;
              SDL_PushEvent(&key);
            }
            ++movement_stage;
          }
        }
