// Test-only replay fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Tools-client editor replay (N3E_EDIT_TEST): publication, input capture and the
// independent terminal.
      if(edit_test&&entry==4&&world.world.has_revision()){
        if(!edit_started){edit_started=SDL_GetTicks();edit_origin=world.predicted;}
        if(edit_stage==0&&SDL_GetTicks()-edit_started>700){
          walking_to=true;held_ground.active=true;melee.target=1;
          editor.smoke(release,world,network.get());edit_stage=1;
        }
        if(edit_stage==1&&world.admin.status()=="applied"){
          if(walking_to||held_ground.active||melee.target)throw std::runtime_error("editor capture retained gameplay action");
          if(std::hypot(world.predicted[0]-edit_origin[0],world.predicted[2]-edit_origin[2])>.01f)throw std::runtime_error("editor preview moved authority");
          std::cout<<"EDIT applied revision="<<world.admin.revision()<<" capture released actions, draft reload passed\n";edit_stage=2;
          editor.open = false;
          SDL_Event toggle{}; toggle.type=SDL_EVENT_KEY_DOWN;
          toggle.key.windowID=SDL_GetWindowID(w);
          toggle.key.scancode=SDL_SCANCODE_GRAVE; toggle.key.key=SDLK_GRAVE;
          SDL_PushEvent(&toggle);
          edit_started=SDL_GetTicks();
        } else if(edit_stage==2 && SDL_GetTicks()-edit_started>250) {
          if (!editor.terminal_open || editor.open)
            throw std::runtime_error("terminal did not open independently");
          if (!SDL_TextInputActive(w))
            throw std::runtime_error("terminal did not enable SDL text input");
          edit_type(w,"help");edit_stage=3; edit_started=SDL_GetTicks();
        } else if(edit_stage==3 && SDL_GetTicks()-edit_started>150) {
          edit_enter(w);edit_stage=4; edit_started=SDL_GetTicks();
        } else if(edit_stage==4 && SDL_GetTicks()-edit_started>150) {
          if (!editor.help_visible() || entry!=4)
            throw std::runtime_error("terminal typing/Enter focus failed");
          if (!editor.logged("> help"))
            throw std::runtime_error("terminal did not record the command");
          edit_type(w,"scene");edit_stage=5; edit_started=SDL_GetTicks();
        } else if(edit_stage==5 && SDL_GetTicks()-edit_started>150) {
          edit_enter(w);edit_stage=6; edit_started=SDL_GetTicks();
        } else if(edit_stage==6 && SDL_GetTicks()-edit_started>150) {
          // The earlier command and its output must survive the next command.
          if (!editor.logged("> help") || !editor.logged("> scene"))
            throw std::runtime_error("terminal scrollback lost earlier commands");
          if (!editor.logged("decoration.banner:") || !editor.logged("live revision"))
            throw std::runtime_error("scene listing missing package objects");
          SDL_Event toggle{}; toggle.type=SDL_EVENT_KEY_DOWN;
          toggle.key.windowID=SDL_GetWindowID(w);
          toggle.key.scancode=SDL_SCANCODE_GRAVE; toggle.key.key=SDLK_GRAVE;
          SDL_PushEvent(&toggle);
          edit_stage=7;
        } else if(edit_stage==7) {
          if (editor.terminal_open || editor.capture())
            throw std::runtime_error("terminal did not release capture");
          if (SDL_TextInputActive(w))
            throw std::runtime_error("closed terminal retained SDL text input");
          if (!editor.logged("> help"))
            throw std::runtime_error("closing the terminal discarded scrollback");
          edit_stage=8;
          std::cout<<"EDIT independent terminal toggle, typing, scrollback across commands, scene listing and capture release passed\n";
        }
      }
