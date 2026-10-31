#include "wire.pb.h"
#include <arpa/inet.h>
#include <csignal>
#include <fstream>
#include <iostream>
#include <limits>
#include <openssl/err.h>
#include <openssl/ssl.h>
#include <stdexcept>
#include <sys/socket.h>
#include <unistd.h>
using n3e::Envelope;
void check(bool v, const char *m) {
  if (!v)
    throw std::runtime_error(m);
}
std::string bytes(const Envelope &e) { return e.SerializeAsString(); }
std::string frame(const Envelope &e) {
  auto b = bytes(e);
  uint32_t n = htonl(b.size());
  return std::string((char *)&n, 4) + b;
}
void write_all(SSL *s, const std::string &b, bool fragment = false) {
  size_t o = 0;
  while (o < b.size()) {
    int n = SSL_write(s, b.data() + o, fragment ? 1 : b.size() - o);
    check(n > 0, "TLS write");
    o += n;
  }
}
void read_all(SSL *s, char *p, size_t n) {
  while (n) {
    int k = SSL_read(s, p, n);
    check(k > 0, "TLS read");
    p += k;
    n -= k;
  }
}
Envelope receive(SSL *s) {
  uint32_t n;
  read_all(s, (char *)&n, 4);
  n = ntohl(n);
  check(n > 0 && n <= 65536, "frame bound");
  std::string b(n, 0);
  read_all(s, b.data(), n);
  Envelope e;
  check(e.ParseFromString(b), "decode");
  return e;
}
Envelope golden(bool optional) {
  Envelope e;
  auto *i = e.mutable_input();
  i->set_id(std::numeric_limits<uint64_t>::max());
  i->set_text("雪🙂");
  if (optional)
    i->set_optional_id(0);
  return e;
}
int main(int argc, char **argv) {
  std::signal(SIGPIPE, SIG_IGN);
  try {
    if (argc == 3 && std::string(argv[1]) == "--golden") {
      for (bool o : {false, true}) {
        std::ofstream f(std::string(argv[2]) +
                            (o ? "-present.bin" : "-absent.bin"),
                        std::ios::binary);
        auto b = bytes(golden(o));
        f.write(b.data(), b.size());
      }
      {Envelope e;auto*w=e.mutable_world();w->set_self(7);auto*a=w->add_entities();a->set_id(7);a->set_strike_tick(100);a->set_strike_sequence(129);auto*v=w->add_events();v->set_sequence(1);v->set_tick(100);v->set_actor(7);v->set_target(8);v->set_kind(2);v->set_style(2);v->set_request_sequence(129);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-strike.bin",std::ios::binary).write(b.data(),b.size());}
      // Wire30 (PQ-249): a templated NPC's looks key and maximum health.
      {Envelope e;auto*w=e.mutable_world();w->set_self(7);auto*a=w->add_entities();a->set_id(129);a->set_name("demo:creature/brute");a->set_health(6);a->set_npc(true);a->set_looks("demo:looks/brute");a->set_max_health(100000);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-template.bin",std::ios::binary).write(b.data(),b.size());}
      Envelope movement;
      auto *m = movement.mutable_move();
      m->set_session(63);
      m->set_seq(127);
      m->set_x(-.5f);
      m->set_z(1.f);
      std::ofstream f(std::string(argv[2]) + "-move.bin", std::ios::binary);
      auto b = bytes(movement);
      m->set_mode(1);
      auto mode_bytes = bytes(movement);
      std::ofstream(std::string(argv[2]) + "-move-mode.bin", std::ios::binary)
          .write(mode_bytes.data(), mode_bytes.size());
      f.write(b.data(), b.size());
      Envelope action;
      auto *a = action.mutable_action();
      a->set_session(63);
      a->set_seq(127);
      a->set_target(9223372036854775807ULL);
      a->set_action("fixture:action/strike");
      std::ofstream af(std::string(argv[2]) + "-action.bin", std::ios::binary);
      auto ab = bytes(action);
      af.write(ab.data(), ab.size());
      Envelope respawn;
      auto *request = respawn.mutable_respawn();
      request->set_session(63); request->set_seq(127);
      request->set_entity(9223372036854775807ULL);
      auto rb = bytes(respawn);
      std::ofstream(std::string(argv[2]) + "-respawn.bin", std::ios::binary).write(rb.data(), rb.size());
      Envelope life;
      auto *world = life.mutable_world();
      world->set_tick(128); world->set_session(63); world->set_self(127);
      auto *entity = world->add_entities();
      entity->set_id(127); entity->set_respawn_tick(129); entity->set_life_state(n3e::DEAD_READY);
      auto lb = bytes(life);
      std::ofstream(std::string(argv[2]) + "-life.bin", std::ios::binary).write(lb.data(), lb.size());
      Envelope settlement;
      auto *sr = settlement.mutable_settlement_result();
      sr->set_encounter(127); sr->set_status("entitled"); sr->set_awarded_xp(6);
      sr->set_xp(51); sr->set_curve_xp(66); sr->set_level(3); sr->set_revision(1);
      auto sb = bytes(settlement);
      std::ofstream(std::string(argv[2]) + "-settlement.bin", std::ios::binary).write(sb.data(), sb.size());
      { n3e::Envelope private_request;
        private_request.mutable_private_message()->set_recipient("Peer");
        private_request.mutable_private_message()->set_text("secret");
        const auto bytes = private_request.SerializeAsString();
        std::ofstream(std::string(argv[2])+"-private.bin",std::ios::binary).write(bytes.data(),bytes.size());
      }
      { Envelope e; auto*q=e.mutable_bag_request();q->set_operation(1);q->set_request("move-1");q->set_expected_revision(127);q->set_destination(41);q->set_instance(9223372036854775807ULL);
        auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-bag.bin",std::ios::binary).write(b.data(),b.size()); }
      { Envelope e;auto*r=e.mutable_bag_result();r->set_request("move-1");r->set_status("committed");auto*s=r->mutable_state();s->set_revision(128);s->set_capacity(2);s->set_currency("fixture:currency/coin");s->set_coins(100);s->add_slots();auto*i=s->add_slots();i->set_instance(9223372036854775807ULL);i->set_item("fixture:item/blade");i->set_quantity(1);i->set_durability(80);
        auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-bag-state.bin",std::ios::binary).write(b.data(),b.size()); }
      { Envelope e;auto*q=e.mutable_bag_request();q->set_operation(2);q->set_request("buy-1");q->set_expected_revision(127);q->set_source(2);q->set_service("fixture:shop/supplies");q->set_item("fixture:item/potion");q->set_quantity(3);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-commerce.bin",std::ios::binary).write(b.data(),b.size()); }
      Envelope claim;
      auto *c=claim.mutable_claim(); c->set_session(63);c->set_seq(127);c->set_entity(128);
      c->set_operation(9223372036854775807ULL);c->set_encounter(129);c->set_item("fixture:item/token");c->set_quantity(1);
      auto cb=bytes(claim);
      std::ofstream(std::string(argv[2])+"-claim.bin",std::ios::binary).write(cb.data(),cb.size());
      {Envelope e;auto*q=e.mutable_storage_request();q->set_operation(2);q->set_request("bank-1");q->set_bag_revision(128);q->set_storage_revision(129);q->set_service("fixture:bank/main");q->set_source(191);q->set_destination(63);q->set_instance(9223372036854775807ULL);q->set_quantity(9999);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-storage.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_storage_result();r->set_request("bank-1");r->set_status("committed");auto*b=r->mutable_bag();b->set_revision(130);b->set_capacity(1);b->set_currency("fixture:currency/coin");b->set_coins(17);b->add_slots();auto*s=r->mutable_storage();s->set_revision(131);s->set_capacity(2);s->set_coins(2100000000);auto*i=s->add_slots();i->set_instance(9223372036854775807ULL);i->set_item("fixture:item/blade");i->set_quantity(1);i->set_durability(80);s->add_slots();auto bytes=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-storage-state.bin",std::ios::binary).write(bytes.data(),bytes.size());}
      {Envelope e;auto*q=e.mutable_storage_auth_request();q->set_operation(2);q->set_request("credential-1");q->set_service("fixture:bank/main");q->set_password("Original_123");q->set_replacement("Replacement_123");auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-storage-auth.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_storage_auth_result();r->set_request("credential-1");r->set_status("changed");r->set_revision(128);r->set_authorized_revision(129);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-storage-auth-state.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*q=e.mutable_friend_request();q->set_operation(1);q->set_request("friend-1");q->set_expected_revision(129);q->set_name("Peer");auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-friends.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_friend_result();r->set_request("friend-1");r->set_status("committed");r->set_revision(130);r->set_capacity(24);auto*f=r->add_entries();f->set_slot(23);f->set_character(9223372036854775807ULL);f->set_name("Peer");auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-friends-state.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_friend_presence();r->set_sequence(63);r->set_tick(127);auto*f=r->add_entries();f->set_name("Peer");f->set_character(9223372036854775807ULL);f->set_entity(128);f->set_online(true);f->set_in_party(true);f=r->add_entries();f->set_name("Missing");auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-friends-presence.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*s=e.mutable_world()->mutable_stats();s->set_attack(129);s->set_defense(17);s->set_accuracy(1.625f);s->set_evasion(2.25f);s->set_max_health(32767);s->set_max_resource(1024);s->set_carry_limit(3050);s->set_equipment_revision(129);for(auto a:{60,70,80,90,100})s->add_attributes(a);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-stats.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_bag_result();r->set_request("equip-1");r->set_status("committed");auto*s=r->mutable_state();s->set_revision(129);s->set_capacity(1);s->set_currency("fixture:currency/coin");s->set_coins(100);s->add_slots();auto*i=s->add_equipment();i->set_instance(9223372036854775807ULL);i->set_item("fixture:item/blade");i->set_quantity(1);i->set_durability(80);s->add_equipment();auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-equipment.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*q=e.mutable_party_request();q->set_sequence(63);q->set_operation(2);q->set_invitation(128);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-party.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_party_state();r->set_tick(127);r->set_group(129);r->set_leader(9223372036854775807ULL);auto*m=r->add_members();m->set_slot(7);m->set_character(9223372036854775807ULL);m->set_entity(128);m->set_name("Peer");m->set_level(30);m->set_health(70);m->set_max_health(100);m->set_resource(4);m->set_max_resource(20);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-party-state.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_party_state();r->set_tick(130);r->set_invitation(129);r->set_inviter(9223372036854775807ULL);r->set_inviter_name("Peer");auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-party-invitation.bin",std::ios::binary).write(b.data(),b.size());}
      {Envelope e;auto*r=e.mutable_party_result();r->set_sequence(63);r->set_status("joined");auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-party-result.bin",std::ios::binary).write(b.data(),b.size());}
      // PQ-405 (D-208): a refusal names the request it answers (32 BagRequest).
      {Envelope e;auto*r=e.mutable_error();r->set_code(n3e::Error::RATE_LIMITED);r->set_detail("inventory rate limit");r->set_request(Envelope::kBagRequestFieldNumber);auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+"-error.bin",std::ios::binary).write(b.data(),b.size());}
      // specs/02-auth-sessions.md: the Discord and session logins and their result.
      {std::string token;for(int i=0;i<32;++i)token.push_back(char(i));
       auto write=[&](const Envelope&e,const char*name){auto b=e.SerializeAsString();std::ofstream(std::string(argv[2])+name,std::ios::binary).write(b.data(),b.size());};
       Envelope d;auto*l=d.mutable_discord_login();l->set_code("c0de");l->set_code_verifier("verifier-0123456789abcdefghijklmnopqrstuvwxyzAB");l->set_redirect_uri("http://127.0.0.1:49152/callback");l->set_client_label("host");write(d,"-discord-login.bin");
       Envelope s;s.mutable_session_login()->set_token(token);s.mutable_session_login()->set_client_label("host");write(s,"-session-login.bin");
       Envelope r;auto*x=r.mutable_login_result();x->set_token(token);x->set_expires_at_unix(1795996800);x->set_discord_id("80351110224678912");x->set_discord_name("Nelly");write(r,"-login-result.bin");
       Envelope c;auto*a=c.mutable_characters()->add_characters();a->set_id(129);a->set_name("Nelly");a->set_level(30);a=c.mutable_characters()->add_characters();a->set_id(7);a->set_name("Peer");a->set_level(1);write(c,"-characters.bin");}
      Envelope admin;auto*q=admin.mutable_admin_request();q->set_session(63);q->set_id("request-1");q->set_operation("publish");q->set_expected(127);q->set_base(std::string(64,'a'));auto*v=q->add_patch();v->set_key("fixture:lighting.intensity");v->set_value(.5f);q->set_reason("golden");auto admin_bytes=bytes(admin);std::ofstream(std::string(argv[2])+"-admin.bin",std::ios::binary).write(admin_bytes.data(),admin_bytes.size());
      return 0;
    }
    check(argc == 7, "peer port CA hostname mode game content-hash");
    std::string mode = argv[4];
    auto *ctx = SSL_CTX_new(TLS_client_method());
    check(ctx, "SSL context");
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, nullptr);
    check(SSL_CTX_load_verify_locations(ctx, argv[2], nullptr) == 1, "CA load");
    auto *s = SSL_new(ctx);
    SSL_set_tlsext_host_name(s, argv[3]);
    check(SSL_set1_host(s, argv[3]) == 1, "hostname policy");
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    timeval tv{4, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(std::stoi(argv[1]));
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    check(connect(fd, (sockaddr *)&a, sizeof a) == 0, "connect");
    SSL_set_fd(s, fd);
    int connected = SSL_connect(s);
    if (mode == "reject-tls") {
      check(connected != 1, "invalid TLS accepted");
      std::cout << "PASS TLS rejection\n";
    } else {
      check(connected == 1 && SSL_get_verify_result(s) == X509_V_OK,
            "TLS verify");
      Envelope h;
      auto *hs = h.mutable_handshake();
      hs->set_version(mode == "version" ? 2 : 1);
      hs->set_game(argv[5]);
      hs->set_content(mode == "content" ? "wrong" : argv[6]);
      write_all(s, frame(h), true);
      auto r = receive(s);
      if (mode == "version" || mode == "content") {
        check(r.has_error() &&
                  r.error().code() == (mode == "version" ? n3e::Error::VERSION
                                                         : n3e::Error::CONTENT),
              "typed negotiation rejection");
      } else {
        check(r.has_snapshot() && r.snapshot().tick() == 0, "handshake reply");
        auto x = golden(false), y = golden(true);
        write_all(s, frame(x) + frame(y));
        check(receive(s).error().code() == n3e::Error::UNAUTHENTICATED &&
                  receive(s).error().code() == n3e::Error::UNAUTHENTICATED,
              "diagnostic input must not bypass authentication");
      }
      std::cout << "PASS " << mode << "\n";
    }
    SSL_free(s);
    close(fd);
    SSL_CTX_free(ctx);
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
