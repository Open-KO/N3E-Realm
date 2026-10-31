// Test-only replay fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Replay state: command-line modes, N3E_TEST_* switches and the stage counters
// the replays advance. The player build declares only the few modes viewer.cpp
// tests in shared code, as constants.
    bool smoke = false, bad = false, auto_login = false, play_smoke = false;
    bool movement_smoke = false, melee_smoke = false, npc_observe = false;
    std::set<std::string> npc_observed;
    Uint64 melee_start = 0;
    unsigned melee_stage = 0, melee_hits = 0;
    // PQ-010: hits counted when the replay pressed the cancel key mid-melee.
    std::optional<unsigned> melee_cancel_hits;
    uint64_t melee_strike = 0, melee_stopped_seq = 0;
    // PQ-011: the NPC the mouse stages click.
    uint64_t melee_npc = 0;
    bool controls_smoke = false, camera_smoke = false;
    // Pointer events the panel and play replays push carry this mouse ID;
    // under those replays the viewer drops the desktop's (PQ-238).
    constexpr SDL_MouseID replay_mouse = 0x6e3e;
    bool pending_camera_events = false;
    SDL_Event pending_camera_motion{}, pending_camera_wheel{};
    Uint64 controls_start = 0;
    unsigned controls_stage = 0;
    n3e::V controls_before{}, controls_destination{};
    unsigned movement_stage = 0;
    bool movement_cancel = false;  // PQ-010: cancel pressed during E movement
    unsigned movement_pose_captures = 0;
    std::string movement_capture;
    uint64_t movement_session = 0;
    Uint64 movement_start = 0;
    n3e::V test_origin{};
    unsigned play_stage = 0;
    // PQ-129: a package with melee answers the HUD strike with auto-attack on the
    // target (melee.toggle), not with one action result.
    bool play_melee = false;
    unsigned hud_test_stage = 0;
    Uint64 play_start = 0;
    float fixed = -1;
    std::string capture_path;
    const bool edit_test=std::getenv("N3E_EDIT_TEST")!=nullptr;
    const bool edit_observe=std::getenv("N3E_EDIT_OBSERVE")!=nullptr;
    unsigned edit_stage=0;
#if TOOLS
    uint64_t edit_started=0;n3e::V edit_origin{};
    // Replay helpers: drive the terminal through SDL's real event queue so the
    // test depends on the same delivery path as a keyboard.
    auto edit_type=[](SDL_Window *win,const char *typed){
      SDL_Event e{};e.type=SDL_EVENT_TEXT_INPUT;e.text.windowID=SDL_GetWindowID(win);
      e.text.text=typed;SDL_PushEvent(&e);};
    auto edit_enter=[](SDL_Window *win){
      SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.windowID=SDL_GetWindowID(win);
      e.key.key=SDLK_RETURN;e.key.scancode=SDL_SCANCODE_RETURN;SDL_PushEvent(&e);};
#endif
    bool life_smoke = false;
    unsigned life_stage = 0;
    uint64_t life_old = 0, life_action = 0, life_ready = 0;
    int world_smoke = 0;
    // PQ-232: N3E_TEST_WORLD_PATH's frame count delays the world captures and
    // the smoke quit by that much; smoke_quit moves while a streamed capture waits.
    int world_path_frames = 0;
    if (const char *path = std::getenv("N3E_TEST_WORLD_PATH")) {
      std::istringstream steps(path); float x = 0, frames = 0;
      for (int i = 0; i < 3; ++i) steps >> x;
      if (steps >> frames && frames >= 1 && frames <= 100000) world_path_frames = int(frames);
    }
    int smoke_quit = 50 + world_path_frames;
    bool resized = false, minimized = false, restored = false, focus_checked = false;
    bool layout_test=std::getenv("N3E_TEST_UIF_LAYOUT")!=nullptr;unsigned layout_stage=0;uint64_t layout_due=0;
    bool drag_test=std::getenv("N3E_TEST_UIF_DRAG")!=nullptr;
    bool hotbar_test=std::getenv("N3E_TEST_HOTBAR")!=nullptr;unsigned hotbar_flash_mask=0;
    bool marker_test=std::getenv("N3E_TEST_TARGET_MARKER")!=nullptr;
    // PQ-296: targets whose drawn marker TARGET_MARKER has reported; under
    // N3E_TEST_NPC_LOOKS the looks NPCs the pick reached, selected in turn.
    std::set<uint64_t> marker_reported;std::deque<uint64_t> marker_queue;
    // PQ-177: N3E_TEST_NPC_INFO counts NPC name labels drawn and the info
    // lines drawn with them; the world replay's end prints NPC_INFO.
    const bool npc_info_test=std::getenv("N3E_TEST_NPC_INFO")!=nullptr;uint64_t npc_info_names=0,npc_info_lines=0,npc_info_traced=0;std::string npc_info_text,npc_info_traced_text;
    // PQ-178: N3E_TEST_CHAT says that local line once (none when empty), 2 s
    // or more after start and once another player is in view; a world replay's
    // end prints CHAT_LINE with the last line received, its server mark and
    // the colour the HUD last drew it in.
    const char*chat_test=std::getenv("N3E_TEST_CHAT");bool chat_sent=false;
    // PQ-186: `traced` says the server reported this NPC's state to the session.
    auto npc_info_seen=[&](const std::string&line,bool traced){if(!npc_info_test)return;++npc_info_names;if(!line.empty()){++npc_info_lines;if(npc_info_text.empty())npc_info_text=line;if(traced){++npc_info_traced;if(npc_info_traced_text.empty())npc_info_traced_text=line;}}};
    bool nameplate_test=std::getenv("N3E_TEST_NAMEPLATES")!=nullptr;int nameplate_standing_y=0;uint64_t nameplate_party_deadline=0;uint64_t nameplate_npc=0,nameplate_npc_deadline=0;bool nameplate_npc_dying=false,nameplate_npc_picked=false,nameplate_npc_b=false;
    bool skills_test=std::getenv("N3E_TEST_SKILLS")!=nullptr;
    bool potion_test=std::getenv("N3E_TEST_POTIONS")!=nullptr;
    bool moving_test=std::getenv("N3E_TEST_MOVING_ATTACKS")!=nullptr;
    bool weapon_test=std::getenv("N3E_TEST_WEAPON_ANIMATIONS")!=nullptr;
    unsigned weapon_loadout=0;uint64_t weapon_strike=0;
    bool rest_items_test=std::getenv("N3E_TEST_REST_ITEMS")!=nullptr;
    bool chest_test=std::getenv("N3E_TEST_LOOT_CHESTS")!=nullptr;unsigned chest_checks=0;
    bool loot_range_test=std::getenv("N3E_TEST_LOOT_RANGE")!=nullptr,loot_range_checked=false;
    bool expiry_test=std::getenv("N3E_TEST_LOOT_EXPIRY")!=nullptr;
    bool approach_test=std::getenv("N3E_TEST_MELEE_START")!=nullptr;
    // Optional waypoints "x,z;x,z" walked once, running, when the scripted
    // replay reaches stage N3E_TEST_ROUTE_STAGE, so worm stages start near worms.
    std::vector<std::array<float,2>> test_route;size_t route_index=0;unsigned route_stage=0;bool route_running=false;
    if(const char*r=std::getenv("N3E_TEST_ROUTE")){
      std::stringstream in(r);std::string pair;
      while(std::getline(in,pair,';')){auto comma=pair.find(',');if(comma==std::string::npos)throw std::runtime_error("test route");
        test_route.push_back({std::stof(pair.substr(0,comma)),std::stof(pair.substr(comma+1))});}
    }
    if(const char*r=std::getenv("N3E_TEST_ROUTE_STAGE"))route_stage=std::stoul(r);
    double approach_arrival=0,approach_request=0,approach_pose=0,loot_seen=0;
    uint64_t approach_sequence=0;bool expiry_opened=false;
    unsigned expiry_potions=0;double expiry_drink=0;
    bool next_three_test=std::getenv("N3E_TEST_NEXT_THREE")!=nullptr;
    // N3E_TEST_ITEM_TOOLTIP=<role> (PQ-321): open the inventory, find the slot that
    // holds the N3E_TEST_ITEMS item of that role, print its slot and icon, capture
    // <capture>.item-slot.ppm, hover it, print the tooltip rows and capture
    // <capture>.item-tooltip.ppm.
    const char*item_tooltip_test=std::getenv("N3E_TEST_ITEM_TOOLTIP");std::string item_tooltip_key;uint64_t item_tooltip_hover=0;
    // N3E_TEST_PANELS=drag|restore: drag the chat and hotkey handles with SDL
    // events and exit normally (saving), or print the restored layout.
    // N3E_TEST_TOUR="x,z;x,z;...": walk each waypoint with click-to-move, settle,
    // capture <capture>.tour-N.ppm and exit after the last (package previews).
    std::vector<std::array<float,2>> tour;size_t tour_index=0;uint64_t tour_due=0;int tour_phase=0;
    if(const char*r=std::getenv("N3E_TEST_TOUR")){
      std::string all=r;size_t at=0;
      while(at<all.size()){auto end=all.find(';',at);if(end==std::string::npos)end=all.size();
        auto part=all.substr(at,end-at);auto comma=part.find(',');
        if(comma==std::string::npos)throw std::runtime_error("N3E_TEST_TOUR expects x,z;x,z");
        tour.push_back({std::stof(part.substr(0,comma)),std::stof(part.substr(comma+1))});at=end+1;}
    }
    const char*panel_test=std::getenv("N3E_TEST_PANELS");unsigned panel_stage=0;uint64_t panel_due=0;std::array<float,4> panel_before{};
    bool uif_test=skills_test||marker_test||nameplate_test||hotbar_test||potion_test||weapon_test||rest_items_test||next_three_test||drag_test||item_tooltip_test||std::getenv("N3E_TEST_UIF_ACTIONS")!=nullptr;unsigned uif_stage=0;uint64_t uif_due=0,uif_serial=0;n3e::V skill_origin{};
    bool feature_test=std::getenv("N3E_TEST_FEATURE_HUD")!=nullptr;unsigned feature_stage=0;uint64_t feature_due=0,feature_deadline=0;bool feature_sent=false;
    bool friends_test=std::getenv("N3E_TEST_FRIENDS")!=nullptr;unsigned friends_stage=0;uint64_t friends_wait=0;
    bool party_test=std::getenv("N3E_TEST_PARTY")!=nullptr;unsigned party_stage=0;
    bool coin_loot_test=std::getenv("N3E_TEST_COIN_LOOT")!=nullptr;
    bool coin_capture_ready=false;
    bool party_loot_test=std::getenv("N3E_TEST_PARTY_LOOT")!=nullptr;
    bool storage_auth_test=std::getenv("N3E_TEST_STORAGE_AUTH")!=nullptr;unsigned auth_stage=0;uint64_t auth_wait=0;
    bool storage_test=std::getenv("N3E_TEST_STORAGE")!=nullptr;unsigned storage_stage=0;uint64_t storage_serial=0,storage_wait=0;
    bool wear_test=std::getenv("N3E_TEST_WEAR")!=nullptr;unsigned wear_stage=0,wear_attack=0;uint64_t wear_serial=0;
    bool equipment_test=std::getenv("N3E_TEST_EQUIPMENT")!=nullptr;unsigned equipment_stage=0;uint64_t equipment_serial=0,equipment_responses=0,equipment_revision=0;
    bool repair_test=std::getenv("N3E_TEST_REPAIR")!=nullptr; unsigned repair_stage=0;uint64_t repair_revision=0,repair_responses=0;
    bool commerce_test=std::getenv("N3E_TEST_COMMERCE")!=nullptr; unsigned commerce_stage=0; uint64_t commerce_revision=0, commerce_responses=0;uint32_t commerce_coins=0;
    bool bag_test=std::getenv("N3E_TEST_BAG")!=nullptr; unsigned bag_stage=0; uint64_t bag_test_serial=0;
    // PQ-405: N3E_TEST_REFUSALS routes a movement, a bag and a party refusal;
    // PQ-406 adds a chat and a private message refusal (the world notice);
    // PQ-407 a client notice, and the drawn message rows and colours.
    // PQ-408 the message line's scroll bar: steps, a page, the line limit, a
    // thumb drag and a held button.
    bool refusal_test=std::getenv("N3E_TEST_REFUSALS")!=nullptr; unsigned refusal_stage=0; uint64_t refusal_count=0; std::array<std::string,5> refusal_lines; uint64_t refusal_notices=0; std::string refusal_chat, refusal_client;
    int refusal_pos=0; uint64_t refusal_held=0; std::vector<std::string> refusal_posted;
    const char *animation_test = std::getenv("N3E_TEST_ANIMATION");
    std::set<std::string> animation_captured;
    std::map<uint64_t, std::pair<int, uint64_t>> animation_observed;
    const char *loot_test = std::getenv("N3E_TEST_LOOT");
    bool loot_test_action=false, loot_test_claim=false;
    uint64_t loot_test_start=0;
    const char *combat_test = std::getenv("N3E_TEST_COMBAT");
    bool saw_dead = false, saw_respawn = false, saw_reward = false;
    unsigned captured_stages = 0;
    bool world_sampling_captured = false;
    uint64_t initial_self = 0, initial_reward = 0, next_test_action = 0;
    bool automated_login = false, automated_select = false;
    std::set<std::string> captured_effects;
