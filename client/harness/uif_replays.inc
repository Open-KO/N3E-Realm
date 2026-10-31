// Test-only replay fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// UIF replays after the HUD draw: hotbar flash, nameplates, tours, panels, route,
// N3E_TEST_UIF_* actions, layout, integrated feature HUD and the HUD mode replay.
        if (pending_camera_events) {
          SDL_PushEvent(&pending_camera_motion);
          SDL_PushEvent(&pending_camera_wheel);
          pending_camera_events = false;
        }
        if(hotbar_test&&hud)for(const auto&[key,state]:hud->cooldowns)if(key=="hotbar:0"&&state.second>=0){
          unsigned bit=1u<<state.second;
          if(!(hotbar_flash_mask&bit)&&!capture_path.empty())capture(capture_path+".flash"+std::to_string(state.second)+".ppm",width,height);
          hotbar_flash_mask|=bit;
        }
        if(nameplate_test&&uif_stage==1){static int prior=-1;int state=poses[world.world.self()].state*2+window_focused;if(state!=prior){std::cout<<"NAMEPLATE replay pose="<<poses[world.world.self()].state<<" focus="<<window_focused<<" names="<<hud->names.size()<<"\n";prior=state;}}
        if(!tour.empty()&&world.connected&&entry==4&&tour_index<tour.size()&&SDL_GetTicks()>=tour_due){
          bool dead=false;for(const auto&e:world.world.entities())if(e.id()==world.world.self())dead=e.health()==0;
          if(dead&&tour_phase!=2){
            // A fallen character first rises again (E), like a player would.
            press_action(n3e::input::Action::respawn);tour_due=SDL_GetTicks()+1500;tour_phase=0;
          } else if(tour_phase==0){destination={tour[tour_index][0],world.predicted[1],tour[tour_index][1]};walking_to=true;running=true;tour_phase=1;}
          else if(tour_phase==1&&!walking_to){
            // Arrived or stopped by collision: let the camera settle, then capture.
            tour_phase=2;tour_due=SDL_GetTicks()+1500;
            std::cout<<"TOUR "<<tour_index<<" at "<<world.predicted[0]<<","<<world.predicted[2]<<"\n";
          } else if(tour_phase==2&&SDL_GetTicks()>=tour_due){
            if(!capture_path.empty())capture(capture_path+".tour-"+std::to_string(tour_index)+".ppm",width,height);
            ++tour_index;tour_phase=0;if(tour_index==tour.size())run=false;
          }
        }
        // A HUD without draggable panels (N3HE, PQ-217) has no saved-layout scope;
        // its overview replay waits for the player's own entity instead.
        if(panel_test&&hud&&world.connected&&window_focused&&entry==4&&SDL_GetTicks()>=panel_due&&
           (!panel_state.identity.empty()||(hud->data.movables.empty()&&std::any_of(world.world.entities().begin(),world.world.entities().end(),[&](const auto&e){return e.id()==world.world.self();})))){
          auto find=[&](const std::string&key)->const n3e::HudMovable&{for(const auto&m:hud->data.movables)if(m.key==key)return m;throw std::runtime_error("missing movable "+key);};
          auto bounds=[&](const n3e::HudMovable&m){return hud->movable_rectangle(m,m.bounds,width,height);};
          auto layout=[&](const char*phase){
            const auto&chat=find("chat"),&hot=find("hotkey");auto c=bounds(chat),k=bounds(hot);
            std::cout<<"PANEL "<<phase<<" chat="<<c[0]<<","<<c[1]<<" hotkey="<<k[0]<<","<<k[1];
            for(const auto&m:hud->data.movables)if(m.group==chat.group&&m.panel!=chat.panel){auto b=bounds(m);std::cout<<" follower="<<b[0]<<","<<b[1];}
            std::cout<<" size="<<width<<"x"<<height<<"\n";
          };
          int lw,lh;SDL_GetWindowSize(w,&lw,&lh);
          auto mouse=[&](Uint32 type,float x,float y){SDL_Event e{};e.type=type;float wx=x*lw/std::max(1,width),wy=y*lh/std::max(1,height);
            if(type==SDL_EVENT_MOUSE_MOTION){e.motion.which=0x6e3e;e.motion.windowID=SDL_GetWindowID(w);e.motion.x=wx;e.motion.y=wy;e.motion.state=SDL_BUTTON_LMASK;}
            else{e.button.which=0x6e3e;e.button.windowID=SDL_GetWindowID(w);e.button.button=SDL_BUTTON_LEFT;e.button.down=type==SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.x=wx;e.button.y=wy;}
            SDL_PushEvent(&e);};
          auto grip=[&](const std::string&key){const auto&m=find(key);auto r=hud->movable_rectangle(m,m.handle,width,height);return std::array<float,2>{(r[0]+r[2])*.5f,(r[1]+r[3])*.5f};};
          panel_due=SDL_GetTicks()+150;
          auto map_state=[&](const char*phase){
            for(const auto&q:hud->data.records)if(q.binding=="minimap"){auto r=hud->rectangle(q,width,height);
              std::cout<<"MINIMAP "<<phase<<" open="<<hud->minimap_open<<" rect="<<r[0]<<","<<r[1]<<","<<r[2]<<","<<r[3]
                     <<" self="<<hud->minimap_self[0]<<","<<hud->minimap_self[1]<<" player="<<world.predicted[0]<<","<<world.predicted[2]<<"\n";}
            if(!capture_path.empty())capture(capture_path+"."+phase+".ppm",width,height);};
          if(std::string(panel_test)=="restore"){layout("restored");run=false;}
          else if(std::string(panel_test)=="escape"){
            // PQ-010: Esc closes the front-most dialog only, one per press
            // (00648a40 -> the focused window; 00579260 front of the z-list),
            // and never the minimap, which is the state bar's group (005445c0).
            using A=n3e::input::Action;
            auto fail=[&](const char*what){std::cerr<<"ESCAPE diagnostic bag="<<bag_open<<" character="<<(equipment_open||friends_open)<<" minimap="<<hud->minimap_open<<"\n";throw std::runtime_error(what);};
            switch(panel_stage++){
            case 0:if(bag_open||equipment_open||friends_open||hud->minimap_open||!hud->data.minimap)fail("escape replay must start with no window open");
              press_action(A::minimap);press_action(A::character);break;
            case 1:if(!hud->minimap_open||!(equipment_open||friends_open))fail("M and U did not open the minimap and the character window");
              press_action(A::inventory);break;
            case 2:if(!bag_open||!(equipment_open||friends_open))fail("I did not open the inventory beside the character window");
              if(!capture_path.empty())capture(capture_path+".open.ppm",width,height);
              press_action(A::cancel);break;
            case 3:if(bag_open||!(equipment_open||friends_open)||!hud->minimap_open)fail("the first Esc must close only the inventory, opened last");
              std::cout<<"ESCAPE first=inventory character=open minimap=open\n";press_action(A::cancel);break;
            case 4:if(equipment_open||friends_open||bag_open||!hud->minimap_open)fail("the second Esc must close the character window and keep the minimap");
              std::cout<<"ESCAPE second=character minimap=open\n";press_action(A::cancel);break;
            case 5:if(!hud->minimap_open)fail("Esc with no dialog open closed the minimap");
              if(!capture_path.empty())capture(capture_path+".closed.ppm",width,height);
              std::cout<<"ESCAPE third=none minimap=open\n";run=false;break;
            }
          }
          else if(std::string(panel_test)=="minimap")switch(panel_stage++){
            // M opens the overview map (hidden at start); the command-bar map button closes it.
            case 0:if(!hud->data.minimap||hud->minimap_open)throw std::runtime_error("minimap must start hidden");
              {SDL_Event k{};k.type=SDL_EVENT_KEY_DOWN;k.key.windowID=SDL_GetWindowID(w);k.key.key=SDLK_M;k.key.down=true;SDL_PushEvent(&k);k.type=SDL_EVENT_KEY_UP;k.key.down=false;SDL_PushEvent(&k);}break;
            case 1:if(!hud->minimap_open)throw std::runtime_error("M did not open the minimap");map_state("open");break;
            case 2:for(const auto&q:hud->data.records)if(q.kind==2&&q.binding=="toggle_minimap"){auto r=hud->rectangle(q,width,height);
                mouse(SDL_EVENT_MOUSE_MOTION,(r[0]+r[2])*.5f,(r[1]+r[3])*.5f);mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,(r[0]+r[2])*.5f,(r[1]+r[3])*.5f);mouse(SDL_EVENT_MOUSE_BUTTON_UP,(r[0]+r[2])*.5f,(r[1]+r[3])*.5f);}break;
            case 3:if(hud->minimap_open)throw std::runtime_error("map button did not close the minimap");map_state("closed");run=false;break;
          }
          else switch(panel_stage++){
            case 0:layout("default");{auto g=grip("chat");panel_before={g[0],g[1],0,0};mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,g[0],g[1]);}break;
            case 1:if(!hud->panel_drag)throw std::runtime_error("chat handle did not start a drag");mouse(SDL_EVENT_MOUSE_MOTION,panel_before[0]+100,panel_before[1]-150);break;
            case 2:mouse(SDL_EVENT_MOUSE_MOTION,panel_before[0]+200,panel_before[1]-300);break;
            case 3:mouse(SDL_EVENT_MOUSE_BUTTON_UP,panel_before[0]+200,panel_before[1]-300);break;
            // The hotkey starts at the left edge; a 6 px nudge must snap back to x = 0.
            case 4:layout("chat-moved");{auto g=grip("hotkey");panel_before={g[0],g[1],0,0};mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,g[0],g[1]);}break;
            case 5:mouse(SDL_EVENT_MOUSE_MOTION,panel_before[0]+6,panel_before[1]+120);break;
            case 6:mouse(SDL_EVENT_MOUSE_BUTTON_UP,panel_before[0]+6,panel_before[1]+120);break;
            case 7:if(hud->panel_drag)throw std::runtime_error("drag survived release");layout("moved");run=false;break;
          }
        }
        // Holds the scripted replay at its route stage until every waypoint is reached.
        auto route_step=[&]()->bool{
          if(test_route.empty()||route_index>test_route.size()||uif_stage!=route_stage)return false;
          if(walking_to)return true;
          if(route_index==test_route.size()){
            ++route_index;running=route_running;uif_due=SDL_GetTicks()+800;
            if(skills_test)skill_origin=world.predicted; // cast checks measure from the worm area
            return true;
          }
          if(route_index==0){route_running=running;running=true;}
          destination={test_route[route_index][0],world.predicted[1],test_route[route_index][1]};walking_to=true;++route_index;return true;
        };
        if(uif_test&&uif_dialogs&&world.connected&&window_focused&&entry>=4&&SDL_GetTicks()>=uif_due&&!route_step()){
          auto click=[&](const std::string&action){
            for(const auto&q:hud->data.records)if(q.kind==2&&q.binding=="action"&&q.text==action&&hud->visible(q)){
              auto r=hud->rectangle(q,width,height);int lw,lh;SDL_GetWindowSize(w,&lw,&lh);
              SDL_Event e{};e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.which=replay_mouse;e.button.button=SDL_BUTTON_LEFT;e.button.x=(r[0]+r[2])*.5f*lw/width;e.button.y=(r[1]+r[3])*.5f*lh/height;SDL_PushEvent(&e);e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+250;return;
            }throw std::runtime_error("missing visible UIF action: "+action);
          };
          auto type=[&](const char*value){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=value;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+250;};
          auto confirm=[&](){if(!feature_ui.prompt)throw std::runtime_error("UIF confirmation missing at stage "+std::to_string(uif_stage));click("confirm");};
          auto point=[&](const std::string&action){
            for(const auto&q:hud->data.records)if(q.kind==2&&q.text==action&&hud->visible(q)){
              auto r=hud->rectangle(q,width,height);int lw,lh;SDL_GetWindowSize(w,&lw,&lh);
              return std::array<float,2>{(r[0]+r[2])*.5f*lw/width,(r[1]+r[3])*.5f*lh/height};
            }throw std::runtime_error("missing drag target "+action);
          };
          auto mouse=[&](unsigned type,const std::array<float,2>&xy){
            SDL_Event e{};e.type=type;
            // The replay's own mouse ID (PQ-355): the item tooltip replay drops
            // the desktop's pointer events, as the panel and play replays do.
            if(type==SDL_EVENT_MOUSE_MOTION){e.motion.which=replay_mouse;e.motion.x=xy[0];e.motion.y=xy[1];e.motion.state=SDL_BUTTON_LMASK;}
            else{e.button.which=replay_mouse;e.button.button=SDL_BUTTON_LEFT;e.button.x=xy[0];e.button.y=xy[1];}
            SDL_PushEvent(&e);
          };
          auto drag_to=[&](const std::string&from,const std::string&to){
            mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,point(from));
            auto xy=to.empty()?std::array<float,2>{20,200}:point(to);
            mouse(SDL_EVENT_MOUSE_MOTION,xy);mouse(SDL_EVENT_MOUSE_BUTTON_UP,xy);++uif_stage;uif_due=SDL_GetTicks()+250;
          };
          auto hover=[&](const std::string&key){mouse(SDL_EVENT_MOUSE_MOTION,point(key));++uif_stage;uif_due=SDL_GetTicks()+350;};
          auto screenshot=[&](const std::string&label){if(!capture_path.empty())capture(capture_path+"."+label+".ppm",width,height);};
          auto chest_click=[&](unsigned button){
            if(!release.loot_model||loot_mesh.empty()||world.loot.drops_size()==0)throw std::runtime_error("chest model/bundle missing");
            n3e::V lo{100,100,100},hi{-100,-100,-100};
            for(size_t i=0;i<loot_mesh.size();i+=8)for(unsigned k=0;k<3;++k){lo[k]=std::min(lo[k],loot_mesh[i+k]);hi[k]=std::max(hi[k],loot_mesh[i+k]);}
            const auto&drop=world.loot.drops(0);uif_serial=drop.encounter();auto q=orbit.project({drop.x()+(lo[0]+hi[0])*.5f,drop.y()+(lo[1]+hi[1])*.5f,drop.z()+(lo[2]+hi[2])*.5f},width,height);
            if(pick_loot(world,loot_mesh,scene,orbit,q[0],q[1],width,height)!=uif_serial)throw std::runtime_error("chest test ray missed");
            int lw,lh;SDL_GetWindowSize(w,&lw,&lh);SDL_Event e{};e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.button=button;e.button.x=q[0]*lw/width;e.button.y=q[1]*lh/height;SDL_PushEvent(&e);e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);uif_due=SDL_GetTicks()+350;
          };
          auto appearance=[&](uint32_t key){for(const auto&e:world.world.entities())if(e.id()==world.world.self())return std::find(e.appearance().begin(),e.appearance().end(),key)!=e.appearance().end();return false;};
          auto tooltip_check=[&](const std::string&key,const std::string&line){
            if(hud->hit(hud->pointer_x,hud->pointer_y,width,height)!=key||!hud->tooltips.contains(key)||
               std::none_of(hud->tooltips.at(key).begin(),hud->tooltips.at(key).end(),[&](const auto&row){return row.text.starts_with(line);}))throw std::runtime_error("tooltip missing "+key+" / "+line);
          };
          if(expiry_test&&uif_stage==28&&chest_checks==2){
            for(const auto&e:world.world.entities())if(e.id()==world.world.self()){
              if(!e.health())throw std::runtime_error("expiry replay actor died");
              double now=SDL_GetTicks()/1000.0;
              if(!item_wait&&expiry_potions<5&&e.health()+80<=world.world.max_health()&&now-expiry_drink>3){text_entry="/use 2";item_command();++expiry_potions;expiry_drink=now;}
            }
            if(loot_ui.encounter)expiry_opened=true;
            if(world.loot.drops_size()==0){
              double elapsed=SDL_GetTicks()/1000.0-loot_seen;
              if(!expiry_opened||!approach_pose||loot_ui.encounter||!loot_instances(world).empty()||elapsed<18||elapsed>22)throw std::runtime_error("loot expiry timing/cleanup");
              screenshot("expired");std::cout<<"EXPIRY_POTIONS "<<expiry_potions<<"\n";std::cout<<"PASS UIF SDL Z/R confirmed approach and chest/pickup expiry elapsed="<<elapsed<<"\n";run=false;
            }
          }else
          if(skills_test){
            const n3e::Entity* self=nullptr;for(const auto&e:world.world.entities())if(e.id()==world.world.self())self=&e;
            if(!self||!release.skills||!self->health())throw std::runtime_error("skill replay actor");
            auto key=[&](SDL_Keycode code,unsigned delay=400){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=code;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+delay;};
            auto advance=[&](unsigned delay=400){++uif_stage;uif_due=SDL_GetTicks()+delay;};
            switch(uif_stage){
            case 0:if(world.bag.slots_size()>9){skill_origin={self->x(),self->y(),self->z()};key(SDLK_K);}break;
            case 1:if(!skills_ui.open||bag_open)throw std::runtime_error("skill window toggle");screenshot("skills");drag_to("skill:0","hotbar:0");break;
            case 2:{auto xy=point("skill:1");SDL_Event e{};e.button.button=SDL_BUTTON_RIGHT;e.button.x=xy[0];e.button.y=xy[1];e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;SDL_PushEvent(&e);e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);advance();}break;
            // PQ-481 (D-245): Light Strike is above the new character's level,
            // so the right button's copy leaves its slot empty, as 1298's tree
            // keeps a locked skill's enigma icon off the hotbar (004e3120).
            case 3:if(hotbar.assignments[0]!=release.skills->entries[0].id||world.world.inventory().level()>=release.skills->entries[1].level||!hotbar.assignments[1].empty())throw std::runtime_error("skill registration");std::cout<<"SKILL_LOCKED_COPY_REFUSED skill="<<release.skills->entries[1].id<<" level="<<world.world.inventory().level()<<"\n";key(SDLK_K);break;
            case 4:if(skills_ui.open)throw std::runtime_error("K did not close skills");uif_serial=self->resource();key(SDLK_1,900);break;
            case 5:if(self->cast_skill()!=release.skills->entries[0].id)throw std::runtime_error("healing cast missing");screenshot("healing-cast");advance(1500);break;
            case 6:if(!self->cast_skill().empty()||(self->resource()+5<uif_serial||self->resource()+3>uif_serial))throw std::runtime_error("healing completion/cost");screenshot("healed");key(SDLK_K);break;
            case 7:click("inventory");break;
            case 8:if(skills_ui.open||!bag_open)throw std::runtime_error("inventory/skill overlap");text_entry="/equip 1 1";item_command();click("close:1");break;
            case 9:
              if(world.world.inventory().level()>=2){melee.stop();walking_to=false;destination=skill_origin;walking_to=true;advance();}
              else if(!melee.target){target=0;float best=1e9;for(const auto&e:world.world.entities())if(e.npc()&&e.health()){float d=std::hypot(e.x()-self->x(),e.z()-self->z());if(d<best){best=d;target=e.id();}}if(target)melee.toggle(target);}
              break;
            // PQ-481 (D-245): at its level the right button copies Light Strike.
            case 10:if(!walking_to){if(world.world.inventory().level()<release.skills->entries[1].level)throw std::runtime_error("strike still locked");key(SDLK_K);}break;
            case 11:{if(!skills_ui.open)throw std::runtime_error("skill window reopen");auto xy=point("skill:1");SDL_Event e{};e.button.button=SDL_BUTTON_RIGHT;e.button.x=xy[0];e.button.y=xy[1];e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;SDL_PushEvent(&e);e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);advance();}break;
            case 12:if(hotbar.assignments[1]!=release.skills->entries[1].id)throw std::runtime_error("unlocked skill registration");std::cout<<"SKILL_UNLOCKED_COPY skill="<<release.skills->entries[1].id<<" level="<<world.world.inventory().level()<<"\n";key(SDLK_K);break;
            case 13:if(!walking_to){if(skills_ui.open)throw std::runtime_error("K did not close skills");target=0;float best=25;for(const auto&e:world.world.entities())if(e.npc()&&e.health()){float d=std::hypot(e.x()-self->x(),e.z()-self->z());if(d<best){best=d;target=e.id();}}if(!target)throw std::runtime_error("spell replay range");for(const auto&e:world.world.entities())if(e.id()==target)orbit.yaw=std::atan2(self->x()-e.x(),self->z()-e.z());key(SDLK_2,1050);}break;
            case 14:if(self->cast_skill()!=release.skills->entries[1].id)throw std::runtime_error("strike cast missing");screenshot("strike-cast");advance(1000);break;
            case 15:if(!hud->cooldowns.contains("hotbar:1"))throw std::runtime_error("skill cooldown sweep missing");screenshot("strike-cooldown");advance(900);break;
            case 16:if(!audio.enabled||!audio.audible_frames||audio.peak<=0)throw std::runtime_error("skill native audio empty");std::cout<<"AUDIO frames="<<audio.audible_frames<<" peak="<<audio.peak<<"\n";std::cout<<"PASS UIF SDL skill window, K toggling, inventory exclusion, drag/right-click registration, cast pose, healing, ordinary level progression, attack spell and cooldown sweep\n";run=false;break;
            }
          }else if(marker_test){
            if(!release.target_marker||release.target_marker->parts.size()!=2)throw std::runtime_error("missing target artwork");
            auto key=[&](SDL_Keycode key){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=key;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+500;};
            auto face=[&](){for(const auto&e:world.world.entities())if(e.id()==target){
              orbit.yaw=std::atan2(world.predicted[0]-e.x(),world.predicted[2]-e.z());
              std::cout<<"MARKER target="<<target<<" position="<<e.x()<<","<<e.y()<<","<<e.z()<<" terrain_faces="<<marker_ground.collision.triangles()<<" gl="<<glGetError()<<"\n";
            }++uif_stage;uif_due=SDL_GetTicks()+500;};
            switch(uif_stage){
            case 0:if(marker_drawn)throw std::runtime_error("unselected marker");press_action(n3e::input::Action::target_enemy);++uif_stage;uif_due=SDL_GetTicks()+500;break;
            case 1:if(!target||marker_drawn!=target)throw std::runtime_error("nearest target marker missing");uif_serial=target;face();break;
            case 2:{
              // The KO map has no cycle key (Tab has no gameplay handler): turn
              // the camera to the next-nearest NPC, then pick it with the mouse,
              // as a KO player does (005e16f0).
              static uint64_t retarget=0;
              if(!retarget){
                screenshot("nearest");float best=1e9;
                for(const auto&e:world.world.entities())if(e.npc()&&e.health()&&e.id()!=uif_serial){
                  float d=std::hypot(e.x()-world.predicted[0],e.z()-world.predicted[2]);if(d<best){best=d;retarget=e.id();}
                }
                if(!retarget)throw std::runtime_error("no second NPC for the retarget replay");
                for(const auto&e:world.world.entities())if(e.id()==retarget)orbit.yaw=std::atan2(world.predicted[0]-e.x(),world.predicted[2]-e.z());
                uif_due=SDL_GetTicks()+500;break;
              }
              bool sent=false;
              for(const auto&e:world.world.entities())if(e.id()==retarget&&e.health()){
                auto*volume=n3e::targeting::volume(pick_frame,e.id());if(!volume)continue;  // aim at its drawn pick box (PQ-146)
                auto xy=orbit.project(n3e::targeting::box_centre(volume->box),width,height);
                if(xy[0]>50&&xy[0]<width-50&&xy[1]>140&&xy[1]<height*.7f&&xy[2]>0&&hud->hit(xy[0],xy[1],width,height).empty()){
                  int lw,lh;SDL_GetWindowSize(w,&lw,&lh);auto point=std::array<float,2>{xy[0]*lw/width,xy[1]*lh/height};
                  mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,point);mouse(SDL_EVENT_MOUSE_BUTTON_UP,point);sent=true;break;
                }
              }
              if(!sent)throw std::runtime_error("no second visible NPC for the retarget replay");
              ++uif_stage;uif_due=SDL_GetTicks()+500;
            }break;
            case 3:if(!target||target==uif_serial||marker_drawn!=target)throw std::runtime_error("retargeted marker stale");
              for(const auto&e:world.world.entities())if(e.id()==target){
                float dx=e.x()-world.predicted[0],dz=e.z()-world.predicted[2],d=std::hypot(dx,dz);
                if(d>5){destination={e.x()-dx/d*5,e.y(),e.z()-dz/d*5};walking_to=true;}
              }face();break;
            case 4:if(!walking_to){screenshot("cycle");orbit.yaw+=.5f;++uif_stage;uif_due=SDL_GetTicks()+500;}break;
            case 5:{
              screenshot("rotated");bool sent=false;
              for(float y=height*.55f;y<height*.7f&&!sent;y+=30)for(float x=width*.75f;x<width*.85f&&!sent;x+=30){
                bool clear=hud->hit(x,y,width,height).empty();
                // Clear of the whole pick set (PQ-011: players and dying NPCs too, PQ-199).
                if(n3e::targeting::pick(world,pick_frame,orbit.eye,orbit.ray(x,y,width,height),release.pick.mesh_lod))clear=false;
                n3e::V point;if(clear&&orbit.ground_point(x,y,width,height,scene,point)){
                  int lw,lh;SDL_GetWindowSize(w,&lw,&lh);auto xy=std::array<float,2>{x*lw/width,y*lh/height};
                  mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,xy);mouse(SDL_EVENT_MOUSE_BUTTON_UP,xy);sent=true;++uif_stage;uif_due=SDL_GetTicks()+150;
                }
              }
              if(!sent)throw std::runtime_error("no empty ground for target replay");
            }break;
            case 6:if(target||marker_drawn)throw std::runtime_error("cleared marker remains");screenshot("cleared");key(SDLK_ESCAPE);break;
            case 7:{
              bool sent=false;
              for(const auto&e:world.world.entities())if(e.npc()&&e.health()){
                auto*volume=n3e::targeting::volume(pick_frame,e.id());if(!volume)continue;  // aim at its drawn pick box (PQ-146)
                auto xy=orbit.project(n3e::targeting::box_centre(volume->box),width,height);
                if(xy[0]>50&&xy[0]<width-50&&xy[1]>140&&xy[1]<height*.7f&&xy[2]>0&&hud->hit(xy[0],xy[1],width,height).empty()){
                  int lw,lh;SDL_GetWindowSize(w,&lw,&lh);auto point=std::array<float,2>{xy[0]*lw/width,xy[1]*lh/height};
                  mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,point);mouse(SDL_EVENT_MOUSE_BUTTON_UP,point);uif_serial=e.id();++uif_stage;uif_due=SDL_GetTicks()+500;sent=true;break;
                }
              }
              if(!sent)throw std::runtime_error("no visible mouse target for replay");
            }break;
            case 8:if(target!=uif_serial||marker_drawn!=target)throw std::runtime_error("mouse target marker missing");screenshot("mouse");click("inventory");break;
            case 9:screenshot("hud");std::cout<<"PASS UIF SDL target marker keyboard nearest, mouse retarget, camera billboard, ground clear, mouse selection and HUD overlay\n";run=false;break;
            }
          }else if(nameplate_test){
            if(!hud->data.nameplates)throw std::runtime_error("missing nameplate metadata");
            auto self=std::find_if(hud->names.begin(),hud->names.end(),[&](const auto&n){return n.entity==world.world.self();});
            auto key=[&](){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_C;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+1500;};
            switch(uif_stage){
            case 0:
              if(self!=hud->names.end()&&std::any_of(hud->names.begin(),hud->names.end(),[&](const auto&n){return n.entity!=world.world.self()&&n.font==0;})){
                if(self->text!=n3e::harness::required("N3E_TEST_UIF_NAME")||self->font!=0)throw std::runtime_error("self name case/style");
                nameplate_standing_y=self->y;screenshot("standing");key();
              }break;
            case 1:
              if(poses[world.world.self()].state==8&&self!=hud->names.end()){
                if(self->y<=nameplate_standing_y)throw std::runtime_error("sitting name did not lower");
                screenshot("sitting");key();
              }break;
            case 2:
              if(!hud->sitting&&self!=hud->names.end()){
                if(std::abs(self->y-nameplate_standing_y)>2)throw std::runtime_error("standing name did not restore");
                orbit.yaw+=1.5707963f;++uif_stage;uif_due=SDL_GetTicks()+500;
              }break;
            case 3:
              if(std::any_of(hud->names.begin(),hud->names.end(),[](const auto&n){return n.font==1;})){
                // PQ-177: with N3E_TEST_NPC_INFO the suite granted this character
                // server.inspect; every NPC name then carries the package's info
                // line, the NPC font's height plus the gap above it, centred.
                if(npc_info_test&&release.names.npc_info){
                  const auto&style=*hud->data.nameplates;const auto&info=*release.names.npc_info;
                  for(const auto&n:hud->names)if(n.font==1&&!n.info){
                    auto line=std::find_if(hud->names.begin(),hud->names.end(),[&](const auto&l){return l.info&&l.entity==n.entity;});
                    if(line==hud->names.end())throw std::runtime_error("NPC name without the info line");
                    auto traced=world.npc_states.find(n.entity);
                    if(line->text!=n3e::npc_info_line(info,n.entity,traced==world.npc_states.end()?std::string():traced->second)||line->color!=info.color||line->y!=n.y-int(style.gap)-int(style.fonts[1].height)||line->x+line->width/2!=n.x+n.width/2)
                      throw std::runtime_error("NPC info line text, colour or placement");
                    std::cout<<"NAME_NPC_INFO entity="<<n.entity<<" text="<<line->text<<" color="<<line->color<<" y="<<line->y<<" name_y="<<n.y<<"\n";
                  }
                }
                // PQ-014: the package's names_toggle key (KO: O) hides the
                // player names the package lists and leaves NPC names.
                screenshot("mobs");press_action(n3e::input::Action::names_toggle);++uif_stage;uif_due=SDL_GetTicks()+500;
              }else if(release.names.npc_lifetime&&!walking_to){
                // PQ-174: an NPC is named only near the player; approach the
                // nearest living one.
                float best=1e9;for(const auto&e:world.world.entities())if(e.npc()&&e.health()){
                  float d=std::hypot(e.x()-world.predicted[0],e.z()-world.predicted[2]);
                  if(d<best){best=d;destination={e.x(),e.y(),e.z()};}}
                if(best<1e9){walking_to=true;uif_due=SDL_GetTicks()+500;}
              }break;
            case 4:{
              using P=n3e::NameDisplayPolicy;auto hides=name_display.policy.hides;
              bool own=self!=hud->names.end();
              bool others=std::any_of(hud->names.begin(),hud->names.end(),[&](const auto&n){return n.font==0&&n.entity!=world.world.self();});
              bool npcs=std::any_of(hud->names.begin(),hud->names.end(),[](const auto&n){return n.font==1;});
              if(name_display.shown||own==bool(hides&P::self)||(others&&(hides&P::players))||npcs==bool(hides&P::npcs))
                throw std::runtime_error("name display toggle did not apply the package policy");
              std::cout<<"NAMEPLATE toggle off self="<<own<<" players="<<others<<" npcs="<<npcs<<"\n";
              screenshot("names-off");press_action(n3e::input::Action::names_toggle);++uif_stage;uif_due=SDL_GetTicks()+500;
            }break;
            case 5:
              if(!name_display.shown||self==hud->names.end())throw std::runtime_error("second names_toggle did not restore the names");
              // PQ-166: with a party-name policy, invite the observer peer
              // (N3E_TEST_PARTY_PEER), which accepts and walks back into view
              // beyond the camera limit.
              if(release.names.party&&release.party){
                n3e::Envelope m;auto*q=m.mutable_party_request();q->set_sequence(++party_seq);q->set_operation(1);
                q->set_name(n3e::harness::required("N3E_TEST_PARTY_PEER"));network->send(m);
                nameplate_party_deadline=SDL_GetTicks()+90000;uif_stage=6;uif_due=SDL_GetTicks()+250;
              }else uif_stage=release.names.npc_lifetime?20:9;
              break;
            case 6:case 7:case 8:{
              const auto&party_names=*release.names.party;const auto&style=*hud->data.nameplates;
              float player_limit=name_distance(style,release.names,false,false); // PQ-173: other players' class limit
              const n3e::Entity*peer=nullptr;
              for(const auto&e:world.world.entities())if(e.name()==n3e::harness::required("N3E_TEST_PARTY_PEER"))peer=&e;
              bool member=peer&&std::any_of(world.party.members().begin(),world.party.members().end(),[&](const auto&m){return m.entity()==peer->id();});
              auto plate=peer?std::find_if(hud->names.begin(),hud->names.end(),[&](const auto&n){return n.entity==peer->id();}):hud->names.end();
              if(peer){
                // Face the peer from low so its name is on screen.
                auto own=effect_positions[world.world.self()];float dx=effect_positions[peer->id()][0]-own[0],dz=effect_positions[peer->id()][2]-own[2];
                orbit.yaw=std::atan2(-dx,-dz);orbit.pitch=orbit.config.pitch_min;
              }
              float camera=peer?std::sqrt(std::pow(effect_positions[peer->id()][0]-orbit.eye[0],2.f)+std::pow(effect_positions[peer->id()][1]-orbit.eye[1],2.f)+std::pow(effect_positions[peer->id()][2]-orbit.eye[2],2.f)):-1;
              if(uif_stage==6){
                if(SDL_GetTicks()>nameplate_party_deadline)throw std::runtime_error("party peer name not drawn beyond the camera limit: present="+std::to_string(peer!=nullptr)+" member="+std::to_string(member)+" labelled="+std::to_string(peer&&name_lifetime.labelled(peer->id()))+" plate="+std::to_string(plate!=hud->names.end())+" camera="+std::to_string(camera));
                if(member&&plate!=hud->names.end()&&camera>player_limit+1){
                  if(plate->color!=party_names.color.value_or(style.colors[1])||!party_names.beyond_distance)throw std::runtime_error("party name colour or distance policy");
                  std::cout<<"NAME_PARTY drawn entity="<<peer->id()<<" camera="<<camera<<" limit="<<player_limit<<" color="<<plate->color<<"\n";
                  screenshot("party-far");press_action(n3e::input::Action::names_toggle);uif_stage=7;uif_due=SDL_GetTicks()+500;nameplate_party_deadline=uif_due+3000;
                }
              }else if(uif_stage==7){
                // The camera turned away while the stage waited; face the peer
                // again for up to 3 s before judging.
                if(plate==hud->names.end()&&SDL_GetTicks()<nameplate_party_deadline)break;
                // O on: the party member's name stays (0046ea90), no other player's does.
                bool others=std::any_of(hud->names.begin(),hud->names.end(),[&](const auto&n){return n.font==0&&n.entity!=world.world.self()&&(!peer||n.entity!=peer->id());});
                bool kept=member&&plate!=hud->names.end();
                if(name_display.shown||kept!=party_names.while_hidden||((name_display.policy.hides&n3e::NameDisplayPolicy::players)&&others))
                  throw std::runtime_error("names_toggle did not keep only the party member's name: shown="+std::to_string(name_display.shown)+" member="+std::to_string(member)+" plate="+std::to_string(plate!=hud->names.end())+" others="+std::to_string(others)+" camera="+std::to_string(camera));
                std::cout<<"NAME_PARTY hidden entity="<<(peer?peer->id():0)<<" kept="<<kept<<" camera="<<camera<<"\n";
                screenshot("party-names-off");press_action(n3e::input::Action::names_toggle);uif_stage=8;uif_due=SDL_GetTicks()+500;
              }else{
                if(!name_display.shown||self==hud->names.end())throw std::runtime_error("names_toggle did not restore the names after the party check");
                uif_stage=release.names.npc_lifetime?20:9;uif_due=SDL_GetTicks()+250;
              }
            }break;
            case 9:
              click("inventory");break;
            case 10:
              screenshot("inventory");std::cout<<"PASS UIF SDL self/remote case-preserving names, NPC bold font, sitting anchor, camera, name display toggle"<<(release.names.party&&release.party?", party names":"")<<(release.names.npc_lifetime?", NPC label lifetime":"")<<" and HUD overlay\n";run=false;break;
            // PQ-174: with an NPC label lifetime, kill the nearest named NPC
            // (its name stays while it dies and goes once the death clip has
            // played: KO state 5), then walk back along the route until every
            // NPC name has been dropped by range.
            case 20:{
              const n3e::Entity*best=nullptr;float near=1e9;
              for(const auto&e:world.world.entities())if(e.npc()&&e.health()&&npc_name_lifetime.labelled(e.id())){
                float d=std::hypot(e.x()-world.predicted[0],e.z()-world.predicted[2]);if(d<near){near=d;best=&e;}}
              if(!best){
                // The worms wandered off: approach the nearest living one.
                if(!walking_to)for(const auto&e:world.world.entities())if(e.npc()&&e.health()){
                  float d=std::hypot(e.x()-world.predicted[0],e.z()-world.predicted[2]);if(d<near){near=d;destination={e.x(),e.y(),e.z()};walking_to=true;}}
                uif_due=SDL_GetTicks()+500;break;
              }
              nameplate_npc=target=best->id();destination={best->x(),best->y(),best->z()};walking_to=true;
              nameplate_npc_deadline=SDL_GetTicks()+60000;++uif_stage;uif_due=SDL_GetTicks()+250;
            }break;
            case 21:case 22:{
              if(SDL_GetTicks()>nameplate_npc_deadline)throw std::runtime_error("NPC kill for the label lifetime did not finish");
              const n3e::Entity*npc=nullptr;for(const auto&e:world.world.entities())if(e.id()==nameplate_npc)npc=&e;
              if(!npc)throw std::runtime_error("the NPC chosen for the label lifetime left view");
              if(uif_stage==21){if(!walking_to){melee.toggle(nameplate_npc);++uif_stage;}uif_due=SDL_GetTicks()+100;break;}
              uif_due=SDL_GetTicks()+50;
              if(npc->health())break;
              bool labelled=npc_name_lifetime.labelled(npc->id());
              const auto&pose=poses[npc->id()];
              // Time past the end of the death clip (the stand-in model has
              // none); the viewer judged it a moment earlier this frame.
              double past=1;
              if(release.animation&&release.animation->size()>=11){
                const auto*clips=release.animation->data()+(release.rest?10:7);
                double clock=std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
                past=pose.state==3?clock-pose.since-(clips[3].duration+clips[3].blend):-1;
              }
              // PQ-199: the actor pick (aimed at its drawn box) and B count it
              // while it dies; once the clip has ended it is a corpse and
              // neither does (KO's manager tick moves it at state 5, 00470b25).
              auto aim=[&]()->uint64_t{auto*volume=n3e::targeting::volume(pick_frame,npc->id());if(!volume)return 0;
                auto q=orbit.project(n3e::targeting::box_centre(volume->box),width,height);
                return n3e::targeting::pick(world,pick_frame,orbit.eye,orbit.ray(q[0],q[1],width,height),release.pick.mesh_lod);};
              if(past<0){
                if(pick_frame.corpses.contains(npc->id()))throw std::runtime_error("a dying NPC left the actor pick");
                if(aim()==npc->id())nameplate_npc_picked=true;
                if(n3e::targeting::npc(world,pick_frame.corpses)==npc->id())nameplate_npc_b=true;
                if(labelled)nameplate_npc_dying=true;break;
              }
              if(labelled){if(past<.5)break;throw std::runtime_error("a dead NPC kept its name after its death clip");}
              if(past<.2)break;  // the last drawn frame may predate the end of the clip
              if(!pick_frame.corpses.contains(npc->id())||aim()==npc->id()||n3e::targeting::npc(world,pick_frame.corpses)==npc->id())
                throw std::runtime_error("a corpse stayed in the actor pick or B");
              std::cout<<"PICK_NPC dying picked="<<nameplate_npc_picked<<" b="<<nameplate_npc_b<<" dead picked=0 b=0 entity="<<npc->id()<<"\n";
              std::cout<<"NAME_NPC dead entity="<<npc->id()<<" named_while_dying="<<nameplate_npc_dying<<"\n";
              screenshot("npc-dead");melee.stop();
              if(test_route.size()>=2){destination={test_route[test_route.size()-2][0],world.predicted[1],test_route[test_route.size()-2][1]};walking_to=true;}
              ++uif_stage;uif_due=SDL_GetTicks()+500;
            }break;
            case 23:
              if(walking_to)break;
              {
                unsigned named=0;for(const auto&e:world.world.entities())if(e.npc()&&npc_name_lifetime.labelled(e.id()))++named;
                std::cout<<"NAME_NPC walked away named="<<named<<"\n";
                screenshot("npc-away");uif_stage=9;uif_due=SDL_GetTicks()+250;
              }break;
            }
          }else if(weapon_test){
            const n3e::Entity* self=nullptr;for(const auto&e:world.world.entities())if(e.id()==world.world.self())self=&e;
            if(!self||!self->health())throw std::runtime_error("weapon replay actor unavailable");
            const std::array<std::array<std::string,2>,5> loadouts={{{"",""},{n3e::harness::item("blade"),""},{n3e::harness::item("blade"),n3e::harness::item("blade")},{n3e::harness::item("twohand"),""},{"",n3e::harness::item("shield")}}};
            const unsigned expected_styles[5]={1,2,3,4,5};
            auto command=[&](const std::string&text){text_entry=text;item_command();bag_open=false;uif_due=SDL_GetTicks()+250;};
            if(uif_stage==0&&world.bag.slots_size()>9&&world.bag.equipment_size()>=2){command("/buy 1 10 1");++uif_stage;}
            else if(uif_stage==1&&world.bag.slots_size()>9&&world.bag.slots(9).instance()){++uif_stage;}
            else if(uif_stage==2&&!item_wait){
              bool sent=false;
              for(unsigned slot=0;slot<2&&!sent;++slot)if(world.bag.equipment(slot).item()!=loadouts[weapon_loadout][slot]&&world.bag.equipment(slot).instance()){
                for(int i=0;i<world.bag.slots_size();++i)if(!world.bag.slots(i).instance()){
                  command("/unequip "+std::to_string(slot+1)+" "+std::to_string(i+1));sent=true;break;}}
              for(unsigned slot=0;slot<2&&!sent;++slot)if(world.bag.equipment(slot).item()!=loadouts[weapon_loadout][slot]){
                for(int i=0;i<world.bag.slots_size();++i)if(world.bag.slots(i).item()==loadouts[weapon_loadout][slot]){
                  command("/equip "+std::to_string(i+1)+" "+std::to_string(slot+1));sent=true;break;}}
              if(!sent&&self->combat_style()==expected_styles[weapon_loadout]){
                target=0;float best=1e9;for(const auto&e:world.world.entities())if(e.npc()&&e.health()){
                  float distance=std::hypot(e.x()-world.predicted[0],e.z()-world.predicted[2]);if(distance<best){best=distance;target=e.id();destination={e.x(),e.y(),e.z()};}}
                if(target){walking_to=true;++uif_stage;}
              }
            }else if(uif_stage==3&&!walking_to&&poses[self->id()].state==6){
              auto &animation=animations[self->id()];
              const auto&profile=release.combat_animation->profiles[self->combat_style()-1];
              if(animation.state!=int(10+profile.ready))throw std::runtime_error("wrong weapon ready clip");
              screenshot("style-"+std::to_string(self->combat_style())+"-ready");weapon_strike=self->strike_tick();
              if(!moving_test)melee.toggle(target);
              ++uif_stage;uif_due=SDL_GetTicks()+200;
            }else if(uif_stage==4&&moving_test&&!melee.target&&self->strike_tick()==weapon_strike){melee.toggle(target);uif_due=SDL_GetTicks()+100;
            }else if(uif_stage==4&&self->strike_tick()!=weapon_strike&&poses[self->id()].state==2){
              if(self->strike_style()!=expected_styles[weapon_loadout])throw std::runtime_error("wrong weapon strike style");
              melee.stop();weapon_strike=self->strike_tick();++uif_stage;uif_due=SDL_GetTicks()+350;
            }else if(uif_stage==5){
              auto &animation=animations[self->id()];auto&profile=release.combat_animation->profiles[self->strike_style()-1];
              if(animation.role!=2||(self->strike_moving()?animation.state!=int(10+profile.moving):std::none_of(profile.attacks.begin(),profile.attacks.end(),[&](auto c){return animation.state==int(10+c);}))||(moving_test&&!self->strike_moving()))throw std::runtime_error("wrong weapon attack clip");
              screenshot("style-"+std::to_string(self->strike_style())+"-attack");
              std::cout<<"WEAPON style="<<self->strike_style()<<" clip="<<animation.state-10<<" moving="<<self->strike_moving()<<" strike="<<weapon_strike<<"\n";
              melee.stop();walking_to=false;
              if(++weapon_loadout==5){std::cout<<"PASS UIF SDL five equipment ready/attack profiles through real accepted combat\n";run=false;}
              else uif_stage=2;
            }
          }else if(hotbar_test)switch(uif_stage){
          case 0:if(world.bag.slots_size()>9)click("inventory");break;
          case 1:drag_to("bag:1","hotbar:0");break;
          case 2:drag_to("bag:1","hotbar:1");break;
          case 3:
            if(world.bag.slots(1).quantity()!=5||hotbar.assignments[0]!=world.bag.slots(1).item()||hotbar.assignments[1]!=hotbar.assignments[0])throw std::runtime_error("hotbar registration moved inventory");
            screenshot("registered");click("close:1");break;
          case 4:{SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_1;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+200;break;}
          case 5:
            if(bag_open||!hud->cooldowns.contains("hotbar:0")||!hud->cooldowns.contains("hotbar:1"))throw std::runtime_error("hotbar key/sweep/duplicate behavior");
            screenshot("sweep");++uif_stage;uif_due=SDL_GetTicks()+500;break;
          case 6:if(!item_wait&&world.bag.slots(1).quantity()==4){click("hotbar:1");uif_due=SDL_GetTicks()+700;}break;
          case 7:if(!item_wait){if(world.bag.slots(1).quantity()!=4||world.bag_status!="cooldown")throw std::runtime_error("hotbar cooldown rejection");++uif_stage;uif_due=SDL_GetTicks()+1800;}break;
          case 8:if(hotbar_flash_mask!=7)throw std::runtime_error("hotbar completion frames missing");else click("inventory");break;
          case 9:drag_to("bag:1","bag:9");break;
          case 10:if(!item_wait&&world.bag.slots(9).quantity()==4)click("close:1");break;
          case 11:click("hotbar:0");uif_due=SDL_GetTicks()+700;break;
          case 12:if(!item_wait&&world.bag.slots(9).quantity()==3){
            if(bag_open||hud->values["count:hotbar:0"]!="3")throw std::runtime_error("hotbar moved stack count");
            text_entry="/buy 10 2 1";item_command();++uif_stage;uif_due=SDL_GetTicks()+2000;
          }break;
          case 13:if(!item_wait&&world.bag.slots(1).item()==n3e::harness::item("mana_potion")){shop_open=false;bag_open=true;click("hotbar_next");}break;
          case 14:if(hotbar.page!=1||!hud->items["hotbar:0"].empty())throw std::runtime_error("hotbar page isolation");else drag_to("bag:1","hotbar:0");break;
          case 15:click("close:1");break;
          case 16:click("hotbar:0");uif_due=SDL_GetTicks()+700;break;
          case 17:if(!item_wait&&!world.bag.slots(1).instance()){
            if(hud->values["count:hotbar:0"]!="0"||hotbar.command(0,release,world))throw std::runtime_error("empty hotbar stack");
            Hotbar reload;reload.context(hotbar.identity,world.world.self(),release);
            if(reload.assignments!=hotbar.assignments)throw std::runtime_error("hotbar persistence");
            screenshot("empty-mana");click("hotbar_prev");
          }break;
          case 18:if(hotbar.page||hud->values["count:hotbar:0"]!="3")throw std::runtime_error("hotbar return page");else drag_to("hotbar:1","hotbar:2");break;
          case 19:if(!hotbar.assignments[1].empty()||hotbar.assignments[2]!=hotbar.assignments[0])throw std::runtime_error("hotbar move");else drag_to("hotbar:2","");break;
          case 20:if(!hotbar.assignments[2].empty()||world.bag.slots(9).quantity()!=3)throw std::runtime_error("hotbar remove consumed an item");else{
            std::cout<<"PASS UIF SDL potion registration, duplicates, number key/click use, radial sweep/three original flash frames, cooldown rejection, moved stacks, pages, empty counts and saved bindings\n";run=false;
          }break;
          }else if(potion_test){
            auto right=[&](const char*key,bool down,bool up){auto xy=point(key);SDL_Event e{};e.button.button=SDL_BUTTON_RIGHT;e.button.x=xy[0];e.button.y=xy[1];
              if(down){e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;SDL_PushEvent(&e);}if(up){e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);}};
            auto advance=[&](){++uif_stage;uif_due=SDL_GetTicks()+400;};
            switch(uif_stage){
            case 0:if(world.bag.slots_size()>9)click("inventory");break;
            case 1:right("bag:1",true,false);advance();break;
            case 2:if(!hotbar.assignments[0].empty()||world.bag.slots(1).quantity()!=5)throw std::runtime_error("right press acted before release");else{right("bag:0",false,true);advance();}break;
            case 3:if(!hotbar.assignments[0].empty())throw std::runtime_error("mismatched right release registered");else{right("bag:1",true,true);advance();}break;
            case 4:if(hotbar.assignments[0]!=n3e::harness::item("potion")||world.bag.slots(1).quantity()!=5)throw std::runtime_error("right click must register without consumption");else{
              for(unsigned i=0;i<8;++i)right("bag:1",true,true);
              advance();
            }break;
            case 5:for(unsigned i=0;i<8;++i)if(hotbar.assignments[i]!=n3e::harness::item("potion"))throw std::runtime_error("right click first empty/full page");
              if(world.bag.slots(1).quantity()!=5||!hotbar.assignments[8].empty())throw std::runtime_error("full page changed inventory/other page");
              screenshot("registered");click("hotbar_next");break;
            case 6:right("bag:1",true,true);advance();break;
            case 7:if(hotbar.page!=1||hotbar.assignments[8]!=n3e::harness::item("potion")||world.bag.slots(1).quantity()!=5)throw std::runtime_error("right click current page");else click("hotbar:0");break;
            case 8:if(world.bag_status=="consumed"&&world.bag.slots(1).quantity()==4){screenshot("hp-consumed");text_entry="/retry";item_command();advance();}break;
            case 9:if(!item_wait){if(world.bag.slots(1).quantity()!=4)throw std::runtime_error("potion retry consumed twice");hover("bag:1");}break;
            case 10:tooltip_check("bag:1","Right-click to add to hotbar");screenshot("hp-tooltip");text_entry="/buy 10 10 1";item_command();advance();uif_due=SDL_GetTicks()+2500;break;
            case 11:if(!item_wait&&world.bag.slots(9).item()==n3e::harness::item("mana_potion")){shop_open=false;bag_open=true;advance();}break;
            case 12:right("bag:9",true,true);advance();break;
            case 13:if(hotbar.assignments[9]!=n3e::harness::item("mana_potion")||world.bag.slots(9).quantity()!=1)throw std::runtime_error("MP right click consumed");else click("hotbar:1");break;
            case 14:if(!item_wait&&world.bag_status=="consumed"&&!world.bag.slots(9).instance()){
              Hotbar loaded;loaded.context(hotbar.identity,hotbar.self,release);if(loaded.assignments!=hotbar.assignments)throw std::runtime_error("registered shortcuts not saved");
              advance();uif_due=SDL_GetTicks()+1000;
            }break;
            case 15:{
              screenshot("mp-consumed");if(std::getenv("N3E_TEST_EFFECTS")){if(!audio.enabled||audio.audible_frames==0||audio.peak<=0)throw std::runtime_error("native audio empty");std::cout<<"AUDIO frames="<<audio.audible_frames<<" peak="<<audio.peak<<"\n";}std::cout<<"PASS UIF SDL right-release registration, mismatch cancellation, first empty/full/current page, HP/MP hotbar use, tooltip, saved shortcuts and immutable retry\n";run=false;
            }break;
            }
          }
          else if(rest_items_test)switch(uif_stage){
          case 0:screenshot("unarmed-world");click("inventory");break;
          case 1:case 3:case 5:case 7:case 9:{
            const char*key=uif_stage==1?"bag:0":uif_stage==3?"bag:3":uif_stage==5?"bag:3":uif_stage==7?"gear:0":"bag:2";
            auto xy=point(key);SDL_Event e{};e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.button=SDL_BUTTON_RIGHT;e.button.x=xy[0];e.button.y=xy[1];SDL_PushEvent(&e);e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+400;break;
          }
          case 2:if(appearance(1)){screenshot("right-blade");++uif_stage;}break;
          case 4:if(appearance(4)){screenshot("right-twohand");++uif_stage;}break;
          case 6:if(appearance(1)){if(world.bag.equipment(1).instance())throw std::runtime_error("right-click exclusion");++uif_stage;}break;
          case 8:if(!world.bag.equipment(0).instance()){++uif_stage;}break;
          case 10:if(appearance(3)){screenshot("right-shield");click("close:1");}break;
          case 11:{SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_C;SDL_PushEvent(&e);++uif_stage;uif_due=SDL_GetTicks()+300;break;}
          case 12:if(hud->sitting&&poses[world.world.self()].state==7){screenshot("sit-down");++uif_stage;}break;
          case 13:if(poses[world.world.self()].state==8){screenshot("sitting");
            bool found=false;for(const auto&q:hud->data.records)if(q.kind==2&&q.binding=="rest"&&hud->visible(q)){
              auto r=hud->rectangle(q,width,height);int lw,lh;SDL_GetWindowSize(w,&lw,&lh);std::array<float,2>xy{(r[0]+r[2])*.5f*lw/width,(r[1]+r[3])*.5f*lh/height};mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,xy);mouse(SDL_EVENT_MOUSE_BUTTON_UP,xy);found=true;break;}
            if(!found)throw std::runtime_error("stand HUD missing");
            ++uif_stage;uif_due=SDL_GetTicks()+250;
          }break;
          case 14:if(!hud->sitting&&poses[world.world.self()].state==9){screenshot("stand-up");++uif_stage;}break;
          case 15:if(poses[world.world.self()].state==0)click("shop");break;
          case 16:drag_to("offer:1","bag:9");break;
          case 17:if(feature_ui.prompt){text_entry="18";confirm();}break;
          case 18:if(world.bag.slots(9).quantity()==18)drag_to("bag:1","bag:9");break;
          case 19:if(world.bag.slots(9).quantity()==20){
            unsigned total=0;bool remainder=false;for(const auto&r:world.bag.slots())if(r.item()==world.bag.slots(9).item()){total+=r.quantity();remainder|=r.quantity()==3;}
            if(total!=23||!remainder)throw std::runtime_error("stack overflow conservation");
            screenshot("stack-overflow");drag_to("bag:9","bag:1");
          }break;
          case 20:if(world.bag.slots(1).quantity()==20){
            // Selling only the excess of the max stack leaves a merge below cap.
            text_entry="/sell 2 5";item_command();++uif_stage;uif_due=SDL_GetTicks()+400;
          }break;
          case 21:if(world.bag.slots(1).quantity()==15)drag_to("bag:2","bag:1");break;
          case 22:if(world.bag.slots(1).quantity()==18){
            if(world.bag.slots(2).instance())throw std::runtime_error("consumed stack not cleared");
            screenshot("stack-merged");std::cout<<"PASS UIF SDL C sit-down/idle, HUD stand-up, right-click equip/replace/unequip and drag stack merge/overflow counts\n";run=false;
          }break;
          }else if(next_three_test)switch(uif_stage){
          case 0:click("inventory");break;
          case 1:if(world.bag.capacity())hover("bag:0");break;
          case 2:tooltip_check("bag:0","Durability:");screenshot("bag-tooltip");drag_to("bag:0","gear:0");break;
          case 3:if(appearance(1))hover("gear:0");break;
          case 4:tooltip_check("gear:0","Attack:");screenshot("weapon-tooltip");drag_to("bag:2","gear:1");break;
          case 5:if(appearance(3))drag_to("bag:8","gear:4");break;
          case 6:if(appearance(5))hover("gear:4");break;
          case 7:tooltip_check("gear:4","Defense:");screenshot("armor-shield");drag_to("gear:0","bag:0");break;
          case 8:if(!appearance(1))drag_to("bag:3","gear:0");break;
          case 9:if(appearance(4)&&!appearance(3)){screenshot("twohand");drag_to("gear:0","bag:2");}break;
          case 10:if(!appearance(4)){drag_to("gear:4","bag:8");}break;
          case 11:if(!appearance(5)){screenshot("unequipped");click("shop");}break;
          case 12:hover("offer:0");break;
          case 13:tooltip_check("offer:0","Buy price:");screenshot("shop-tooltip");click("bank");break;
          case 14:if(world.storage_status=="locked")click("unlock");break;
          case 15:type(n3e::harness::required("N3E_TEST_STORAGE_PASSWORD"));break;
          case 16:click("confirm");break;
          case 17:if(world.storage_authorized)click("bank");break;
          case 18:if(world.storage.capacity())drag_to("bag:0","bank:0");break;
          case 19:if(world.storage.slots(0).instance())hover("bank:0");break;
          case 20:tooltip_check("bank:0","Durability:");screenshot("warehouse-tooltip");drag_to("bank:0","bag:0");break;
          case 21:if(world.bag.slots(0).instance())click("close:4");break;
          case 22:click("inventory");break;
          case 23:drag_to("bag:0","gear:0");break;
          case 24:if(appearance(1))click("close:1");break;
          case 25:{
            target=0;float best=1e9;for(const auto&e:world.world.entities())if(e.npc()&&e.health()){
              float distance=std::hypot(e.x()-world.predicted[0],e.z()-world.predicted[2]);if(distance<best){best=distance;target=e.id();}}
            if(target){
              if(approach_test){for(auto key:{SDLK_Z,SDLK_R}){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=key;SDL_PushEvent(&e);}}
              else{for(const auto&e:world.world.entities())if(e.id()==target)destination={e.x(),e.y(),e.z()};walking_to=true;}
              ++uif_stage;
            }
          }break;
          case 26:if(!walking_to&&!melee.target&&world.loot.drops_size()==0)melee.toggle(target);
            if(world.loot.drops_size()>=3){melee.stop();walking_to=false;
            const auto&drop=world.loot.drops(0);destination={drop.x(),drop.y(),drop.z()-(loot_range_test?5.f:0.f)};walking_to=true;int lw,lh;SDL_GetWindowSize(w,&lw,&lh);mouse(SDL_EVENT_MOUSE_MOTION,{lw*.5f,lh*.5f});++uif_stage;
          }break;
          case 27:if(!walking_to){
            screenshot("ground-chest");
            if(chest_test&&(!loot_range_test||loot_range_checked))chest_click(SDL_BUTTON_LEFT);
            else{
              // KO opens a corpse's bundle by click only (005c7c60, PQ-009): turn
              // the camera to the bundle, let it settle, then left-click it.
              static bool aimed=false;
              if(!aimed){
                const auto&drop=world.loot.drops(0);orbit.yaw=std::atan2(world.predicted[0]-drop.x(),world.predicted[2]-drop.z());
                aimed=true;uif_due=SDL_GetTicks()+500;break;
              }
              aimed=false;chest_click(SDL_BUTTON_LEFT);
            }
            ++uif_stage;uif_due=SDL_GetTicks()+350;
          }break;
          case 28:if(loot_ui.encounter){
            if(loot_range_test&&!loot_range_checked){
              const auto&d=loot_ui.slots[0];float distance=std::hypot(d.x()-world.predicted[0],d.z()-world.predicted[2]);
              if(distance<=release.claim_radius||distance>=release.loot_open_radius.value_or(0))throw std::runtime_error("loot open/claim separation");
              screenshot("distant-open");click("loot:0");uif_stage=37;
            }else if(chest_test&&!chest_checks){
              if(loot_ui.encounter!=uif_serial||walking_to)throw std::runtime_error("left chest selection failed");
              screenshot("left-open");chest_checks=1;uif_stage=35;uif_due=SDL_GetTicks()+150;
            }else hover("loot:0");
          }break;
          case 37:if(!loot_ui.pending&&world.claim.status()=="out_of_range"){
            loot_range_checked=true;const auto&d=loot_ui.slots[0];destination={d.x(),d.y(),d.z()};walking_to=true;uif_stage=27;
            std::cout<<"PASS distant chest inspection with authoritative out-of-range pickup rejection\n";
          }break;
          case 33:if(!loot_ui.encounter){chest_click(SDL_BUTTON_RIGHT);uif_stage=34;}break;
          case 35:
            if(loot_ui.encounter)throw std::runtime_error("walking failed to close pickup");
            screenshot("walk-closed");uif_stage=33;break;
          case 36:
            if(loot_ui.encounter)throw std::runtime_error("turning failed to close pickup");
            screenshot("turn-closed");chest_checks=2;uif_stage=33;break;
          case 34:if(loot_ui.encounter){
            if(loot_ui.encounter!=uif_serial||orbit_drag)throw std::runtime_error("right chest selection captured camera");
            screenshot("right-open");uif_stage=chest_checks==1?36:28;uif_due=SDL_GetTicks()+150;
          }break;
          case 29:if(!hud->tooltips.contains("loot:0")||!hud->item_icon("loot:0")||!hud->item_icon("loot:1")||!hud->item_icon("loot:2")||std::count_if(hud->data.records.begin(),hud->data.records.end(),[](const auto&r){return r.panel==9&&r.binding=="item";})!=6)throw std::runtime_error("loot tooltip/icon bindings");screenshot("pickup");click("loot:0");break;
          case 30:if(!loot_ui.pending&&!loot_ui.slots[0].operation())click("loot:1");break;
          case 31:if(!loot_ui.pending&&!loot_ui.slots[1].operation())click("loot:2");break;
          case 32:if(!loot_ui.encounter&&world.loot.drops_size()==0){
            std::cout<<"PASS UIF SDL equipped weapon/shield/armor, displacement/restore, bag/gear/shop/warehouse tooltips, real combat bundle and three individual authoritative claims\n";run=false;
          }break;
          }
          else if(drag_test)switch(uif_stage){
          case 0:click("inventory");break;
          case 1:if(world.bag.capacity()){
            uif_serial=world.bag.slots(0).instance();mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,point("bag:0"));
            mouse(SDL_EVENT_MOUSE_MOTION,{600,250});++uif_stage;uif_due=SDL_GetTicks()+250;
          }break;
          case 2:
            if(!feature_ui.drag||hud->drag_key!="bag:0"||movement_intent!=n3e::V{})throw std::runtime_error("drag capture/ghost/movement");
            if(!capture_path.empty())capture(capture_path+".paperdoll-drag.ppm",width,height);
            mouse(SDL_EVENT_MOUSE_MOTION,point("gear:0"));mouse(SDL_EVENT_MOUSE_BUTTON_UP,point("gear:0"));++uif_stage;break;
          case 3:if(world.bag.equipment(0).instance()==uif_serial)drag_to("gear:0","bag:0");break;
          case 4:if(world.bag.slots(0).instance()==uif_serial)drag_to("bag:0","bag:2");break;
          case 5:if(world.bag.slots(2).instance()==uif_serial)drag_to("bag:2","");break;
          case 6:
            if(feature_ui.drag||feature_ui.prompt||world.bag.slots(2).instance()!=uif_serial||walking_to)throw std::runtime_error("outside drop failed to cancel");
            drag_to("bag:2","bag:0");break;
          case 7:if(world.bag.slots(0).instance()==uif_serial)click("shop");break;
          case 8:drag_to("offer:1","bag:2");break;
          case 9:confirm();break;
          case 10:if(world.bag.slots(2).quantity()==1)drag_to("bag:2","offer:0");break;
          case 11:if(!world.bag.slots(2).instance())click("bank");break;
          case 12:if(world.storage_status=="locked")click("unlock");break;
          case 13:type(n3e::harness::required("N3E_TEST_STORAGE_PASSWORD"));break;
          case 14:click("confirm");break;
          case 15:if(world.storage_authorized)click("bank");break;
          case 16:if(world.storage_authorized&&world.storage.capacity())drag_to("bag:0","bank:0");break;
          case 17:if(world.storage.slots(0).instance()==uif_serial)drag_to("bank:0","bag:0");break;
          case 18:if(world.bag.slots(0).instance()==uif_serial){mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,point("bag:0"));++uif_stage;uif_due=SDL_GetTicks()+250;}break;
          case 19:{
            if(!feature_ui.drag)throw std::runtime_error("focus test capture missing");
            SDL_Event e{};e.type=SDL_EVENT_WINDOW_FOCUS_LOST;SDL_PushEvent(&e);e.type=SDL_EVENT_WINDOW_FOCUS_GAINED;SDL_PushEvent(&e);
            mouse(SDL_EVENT_MOUSE_BUTTON_UP,point("bank:1"));++uif_stage;uif_due=SDL_GetTicks()+250;
          }break;
          case 20:
            if(feature_ui.drag||!hud->drag_key.empty()||world.bag.slots(0).instance()!=uif_serial||world.storage.slots(1).instance())throw std::runtime_error("focus loss did not cancel drag");
            std::cout<<"PASS UIF SDL drag preview/ghost, equip/unequip, bag move, outside/focus cancellation, shop buy/sell and warehouse deposit/withdraw\n";run=false;break;
          }
          else if(item_tooltip_test)switch(uif_stage){
          // PQ-321: the slot holding the role's item (bag first, then gear), its
          // drawn icon rectangle and its tooltip rows, for the suite to check.
          case 0:click("inventory");break;
          case 1:if(world.bag.capacity()){
            const auto&wanted=n3e::harness::item(item_tooltip_test);
            for(unsigned i=0;i<unsigned(world.bag.slots_size())&&item_tooltip_key.empty();++i)if(world.bag.slots(i).item()==wanted)item_tooltip_key="bag:"+std::to_string(i);
            for(unsigned i=0;i<unsigned(world.bag.equipment_size())&&item_tooltip_key.empty();++i)if(world.bag.equipment(i).item()==wanted)item_tooltip_key="gear:"+std::to_string(i);
            if(item_tooltip_key.empty())throw std::runtime_error("no slot holds "+wanted);
            bool drawn=false;
            for(const auto&q:hud->data.records)if(q.kind==0&&q.binding=="item"&&q.text==item_tooltip_key&&hud->visible(q)){
              auto r=hud->rectangle(q,width,height);drawn=true;
              std::cout<<"ITEM_SLOT key="<<item_tooltip_key<<" item="<<wanted<<" icon="<<(hud->item_icon(item_tooltip_key)?1:0)
                       <<" rect="<<r[0]<<","<<r[1]<<","<<r[2]<<","<<r[3]<<"\n";
            }
            if(!drawn)throw std::runtime_error("item slot not drawn: "+item_tooltip_key);
            screenshot("item-slot");hover(item_tooltip_key);item_tooltip_hover=SDL_GetTicks();
          }break;
          case 2:{
            // PQ-355: wait for the hover's result, not a fixed time: the pointer
            // on the slot, its tooltip rows, and the tooltip drawn this frame
            // for that slot; bounded, then a failure naming what was seen.
            const auto hit=hud->hit(hud->pointer_x,hud->pointer_y,width,height);
            if(hit!=item_tooltip_key||!hud->tooltips.contains(item_tooltip_key)||!hud->drawn_tooltip||hud->drawn_tooltip->key!=item_tooltip_key){
              if(SDL_GetTicks()<item_tooltip_hover+5000)break;
              std::ostringstream why;why<<"no tooltip on "<<item_tooltip_key<<" 5 s after the hover: pointer "<<hud->pointer_x<<","<<hud->pointer_y
                <<" (active "<<hud->pointer_active<<") hits '"<<hit<<"', rows "<<hud->tooltips.contains(item_tooltip_key)<<", drawn '"
                <<(hud->drawn_tooltip?hud->drawn_tooltip->key:std::string())<<"', focused "<<window_focused;
              throw std::runtime_error(why.str());
            }
            const auto&rows=hud->tooltips.at(item_tooltip_key);
            for(size_t i=0;i<rows.size();++i)std::cout<<"ITEM_TOOLTIP key="<<item_tooltip_key<<" row="<<i<<" text="<<rows[i].text<<"\n";
            // PQ-354: each row's colour and centring (the head, N3IH).
            for(size_t i=0;i<rows.size();++i){char colour[8];std::snprintf(colour,sizeof colour,"%06x",unsigned(rows[i].color&0xffffffu));
              std::cout<<"ITEM_TOOLTIP_STYLE key="<<item_tooltip_key<<" row="<<i<<" color="<<colour<<" centred="<<(i==0||rows[i].centred)<<"\n";}
            screenshot("item-tooltip");
            // PQ-354: the tooltip as drawn for the capture: its box and each
            // line's origin and drawn width (window pixels), and the scale.
            if(!hud->drawn_tooltip||hud->drawn_tooltip->key!=item_tooltip_key)throw std::runtime_error("tooltip not drawn: "+item_tooltip_key);
            {const auto&d=*hud->drawn_tooltip;std::cout<<"ITEM_TOOLTIP_DRAWN key="<<item_tooltip_key<<" rect="<<d.rect[0]<<","<<d.rect[1]<<","<<d.rect[2]<<","<<d.rect[3]
              <<" scale="<<hud->scale(width,height)<<" font="<<hud->data.font_advance<<","<<hud->data.font_height<<"\n";
             for(size_t i=0;i<d.lines.size();++i)std::cout<<"ITEM_TOOLTIP_LINE key="<<item_tooltip_key<<" row="<<i<<" x="<<d.lines[i][0]<<" y="<<d.lines[i][1]<<" width="<<d.lines[i][2]<<"\n";}
            run=false;
          }break;
          }
          else switch(uif_stage){
          case 0:click("inventory");break;
          case 1:if(world.bag.capacity()){uif_serial=world.bag.slots(0).instance();click("bag:0");}break;
          case 2:click("gear:0");break;
          case 3:confirm();break;
          case 4:if(world.bag.equipment_size()&&world.bag.equipment(0).instance()==uif_serial){if(!capture_path.empty())capture(capture_path+".equipped.ppm",width,height);++uif_stage;}break;
          case 5:click("gear:0");break;
          case 6:click("bag:0");break;
          case 7:confirm();break;
          case 8:if(world.bag.slots(0).instance()==uif_serial)click("shop");break;
          case 9:if(!capture_path.empty())capture(capture_path+".shop.ppm",width,height);click("offer_next");break;
          case 10:if(feature_ui.offer_page!=1)throw std::runtime_error("stock arrow failed");click("bag_next");break;
          case 11:if(feature_ui.offer_page!=1||feature_ui.bag_page!=1)throw std::runtime_error("stock/bag pages coupled");if(!capture_path.empty())capture(capture_path+".shop-page2.ppm",width,height);click("bag_prev");break;
          case 12:if(feature_ui.bag_page||feature_ui.offer_page!=1)throw std::runtime_error("bag previous page failed");click("close:3");break;
          case 13:if(shop_open||bag_open)throw std::runtime_error("shop close failed");click("shop");break;
          case 14:if(!shop_open||feature_ui.offer_page||feature_ui.bag_page)throw std::runtime_error("shop reopen did not reset pages");click("offer_prev");break;
          case 15:if(feature_ui.offer_page)throw std::runtime_error("stock first page boundary failed");click("offer:23");break;
          case 16:click("buy");break;
          case 17:if(feature_ui.prompt)throw std::runtime_error("empty stock purchased");click("offer:1");break;
          case 18:click("buy");break;
          case 19:if(!capture_path.empty())capture(capture_path+".quantity.ppm",width,height);confirm();break;
          case 20:if(world.bag.slots(9).quantity()==1&&world.bag.coins()<10000)click("bag:9");break;
          case 21:click("sell");break;
          case 22:confirm();break;
          case 23:if(!world.bag.slots(9).instance())click("bank");break;
          case 24:click("unlock");break;
          case 25:type(n3e::harness::required("N3E_TEST_STORAGE_PASSWORD"));break;
          case 26:if(!capture_path.empty())capture(capture_path+".masked.ppm",width,height);click("confirm");break;
          case 27:if(world.storage_authorized==1)click("bank");break;
          case 28:if(world.storage.capacity())click("bag:0");break;
          case 29:click("bank:0");break;
          case 30:confirm();break;
          case 31:if(world.storage.slots_size()&&world.storage.slots(0).instance()==uif_serial){if(!capture_path.empty())capture(capture_path+".deposit.ppm",width,height);click("bank:0");}break;
          case 32:click("bag:0");break;
          case 33:confirm();break;
          case 34:if(world.bag.slots(0).instance()==uif_serial)click("friends");break;
          case 35:click("friend_add");break;
          case 36:type(n3e::harness::required("N3E_TEST_UIF_NAME"));break;
          case 37:confirm();break;
          case 38:if(world.friends.entries_size()==1)click("friend:0");break;
          case 39:if(!capture_path.empty())capture(capture_path+".friend.ppm",width,height);click("friend_remove");break;
          case 40:confirm();break;
          case 41:if(world.friends.entries_size()==0){std::cout<<"PASS UIF SDL equip/unequip, merchant stock/bag paging, close/reopen, buy/sell, masked unlock, deposit/withdraw and friend add/remove through authoritative APIs\n";run=false;}break;
          }
        }
        if(layout_test&&hud&&world.connected&&window_focused&&entry==4){
          if(!layout_due)layout_due=SDL_GetTicks()+500;
          if(SDL_GetTicks()>=layout_due){
            auto check=[&](bool ok){if(!ok)throw std::runtime_error("UIF layout/state regression stage="+std::to_string(layout_stage));};
            const std::vector<std::string> actions={"equipment","equipment","equipment","tab:friends","tab:friends","tab:state","inventory","close:2","equipment","tab:friends","equipment","equipment","close:5","close:1"};
            // Each assertion observes the previous real SDL click, including the
            // original bottom command buttons (not their supplemental aliases).
            if(layout_stage){
              static const unsigned expected[]={4,0,4,32,32,4,6,2,6,34,2,34,2,0};
              check(((equipment_open?4u:0u)|(friends_open?32u:0u)|(bag_open?2u:0u))==expected[layout_stage-1]);
              for(const auto&q:hud->data.records)if(q.kind==2&&q.binding=="action"&&hud->visible(q)){
                if(q.text=="tab:state")check((hud->state(q.control)==1)==equipment_open);
                if(q.text=="tab:friends")check((hud->state(q.control)==1)==friends_open);
              }
              if(!capture_path.empty()&&(layout_stage==1||layout_stage==7||layout_stage==12))capture(capture_path+"."+std::to_string(layout_stage)+".ppm",width,height);
            }
            if(layout_stage==actions.size()){std::cout<<"PASS UIF layout: independent Character/Inventory, bottom toggle, tab selection/reselection, remembered page and scoped close at "<<width<<"x"<<height<<"\n";run=false;}
            else {
              auto action=actions[layout_stage];bool found=false;
              for(const auto&q:hud->data.records)if(q.kind==2&&hud->visible(q)&&((q.binding==action)||(q.binding=="action"&&q.text==action))){
                auto r=hud->rectangle(q,width,height);float x=(r[0]+r[2])*.5f,y=(r[1]+r[3])*.5f;
                check(hud->hit(x,y,width,height)==action);
                int lw,lh;SDL_GetWindowSize(w,&lw,&lh);SDL_Event e{};e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.button=SDL_BUTTON_LEFT;e.button.x=x*lw/width;e.button.y=y*lh/height;SDL_PushEvent(&e);e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);found=true;break;
              }
              check(found);++layout_stage;layout_due=SDL_GetTicks()+500;
            }
          }
        }
        if(feature_test&&hud&&world.connected&&window_focused&&(entry==4||entry==5)&&!feature_due)feature_due=SDL_GetTicks()+500;
        if(feature_test&&hud&&world.connected&&window_focused&&(entry==4||entry==5)&&feature_due&&SDL_GetTicks()>=feature_due){
          const std::vector<std::string> actions={"inventory","equipment","party","features","friends","shop","bank","command","unlock"};
          if(feature_stage<actions.size()){
            const auto &action=actions[feature_stage];
            if(!feature_sent){
              if(action=="command"){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_RETURN;SDL_PushEvent(&e);e={};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text="/bankcoins 10";SDL_PushEvent(&e);feature_sent=true;feature_due=SDL_GetTicks()+700;feature_deadline=SDL_GetTicks()+5000;}
              else {
              float x=width-90,y=0;
              if(feature_stage<3){bool found=false;for(const auto&q:hud->data.records)if(q.kind==2&&q.binding==action&&hud->visible(q)){auto r=hud->rectangle(q,width,height);x=(r[0]+r[2])*.5f;y=(r[1]+r[3])*.5f;found=true;break;}if(!found)throw std::runtime_error("missing integrated HUD control");}
              else if(uif_dialogs){bool found=false;for(const auto&q:hud->data.records)if(q.kind==2&&q.binding=="action"&&q.text==action&&hud->visible(q)){auto r=hud->rectangle(q,width,height);x=(r[0]+r[2])*.5f;y=(r[1]+r[3])*.5f;found=true;break;}if(!found)throw std::runtime_error("missing UIF action "+action);}
              else {auto buttons=feature_buttons();for(size_t i=0;i<buttons.size();++i)if(buttons[i].first==action)y=233+28*i;}
              int lw,lh;SDL_GetWindowSize(w,&lw,&lh);SDL_Event e{};e.type=SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.button=SDL_BUTTON_LEFT;e.button.x=x*lw/width;e.button.y=y*lh/height;SDL_PushEvent(&e);
              e.type=SDL_EVENT_MOUSE_BUTTON_UP;SDL_PushEvent(&e);feature_sent=true;feature_due=SDL_GetTicks()+700;feature_deadline=SDL_GetTicks()+5000;}
            }else{
              bool ok=action=="inventory"?bag_open&&world.bag.capacity()>0:action=="equipment"?equipment_open:action=="party"?party_open:action=="features"?features_open:action=="friends"?friends_open:action=="shop"?shop_open:action=="bank"?bank_open&&world.storage_status=="locked":action=="command"?entry==5&&text_entry=="/bankcoins 10":bank_secret==1&&entry==5;
              if(!ok&&SDL_GetTicks()>=feature_deadline){std::cerr<<"HUD diagnostic focus="<<window_focused<<" entry="<<entry<<" bag_open="<<bag_open<<" capacity="<<world.bag.capacity()<<" bag_status="<<world.bag_status<<"\n";throw std::runtime_error("integrated HUD action failed: "+action);}
              if(ok){
              if(!capture_path.empty())capture(capture_path+"."+action+".ppm",width,height);
              if(action=="command"){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_ESCAPE;SDL_PushEvent(&e);}
              feature_sent=false;++feature_stage;feature_due=SDL_GetTicks()+100;}
            }
          }else{SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_ESCAPE;SDL_PushEvent(&e);std::cout<<"PASS integrated KO HUD inventory, character, party, help, friends, shop, locked warehouse, command entry and masked unlock prompt\n";run=false;}
        }
        if (std::getenv("N3E_TEST_HUD") && hud && world.connected &&
            (entry == 4 || entry == 5) && hud_test_stage < 10) {
          auto check = [](bool ok) { if (!ok) throw std::runtime_error("HUD graphical replay failed"); };
          auto control = [&](const std::string &binding) -> const n3e::HudRecord & {
            for (const auto &q : hud->data.records)
              if (q.kind == 2 && q.binding == binding && hud->visible(q)) return q;
            throw std::runtime_error("HUD replay missing visible control: " + binding);
          };
          auto key = [&](SDL_Keycode code) {
            SDL_Event e{}; e.type=SDL_EVENT_KEY_DOWN; e.key.key=code; SDL_PushEvent(&e);
          };
          auto pointer = [&](const std::string &binding, Uint32 type) {
            auto r=hud->rectangle(control(binding),width,height);
            int lw,lh; SDL_GetWindowSize(w,&lw,&lh);
            SDL_Event e{}; e.type=type;
            float x=(r[0]+r[2])*.5f*lw/width, y=(r[1]+r[3])*.5f*lh/height;
            if(type==SDL_EVENT_MOUSE_MOTION) { e.motion.x=x; e.motion.y=y; }
            else { e.button.button=SDL_BUTTON_LEFT; e.button.x=x; e.button.y=y; }
            SDL_PushEvent(&e);
          };
          auto focus = [&](Uint32 type) { SDL_Event e{}; e.type=type; SDL_PushEvent(&e); };
          auto shot = [&](const char *state) {
            if(!capture_path.empty()) capture(capture_path+".hud-"+state+".ppm",width,height);
          };
          switch(hud_test_stage++) {
          case 0: check(running); shot("default"); press_action(n3e::input::Action::run_toggle); break;
          case 1: check(!running); shot("walk"); pointer("run",SDL_EVENT_MOUSE_BUTTON_DOWN); break;
          case 2: check(running && !hud->pressed); pointer("walk",SDL_EVENT_MOUSE_BUTTON_UP); break;
          case 3: pointer("inventory",SDL_EVENT_MOUSE_MOTION); break;
          case 4: check(hud->state(control("inventory").control)==2); shot("hover"); pointer("inventory",SDL_EVENT_MOUSE_BUTTON_DOWN); break;
          case 5: check(hud->state(control("inventory").control)==1); shot("down"); pointer("inventory",SDL_EVENT_MOUSE_BUTTON_UP); break;
          case 6: check(hud->state(control("inventory").control)==2); pointer("inventory",SDL_EVENT_MOUSE_BUTTON_DOWN); break;
          case 7: check(hud->pressed!=0); focus(SDL_EVENT_WINDOW_FOCUS_LOST); break;
          case 8: check(!hud->pressed && !hud->hovered); focus(SDL_EVENT_WINDOW_FOCUS_GAINED); key(SDLK_RETURN); break;
          case 9: check(entry==5 && !hud->pressed && !hud->hovered); key(SDLK_RETURN);
            std::cout << "PASS HUD graphical mode key/click, hover/down/release, focus and chat capture\n"; break;
          }
        }
