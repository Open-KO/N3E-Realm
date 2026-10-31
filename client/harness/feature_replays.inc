// Test-only replay fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Feature replays after the HUD draw: party, friends, warehouse password, storage,
// wear, equipment, repair, commerce, inventory and loot.
        if(party_test&&world.party.tick()){
          auto key=[&](){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=SDLK_RETURN;SDL_PushEvent(&e);};
          auto command=[&](const char*v){if(entry==4)key();else if(entry==5){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);key();++party_stage;}};
          if(party_stage==0)command("/party");
          else if(party_stage==1&&world.party_responses)++party_stage;
          else if(party_stage==2)command("/invite Explorer");
          else if(party_stage==3&&world.party.members_size()==2&&(!party_loot_test||world.loot_status=="claimed > Companion")&&(!coin_loot_test||(world.loot_status=="claimed coins"&&world.coin_revision>0&&world.bag.revision()>=world.coin_revision))){
            if(coin_loot_test&&!coin_capture_ready){party_open=false;bag_open=true;coin_capture_ready=true;}
            else{if(!capture_path.empty())capture(capture_path+".party.ppm",width,height);if(coin_loot_test){bag_open=false;party_open=true;}++party_stage;}
          }
          else if(party_stage==4)command("/leave");
          else if(party_stage==5&&!world.party.group()&&world.party_status=="disbanded")++party_stage;
          else if(party_stage==6)command("/partyblock");
          else if(party_stage==7&&party_block&&!world.party.invitation()&&world.party_status=="declined"){if(!capture_path.empty())capture(capture_path+".party-block.ppm",width,height);++party_stage;}
          else if(party_stage==8)command("/partyblock");
          else if(party_stage==9&&!party_block&&world.party.invitation()){if(!capture_path.empty())capture(capture_path+".party-invite.ppm",width,height);++party_stage;}
          else if(party_stage==10)command("/accept");
          else if(party_stage==11&&world.party.members_size()==2)++party_stage;
          else if(party_stage==12)command("/disband");
          else if(party_stage==13&&world.party_status=="not_leader")++party_stage;
          else if(party_stage==14)command("/leave");
          else if(party_stage==15&&!world.party.group()&&world.party_status=="disbanded"){++party_stage;std::cout<<"PASS party SDL roster, invite, leave, blocking/automatic decline, accept and server leader denial\n";}
        }
        if(friends_test&&world.friends.capacity()){
          auto key=[&](SDL_Keycode k=SDLK_RETURN){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          auto type=[&](const char*v){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);};
          if(friends_stage==0&&entry==4){key();++friends_stage;}
          else if(friends_stage==1&&entry==5){type("/friends");friends_wait=world.friend_responses;key();++friends_stage;}
          else if(friends_stage==2&&world.friend_responses>friends_wait){if(world.friends.entries_size())throw std::runtime_error("friend initial roster");key();++friends_stage;}
          else if(friends_stage==3&&entry==5){type("/friend Explorer");friends_wait=world.friend_responses;key();++friends_stage;}
          else if(friends_stage==4&&world.friend_responses>friends_wait){if(world.friend_status!="committed"||world.friends.entries_size()!=1)throw std::runtime_error("friend add: "+world.friend_status);++friends_stage;}
          else if(friends_stage==5&&world.friend_presence.entries_size()&&world.friend_presence.entries(0).online()){
            if(!capture_path.empty()){capture(capture_path+".friends.ppm",width,height);}key(SDLK_RIGHTBRACKET);++friends_stage;}
          else if(friends_stage==6&&friend_page==1){key(SDLK_LEFTBRACKET);key();++friends_stage;}
          else if(friends_stage==7&&entry==5){type("/unfriend Explorer");friends_wait=world.friend_responses;key();++friends_stage;}
          else if(friends_stage==8&&world.friend_responses>friends_wait){if(world.friend_status!="committed"||world.friends.entries_size())throw std::runtime_error("friend remove");key();++friends_stage;}
          else if(friends_stage==9&&entry==5){type("/friendretry");friends_wait=world.friend_responses;key();++friends_stage;}
          else if(friends_stage==10&&world.friend_responses>friends_wait){if(world.friend_status!="committed"||world.friends.entries_size())throw std::runtime_error("friend retry");++friends_stage;std::cout<<"PASS friends SDL load, directed add, online presence, pages, remove and exact retry\n";}
        }
        if(storage_auth_test&&world.bag.capacity()){
          auto key=[&](){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=SDLK_RETURN;SDL_PushEvent(&e);};
          auto type=[&](const char*v){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);};
          if(auth_stage==0&&entry==4){key();++auth_stage;}
          else if(auth_stage==1&&entry==5){type("/bank");key();++auth_stage;}
          else if(auth_stage==2&&world.storage_responses){if(world.storage_status!="locked"||world.storage.capacity())throw std::runtime_error("protected bank disclosed storage");key();++auth_stage;}
          else if(auth_stage==3&&entry==5){type("/bankunlock discarded_inline");key();++auth_stage;}
          else if(auth_stage==4&&bank_secret==1){if(!text_entry.empty())throw std::runtime_error("inline warehouse secret retained");type(n3e::harness::required("N3E_TEST_STORAGE_PASSWORD"));++auth_stage;}
          else if(auth_stage==5&&!text_entry.empty()){if(!capture_path.empty())capture(capture_path+".masked.ppm",width,height);key();++auth_stage;}
          else if(auth_stage==6&&entry==4&&world.storage_auth_responses){if(world.storage_authorized!=1)throw std::runtime_error("warehouse unlock failed");key();++auth_stage;}
          else if(auth_stage==7&&entry==5){type("/bank");key();++auth_stage;}
          else if(auth_stage==8&&world.storage_responses==2){if(world.storage_status!="committed"||world.storage.slots_size()!=192)throw std::runtime_error("unlocked warehouse open failed");key();++auth_stage;}
          else if(auth_stage==9&&entry==5){type("/bankpassword");key();++auth_stage;}
          else if(auth_stage==10&&bank_secret==2){type(n3e::harness::required("N3E_TEST_STORAGE_PASSWORD"));key();++auth_stage;}
          else if(auth_stage==11&&bank_secret==3){type(n3e::harness::required("N3E_TEST_STORAGE_REPLACEMENT"));key();++auth_stage;}
          else if(auth_stage==12&&bank_secret==4){type("Mismatch_123");key();++auth_stage;}
          else if(auth_stage==13&&bank_secret==3){if(bank_prompt.find("differ")==std::string::npos)throw std::runtime_error("warehouse confirmation missing");type(n3e::harness::required("N3E_TEST_STORAGE_REPLACEMENT"));key();++auth_stage;}
          else if(auth_stage==14&&bank_secret==4){type(n3e::harness::required("N3E_TEST_STORAGE_REPLACEMENT"));key();++auth_stage;}
          else if(auth_stage==15&&entry==4&&world.storage_auth_responses==2){if(world.storage_authorized!=2||world.storage_auth_status!="changed")throw std::runtime_error("warehouse change failed");key();++auth_stage;}
          else if(auth_stage==16&&entry==5){type("/bankauthretry");auth_wait=world.storage_auth_responses;key();++auth_stage;}
          else if(auth_stage==17&&world.storage_auth_responses>auth_wait){if(world.storage_authorized!=2||world.storage_auth_status!="changed"||bank_secret||!bank_old.empty()||!bank_new.empty()||!text_entry.empty())throw std::runtime_error("warehouse retry or prompt cleanup");if(!capture_path.empty())capture(capture_path+".password.ppm",width,height);++auth_stage;}
          else if(auth_stage==18&&entry==4){key();++auth_stage;}
          else if(auth_stage==19&&entry==5){type("/bankpassword");key();++auth_stage;}
          else if(auth_stage==20&&bank_secret==2){type(n3e::harness::required("N3E_TEST_STORAGE_REPLACEMENT"));key();++auth_stage;}
          else if(auth_stage==21&&bank_secret==3){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=SDLK_ESCAPE;SDL_PushEvent(&e);++auth_stage;}
          else if(auth_stage==22&&entry==4){if(bank_secret||!bank_old.empty()||!bank_new.empty()||!bank_auth_retry.request().empty()||!text_entry.empty())throw std::runtime_error("warehouse cancel cleanup");++auth_stage;std::cout<<"PASS warehouse SDL locked access, masked input, inline discard, confirmation mismatch, change, retry and cancel cleanup\n";}
        }
        if(storage_test&&world.bag.capacity()){
          static const char *steps[]={"/bank","/deposit 1 192 1","/bankmove 192 1","/bankcoins 5","/takecoins 2","/withdraw 1 1 1","/bankretry"};
          auto key=[&](SDL_Keycode k){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          if(storage_stage==0&&entry==4){storage_serial=world.bag.slots(0).instance();key(SDLK_RETURN);++storage_stage;}
          else if(storage_stage<=13&&storage_stage%2==1&&entry==5){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=steps[storage_stage/2];SDL_PushEvent(&e);storage_wait=world.storage_responses;key(SDLK_RETURN);++storage_stage;}
          else if(storage_stage>=2&&storage_stage<=14&&storage_stage%2==0&&entry==4&&world.storage_responses>storage_wait){
            if(world.storage_status!="committed")throw std::runtime_error("storage SDL operation: "+world.storage_status);
            if(storage_stage==14){if(world.bag.slots(0).instance()!=storage_serial||world.storage.slots(0).instance()||world.storage.coins()!=3)throw std::runtime_error("storage SDL conservation");if(!capture_path.empty())capture(capture_path+".storage.ppm",width,height);++storage_stage;std::cout<<"PASS storage SDL deposit, move, coins, withdrawal and retry\n";}
            else{key(SDLK_RETURN);++storage_stage;}
          }
        }
        if(wear_test&&world.bag.capacity()&&world.world.has_stats()) {
          auto key=[&](SDL_Keycode k){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          auto type=[&](const char*v){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);};
          if(wear_stage==0&&entry==4){
            if(world.bag.equipment_size()<3||world.bag.equipment(0).durability()!=3)throw std::runtime_error("wear fixture");
            wear_serial=world.bag.equipment(0).instance();wear_attack=world.world.stats().attack();key(SDLK_RETURN);++wear_stage;
          }else if(wear_stage==1&&entry==5){type("/equipment");key(SDLK_RETURN);++wear_stage;}
          else if(wear_stage==2&&entry==4&&equipment_open){key(SDLK_Z);key(SDLK_R);++wear_stage;}
          else if(wear_stage==3&&world.bag.equipment(0).durability()==0&&world.world.stats().equipment_revision()==world.bag.revision()){
            if(world.bag.equipment(0).instance()!=wear_serial||world.world.stats().attack()>=wear_attack)throw std::runtime_error("wear stat refresh");
            key(SDLK_R);++wear_stage;
          }else if(wear_stage==4&&!melee.target){
            if(!capture_path.empty())capture(capture_path+".worn.ppm",width,height);
            ++wear_stage;std::cout<<"PASS wear SDL combat, committed durability updates, weapon break and derived stat display\n";
          }
        }
        if(equipment_test && world.bag.capacity()) {
          auto key=[&](SDL_Keycode k){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          auto type=[&](const char *v){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);};
          if(equipment_stage==0&&entry==4){equipment_serial=world.bag.slots(0).instance();equipment_revision=world.bag.revision();key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==1&&entry==5){type("/equip 1 1");key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==2&&world.bag.revision()==equipment_revision+1&&(!world.world.has_stats()||world.world.stats().equipment_revision()==world.bag.revision())){
            if(world.bag.equipment(0).instance()!=equipment_serial||world.bag.slots(0).instance())throw std::runtime_error("equipment SDL equip");
            equipment_responses=world.bag_responses;key(SDLK_RETURN);++equipment_stage;
          }else if(equipment_stage==3&&entry==5){type("/retry");key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==4&&world.bag_responses>equipment_responses){if(world.bag.revision()!=equipment_revision+1)throw std::runtime_error("equipment SDL retry");key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==5&&entry==5){type("/repairgear 1");key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==6&&world.bag.revision()==equipment_revision+2&&(!world.world.has_stats()||world.world.stats().equipment_revision()==world.bag.revision())){
            if(world.bag.coins()!=56||world.bag.equipment(0).durability()!=80)throw std::runtime_error("equipped repair SDL");
            key(SDLK_RETURN);++equipment_stage;
          }else if(equipment_stage==7&&entry==5){type("/gearswap 1 2");key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==8&&world.bag.revision()==equipment_revision+3&&(!world.world.has_stats()||world.world.stats().equipment_revision()==world.bag.revision())){
            if(world.bag.equipment(1).instance()!=equipment_serial||!equipment_open)throw std::runtime_error("equipment SDL move");
            if(!capture_path.empty())capture(capture_path+".equipped.ppm",width,height);
            key(SDLK_RETURN);++equipment_stage;
          }else if(equipment_stage==9&&entry==5){type("/unequip 2 1");key(SDLK_RETURN);++equipment_stage;}
          else if(equipment_stage==10&&world.bag.revision()==equipment_revision+4&&(!world.world.has_stats()||world.world.stats().equipment_revision()==world.bag.revision())){
            if(world.bag.slots(0).instance()!=equipment_serial||world.bag.equipment(1).instance())throw std::runtime_error("equipment SDL unequip");
            ++equipment_stage;std::cout<<"PASS equipment SDL equip, exact retry, equipped repair, compatible slot move, unequip and item identity\n";
          }
        }
        if(repair_test && world.bag.capacity()) {
          auto key=[&](SDL_Keycode k){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          auto type=[&](const char *v){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);};
          if(repair_stage==0&&entry==4){
            if(world.bag.coins()!=100||world.bag.slots(0).durability()!=10)throw std::runtime_error("repair graphical fixture");
            repair_revision=world.bag.revision();key(SDLK_I);++repair_stage;
          } else if(repair_stage==1&&bag_open){
            if(!capture_path.empty())capture(capture_path+".damaged.ppm",width,height);
            key(SDLK_RETURN);++repair_stage;
          } else if(repair_stage==2&&entry==5){type("/repair 1");key(SDLK_RETURN);++repair_stage;}
          else if(repair_stage==3&&world.bag.revision()==repair_revision+1){
            if(world.bag.coins()!=56||world.bag.slots(0).durability()!=80)throw std::runtime_error("repair graphical debit");
            repair_responses=world.bag_responses;key(SDLK_RETURN);++repair_stage;
          } else if(repair_stage==4&&entry==5){type("/retry");key(SDLK_RETURN);++repair_stage;}
          else if(repair_stage==5&&world.bag_responses>repair_responses){
            if(world.bag.revision()!=repair_revision+1||world.bag.coins()!=56)throw std::runtime_error("repair graphical retry");
            ++repair_stage;std::cout<<"PASS repair SDL damaged item, 44 coin debit, restored durability and exact retry\n";
          }
        }
        if(commerce_test && world.bag.capacity()) {
          auto key=[&](SDL_Keycode k){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          auto type=[&](const char *v){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=v;SDL_PushEvent(&e);};
          if(commerce_stage==0&&entry==4){commerce_revision=world.bag.revision();commerce_coins=world.bag.coins();key(SDLK_RETURN);++commerce_stage;}
          else if(commerce_stage==1&&entry==5){type("/shop");key(SDLK_RETURN);++commerce_stage;}
          else if(commerce_stage==2&&entry==4&&shop_open&&bag_open){key(SDLK_RETURN);++commerce_stage;}
          else if(commerce_stage==3&&entry==5){type("/buy 2 3 2");key(SDLK_RETURN);++commerce_stage;}
          else if(commerce_stage==4&&world.bag.revision()==commerce_revision+1){
            if(world.bag.coins()!=commerce_coins-26||world.bag.slots(2).quantity()!=2)throw std::runtime_error("commerce graphical purchase");
            key(SDLK_RETURN);++commerce_stage;
          } else if(commerce_stage==5&&entry==5){type("/sell 3 1");key(SDLK_RETURN);++commerce_stage;}
          else if(commerce_stage==6&&world.bag.revision()==commerce_revision+2){
            if(world.bag.coins()!=commerce_coins-24||world.bag.slots(2).quantity()!=1)throw std::runtime_error("commerce graphical sale");
            commerce_responses=world.bag_responses;key(SDLK_RETURN);++commerce_stage;
          } else if(commerce_stage==7&&entry==5){type("/retry");key(SDLK_RETURN);++commerce_stage;}
          else if(commerce_stage==8&&world.bag_responses>commerce_responses){
            if(world.bag.revision()!=commerce_revision+2||world.bag.coins()!=commerce_coins-24)throw std::runtime_error("commerce graphical retry");
            ++commerce_stage;std::cout<<"PASS commerce SDL shop, purchase, sale and original retry balance\n";
          }
        }
        if(bag_test && world.bag.capacity()) {
          auto key=[&](SDL_Keycode k){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(w);e.key.key=k;SDL_PushEvent(&e);};
          auto type=[&](const char *value){SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(w);e.text.text=value;SDL_PushEvent(&e);};
          if(bag_stage==0 && entry==4) {bag_test_serial=world.bag.slots(0).instance();key(SDLK_I);++bag_stage;}
          else if(bag_stage==1 && bag_open) {key(SDLK_RETURN);++bag_stage;}
          else if(bag_stage==2 && entry==5) {type("/swap 1 2");key(SDLK_RETURN);++bag_stage;}
          else if(bag_stage==3 && world.bag_status=="committed" && world.bag.slots(1).instance()==bag_test_serial) {key(SDLK_RETURN);++bag_stage;}
          else if(bag_stage==4 && entry==5) {type("/retry");key(SDLK_RETURN);++bag_stage;}
          else if(bag_stage==5 && entry==4) {key(SDLK_RIGHTBRACKET);++bag_stage;}
          else if(bag_stage==6 && bag_page==1) {key(SDLK_LEFTBRACKET);++bag_stage;}
          else if(bag_stage==7 && bag_page==0) {
            if(!bag_open || world.bag.revision()!=1 || world.bag.slots(1).instance()!=bag_test_serial) throw std::runtime_error("inventory graphical result");
            ++bag_stage; std::cout<<"PASS inventory SDL view, numbered whole-record swap, retry and pagination\n";
          }
        }
        // PQ-405 (D-208), N3E_TEST_REFUSALS: once the bag and friends list have
        // answered and the server has acknowledged two movements, a stale Move
        // (seq 1) draws a movement refusal, which must leave every feature line
        // as it was. A malformed BagRequest and a zero-sequence PartyRequest then
        // draw those features' own refusals, which reach the bag line and the
        // party line only. The walk's own refusals, if any, change no line.
        // PQ-406 (D-209): an empty Chat and a PrivateMessage to an absent name
        // then draw a chat and a private message refusal, which become the
        // world's notice and are drawn on the HUD's message line, while every
        // feature line and the chat line stay as they were. PQ-407 (D-210): the
        // line keeps the package's rows (the demo HUD: two), each message in its
        // kind's colour; a client notice then takes the newest row in the notice
        // colour and the chat refusal, the oldest, leaves the rows. PQ-408
        // (D-211): the demo HUD's scroll bar (12 messages, 6 lines, steps 1 and
        // 2) through the client's own pointer path: the up button steps back
        // on release, a new message leaves a view that is off the bottom, a
        // press below the thumb pages to the bottom, four more messages drop
        // the lines past 6 while following, a thumb drag to the top shows the
        // oldest kept lines, a message then drops none, and the down button
        // held past its delay repeats to the bottom.
        if(refusal_test && entry==4 && world.bag_responses && world.friend_responses) {
          uint64_t acknowledged=0;
          for(const auto&a:world.world.entities())if(a.id()==world.world.self())acknowledged=a.ack();
          auto lines=[&]{return std::array<std::string,5>{world.bag_status,world.storage_status,world.storage_auth_status,world.friend_status,world.party_status};};
          auto names=[&]{return "bag="+world.bag_status+" storage="+world.storage_status+" auth="+world.storage_auth_status+" friends="+world.friend_status+" party="+world.party_status;};
          auto rows=[&]{std::string out;for(const auto&l:hud->messages_drawn){char c[16];std::snprintf(c,sizeof c,"%08x",l.color);out+=" ['"+l.text+"' "+c+"]";}return out;};
          auto texts=[&]{std::vector<std::string> out;for(const auto&l:hud->messages_drawn)out.push_back(l.text);return out;};
          auto mouse=[&](SDL_EventType type,std::array<float,2> at){
            int lw,lh;SDL_GetWindowSize(w,&lw,&lh);SDL_Event e{};e.type=type;
            if(type==SDL_EVENT_MOUSE_MOTION){e.motion.which=replay_mouse;e.motion.windowID=SDL_GetWindowID(w);e.motion.state=SDL_BUTTON_LMASK;e.motion.x=at[0]*lw/width;e.motion.y=at[1]*lh/height;}
            else{e.button.which=replay_mouse;e.button.windowID=SDL_GetWindowID(w);e.button.button=SDL_BUTTON_LEFT;e.button.down=type==SDL_EVENT_MOUSE_BUTTON_DOWN;e.button.x=at[0]*lw/width;e.button.y=at[1]*lh/height;}
            SDL_PushEvent(&e);};
          auto centre=[&](const char*binding){
            for(const auto&q:hud->data.records)if(q.kind==2&&q.binding==binding){auto r=hud->rectangle(q,width,height);return std::array<float,2>{(r[0]+r[2])*.5f,(r[1]+r[3])*.5f};}
            throw std::runtime_error(std::string("the HUD has no ")+binding);};
          auto click=[&](std::array<float,2> at){mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,at);mouse(SDL_EVENT_MOUSE_BUTTON_UP,at);};
          auto scroll_line=[&](const char*name){const auto&l=hud->messages;
            std::cout<<"REFUSAL scroll "<<name<<" pos="<<l.pos<<" max="<<l.max<<" lines="<<l.wrapped.size()<<" thumb="<<l.thumb<<" rows"<<rows()<<"\n";};
          auto post=[&](int n){for(int i=0;i<n;++i){const auto what="Scroll test "+std::to_string(refusal_posted.size()+1);unimplemented(what.c_str());refusal_posted.push_back(hud->messages.newest());}};
          // The thumb at position / maximum of the free track (00410700).
          auto placed=[&]{const auto&l=hud->messages;return l.max&&l.thumb==std::trunc(float(l.pos)/float(l.max)*(l.track-l.thumb_size));};
          using Texts=std::vector<std::string>;
          if(refusal_stage==0&&acknowledged>=2){
            refusal_lines=lines();refusal_count=world.refusals;
            n3e::Envelope e;auto*m=e.mutable_move();m->set_session(world.world.session());m->set_seq(1);m->set_entity(world.world.self());network->send(e);
            ++refusal_stage;
          } else if(refusal_stage==1&&world.refusals>refusal_count&&world.refused_request==n3e::Envelope::kMoveFieldNumber){
            if(lines()!=refusal_lines)throw std::runtime_error("a movement refusal reached a feature line: "+names());
            std::cout<<"REFUSAL movement '"<<world.status<<"' "<<names()<<"\n";
            n3e::Envelope e;e.mutable_bag_request()->set_source(1);network->send(e);
            ++refusal_stage;
          } else if(refusal_stage==2&&world.bag_status!=refusal_lines[0]){
            auto want=refusal_lines;want[0]="inventory unavailable or invalid request";
            if(world.refused_request!=n3e::Envelope::kBagRequestFieldNumber||lines()!=want)throw std::runtime_error("the bag refusal: "+names());
            refusal_lines=want;
            n3e::Envelope e;e.mutable_party_request();network->send(e);
            ++refusal_stage;
          } else if(refusal_stage==3&&world.party_status!=refusal_lines[4]){
            auto want=refusal_lines;want[4]="party request bounds/sequence";
            if(world.refused_request!=n3e::Envelope::kPartyRequestFieldNumber||lines()!=want)throw std::runtime_error("the party refusal: "+names());
            refusal_lines=want;refusal_notices=world.notices;refusal_chat=world.chat;
            if(!world.notice.empty())throw std::runtime_error("a movement, bag or party refusal reached the world notice: "+world.notice);
            n3e::Envelope e;e.mutable_chat();network->send(e);
            ++refusal_stage;
          } else if((refusal_stage==4||refusal_stage==6)&&world.notices>refusal_notices){
            const bool chat=refusal_stage==4;
            const auto request=chat?n3e::Envelope::kChatFieldNumber:n3e::Envelope::kPrivateMessageFieldNumber;
            const std::string want=chat?"chat length/rate":"private message recipient unavailable";
            if(world.refused_request!=uint32_t(request)||world.notice!=want||world.notices!=refusal_notices+1)
              throw std::runtime_error("the "+std::string(chat?"chat":"private message")+" refusal: request "+std::to_string(world.refused_request)+" notice '"+world.notice+"'");
            if(lines()!=refusal_lines||world.chat!=refusal_chat)throw std::runtime_error("a chat refusal reached a feature or chat line: "+names()+" chat="+world.chat);
            refusal_notices=world.notices;
            ++refusal_stage;
          } else if((refusal_stage==5||refusal_stage==7||refusal_stage==8)&&hud&&!hud->messages_drawn.empty()&&
                    hud->notice_drawn==(refusal_stage==8?refusal_client:world.notice)){
            if(!hud->data.messages||hud->data.messages->rows!=2||hud->messages_drawn.size()!=2)
              throw std::runtime_error("the refusal replay needs a package message block of two rows");
            const auto colours=*hud->data.messages;
            std::cout<<"REFUSAL notice '"<<hud->notice_drawn<<"' "<<names()<<" chat='"<<world.chat<<"' rows"<<rows()<<"\n";
            const n3e::MessageLine chat{"chat length/rate",colours.refusal},whisper{"private message recipient unavailable",colours.refusal},
                                   client{refusal_client,colours.notice},none{};
            // Before the chat refusal the log is empty unless the client posted a
            // notice of its own earlier in the run; then that one is the older row.
            const auto&drawn=hud->messages_drawn;
            const bool ok=refusal_stage==5?(hud->messages.count==1?drawn==std::vector{chat,none}:drawn[1]==chat&&!drawn[0].text.empty())
                                          :drawn==(refusal_stage==7?std::vector{chat,whisper}:std::vector{whisper,client});
            if(!ok)throw std::runtime_error("the message line drew"+rows());
            if(refusal_stage==5){
              n3e::Envelope e;auto*m=e.mutable_private_message();m->set_recipient("Nobody");m->set_text("are you there");network->send(e);
            } else if(refusal_stage==7){
              // A client notice through the client's own path (an action n3e
              // does not implement).
              unimplemented("Camera mode selection");refusal_client=hud->messages.newest();
              if(refusal_client!="Unavailable: Camera mode selection is not implemented.")throw std::runtime_error("client notice '"+refusal_client+"'");
            } else {
              const auto&l=hud->messages;
              if(!l.history||l.pos!=l.max||l.max<1||!placed())throw std::runtime_error("the message line does not follow the bottom");
              refusal_pos=l.pos;scroll_line("follow");click(centre("message_up"));
            }
            ++refusal_stage;
          } else if(refusal_stage==9&&hud->messages.pos==refusal_pos-1&&hud->messages.held==n3e::MessagePart::none){
            // The up button's release stepped back one line.
            if(texts()!=Texts{"chat length/rate","private message recipient unavailable"}||!placed())throw std::runtime_error("the up button drew"+rows());
            scroll_line("up");post(1);++refusal_stage;
          } else if(refusal_stage==10&&hud->notice_drawn==refusal_posted.back()){
            const auto&l=hud->messages;
            if(l.pos!=refusal_pos-1||l.max!=refusal_pos+1||texts()!=Texts{"chat length/rate","private message recipient unavailable"})
              throw std::runtime_error("a message moved a view that was off the bottom:"+rows());
            scroll_line("off-bottom");
            // A press on the track below the thumb pages forward (004103f0).
            auto track=centre("message_track");auto thumb=hud->message_thumb_rect(width,height);
            auto r=hud->rectangle(*hud->message_track,width,height);
            if(thumb[3]>=r[3]-2)throw std::runtime_error("the thumb fills the track's end");
            click({track[0],r[3]-2});++refusal_stage;
          } else if(refusal_stage==11&&hud->messages.pos==hud->messages.max){
            if(hud->messages.pos!=refusal_pos+1||texts()!=Texts{refusal_client,refusal_posted[0]}||!placed())throw std::runtime_error("the page drew"+rows());
            scroll_line("page");post(4);++refusal_stage;
          } else if(refusal_stage==12&&hud->notice_drawn==refusal_posted.back()){
            const auto&l=hud->messages;
            // Following, the lines past 6 went, oldest first: whatever came
            // before the client notice.
            if(l.wrapped.size()!=6||l.wrapped.front().text!=refusal_client||l.pos!=4||l.max!=4||
               texts()!=Texts{refusal_posted[3],refusal_posted[4]}||!placed())
              throw std::runtime_error("the line limit kept "+std::to_string(l.wrapped.size())+" lines:"+rows());
            scroll_line("limit");
            // Drag the thumb from its centre to the track's top (004107f0).
            auto thumb=hud->message_thumb_rect(width,height);
            std::array<float,2> from{(thumb[0]+thumb[2])*.5f,(thumb[1]+thumb[3])*.5f};
            std::array<float,2> to{from[0],from[1]-l.thumb*hud->scale(width,height)+.25f};
            mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,from);mouse(SDL_EVENT_MOUSE_MOTION,to);mouse(SDL_EVENT_MOUSE_BUTTON_UP,to);
            ++refusal_stage;
          } else if(refusal_stage==13&&hud->messages.pos==0&&!hud->messages.dragging){
            if(texts()!=Texts{refusal_client,refusal_posted[0]}||hud->messages.thumb>=1)throw std::runtime_error("the thumb drag drew"+rows());
            scroll_line("drag");post(1);++refusal_stage;
          } else if(refusal_stage==14&&hud->notice_drawn==refusal_posted.back()){
            const auto&l=hud->messages;
            // At the first line no line goes (0052ae7f).
            if(l.wrapped.size()!=7||l.pos!=0||texts()!=Texts{refusal_client,refusal_posted[0]})throw std::runtime_error("at the top a line was dropped:"+rows());
            scroll_line("top");
            mouse(SDL_EVENT_MOUSE_BUTTON_DOWN,centre("message_down"));refusal_held=SDL_GetTicks();++refusal_stage;
          } else if(refusal_stage==15&&(hud->messages.pos>0||SDL_GetTicks()-refusal_held>4000)){
            // Held, the down button repeats only once its delay has passed.
            const auto&l=hud->messages;
            if(SDL_GetTicks()-refusal_held<500||l.held!=n3e::MessagePart::down)throw std::runtime_error("the held button stepped after "+std::to_string(SDL_GetTicks()-refusal_held)+" ms");
            ++refusal_stage;
          } else if(refusal_stage==16&&(hud->messages.pos==hud->messages.max||SDL_GetTicks()-refusal_held>6000)){
            const auto&l=hud->messages;
            if(l.pos!=l.max||texts()!=Texts{refusal_posted[4],refusal_posted[5]}||!placed())throw std::runtime_error("the held button drew"+rows());
            mouse(SDL_EVENT_MOUSE_BUTTON_UP,centre("message_down"));scroll_line("hold");
            std::cout<<"PASS client refusal routing: a movement refusal left the bag, storage, friends and party lines; the bag and party refusals reached only their own line; the chat and private message refusals reached only the HUD message line, which kept the newest two messages, refusals in the package's refusal colour and a client notice in its notice colour\n";
            std::cout<<"PASS client message scroll-back: the up button stepped back on release, a message left a view off the bottom, a page reached the bottom, the lines past the package's limit went while following, a thumb drag showed the oldest kept lines, a message at the top dropped none and a held down button repeated to the bottom after its delay\n";
            ++refusal_stage;
          }
        }
        if (loot_test && entry == 4) {
          if (!loot_test_start) loot_test_start=SDL_GetTicks();
          auto elapsed=SDL_GetTicks()-loot_test_start;
          bool actor=std::string(loot_test)=="actor";
          if (!loot_test_action && elapsed>(actor?500:1800)) {
            for (const auto &candidate:world.world.entities()) if (candidate.npc() && candidate.health()) {target=candidate.id();break;}
            press_action(n3e::input::Action::attack_toggle);loot_test_action=true;
          }
          if (actor && !loot_test_claim && world.loot.drops_size()>0) {
            if (!capture_path.empty()) capture(capture_path+".drop.ppm",width,height);
            press_action(n3e::input::Action::loot_nearest);loot_test_claim=true;
          }
          if (elapsed>6000) {
            auto &inv=world.world.inventory();
            std::cout<<"LOOT role="<<loot_test<<" xp="<<inv.xp()<<" level="<<inv.level()<<" count="<<inv.count()<<" combat="<<world.combat<<" result="<<world.loot_status<<"\n";
            if (inv.xp()==0 || inv.count()!=(actor?1u:0u) || (actor && world.loot_status!="claimed")) throw std::runtime_error("graphical loot loop failed");
            if (!capture_path.empty()) capture(capture_path+".loot.ppm",width,height);
            run=false;
          }
        }
