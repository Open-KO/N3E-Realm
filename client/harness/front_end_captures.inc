// Test-only fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Spec 11 acceptance 6: N3E_TEST_FRONT_END=PREFIX draws each KO screen at rest
// in the window (--fixed-window), writes PREFIX.<shot>.ppm and prints, per
// shot, the characters drawn (pixel boxes, y down), one bound node's rect and
// (RQ-106) where the canvas's (0, 0) is as the screen's root carries it, and
// the scale (1: KO's placement on the window's own pixels):
//   FRONT_SHOT name=N size=WxH path=P rect=x0,y0,x1,y1 drawn=intro|hall|create:x0,y0,x1,y1;... origin=X,Y,S
// then the select's buttons where the select placed them (RQ-106):
//   FRONT_PLACED select_prev=x0,y0,x1,y1 select_next=... back=... exit=...
// then (RQ-113) whether prev and next draw at rest with the row's left end in
// focus and with its right end (the package's select.arrows), each 0 or 1:
//   FRONT_ARROWS left=P,N right=P,N
// then (RQ-109), for a select that binds 1298's bar (front-end-1298.json), its
// other buttons and its info texts where the select placed them, and a select
// of no character (the shot select-0, its info texts empty):
//   FRONT_SELECT_BAR select_start=x0,y0,x1,y1 select_create=... select_delete=...
//     char_name=... char_level=... char_class=...
// then (RQ-108) whether the login layout's login group, realm group and
// login_closed node draw at rest, with a login under way and on the realm
// list, each 0 or 1, and (RQ-123) the same with a login under way and on the
// realm list after a Back that lands there (the line hidden, BackHold):
//   FRONT_LOGIN idle=G,R,C waiting=G,R,C realms=G,R,C back=G,R,C back_realms=G,R,C
// (the shot login-waiting is the login with a login under way, rect= the
// login_closed node's).
// then (RQ-111) the select's exit: whether a click on it asks (a package that
// names exit_confirm: 1298's yes/no box) or leaves at once, and, when it asks,
// which of the box's OK, Yes and No draw in that box and in an OK box, and what
// each answer does (closed or open, and the command: none or exit): ESC,
// ENTER, the keypad's ENTER, a click on No, on Yes and on the hidden OK:
//   FRONT_EXIT asks=0 command=exit
//   FRONT_EXIT asks=1 shown=O,Y,N plain=O,Y,N esc=closed:none enter=closed:exit
//     keypad=... no=... yes=... ok=open:none
// and (RQ-116) what ESC on the select at rest does, appended to that line:
// select_esc=asks|back|exit|none
// and (RQ-121) whether ENTER on one character starts it, and what ESC and a
// click on Exit do while its start clip plays:
// started=0|1 start_esc=asks|back|exit|none start_exit=asks|back|exit|none
// and (RQ-112) what a click on Back at rest does and where the package says
// it lands: back=asks|back|exit|none:login|realms
// (the shot message-exit is the select with that box, rect= Yes's);
// then (RQ-114), for a select that binds btn_create, a click on it from an
// occupied slot (the block's own comment below):
//   FRONT_CREATE click=select path=P frames=F ui=0 slot=1 focus=2 arrived=create draws=N back=select slot=2
//   FRONT_CREATE click=create back=select slot=S
// (the second without a fly), or (RQ-125) for a create over the hall:
//   FRONT_CREATE click=create path=P frames=F slot=1 focus=2 new=0 arrived=2 draws=N new=1 back=select slot=2
//     cancel=select slot=2 ui=1
// (on one line; RQ-130: for a create that waits for its race, new=0 on the
// arrival, then ` race=S new=1 figure=2` after a click on the race button,
// S its draw state, and after cancel= ` flown=F new=1`: the slot the new
// character stands at when the race is clicked one frame into a flight, and
// whether it stands once the camera is on the slot); then (RQ-126), for a
// package with a create slide, create opened by ENTER on an empty slot and
// each frame of its slide 1/32 s apart:
//   FRONT_CREATE_SLIDE screen=create frames=x,y,..;x,y,.. on=0
// then (RQ-130), for a create that waits for its race, create opened by ENTER
// on an empty slot at rest, then Create (ENTER) and the race and class
// buttons pressed as a player does (RQ-172: the race button of the package's
// fixed race, the class button of its fixed specialty, and the button of
// another specialty that race has): whether the new character stands and the
// race and class buttons' draw states (0 normal, 1 down, 2 on, 3 disabled),
// and the message each Create shows (none: the create was sent):
//   FRONT_CREATE_CHOICE open=N,R,C column=U labels=L stats=V looks=F,H empty=M norace=M class=C,N column=U
//     labels=L classfirst=M race=R,C,N column=U labels=L model=K row=S stats=V drawn=F,H noclassarrows=V
//     noclass=M both=R,C,N labels=L stats=V arrows=F,H drawn=F,H again=R,C,N labels=L other=R,O,C,N labels=L
//     stats=V points=M spent=V moved=V create=M sent=0|1 as=K,S,V,F,H reopen=U labels=L stats=V looks=F,H
// (on one line; RQ-172: U the ids of create's class buttons and their images
// that draw then, in draw order, comma-separated, `-` for none; L the same
// for its class labels; model= the race code of the create model drawn and
// row= the specialty whose stat row the screen holds; again= after a second
// click on the chosen race; other= after a click on the other class (its
// state O), whose create is then sent as race K and specialty S; reopen=
// after a race and a class click, a Cancel and ENTER opening create again;
// RQ-173: V the stat value texts and then the points text, `/`-separated, `-`
// for an empty one; noclassarrows= after a right and then a left click on the
// first stat's arrows with no class; points= the Create after other=; spent=
// after a left click on the first stat and eleven right clicks on the last;
// moved= after a left click on the last and a right click on the first; as=
// also the stats sent; RQ-174: looks= the face and hair the create holds,
// drawn= the face and hair parts the new character draws (-1 none); the race=
// segment after a click on the face's right arrow before the race (a face
// click needs neither race nor class); arrows= after five face right clicks,
// four hair right clicks and a hair left click; as= also the face and hair
// sent; reopen= the face and hair kept), then
// (RQ-153) the frame of both= (the race and then the class clicked) as the shot
// create-class, its FRONT_SHOT line (rect= the class button's) after that
// line (RQ-172: the fixed specialty's class button's), and the box of each
// refusal it words:
//   FRONT_CREATE_MESSAGE M|title|text
// then (RQ-180), for a create with description text (version 28, RQ-175),
// its rest and colour, and the text (a JSON string) after each step: create
// opened by ENTER on the empty slot at rest (open), the pointer on each tip's
// node in the package's order (hover), off every node (away), on the first
// tip and off, a click on the fixed race's button (race), on the first tip and
// off, a click on the fixed specialty's class button (class), on the race
// button and off, then a Cancel and ENTER (reopen):
//   FRONT_CREATE_DESC rest=none|keep|chosen colour=AARRGGBB tips=N
//   FRONT_CREATE_DESC_TEXT open|hover|away|race|class|reopen <node id>|- "text"
// then the shots create-desc-open (the open) and create-desc-hover (the
// pointer on the first tip), drawn at the same time, rect= the class_desc
// node's;
// then the screens' music (FRONT_MUSIC, below), and exits. RQ-101: the logo
// screen's shots are logo-<group> at a time in each group's hold and
// logo-fade half way into the first group's fade-in, with rect= the logo
// layout's canvas (its pixel rect) and drawn= empty; then
//   FRONT_LOGO groups=G length=L skip=0|1 cursor=0|1 alpha=A0,A1,... before=logo|login end=logo|login
// (L the screen's seconds; A the alpha of each shot in order; before the
// screen on a frame 0.1 s before its end, end the screen after a frame that
// runs it 0.1 s past it).
// tests/front_end_live.py checks the frames and the music. No server.
if (const char *prefix = std::getenv("N3E_TEST_FRONT_END")) {
  if (!front) throw std::runtime_error("N3E_TEST_FRONT_END needs front-end.bin and a Discord realm");
  int width, height;
  SDL_GetWindowSizeInPixels(w, &width, &height);
  n3e::Characters list;
  using Screen = n3e::front::Screen;
  // The frame just drawn written to PREFIX.<name>.ppm, and its FRONT_SHOT
  // line (returned, so a capture inside another line's report prints after it).
  auto capture_shot = [&](const std::string &name, n3e::FrontAction bound, bool logo = false, int node = -1) {
    const std::string path = std::string(prefix) + "." + name + ".ppm";
    capture(path, width, height);
    std::ostringstream line;
    line << "FRONT_SHOT name=" << name << " size=" << width << "x" << height << " path=" << path << " rect=";
    const auto origin = front->layout_origin(width, height);
    if (logo) {
      const float s = origin[2];
      line << int(origin[0]) << "," << int(origin[1]) << "," << int(origin[0] + 1024 * s) << ","
           << int(origin[1] + 768 * s);
    } else if (auto r = node >= 0 ? front->node_rect(node, width, height) : front->action_rect(bound, width, height))
      line << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
    line << " drawn=";
    const char *sep = "";
    for (const auto &d : front->drawn()) {
      const auto &b = d.box;
      const auto &v = d.viewport;
      static const char *kinds[] = {"intro", "hall", "create"};
      line << sep << kinds[d.which] << ":" << int(v[0] + (b[0] + 1) / 2 * v[2]) << ","
           << int(height - v[1] - (b[3] + 1) / 2 * v[3]) << "," << int(v[0] + (b[2] + 1) / 2 * v[2]) << ","
           << int(height - v[1] - (b[1] + 1) / 2 * v[3]);
      sep = ";";
    }
    line << " origin=" << origin[0] << "," << origin[1] << "," << origin[2];
    SDL_GL_SwapWindow(w);
    return line.str();
  };
  auto shot = [&](const std::string &name, Screen screen, int characters, const std::string &realm, float progress,
                  n3e::FrontAction bound, const std::string &message, double logo = -1,
                  n3e::FrontMessage kind = n3e::FrontMessage::disconnected, bool waiting = false) {
    SDL_PumpEvents();
    list.Clear();
    for (int i = 0; i < characters; ++i) {
      auto *c = list.add_characters();
      c->set_id(i + 1);
      c->set_name("Shot" + std::to_string(i + 1));
      c->set_level(10 * (i + 1));
    }
    front->jump(screen);
    front->login_waiting(waiting);
    if (logo >= 0) front->logo_at(logo);
    if (!message.empty()) front->show_message(kind, message);
    const n3e::front::Context context{realm, "ENTER - Log in with Discord", release.version, &list, progress};
    front->draw(width, height, 1.0, context);
    front->draw(width, height, 1.0, context);
    std::cout << capture_shot(name, bound, logo >= 0) << std::endl;
  };
  using A = n3e::FrontAction;
  shot("login", Screen::login, 0, "Local Realm", 0, A::login, "");
  // RQ-108: a login under way: KO's copyright line instead of the login bar.
  shot("login-waiting", Screen::login, 0, "Local Realm", 0, A::login_closed, "", -1,
       n3e::FrontMessage::disconnected, true);
  shot("realms", Screen::realms, 0, "Local Realm", 0, A::realm_list, "");
  shot("realms-unnamed", Screen::realms, 0, "", 0, A::realm_list, "");
  for (int n = 1; n <= 3; ++n) shot("select-" + std::to_string(n), Screen::select, n, "Local Realm", 0, A::char_info, "");
  front->jump(Screen::select);
  std::cout << "FRONT_PLACED";
  for (const auto &[label, action] : {std::pair{"select_prev", A::select_prev}, std::pair{"select_next", A::select_next},
                                      std::pair{"back", A::back}, std::pair{"exit", A::exit}}) {
    const auto r = front->action_rect(action, width, height);
    std::cout << " " << label << "=";
    if (r) std::cout << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
  }
  std::cout << std::endl;
  // RQ-113 (KO-FINDINGS 9.6, 9.13): whether prev and next draw with the
  // left end of the row in focus and with the right end, each 0 or 1.
  std::cout << "FRONT_ARROWS";
  for (const auto &[label, at] : {std::pair{"left", 0}, std::pair{"right", 2}}) {
    front->select_at(at);
    std::cout << " " << label << "=" << front->action_shown(A::select_prev) << ","
              << front->action_shown(A::select_next);
  }
  std::cout << std::endl;
  front->jump(Screen::select);
  if (front->action_rect(A::char_name, width, height)) {
    std::cout << "FRONT_SELECT_BAR";
    for (const auto &[label, action] :
         {std::pair{"select_start", A::select_start}, std::pair{"select_create", A::select_create},
          std::pair{"select_delete", A::select_delete}, std::pair{"char_name", A::char_name},
          std::pair{"char_level", A::char_level}, std::pair{"char_class", A::char_class}}) {
      const auto r = front->action_rect(action, width, height);
      std::cout << " " << label << "=";
      if (r) std::cout << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
    }
    std::cout << std::endl;
    shot("select-0", Screen::select, 0, "Local Realm", 0, A::char_name, "");
  }
  // RQ-005 (version 31): three characters of the given races and
  // specialties (a Tuarek priest, a Tuarek rogue and race 0), each drawn as
  // KO's AddChr picks its model by race and class: per slot, the select
  // character drawn (its index in the package's, -1 the select model) and the
  // plugs it carries, then each character's class text (1097 0052e3e0, 1298
  // 00613ea0; `_` for a space). RQ-198 (version 33): the priest has face 1
  // and hair 2, the rogue face 3 and hair 1, race 0 face 0 and hair 5; per
  // slot, the face and hair parts drawn by those numbers (AddChr's
  // "%s%s%.2d%s"; -1 none, past the model's parts). RQ-197 (version 35):
  // the priest wears appearance keys 5 and 1, the rogue none, race 0 keys 5
  // and 9 (past the package's: nothing); per slot, the KO part slots drawn
  // from its keys and from the looks parts apart (a bit per slot) and the
  // keys' hand plugs drawn; RQ-200: per slot, the hand plugs drawn with
  // their weapon effect, and the tail links the frame drew; RQ-201: the
  // priest's key 1 item at 20 % of its durability, and per slot the hand
  // plugs drawn with the hard and with the soft dust overlay; RQ-204: its
  // key 5 item at 50 %, and per slot the KO part slots drawn with the hard
  // and with the soft dust (a bit per slot):
  //   FRONT_HALL models=M0,M1,M2 plugs=P0,P1,P2 classes=C0|C1|C2 looks=F0/H0,F1/H1,F2/H2
  //     worn=E0/O0/K0,E1/O1/K1,E2/O2/K2 fx=X0,X1,X2 tails=T dust=D0/S0,D1/S1,D2/S2
  //     part_dust=A0/B0,A1/B1,A2/B2
  // and per effect drawn (engine space): its slot, key and copies, the
  // centre of its first copy, its plug's joint origin and its plug mesh's box:
  //   FRONT_HALL_FX slot=S key=K copies=C centre=x,y,z joint=x,y,z box=x0,y0,z0,x1,y1,z1
  // after that frame's shot, select-worn.
  {
    list.Clear();
    struct Made { uint32_t race, specialty, face, hair; std::vector<uint32_t> appearance, durability; };
    const std::array<Made, 3> made{
        {{2, 104, 1, 2, {5, 1}, {50, 20}}, {2, 102, 3, 1, {}, {}}, {0, 0, 0, 5, {5, 9}, {}}}};
    for (size_t i = 0; i < made.size(); ++i) {
      auto *c = list.add_characters();
      c->set_id(i + 1);
      c->set_name("Hall" + std::to_string(i + 1));
      c->set_level(1);
      c->set_race(made[i].race);
      c->set_specialty(made[i].specialty);
      c->set_face(made[i].face);
      c->set_hair(made[i].hair);
      for (const auto key : made[i].appearance) c->add_appearance(key);
      for (const auto percent : made[i].durability) c->add_appearance_durability(percent);
    }
    front->jump(Screen::select);
    const n3e::front::Context context{"Local Realm", "", release.version, &list, 0};
    front->draw(width, height, 1.0, context);
    front->draw(width, height, 1.0, context);
    std::string models, plugs, classes, looks, worn, fx, dust, part_dust;
    for (const auto &d : front->drawn())
      if (d.which == 1) {
        models += (models.empty() ? "" : ",") + std::to_string(d.select);
        plugs += (plugs.empty() ? "" : ",") + std::to_string(d.plugs);
        looks += (looks.empty() ? "" : ",") + std::to_string(d.face) + "/" + std::to_string(d.hair);
        worn += (worn.empty() ? "" : ",") + std::to_string(d.equipped) + "/" + std::to_string(d.own) + "/" +
                std::to_string(d.equipped_plugs);
        fx += (fx.empty() ? "" : ",") + std::to_string(d.effects);
        dust += (dust.empty() ? "" : ",") + std::to_string(d.dust[0]) + "/" + std::to_string(d.dust[1]);
        part_dust += (part_dust.empty() ? "" : ",") + std::to_string(d.part_dust[0]) + "/" +
                     std::to_string(d.part_dust[1]);
      }
    for (int i = 0; i < list.characters_size(); ++i) {
      auto text = front->character_class(list.characters(i));
      std::replace(text.begin(), text.end(), ' ', '_');
      classes += (i ? "|" : "") + text;
    }
    std::cout << "FRONT_HALL models=" << models << " plugs=" << plugs << " classes=" << classes << " looks=" << looks
              << " worn=" << worn << " fx=" << fx << " tails=" << front->hall_effect_tails() << " dust=" << dust
              << " part_dust=" << part_dust << std::endl;
    // RQ-200: that frame, for the eye (the priest's blade and its effect).
    std::cout << capture_shot("select-worn", A::char_info) << std::endl;
    for (const auto &e : front->hall_effects()) {
      const auto &[c, j, b] = std::tuple{e.centre, e.joint, e.plug_box};
      std::cout << "FRONT_HALL_FX slot=" << e.slot << " key=" << e.key << " copies=" << e.copies << " centre=" << c[0]
                << "," << c[1] << "," << c[2] << " joint=" << j[0] << "," << j[1] << "," << j[2] << " box=" << b[0][0]
                << "," << b[0][1] << "," << b[0][2] << "," << b[1][0] << "," << b[1][1] << "," << b[1][2] << std::endl;
    }
  }
  std::cout << "FRONT_LOGIN";
  for (const auto &[label, screen, waiting, back] :
       {std::tuple{"idle", Screen::login, false, false}, std::tuple{"waiting", Screen::login, true, false},
        std::tuple{"realms", Screen::realms, false, false}, std::tuple{"back", Screen::login, true, true},
        std::tuple{"back_realms", Screen::realms, true, true}}) {
    front->jump(screen);
    front->login_waiting(waiting);
    front->login_line_hidden(back);
    std::cout << " " << label << "=" << front->action_shown(A::login_group) << ","
              << front->action_shown(A::realm_group) << "," << front->action_shown(A::login_closed);
  }
  std::cout << std::endl;
  shot("create", Screen::create, 0, "Local Realm", 0, A::name_field, "");
  // RQ-176 (version 29): the dress the create shot's new character wore:
  // the model's race, the specialty whose dress it wore (0 none), the dress
  // parts drawn in place of the model's own (-1 its own) and the hand plugs;
  // `none` when no new character stood.
  {
    std::cout << "FRONT_CREATE_DRESS";
    bool stood = false;
    for (const auto &d : front->drawn())
      if (d.which == 2 && !stood) {
        stood = true;
        std::cout << " race=" << d.race << " dress=" << d.dress << " parts=" << d.dress_parts
                  << " plugs=" << d.dress_plugs;
      }
    std::cout << (stood ? "" : " none") << std::endl;
  }
  shot("loading-start", Screen::loading, 1, "Local Realm", 2 / 3.f, A::progress, "");
  shot("loading-world", Screen::loading, 1, "Local Realm", 1, A::progress, "");
  shot("message", Screen::login, 0, "Local Realm", 0, A::message, "Disconnected from server");
  // RQ-102 (Q81): the same text as a refused create, which the package titles;
  // the rect is the title's.
  shot("message-titled", Screen::login, 0, "Local Realm", 0, A::title, "Disconnected from server", -1,
       n3e::FrontMessage::create_refused);
  {
    // RQ-111 (KO-FINDINGS 9.7): the select's exit, clicked and answered as a
    // player does, through the screens' own input.
    auto click = [&](n3e::FrontAction action) {
      n3e::front::Output out;
      const auto r = front->action_rect(action, width, height);
      if (!r) return out;
      const float x = ((*r)[0] + (*r)[2]) / 2, y = ((*r)[1] + (*r)[3]) / 2;
      SDL_Event e{};
      e.type = SDL_EVENT_MOUSE_MOTION;
      front->event(e, x, y, width, height);
      e = {};
      e.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
      e.button.button = SDL_BUTTON_LEFT;
      e.button.clicks = 1;
      front->event(e, x, y, width, height);
      e.type = SDL_EVENT_MOUSE_BUTTON_UP;
      return front->event(e, x, y, width, height);
    };
    auto key = [&](SDL_Keycode k) {
      SDL_Event e{};
      e.type = SDL_EVENT_KEY_DOWN;
      e.key.key = k;
      return front->event(e, 0, 0, width, height);
    };
    auto asks = [&] {
      front->jump(Screen::select);
      const auto out = click(A::exit);
      return std::pair{front->message_kind() == n3e::FrontMessage::exit_confirm, out};
    };
    auto shown = [&] {
      return std::to_string(front->action_shown(A::ok)) + "," + std::to_string(front->action_shown(A::yes)) + "," +
             std::to_string(front->action_shown(A::no));
    };
    const auto [asked, first] = asks();
    std::cout << "FRONT_EXIT asks=" << asked;
    if (!asked) std::cout << " command=" << (first.command == n3e::front::Command::exit ? "exit" : "none");
    else {
      std::cout << " shown=" << shown();
      front->jump(Screen::select);
      front->show_message(n3e::FrontMessage::disconnected, "Disconnected from server");
      std::cout << " plain=" << shown();
      auto answer = [&](const char *label, auto press) {
        asks();
        const auto out = press();
        std::cout << " " << label << "=" << (front->showing_message() ? "open" : "closed") << ":"
                  << (out.command == n3e::front::Command::exit ? "exit" : out.command == n3e::front::Command::none
                                                                             ? "none"
                                                                             : "other");
      };
      answer("esc", [&] { return key(SDLK_ESCAPE); });
      answer("enter", [&] { return key(SDLK_RETURN); });
      answer("keypad", [&] { return key(SDLK_KP_ENTER); });
      answer("no", [&] { return click(A::no); });
      answer("yes", [&] { return click(A::yes); });
      answer("ok", [&] { return click(A::ok); });
    }
    // RQ-116: ESC on the select at rest: asks (the exit question, 1264's
    // OnKeyPress 004454e0 pressing bt_exit), back, exit or none.
    auto did = [&](const n3e::front::Output &out) {
      return front->message_kind() == n3e::FrontMessage::exit_confirm ? "asks"
             : out.command == n3e::front::Command::back               ? "back"
             : out.command == n3e::front::Command::exit               ? "exit"
                                                                      : "none";
    };
    front->jump(Screen::select);
    std::cout << " select_esc=" << did(key(SDLK_ESCAPE));
    // RQ-121 (KO-FINDINGS 9.10): with one character, ENTER starts it
    // (started=1: the select request), then ESC and a click on Exit while its
    // start clip plays: none, as 1264's and 1097's select take no input then.
    list.Clear();
    list.add_characters()->set_id(1);
    front->jump(Screen::select);
    const bool started = key(SDLK_RETURN).command == n3e::front::Command::select;
    std::cout << " started=" << started << " start_esc=" << did(key(SDLK_ESCAPE));
    std::cout << " start_exit=" << did(click(A::exit));
    list.Clear();
    front->jump(Screen::select);
    // RQ-112 (KO-FINDINGS 9.12): a click on Back at rest, and where the
    // package says it lands: login, or realms (1298's and 1264's, through a login held
    // with the bar hidden from the click).
    std::cout << " back=" << did(click(A::back)) << ":"
              << (front->back_lands() == n3e::FrontSelectBack::realms ? "realms" : "login");
    front->jump(Screen::select);
    std::cout << std::endl;
    // RQ-114 (KO-FINDINGS 9.6): for a select that binds btn_create, a click on
    // it with slots 0 and 1 taken and slot 1, the row's left end, in focus;
    // the screen right after; in the path mode, after a frame, the path
    // playing (its index in the package), its last frame, whether the select
    // UI shows and the slot the camera is at and the one in focus; then
    // ENTER and ESC, and frames 0.25 s apart until the screen is no longer
    // the select (at most 60): the screen and how many frames that took
    // since the click; then ESC on create and a frame: the camera's slot.
    if (front->action_rect(A::select_create, width, height)) {
      list.Clear();
      for (int i = 0; i < 2; ++i) list.add_characters()->set_id(i + 1);
      const n3e::front::Context flight{"Local Realm", "", release.version, &list, 0};
      double t = 100;
      front->select_at(0);
      front->draw(width, height, t, flight);
      click(A::select_create);
      const auto shown_screen = [&] {
        return front->screen() == Screen::create ? "create" : front->screen() == Screen::select ? "select" : "other";
      };
      std::cout << "FRONT_CREATE click=" << shown_screen();
      // RQ-125 (version 19): over the hall create opens with the click and
      // the camera flies behind it: after a frame the path and its last frame,
      // the slot the camera is at and the one in focus, and whether the new
      // character stands in the hall (new=0 while the camera flies); then
      // frames 0.25 s apart until the camera is on the slot (at most 60): the
      // slot, how many frames that took since the click, and new=1 there.
      const auto stands = [&] {
        for (const auto &d : front->drawn())
          if (d.which == 2) return 1;
        return 0;
      };
      const bool over_hall = front->screen() == Screen::create && front->create_over_hall();
      bool flew = false;
      if (over_hall) {
        front->draw(width, height, t += .25, flight);
        const auto turn = front->front_turn();
        std::cout << " path=" << turn.path << " frames=" << turn.frames << " slot=" << turn.slot
                  << " focus=" << turn.focus << " new=" << stands();
        flew = turn.slot != turn.focus;
        int frames = 1;
        while (front->front_turn().slot != front->front_turn().focus && frames < 60)
          front->draw(width, height, t += .25, flight), ++frames;
        if (flew) std::cout << " arrived=" << front->front_turn().slot << " draws=" << frames << " new=" << stands();
        // RQ-130: a create that waits for its race draws its new character
        // once the race is clicked, at the slot the camera is on.
        if (front->create_waits()) {
          click(A::create_race);
          front->draw(width, height, t += .25, flight);
          std::cout << " race=" << front->action_state(A::create_race) << " new=" << stands()
                    << " figure=" << front->create_figure();
        }
      }
      if (front->screen() == Screen::select) {
        front->draw(width, height, t += .25, flight);
        const auto turn = front->front_turn();
        std::cout << " path=" << turn.path << " frames=" << turn.frames << " ui=" << turn.ui << " slot=" << turn.slot
                  << " focus=" << turn.focus;
        key(SDLK_RETURN);
        key(SDLK_ESCAPE);
        int frames = 1;
        while (front->screen() == Screen::select && frames < 60) front->draw(width, height, t += .25, flight), ++frames;
        std::cout << " arrived=" << shown_screen() << " draws=" << frames;
      }
      if (front->screen() == Screen::create) {
        key(SDLK_ESCAPE);
        front->draw(width, height, t += .25, flight);
        std::cout << " back=" << shown_screen() << " slot=" << front->front_turn().slot;
      }
      // RQ-125: over the hall, ESC one frame into the flight: the select at
      // rest on the slot the camera flew to, its UI shown (1298's Cancel,
      // 005ffb90, sets state 5 and shows the bar at once).
      if (flew) {
        front->select_at(0);
        front->draw(width, height, t += .25, flight);
        click(A::select_create);
        front->draw(width, height, t += .25, flight);
        key(SDLK_ESCAPE);
        front->draw(width, height, t += .25, flight);
        std::cout << " cancel=" << shown_screen() << " slot=" << front->front_turn().slot
                  << " ui=" << front->front_turn().ui;
        // RQ-130: the race clicked one frame into the flight: the new
        // character stands at the slot the flight left (005fd120 by the
        // camera's slot +0x38c), drawn once the camera is on the empty slot.
        if (front->create_waits()) {
          front->select_at(0);
          front->draw(width, height, t += .25, flight);
          click(A::select_create);
          front->draw(width, height, t += .25, flight);
          click(A::create_race);
          int frames = 0;
          while (front->front_turn().slot != front->front_turn().focus && frames < 60)
            front->draw(width, height, t += .25, flight), ++frames;
          front->draw(width, height, t += .25, flight);
          std::cout << " flown=" << front->create_figure() << " new=" << stands();
          key(SDLK_ESCAPE);
          front->draw(width, height, t += .25, flight);
        }
      }
      std::cout << std::endl;
      list.Clear();
      front->jump(Screen::select);
    }
    // RQ-126 (version 20): for a package with a create slide, ENTER on the
    // empty slot in focus at rest (no character) opens create, then frames
    // 1/32 s apart until the slide ends (at most 600): each frame's slid
    // nodes' top-left in window pixels, the first the frame after the press,
    // and whether the slide still runs after the last:
    //   FRONT_CREATE_SLIDE screen=create frames=x,y,..;x,y,.. on=0
    if (!front->create_slide_at(width, height).empty()) {
      list.Clear();
      const n3e::front::Context opened{"Local Realm", "", release.version, &list, 0};
      double t = 200;
      front->select_at(0);
      front->draw(width, height, t, opened);
      key(SDLK_RETURN);
      std::cout << "FRONT_CREATE_SLIDE screen=" << (front->screen() == Screen::create ? "create" : "other")
                << " frames=";
      for (int frame = 0; frame < 600 && (frame == 0 || front->create_sliding()); ++frame) {
        front->draw(width, height, t += 1.0 / 32, opened);
        const char *sep = frame ? ";" : "";
        for (const auto &at : front->create_slide_at(width, height))
          std::cout << sep << at[0] << "," << at[1], sep = ",";
      }
      std::cout << " on=" << front->create_sliding() << std::endl;
      front->jump(Screen::select);
    }
    // RQ-130 (version 21, KO-FINDINGS 9.15): for a create that waits for its
    // race, as 1298's in-select create: opened by ENTER on the empty slot in
    // focus at rest, Create refuses an empty name, then no race (a class
    // clicked first included), then no class (a race click unchooses it), and
    // sends once both are clicked (005fffd0).
    if (front->create_waits()) {
      list.Clear();
      const n3e::front::Context opened{"Local Realm", "", release.version, &list, 0};
      double t = 300;
      // RQ-172: the buttons of the package's fixed race and specialty, and of
      // another specialty of that race.
      const auto fixed = release.create && release.create->fixed ? *release.create->fixed : n3e::CreateRules::Fixed{};
      const int race_node = front->choice_node(true, fixed.race), class_node = front->choice_node(false, fixed.specialty);
      int other_node = -1;
      if (release.create)
        if (const auto *r = n3e::create_race(*release.create, fixed.race))
          for (const auto &s : r->specialties)
            if (s.id != fixed.specialty && other_node < 0) other_node = front->choice_node(false, s.id);
      const auto press = [&](int node) {
        const auto r = front->node_rect(node, width, height);
        if (!r) return;
        const float x = ((*r)[0] + (*r)[2]) / 2, y = ((*r)[1] + (*r)[3]) / 2;
        SDL_Event e{};
        e.type = SDL_EVENT_MOUSE_MOTION;
        front->event(e, x, y, width, height);
        e = {};
        e.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
        e.button.button = SDL_BUTTON_LEFT;
        e.button.clicks = 1;
        front->event(e, x, y, width, height);
        e.type = SDL_EVENT_MOUSE_BUTTON_UP;
        front->event(e, x, y, width, height);
      };
      front->select_at(0);
      front->draw(width, height, t, opened);
      key(SDLK_RETURN);
      // The pointer off every button (the fly's race click left it on the
      // race button, which would draw it on).
      SDL_Event away{};
      away.type = SDL_EVENT_MOUSE_MOTION;
      front->event(away, 0, 0, width, height);
      const auto stands = [&] {
        for (const auto &d : front->drawn())
          if (d.which == 2) return 1;
        return 0;
      };
      const auto frame = [&] { front->draw(width, height, t += .25, opened); };
      std::vector<std::string> boxes;
      // Create (ENTER): the message it shows, closed again, or none.
      n3e::front::CreateRequest as;
      const auto create = [&](bool &sent) {
        const auto out = key(SDLK_RETURN);
        sent = out.command == n3e::front::Command::create;
        if (sent) as = out.create;
        if (!front->showing_message()) return std::string("none");
        const auto kind = *front->message_kind();
        const std::string name = kind == n3e::FrontMessage::create_name          ? "create_name"
                                 : kind == n3e::FrontMessage::create_no_race     ? "create_no_race"
                                 : kind == n3e::FrontMessage::create_no_class    ? "create_no_class"
                                 : kind == n3e::FrontMessage::create_points_left ? "create_points_left"
                                                                                 : "other";
        if (kind != n3e::FrontMessage::create_name)
          boxes.push_back(name + "|" + front->message_title() + "|" + front->message_text());
        key(SDLK_ESCAPE);
        return name;
      };
      bool sent = false;
      frame();
      // RQ-172 (version 25): the ids of create's class buttons and images
      // drawn now, and of its class labels.
      const auto ids_of = [&](bool labels) {
        std::string ids;
        for (const auto &id : front->create_column(labels)) ids += (ids.empty() ? "" : ",") + id;
        return ids.empty() ? std::string("-") : ids;
      };
      const auto until = [&] { return ids_of(false); };
      const auto labels = [&] { return ids_of(true); };
      // RQ-173 (version 26): the stat values and the points left as the
      // texts say them ("-" for an empty one), and a click on stat `k`'s
      // right (`up`) or left arrow.
      const auto stat_texts = [&] {
        std::string out;
        for (const auto &text : front->create_stat_texts()) out += (out.empty() ? "" : "/") + (text.empty() ? "-" : text);
        return out;
      };
      const auto arrow = [&](size_t k, bool up) { press(front->stat_arrow_node(k, up)); };
      // RQ-174 (version 27): the face and hair the create holds, the parts
      // the new character draws (-1 none), and a click on a face or hair arrow.
      const auto looks = [&] {
        return std::to_string(front->create_choice().face) + "," + std::to_string(front->create_choice().hair);
      };
      const auto drawn_looks = [&] {
        for (const auto &d : front->drawn())
          if (d.which == 2) return std::to_string(d.face) + "," + std::to_string(d.hair);
        return std::string("-");
      };
      const auto look = [&](A action) { press(front->create_action_node(action)); };
      // RQ-176 (version 29): the dress the new character wears, as drawn:
      // its specialty, the dress parts in place of the model's own (-1 its
      // own) and the hand plugs ("-" when none stands).
      const auto dressed = [&] {
        for (const auto &d : front->drawn())
          if (d.which == 2)
            return std::to_string(d.dress) + "/" + std::to_string(d.dress_parts) + "/" +
                   std::to_string(d.dress_plugs);
        return std::string("-");
      };
      const auto race_state = [&] { return front->node_state(race_node); };
      const auto class_state = [&] { return front->node_state(class_node); };
      std::cout << "FRONT_CREATE_CHOICE open=" << stands() << "," << race_state() << "," << class_state()
                << " column=" << until() << " labels=" << labels() << " stats=" << stat_texts()
                << " looks=" << looks();
      std::cout << " empty=" << create(sent);
      SDL_Event typed{};
      typed.type = SDL_EVENT_TEXT_INPUT;
      typed.text.text = "Shot";
      front->event(typed, 0, 0, width, height);
      std::cout << " norace=" << create(sent);
      press(class_node);
      frame();
      std::cout << " class=" << class_state() << "," << stands() << " column=" << until() << " labels=" << labels();
      std::cout << " classfirst=" << create(sent);
      // RQ-174: a face click with no race (00604f90 tests neither).
      look(A::create_face_up);
      press(race_node);
      frame();
      std::cout << " race=" << race_state() << "," << class_state() << "," << stands() << " column=" << until()
                << " labels=" << labels() << " model=" << front->create_model_race() << " row=" << front->create_row()
                << " stats=" << stat_texts() << " drawn=" << drawn_looks() << " dress=" << dressed();
      // RQ-173: with no class the right arrow spends a point; the left takes
      // none back (1298's row by race and class has none for class -1,
      // 00604f90); Create says no class before points left (005fffd0).
      arrow(0, true);
      arrow(0, false);
      frame();
      std::cout << " noclassarrows=" << stat_texts();
      std::cout << " noclass=" << create(sent);
      press(class_node);
      frame();
      std::cout << " both=" << race_state() << "," << class_state() << "," << stands() << " labels=" << labels()
                << " stats=" << stat_texts() << " dress=" << dressed();
      // RQ-153: that frame, the race and then the class clicked, as the shot
      // create-class (rect= the class button's), printed after this line.
      front->draw(width, height, t, opened);
      const auto class_shot = capture_shot("create-class", A::create_class, false, class_node);
      // RQ-174: the arrows stop at create.bin's last face and hair (KO's 3
      // and 2), no wrap; the new character draws the parts they chose.
      for (int k = 0; k < 5; ++k) look(A::create_face_up);
      for (int k = 0; k < 4; ++k) look(A::create_hair_up);
      look(A::create_hair_down);
      frame();
      std::cout << " arrows=" << looks() << " drawn=" << drawn_looks();
      // RQ-145: the chosen race clicked again unchooses the class and builds
      // nothing, so the class's marks stay (1298's 00604f90); RQ-172: the
      // other class clicked, its own labels marked, Create sends it.
      press(race_node);
      frame();
      std::cout << " again=" << race_state() << "," << class_state() << "," << stands() << " labels=" << labels()
                << " dress=" << dressed();
      press(other_node);
      frame();
      std::cout << " other=" << race_state() << "," << front->node_state(other_node) << "," << class_state() << ","
                << stands() << " labels=" << labels() << " stats=" << stat_texts() << " dress=" << dressed();
      // RQ-173: the other class's build reset the points; Create says points
      // left (code 10); the left arrow at the row's base takes nothing back,
      // the right arrows spend until none is left (the last click none), a
      // left arrow takes one back and another right arrow spends it.
      std::cout << " points=" << create(sent);
      arrow(0, false);
      for (int k = 0; k < 11; ++k) arrow(4, true);
      frame();
      std::cout << " spent=" << stat_texts();
      arrow(4, false);
      arrow(0, true);
      frame();
      std::cout << " moved=" << stat_texts();
      const auto last = create(sent);
      std::cout << " create=" << last << " sent=" << sent << " as=" << as.race << "," << as.specialty;
      for (size_t k = 0; k < as.stats.size(); ++k) std::cout << (k ? "/" : ",") << as.stats[k];
      std::cout << "," << as.face << "," << as.hair;
      // RQ-133: a race click, a Cancel (ESC) and create opened again: each
      // open shows the until-race nodes again (1298's reset, 006066b0);
      // RQ-145: a class click before the Cancel, the until-class nodes too.
      front->select_at(0);
      frame();
      key(SDLK_RETURN);
      frame();
      press(race_node);
      frame();
      press(class_node);
      frame();
      key(SDLK_ESCAPE);
      frame();
      key(SDLK_RETURN);
      frame();
      std::cout << " reopen=" << until() << " labels=" << labels() << " stats=" << stat_texts()
                << " looks=" << looks() << std::endl;
      std::cout << class_shot << std::endl;
      for (const auto &b : boxes) std::cout << "FRONT_CREATE_MESSAGE " << b << std::endl;
      front->jump(Screen::select);
    }
    // RQ-180 (RQ-175, version 28, KO-FINDINGS 10.6): for a create with
    // description text, create opened by ENTER on the empty slot in focus at
    // rest and its slide run out, then the pointer moved and a frame drawn
    // (KO's MouseProc pass runs each tick) before each report of the text
    // (FRONT_CREATE_DESC_TEXT, below; the node the pointer is on, `-` off
    // every node at the window's top-left).
    if (front->create_description().active()) {
      list.Clear();
      const n3e::front::Context opened{"Local Realm", "", release.version, &list, 0};
      double t = 400;
      const auto &desc = front->create_description();
      const auto fixed = release.create && release.create->fixed ? *release.create->fixed : n3e::CreateRules::Fixed{};
      const int race_node = front->choice_node(true, fixed.race), class_node = front->choice_node(false, fixed.specialty);
      const auto frame = [&] { front->draw(width, height, t += .25, opened); };
      const auto move = [&](int node) {
        float x = 0, y = 0;
        if (const auto r = node >= 0 ? front->node_rect(node, width, height) : std::nullopt)
          x = ((*r)[0] + (*r)[2]) / 2, y = ((*r)[1] + (*r)[3]) / 2;
        SDL_Event e{};
        e.type = SDL_EVENT_MOUSE_MOTION;
        front->event(e, x, y, width, height);
        return std::pair{x, y};
      };
      const auto press = [&](int node) {
        const auto [x, y] = move(node);
        SDL_Event e{};
        e.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
        e.button.button = SDL_BUTTON_LEFT;
        e.button.clicks = 1;
        front->event(e, x, y, width, height);
        e.type = SDL_EVENT_MOUSE_BUTTON_UP;
        front->event(e, x, y, width, height);
      };
      // The text as a JSON string (KO's rows hold line breaks).
      const auto quoted = [](const std::string &s) {
        std::ostringstream out;
        out << '"';
        for (const unsigned char c : s) {
          if (c == '"' || c == '\\') out << '\\' << c;
          else if (c == '\n') out << "\\n";
          else if (c < 0x20 || c >= 0x7f) out << "\\u00" << "0123456789abcdef"[c >> 4] << "0123456789abcdef"[c & 15];
          else out << c;
        }
        return out.str() + '"';
      };
      const auto said = [&](const char *step, int node) {
        const std::string id = node < 0 ? std::string("-") : front->create_node_id(size_t(node));
        std::cout << "FRONT_CREATE_DESC_TEXT " << step << " " << id << " " << quoted(desc.shown) << std::endl;
      };
      // Hover `node` (or leave every node, -1), a frame, the text.
      const auto hover = [&](const char *step, int node) {
        move(node);
        frame();
        said(step, node);
      };
      // ENTER on the empty slot at rest, a frame, and the slide (if any) run out.
      const auto open = [&] {
        key(SDLK_RETURN);
        frame();
        for (int k = 0; k < 60 && front->create_sliding(); ++k) frame();
      };
      static const char *rests[] = {"none", "keep", "chosen"};
      char colour[9];
      std::snprintf(colour, sizeof colour, "%08x", unsigned(desc.package.color));
      std::cout << "FRONT_CREATE_DESC rest=" << rests[size_t(desc.package.rest)] << " colour=" << colour
                << " tips=" << desc.package.tips.size() << std::endl;
      front->select_at(0);
      front->draw(width, height, t, opened);
      // The pointer off every node before create opens (the earlier blocks
      // left it on a button).
      move(-1);
      open();
      said("open", -1);
      // The open's frame and the first tip's, both at the same time (the hall
      // still between them), as the shots create-desc-open and
      // create-desc-hover (rect= the class_desc node's), printed last.
      front->draw(width, height, t, opened);
      const auto open_shot = capture_shot("create-desc-open", A::class_desc);
      const int first = desc.package.tips.empty() ? -1 : int(desc.package.tips[0].node);
      move(first);
      front->draw(width, height, t, opened);
      const auto hover_shot = capture_shot("create-desc-hover", A::class_desc);
      said("hover", first);
      // Each tip in KO's loop order, then off them.
      for (const auto &tip : desc.package.tips) hover("hover", int(tip.node));
      hover("away", -1);
      hover("hover", first);
      hover("away", -1);
      // The fixed race clicked (the pointer on it), a stat area, off them;
      // the fixed specialty's class clicked, the race again, off them.
      press(race_node);
      frame();
      said("race", race_node);
      hover("hover", first);
      hover("away", -1);
      press(class_node);
      frame();
      said("class", class_node);
      hover("hover", race_node);
      hover("away", -1);
      // A Cancel (ESC) and create opened again.
      key(SDLK_ESCAPE);
      frame();
      open();
      said("reopen", -1);
      std::cout << open_shot << std::endl << hover_shot << std::endl;
      front->jump(Screen::select);
    }
    if (asked)
      shot("message-exit", Screen::select, 1, "Local Realm", 0, A::yes, "Exit the game?", -1,
           n3e::FrontMessage::exit_confirm);
  }
  if (const auto &logo = front->logo()) {
    // RQ-101: each group in its hold, and the first half way into its fade-in.
    std::string alphas;
    auto logo_shot = [&](const std::string &name, double t) {
      shot(name, Screen::logo, 0, "Local Realm", 0, A::none, "", t);
      alphas += (alphas.empty() ? "" : ",") + std::to_string(front->logo_shown().alpha);
    };
    for (size_t g = 0; g < logo->groups.size(); ++g)
      logo_shot("logo-" + std::to_string(g),
                n3e::front::logo_group_start(*logo, g) + logo->groups[g].fade_in + logo->groups[g].hold / 2);
    logo_shot("logo-fade", logo->groups[0].fade_in / 2);
    const double length = n3e::front::logo_length(*logo);
    front->logo_at(length - .1);
    const n3e::front::Context context{"Local Realm", "", release.version, &list, 0};
    front->draw(width, height, 1.0, context);
    const bool before = front->screen() == Screen::logo;
    front->draw(width, height, 1.2, context);
    std::cout << "FRONT_LOGO groups=" << logo->groups.size() << " length=" << length
              << " skip=" << bool(logo->flags & n3e::FrontLogo::SKIP_KEY)
              << " cursor=" << bool(logo->flags & n3e::FrontLogo::HIDE_CURSOR) << " alpha=" << alphas
              << " before=" << (before ? "logo" : "login")
              << " end=" << (front->screen() == Screen::login ? "login" : "logo") << std::endl;
  }
  // RQ-018 (Q57): each screen's track (its index among the tracks the
  // screens name, or none), then each of those tracks streamed one second
  // past its end (RQ-083: a PCM track's pass is its sample frames; a track
  // with a restart period restarts on it):
  //   FRONT_MUSIC login=0 realms=0 select=1 create=1 loading=none
  //   FRONT_MUSIC_STREAM track=K kind=mpeg|pcm rate=R channels=C frames=F loop=0|1 restart=S
  //     decoded=D restarts=N peak=P audible=A ended=0|1
  std::vector<std::shared_ptr<const n3e::MusicTrack>> tracks;
  std::cout << "FRONT_MUSIC";
  for (const auto &[label, screen] : {std::pair{"login", Screen::login}, std::pair{"realms", Screen::realms},
                                      std::pair{"select", Screen::select}, std::pair{"create", Screen::create},
                                      std::pair{"loading", Screen::loading}}) {
    front->jump(screen);
    const auto track = front->music();
    auto at = std::find(tracks.begin(), tracks.end(), track);
    if (track && at == tracks.end()) at = tracks.insert(tracks.end(), track);
    std::cout << " " << label << "=" << (track ? std::to_string(at - tracks.begin()) : std::string("none"));
  }
  // RQ-101: the logo screen's track once its delay has run, with its delay
  // and the group its fade-out starts with:
  //   FRONT_MUSIC ... logo=K|none delay=D fade_group=G|none fade=F
  if (const auto &logo = front->logo()) {
    front->logo_at(logo->music_delay);
    const auto track = front->music();
    auto at = std::find(tracks.begin(), tracks.end(), track);
    if (track && at == tracks.end()) at = tracks.insert(tracks.end(), track);
    std::cout << " logo=" << (track ? std::to_string(at - tracks.begin()) : std::string("none"))
              << " delay=" << logo->music_delay << " fade_group="
              << (logo->fade_group == n3e::FrontLogo::kNone ? std::string("none") : std::to_string(logo->fade_group))
              << " fade=" << logo->fade;
  }
  std::cout << std::endl;
  front->jump(Screen::login);
  for (size_t k = 0; k < tracks.size(); ++k) {
    const auto &track = tracks[k];
    const bool pcm = track->kind == n3e::MusicTrack::Kind::pcm;
    n3e::MusicStream stream(track);
    std::vector<float> chunk(4800 * 2);
    float peak = 0;
    uint64_t audible = 0;
    // One pass is frames x 1152 (MPEG-1) or 576 samples, or (PCM) the
    // sample frames; go one second past it.
    const uint64_t samples = uint64_t(track->frames) * (pcm ? 1 : track->rate >= 32000 ? 1152 : 576);
    const uint64_t pass = samples * 48000 / track->rate;
    for (uint64_t written = 0; written < pass + 48000 && !stream.ended();) {
      std::fill(chunk.begin(), chunk.end(), 0.f);
      const auto n = stream.mix(chunk.data(), 4800, 1.f);
      for (unsigned i = 0; i < n * 2; ++i) peak = std::max(peak, std::abs(chunk[i]));
      for (unsigned i = 0; i < n; ++i) audible += std::abs(chunk[i * 2]) > 1e-4f || std::abs(chunk[i * 2 + 1]) > 1e-4f;
      written += n;
    }
    std::cout << "FRONT_MUSIC_STREAM track=" << k << " kind=" << (pcm ? "pcm" : "mpeg") << " rate=" << track->rate
              << " channels=" << track->channels << " frames=" << track->frames << " loop=" << track->loop
              << " restart=" << track->restart << " decoded=" << stream.decoded_frames()
              << " restarts=" << stream.restarts() << " peak=" << peak << " audible=" << audible
              << " ended=" << stream.ended() << std::endl;
  }
  if (glGetError() != GL_NO_ERROR) throw std::runtime_error("GL error");
  std::cout << "FRONT_SHOTS done" << std::endl;
  return 0;
}
