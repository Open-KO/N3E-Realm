#include <set>
#include "world.h"
#include <arpa/inet.h>
#include <chrono>
#include <cmath>
#include <csignal>
#include <fcntl.h>
#include <memory>
#include <netdb.h>
#include <netinet/tcp.h>
#include <openssl/ssl.h>
#include <poll.h>
#include <stdexcept>
#include <unistd.h>
namespace n3e {
namespace {
using Clock = std::chrono::steady_clock;
double now() {
  return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();
}
void check(bool b, const char *m) {
  if (!b)
    throw std::runtime_error(m);
}
struct Transport {
  int fd = -1;
  SSL_CTX *ctx = nullptr;
  SSL *ssl = nullptr;
  ~Transport() {
    if (ssl)
      SSL_free(ssl);
    if (ctx)
      SSL_CTX_free(ctx);
    if (fd >= 0)
      close(fd);
  }
  void wait(int error, double end) {
    int ms = int((end - now()) * 1000);
    check(ms > 0, "TLS deadline");
    pollfd p{fd, short(error == SSL_ERROR_WANT_WRITE ? POLLOUT : POLLIN), 0};
    check(::poll(&p, 1, ms) > 0, "TLS deadline");
  }
  void open(const std::string &endpoint, const std::string &ca) {
    auto colon = endpoint.rfind(':');
    check(colon != std::string::npos, "HOST:PORT required");
    auto host = endpoint.substr(0, colon), port = endpoint.substr(colon + 1);
    addrinfo hints{}, *raw = nullptr;
    hints.ai_socktype = SOCK_STREAM;
    check(getaddrinfo(host.c_str(), port.c_str(), &hints, &raw) == 0,
          "DNS failed");
    std::unique_ptr<addrinfo, decltype(&freeaddrinfo)> addresses(raw,
                                                                 freeaddrinfo);
    for (auto *a = raw; a; a = a->ai_next) {
      fd = socket(a->ai_family, a->ai_socktype | SOCK_NONBLOCK, a->ai_protocol);
      if (fd < 0)
        continue;
      int r = ::connect(fd, a->ai_addr, a->ai_addrlen);
      if (r == 0 || errno == EINPROGRESS) {
        pollfd p{fd, POLLOUT, 0};
        int err = 0;
        socklen_t n = sizeof(err);
        if (::poll(&p, 1, 2000) > 0 &&
            getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &n) == 0 && err == 0)
          break;
      }
      close(fd);
      fd = -1;
    }
    check(fd >= 0, "connect failed");
    int no_delay = 1;
    check(setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &no_delay,
                     sizeof(no_delay)) == 0,
          "TCP_NODELAY failed");
    ctx = SSL_CTX_new(TLS_client_method());
    check(ctx, "TLS context");
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, nullptr);
    check(SSL_CTX_load_verify_locations(ctx, ca.c_str(), nullptr) == 1,
          "CA failed");
    ssl = SSL_new(ctx);
    check(ssl, "TLS allocation");
    SSL_set_fd(ssl, fd);
    SSL_set_tlsext_host_name(ssl, host.c_str());
    check(SSL_set1_host(ssl, host.c_str()) == 1, "hostname policy");
    double end = now() + 2;
    for (;;) {
      int r = SSL_connect(ssl);
      if (r == 1)
        break;
      int e = SSL_get_error(ssl, r);
      check(e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE,
            "TLS verification failed");
      wait(e, end);
    }
    check(SSL_get_verify_result(ssl) == X509_V_OK, "TLS verification failed");
  }
  void transfer(char *b, size_t n, bool write, double end) {
    while (n) {
      int r = write ? SSL_write(ssl, b, n) : SSL_read(ssl, b, n);
      if (r > 0) {
        b += r;
        n -= r;
      } else {
        int e = SSL_get_error(ssl, r);
        check(e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE,
              "connection closed");
        wait(e, end);
      }
    }
  }
  void send(const Envelope &e) {
    auto b = e.SerializeAsString();
    check(b.size() > 0 && b.size() <= 65536, "frame bound");
    uint32_t n = htonl(b.size());
    double end = now() + 2;
    transfer((char *)&n, 4, true, end);
    transfer(b.data(), b.size(), true, end);
  }
  bool available() {
    pollfd p{fd, POLLIN, 0};
    return SSL_pending(ssl) > 0 || ::poll(&p, 1, 5) > 0;
  }
  Envelope receive() {
    uint32_t n;
    double end = now() + 2;
    transfer((char *)&n, 4, false, end);
    n = ntohl(n);
    check(n > 0 && n <= 65536, "frame bound");
    std::string b(n, 0);
    transfer(b.data(), n, false, end);
    Envelope e;
    check(e.ParseFromString(b), "decode");
    return e;
  }
};
} // namespace
WorldClient::WorldClient(const Release &r, const Scene &s, std::string e,
                         std::string c)
    : release(r), scene(s), endpoint(std::move(e)), ca(std::move(c)),
      worker([this](std::stop_token stop) { run(stop); }) {}
WorldClient::~WorldClient() { worker.request_stop(); }
WorldState WorldClient::poll() {
  std::lock_guard lock(mutex);
  return state;
}
void WorldClient::direction(float x, float z, uint32_t selected_mode, bool held) {
  std::lock_guard lock(mutex);
  // Camera rotation can make a diagonal component exceed one. Normalize the
  // intent before serialization, preserving the server's strict component
  // bound.
  float length = std::max(1.f, std::hypot(x, z));
  dx = x / length;
  dz = z / length;
  mode = selected_mode;
  turbo = held;
}
void WorldClient::send(Envelope e) {
  std::lock_guard lock(mutex);
  if (outgoing.size() >= 32) {
    state.status = "Client queue full";
    return;
  }
  outgoing.push_back(std::move(e));
}
void WorldClient::run(std::stop_token stop) {
  std::signal(SIGPIPE, SIG_IGN);
  try {
    Transport t;
    t.open(endpoint, ca);
    Envelope h;
    auto *hs = h.mutable_handshake();
    hs->set_version(release.protocol);
    hs->set_game(release.game);
    hs->set_content(release.hash);
    t.send(h);
    auto response = t.receive();
    if (response.has_error() && (response.error().code() == Error::VERSION ||
                                 response.error().code() == Error::CONTENT)) {
      std::lock_guard lock(mutex);
      state.update_required = true;
      state.status = update_text(release, response.error().detail());
      return;
    }
    if (response.has_error())
      throw std::runtime_error(response.error().detail());
    check(response.has_snapshot(), "handshake reply");
    {
      std::lock_guard lock(mutex);
      state.connected = true;
      state.status = "Account - type then ENTER";
    }
    uint64_t seq = 0, session = 0;
    double next = now(), ping = now(), loot_poll = now();
    float speed = 1;
    std::deque<Move> pending;
    while (!stop.stop_requested()) {
      std::deque<Envelope> queue;
      float x, z;
      uint32_t selected_mode;
      bool held, permitted;
      uint64_t entity, generation;
      {
        std::lock_guard lock(mutex);
        queue.swap(outgoing);
        x = dx;
        z = dz;
        selected_mode = mode;
        held=turbo; permitted=state.world.turbo_allowed();
        entity=state.world.self(); generation=state.world.permission_generation();
      }
      for (auto &e : queue)
        t.send(e);
      if (session && now() >= next) {
        // Retain the 20Hz phase rather than accumulating each poll's lateness.
        // A stall skips missed slots; never burst old inputs to catch up.
        next += .05;
        if (next <= now())
          next = now() + .05;
        check(pending.size() < 64, "unacknowledged input bound");
        Envelope e;
        auto *m = e.mutable_move();
        m->set_session(session);
        m->set_seq(++seq);
        m->set_x(x);
        m->set_z(z);
        m->set_mode(selected_mode);
        if(release.protocol>=7)m->set_entity(entity);
        if(release.exploration) {m->set_turbo(held);m->set_permission_generation(generation);}
        t.send(e);
        pending.push_back(*m);
        std::lock_guard lock(mutex);
        float n = std::max(1.f, std::sqrt(x * x + z * z));
        if (release.movement) {
          if (speed > 0) {
            float multiplier=release.exploration && held && permitted ? release.exploration->multiplier : 1.f;
            state.predicted = advance(scene.collision, state.predicted, x, z,
                                      selected_mode, *release.movement,multiplier);
          }
        } else
          state.predicted = walk(scene.collision, state.predicted,
                                 x / n * speed, z / n * speed);
      }
      if (session && release.protocol >= 5 && now() >= loot_poll) {
        Envelope q; q.mutable_loot_list(); t.send(q); loot_poll = now() + 1;
      }
      if (now() >= ping) {
        Envelope e;
        e.mutable_ping();
        t.send(e);
        ping = now() + 1;
      }
      if (!t.available())
        continue;
      auto e = t.receive();
      std::lock_guard lock(mutex);
      if(e.has_registry()) state.registry=e.registry();
      if (e.has_login_result()) {
        check(e.login_result().token().empty() || e.login_result().token().size() == 32, "login token bound");
        state.login_result = e.login_result();
        ++state.login_results;
      }
      if(e.has_admin_result()) state.admin=e.admin_result();
      if (e.has_characters()) {
        state.characters = e.characters();
        state.status = "1-8 SELECT | N CREATE CHARACTER";
      }
      if (e.has_error())
        refusal(state, release, session != 0, e.error());
      if (e.has_loot_page()) {
        check(e.loot_page().drops_size() <= 64, "loot page bound");
        state.loot = e.loot_page();
      }
      if(e.has_party_result()){
        const auto &v=e.party_result();check(release.party&&v.sequence()>0&&v.sequence()<=INT64_MAX&&v.status().size()<=64,"party result bounds");state.party_status=v.status();++state.party_responses;
      }
      if(e.has_party_state()){
        const auto &v=e.party_state();check(release.party&&v.members_size()<=int(release.party->capacity)&&v.group()<=INT64_MAX&&v.leader()<=INT64_MAX&&v.invitation()<=INT64_MAX&&v.inviter()<=INT64_MAX&&v.inviter_name().size()<=release.party->name_bytes,"party state bounds");
        std::set<unsigned> slots;std::set<uint64_t> ids;
        auto name_ok=[&](const std::string&name){return !name.empty()&&name.size()<=release.party->name_bytes&&name.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")==std::string::npos;};
        for(const auto&m:v.members())check(m.slot()<release.party->capacity&&slots.insert(m.slot()).second&&m.character()>0&&m.character()<=INT64_MAX&&ids.insert(m.character()).second&&m.entity()>0&&m.entity()<=INT64_MAX&&name_ok(m.name())&&m.level()>0&&m.level()<=1000&&m.max_health()>0&&m.health()<=m.max_health()&&m.resource()<=m.max_resource(),"party member");
        check(v.group()?(v.members_size()>0&&ids.contains(v.leader())&&!v.invitation()):(!v.members_size()&&!v.leader()),"party membership");
        check(v.invitation()?(v.inviter()>0&&name_ok(v.inviter_name())):(!v.inviter()&&v.inviter_name().empty()),"party invitation");
        if(v.tick()>=state.party.tick())state.party=v;
      }
      if(e.has_friend_result()){
        const auto &v=e.friend_result();check(release.friends&&v.capacity()==release.friends->capacity&&v.entries_size()<=int(v.capacity())&&v.revision()<=INT64_MAX&&v.request().size()<=64&&v.status().size()<=64,"friend result bounds");
        std::set<unsigned> slots;std::set<uint64_t> ids;
        for(const auto &e:v.entries())check(e.slot()<v.capacity()&&slots.insert(e.slot()).second&&e.character()>0&&e.character()<=INT64_MAX&&ids.insert(e.character()).second&&!e.name().empty()&&e.name().size()<=release.friends->name_bytes&&e.name().find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")==std::string::npos,"friend record");
        if(!state.friends.capacity()||v.revision()>=state.friends.revision()){state.friends=v;}state.friend_status=v.status();++state.friend_responses;
      }
      if(e.has_friend_presence()){
        const auto &v=e.friend_presence();check(release.friends&&v.sequence()>0&&v.sequence()<=INT64_MAX&&v.entries_size()<=int(release.friends->capacity),"friend presence bounds");
        for(const auto &e:v.entries())check(!e.name().empty()&&e.name().size()<=release.friends->name_bytes&&e.name().find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")==std::string::npos&&e.character()<=INT64_MAX&&e.entity()<=INT64_MAX&&(e.online()?(e.character()>0&&e.entity()>0):(!e.character()&&!e.entity()&&!e.in_party())),"friend presence record");
        if(v.sequence()>=state.friend_presence.sequence())state.friend_presence=v;
      }
      if(e.has_storage_auth_result()){
        const auto &reply=e.storage_auth_result();check(release.storage_auth&&reply.revision()<=INT64_MAX&&reply.authorized_revision()<=INT64_MAX&&reply.request().size()<=64&&reply.status().size()<=64,"storage credential reply");
        state.storage_auth_status=reply.status();state.storage_authorized=reply.authorized_revision();++state.storage_auth_responses;
        if(!state.storage_authorized)state.storage.Clear();
      }
      if(e.has_storage_result()){
        const auto &reply=e.storage_result();check(release.storage.has_value(),"unexpected storage reply");
        check((reply.status()=="combat_pending"||reply.status()=="storage_pending"||reply.status()=="stale_snapshot"||reply.status()=="locked"||reply.status()=="unprovisioned")|| (reply.has_bag()&&reply.has_storage()),"missing storage state");
        if(reply.has_storage()){
          const auto &s=reply.storage();check(s.capacity()==release.storage->capacity&&s.slots_size()==int(s.capacity())&&s.coins()<=release.storage->coin_limit&&s.revision()<=INT64_MAX,"storage bounds");
          std::set<uint64_t> serials;for(const auto &i:reply.bag().slots())if(i.instance())serials.insert(i.instance());for(const auto &i:reply.bag().equipment())if(i.instance())serials.insert(i.instance());
          for(const auto &i:s.slots()){
            if(!i.instance())check(i.item().empty()&&!i.quantity()&&!i.durability(),"vacant storage record");
            else{auto d=std::find_if(release.inventory->items.begin(),release.inventory->items.end(),[&](const auto &d){return d.id==i.item();});check(i.instance()<=INT64_MAX&&serials.insert(i.instance()).second&&d!=release.inventory->items.end()&&i.quantity()>0&&i.quantity()<=d->stack&&i.durability()<=d->durability,"storage record");}
          }
          if(!state.storage.capacity()||s.revision()>=state.storage.revision())state.storage=s;
        }
        state.storage_status=reply.status();++state.storage_responses;
        state.item_result(true,reply.request(),reply.status());
        if(reply.status()=="locked"||reply.status()=="unprovisioned"){state.storage.Clear();state.storage_authorized=0;state.storage_auth_status=reply.status();}
      }
      if (e.has_bag_result()||(e.has_storage_result()&&e.storage_result().has_bag())) {
        check(release.inventory.has_value() && (e.has_storage_result()||e.bag_result().has_state()), "unexpected inventory reply");
        const auto &bag=e.has_storage_result()?e.storage_result().bag():e.bag_result().state(); const auto &policy=*release.inventory;
        check(bag.capacity()==policy.capacity && bag.slots_size()==int(policy.capacity) && bag.currency()==policy.currency && bag.coins()<=policy.limit,"inventory bounds");
        std::set<uint64_t> serials;
        check(bag.equipment_size()==(release.equipment?int(release.equipment->slots.size()):0),"equipment shape");
        for(int index=0;index<bag.slots_size()+bag.equipment_size();++index) {
          const auto &slot=index<bag.slots_size()?bag.slots(index):bag.equipment(index-bag.slots_size());
          if(!slot.instance()) check(slot.item().empty() && !slot.quantity() && !slot.durability(),"vacant inventory slot");
          else {
            auto definition=std::find_if(policy.items.begin(),policy.items.end(),[&](const auto &i){return i.id==slot.item();});
            check(serials.insert(slot.instance()).second && definition!=policy.items.end() && slot.quantity()>0 && slot.quantity()<=definition->stack && slot.durability()<=definition->durability,"inventory item");
          }
        }
        if(release.equipment) for(int j=0;j<bag.equipment_size();++j) {
          const auto &record=bag.equipment(j);if(!record.instance())continue;
          const auto &items=release.equipment->items;auto i=std::find_if(items.begin(),items.end(),[&](const auto&i){return i.id==record.item();});
          check(i!=items.end()&&record.quantity()==1&&(i->slots&(1u<<j)),"equipment placement");
          for(int k=0;k<bag.equipment_size();++k)check(!(i->blocks&(1u<<k))||!bag.equipment(k).instance(),"equipment exclusion");
        }
        if(!state.bag.capacity() || bag.revision()>=state.bag.revision()) state.bag=bag;
        if(e.has_bag_result()&&!e.bag_result().request().empty()){
          state.item_result(false,e.bag_result().request(),e.bag_result().status());
          state.bag_results.emplace_back(e.bag_result().request(),e.bag_result().status());
          if(state.bag_results.size()>32)state.bag_results.pop_front();
        }
        state.bag_status=e.has_storage_result()?e.storage_result().status():e.bag_result().status(); ++state.bag_responses;
      }
      if (e.has_claim_result()) {
        state.claim=e.claim_result();++state.claim_responses;
        check(e.claim_result().coins_size()<=8,"coin recipient bound");
        for(const auto &coin:e.claim_result().coins()) {
          check(coin.character()>0&&coin.character()<=INT64_MAX&&!coin.name().empty()&&coin.name().size()<=24&&coin.nominal()<=32766&&coin.added()<=coin.nominal()&&coin.balance()<=2100000000&&coin.added()<=coin.balance()&&coin.bag_revision()<=INT64_MAX,"coin outcome bounds");
          for(const auto &actor:state.world.entities()) if(actor.id()==state.world.self()&&actor.name()==coin.name()) state.coin_revision=std::max(state.coin_revision,coin.bag_revision());
        }
        state.loot_status = e.claim_result().status();
        if(e.claim_result().coins_size()>0) state.loot_status += " coins";
        if(!e.claim_result().recipient_name().empty()) state.loot_status += " > " + e.claim_result().recipient_name();
        if (state.loot_status != "pending") {
          loot_poll = now();
          if(release.inventory) { Envelope q; q.mutable_bag_request(); t.send(q); }
        }
      }
      if (e.has_respawn_result())
        state.respawn = e.respawn_result().status();
      if (e.has_action_result()) {
        state.combat = e.action_result().status();
        state.combat_damage = e.action_result().damage();
        state.action_result_seq = e.action_result().seq();
        state.action_outcomes.push_back({++state.action_outcome_count, e.action_result().seq(), e.action_result().status()});
        if (state.action_outcomes.size() > 32) state.action_outcomes.pop_front();
      }
      if (e.has_chat() && e.chat().notice()) {
        state.operator_notice = e.chat().text();
        state.operator_notice_level = e.chat().notice();
        ++state.operator_notices;
      } else if (e.has_chat()) {
        state.chat = (e.chat().private_message() ? "[Whisper] " : "") +
                     (e.chat().sender_name().empty() ? std::to_string(e.chat().sender()) : e.chat().sender_name()) +
                     ": " + e.chat().text();
        state.chat_operator = e.chat().from_operator();
      }
      if (e.has_world()) {
        check(e.world().events_size()<=128,"presentation event bound");uint64_t event_sequence=0;
        // PQ-420 (D-217): kind 6, a held ranged shot's landing, only under a
        // profile with a cast time, from a player; PQ-439 (D-223): kind 7, its
        // release, only under such a profile with a flight.
        auto cast_style=[&](uint32_t style){return release.combat_animation&&style&&style<=release.combat_animation->profiles.size()&&release.combat_animation->profiles[style-1].ranged.cast_ms;};
        auto flight_style=[&](uint32_t style){return cast_style(style)&&!release.combat_animation->profiles[style-1].ranged.flight.empty();};
        for(const auto&event:e.world().events()){
          check(event.sequence()>event_sequence&&event.sequence()<=e.world().event_cursor()&&event.kind()>=1&&(event.kind()<=(release.skills?5u:2u)||(event.kind()==6&&cast_style(event.style())&&!event.npc())||(event.kind()==7&&flight_style(event.style())&&!event.npc()&&!event.hit()))&&event.actor()&&event.target()&&event.tick()<=e.world().tick()&&event.key().size()<=200,"presentation event identity");
          for(float value:{event.x(),event.y(),event.z(),event.target_x(),event.target_y(),event.target_z()})check(std::isfinite(value)&&std::abs(value)<=1000000,"presentation event position");
          check(event.style()<=(release.combat_animation?release.combat_animation->profiles.size():0),"presentation event style");
          check(!event.request_sequence()||((event.kind()==2||event.kind()==6||event.kind()==7)&&!event.npc()),"presentation request identity");
          event_sequence=event.sequence();
        }
        check(e.world().skill_cooldowns_size()<=32,"skill cooldown bound");
        std::set<std::string> skills;
        for(const auto&cooldown:e.world().skill_cooldowns())check(release.skills&&skills.insert(cooldown.skill()).second&&cooldown.ready_tick()<=e.world().tick()+1200&&std::any_of(release.skills->entries.begin(),release.skills->entries.end(),[&](const auto&s){return s.id==cooldown.skill();}),"skill cooldown identity");
        for(const auto&actor:e.world().entities()){
          check(actor.cast_skill().empty()||(!actor.npc()&&actor.health()&&release.skills&&actor.cast_start()<=e.world().tick()&&actor.cast_end()>actor.cast_start()&&actor.cast_end()-actor.cast_start()<=200&&actor.cast_target()&&std::any_of(release.skills->entries.begin(),release.skills->entries.end(),[&](const auto&s){return s.id==actor.cast_skill();})),"invalid cast state");
          auto profiles=release.combat_animation?release.combat_animation->profiles.size():0;
          check(actor.npc()?(!actor.combat_style()&&!actor.strike_style()):profiles?(actor.combat_style()>=1&&actor.combat_style()<=profiles&&actor.strike_style()<=profiles&&(!actor.strike_tick()||actor.strike_style())):(!actor.combat_style()&&!actor.strike_style()),"invalid combat style");
          check(!actor.strike_moving()||(!actor.npc()&&release.combat_animation&&!release.combat_animation->upper_nodes.empty()&&actor.strike_tick()),"invalid moving strike");
          check(!actor.strike_sequence()||(!actor.npc()&&actor.strike_tick()),"strike request identity");
          check(!actor.sitting()||(release.rest&&!actor.npc()&&actor.health()),"invalid rest state");
          check(actor.appearance_size()<=16&&(!actor.npc()||actor.appearance_size()==0),"appearance count");
          // PQ-272 (D-179): only a templated NPC (one with a looks key) carries
          // a drawn scale, in percent; 0 means 100.
          check(!actor.scale()||(actor.npc()&&!actor.looks().empty()&&actor.scale()<=1000),"npc scale");
          std::set<uint32_t> slots;
          for(auto key:actor.appearance())check(key>0&&key<=release.appearance.size()&&slots.insert(release.appearance[key-1].slot).second,"appearance key/slot");
        }
        // PQ-186: each trace names an NPC of this snapshot once, with an engine
        // behavior word (lower-case letters and '_', at most 16 bytes).
        check(e.world().traces_size()<=64,"npc trace bound");
        std::set<uint64_t> traced;
        for(const auto&trace:e.world().traces()){
          bool listed=std::any_of(e.world().entities().begin(),e.world().entities().end(),[&](const auto&a){return a.id()==trace.entity()&&a.npc();});
          bool word=trace.state().size()<=16&&std::all_of(trace.state().begin(),trace.state().end(),[](char c){return (c>='a'&&c<='z')||c=='_';});
          check(listed&&word&&traced.insert(trace.entity()).second,"npc trace identity");
        }
        check(e.world().has_stats()==release.equipment_stats,"stats capability");
        if(e.world().has_stats()) {
          const auto &s=e.world().stats();
          check(s.equipment_revision()<=INT64_MAX&&s.attack()<=10000&&s.defense()<=10000&&std::isfinite(s.accuracy())&&std::isfinite(s.evasion())&&s.accuracy()>=.000001f&&s.accuracy()<=1000000&&s.evasion()>=.000001f&&s.evasion()<=1000000&&s.max_health()>=1&&s.max_health()<=32767&&s.max_resource()>=1&&s.max_resource()<=32767&&s.max_health()==e.world().max_health()&&s.max_resource()==e.world().max_resource()&&s.attributes_size()==5&&s.carry_limit()<=4590000,"derived stats bounds");
          for(auto a:s.attributes())check(a<=4335,"derived attribute");
          for(const auto &a:e.world().entities())if(a.id()==e.world().self())check(a.health()<=s.max_health()&&a.resource()<=s.max_resource(),"derived vitals");
        }
        if (!session) {
          session = e.world().session();
          if(release.protocol>=6){Envelope q;q.mutable_admin_request()->set_session(session);q.mutable_admin_request()->set_operation("registry");t.send(q);}
          if(release.inventory) { Envelope q; q.mutable_bag_request(); t.send(q); }
          if(release.friends) {Envelope q;q.mutable_friend_request();t.send(q);}
          pending.clear();
          seq = 0;
          state.world.Clear();
          state.previous.Clear();
          state.npc_states.clear();
        }
        check(e.world().session() == session,
              "session changed without baseline");
        if (state.world.self() != e.world().self()) {
          pending.clear();
          state.previous.Clear();
          state.respawn.clear();
          state.combat.clear();
          state.combat_damage = 0;
          dx = dz = 0;
          turbo = false;
        }
        if (state.world.self() == e.world().self())
          state.previous = state.world;
        state.world = e.world();
        state.received = now();
        for(const auto&trace:state.world.traces())state.npc_states[trace.entity()]=trace.state();
        std::erase_if(state.npc_states,[&](const auto&entry){
          return std::none_of(state.world.entities().begin(),state.world.entities().end(),[&](const auto&a){return a.id()==entry.first;});});
        for (auto &actor : state.world.entities())
          if (actor.id() == state.world.self()) {
            while (!pending.empty() && pending.front().seq() <= actor.ack())
              pending.pop_front();
            speed = actor.health() ? state.world.speed() / 3.f : 0.f;
            V predicted{actor.x(), actor.y(), actor.z()};
            for (auto &m : pending) {
              float n = std::max(1.f, std::sqrt(m.x() * m.x() + m.z() * m.z()));
              if (release.movement) {
                if (speed > 0) {
                  float multiplier=release.exploration && m.turbo() && state.world.turbo_allowed() &&
                    m.entity()==state.world.self() && m.permission_generation()==state.world.permission_generation()
                    ? release.exploration->multiplier : 1.f;
                  predicted = advance(scene.collision, predicted, m.x(), m.z(),
                                      m.mode(), *release.movement,multiplier);
                }
              } else
                predicted = walk(scene.collision, predicted, m.x() / n * speed,
                                 m.z() / n * speed);
            }
            if (std::abs(predicted[0] - state.predicted[0]) +
                    std::abs(predicted[2] - state.predicted[2]) >
                .001)
              ++state.corrections;
            state.predicted = predicted;
          }
        state.status =
            "ENTER CHAT | F12 RECONNECT";
      }
    }
    Envelope bye;
    bye.mutable_logout();
    t.send(bye);
    double until = now() + 3;
    while (now() < until) {
      if (t.available() && t.receive().has_logged_out())
        break;
    }
  } catch (const std::exception &e) {
    std::lock_guard lock(mutex);
    state.connected = false;
    state.status = (state.disconnect.empty() ? std::string(e.what()) : state.disconnect) + " | F12 RECONNECT";
  }
}
} // namespace n3e
