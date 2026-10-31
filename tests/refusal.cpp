// PQ-405 (D-208): the client shows a server refusal on the feature whose request
// it names (Error.request) and on no other feature line. Driven with the client's
// own routing (client/network/world.h) on parsed wire bytes. PQ-406 (D-209): a
// chat, private message, rest or admin refusal is also the world's notice (the
// HUD's message line); no other refusal is.
#include "network/world.h"
#include <iostream>
#include <stdexcept>
#include <string>
namespace {
using namespace n3e;
void check(bool ok, const std::string &what) {
  if (!ok) throw std::runtime_error(what);
}
// An Error as the server sends it: encoded, then parsed as the client parses it.
Error wire(int code, uint32_t request, const std::string &detail) {
  Envelope sent;
  auto *e = sent.mutable_error();
  e->set_code(Error::Code(code));
  e->set_request(request);
  e->set_detail(detail);
  Envelope got;
  check(got.ParseFromString(sent.SerializeAsString()) && got.has_error(), "decode");
  return got.error();
}
WorldState before() {
  WorldState s;
  s.status = "ENTER CHAT | F12 RECONNECT";
  s.bag_status = "committed";
  s.storage_status = "committed";
  s.storage_auth_status = "unlocked";
  s.friend_status = "committed";
  s.party_status = "joined";
  return s;
}
struct Lines {
  std::string bag, storage, auth, friends, party;
  bool operator==(const Lines &) const = default;
};
Lines lines(const WorldState &s) {
  return {s.bag_status, s.storage_status, s.storage_auth_status, s.friend_status, s.party_status};
}
}  // namespace
int main() {
  Release all;
  all.inventory.emplace();
  all.storage.emplace();
  all.storage_auth = true;
  all.friends.emplace();
  all.party.emplace();
  const Lines unchanged = lines(before());
  // A movement refusal, either kind the server sends (code 4 one ahead held,
  // code 3 stale), a request-less one and those of features without a status
  // line reach the general line only.
  for (auto [code, request, detail] : std::initializer_list<std::tuple<int, uint32_t, const char *>>{
           {4, Envelope::kMoveFieldNumber, "one movement per tick"},
           {3, Envelope::kMoveFieldNumber, "invalid/stale movement or session"},
           {4, 0, "session rate limit"},
           {4, Envelope::kChatFieldNumber, "chat length/rate"},
           {4, Envelope::kPrivateMessageFieldNumber, "private message recipient unavailable"},
           {8, Envelope::kRestFieldNumber, "busy"},
           {4, Envelope::kAdminRequestFieldNumber, "admin queue full"},
           {4, 999, "a request this client does not know"}}) {
    auto s = before();
    refusal(s, all, true, wire(code, request, detail));
    check(lines(s) == unchanged, std::string("feature lines took a refusal: ") + detail);
    check(s.status == detail && s.refusals == 1 && s.refused_request == request, "general line");
    const bool in_world = request == Envelope::kChatFieldNumber || request == Envelope::kPrivateMessageFieldNumber ||
                          request == Envelope::kRestFieldNumber || request == Envelope::kAdminRequestFieldNumber;
    check(in_world ? s.notice == detail && s.notices == 1 : s.notice.empty() && s.notices == 0,
          std::string("world notice: ") + detail);
    // The same refusal again is a new notice: the count moves, the text stays.
    refusal(s, all, true, wire(code, request, detail));
    check(in_world ? s.notice == detail && s.notices == 2 : s.notice.empty() && s.notices == 0,
          std::string("repeated notice: ") + detail);
  }
  // A later in-world refusal replaces the notice; a movement refusal after it
  // leaves it.
  {
    auto s = before();
    refusal(s, all, true, wire(4, Envelope::kChatFieldNumber, "chat length/rate"));
    refusal(s, all, true, wire(4, Envelope::kPrivateMessageFieldNumber, "private message recipient unavailable"));
    refusal(s, all, true, wire(4, Envelope::kMoveFieldNumber, "one movement per tick"));
    check(s.notice == "private message recipient unavailable" && s.notices == 2 && lines(s) == unchanged &&
              s.status == "one movement per tick",
          "notice order");
  }
  // A feature's own refusal reaches that feature's line and no other.
  auto only = [&](uint32_t request, auto edit) {
    auto s = before();
    refusal(s, all, true, wire(4, request, "refused"));
    auto want = unchanged;
    edit(want);
    check(lines(s) == want && s.status == "refused" && s.notice.empty() && !s.notices,
          "feature refusal " + std::to_string(request));
  };
  only(Envelope::kBagRequestFieldNumber, [](Lines &l) { l.bag = "refused"; });
  only(Envelope::kStorageRequestFieldNumber, [](Lines &l) { l.storage = "refused"; });
  only(Envelope::kStorageAuthRequestFieldNumber, [](Lines &l) { l.storage = l.auth = "refused"; });
  only(Envelope::kFriendRequestFieldNumber, [](Lines &l) { l.friends = "refused"; });
  only(Envelope::kFriendPresenceQueryFieldNumber, [](Lines &l) { l.friends = "refused"; });
  only(Envelope::kPartyRequestFieldNumber, [](Lines &l) { l.party = "refused"; });
  // A package without the feature draws no such line: nothing is written.
  {
    Release none;
    auto s = before();
    for (uint32_t request : {Envelope::kBagRequestFieldNumber, Envelope::kStorageRequestFieldNumber,
                             Envelope::kStorageAuthRequestFieldNumber, Envelope::kFriendRequestFieldNumber,
                             Envelope::kPartyRequestFieldNumber})
      refusal(s, none, true, wire(4, request, "refused"));
    check(lines(s) == unchanged && s.refusals == 5, "feature absent from the package");
  }
  // Before a session (login, selection) a refusal is a general one, with the
  // reconnect hint, whatever it names.
  {
    auto s = before();
    refusal(s, all, false, wire(4, Envelope::kBagRequestFieldNumber, "login rate limit"));
    refusal(s, all, false, wire(4, Envelope::kChatFieldNumber, "login rate limit"));
    check(lines(s) == unchanged && s.status == "login rate limit | F12 RECONNECT" && s.notice.empty() && !s.notices,
          "pre-session refusal");
  }
  // An Error from a server that does not name the request (field 3 absent) is a
  // general refusal: request 0.
  {
    Envelope old;
    old.mutable_error()->set_code(Error::RATE_LIMITED);
    old.mutable_error()->set_detail("inventory rate limit");
    Envelope got;
    check(got.ParseFromString(old.SerializeAsString()), "decode old");
    auto s = before();
    refusal(s, all, true, got.error());
    check(lines(s) == unchanged && s.refused_request == 0 && s.notice.empty(), "request-less refusal");
  }
  std::cout << "PASS client refusal routing: movement and request-less refusals leave every feature line, a feature's own refusal reaches only that line, and chat, private message, rest and admin refusals reach only the world notice\n";
}
