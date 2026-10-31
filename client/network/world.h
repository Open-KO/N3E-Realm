#pragma once
#include "assets/assets.h"
#include "wire.pb.h"
#include <atomic>
#include <deque>
#include <mutex>
#include <thread>
#include <map>
namespace n3e {
V walk(const std::vector<V> &, V, float, float);
V advance(const std::vector<V> &, V, float, float, uint32_t, MovementConfig, float multiplier = 1);
// The same solvers over a package's collision, gathering what each move can reach.
V walk(const Collision &, V, float, float);
V advance(const Collision &, V, float, float, uint32_t, MovementConfig, float multiplier = 1);
struct WorldState {
  struct ItemResult {uint64_t sequence;bool storage;std::string request,status;};
  bool connected = false;
  std::string status = "Connecting", chat, combat, respawn, loot_status, bag_status;
  // The server marked the last chat line as an operator's (PQ-178).
  bool chat_operator = false;
  Registry registry;
  AdminResult admin;
  LootPage loot;
  ClaimResult claim;uint64_t claim_responses=0;
  BagState bag;
  std::deque<std::pair<std::string,std::string>> bag_results;
  std::deque<ItemResult> item_results;
  uint64_t item_result_sequence=0;
  void item_result(bool storage,const std::string&request,const std::string&status){
    if(request.empty())return;
    item_results.push_back({++item_result_sequence,storage,request,status});
    if(item_results.size()>32)item_results.pop_front();
  }
  StorageState storage;
  FriendResult friends;FriendPresence friend_presence;
  std::string friend_status;uint64_t friend_responses=0;
  PartyState party;std::string party_status;uint64_t party_responses=0;
  std::string storage_status,storage_auth_status;
  uint64_t storage_authorized=0,storage_auth_responses=0;
  uint64_t storage_responses=0;
  Characters characters;
  World world, previous;
  // PQ-186: the last server AI state reported for each traced NPC still in view
  // (World.traces, sent only to a session the server leases server.inspect).
  // Kept after reports stop, as KO keeps the NPC byte +0x7c0; dropped when the
  // NPC leaves the snapshot or the session changes.
  std::map<uint64_t,std::string> npc_states;
  V predicted{};
  uint32_t combat_damage = 0;
  uint64_t corrections = 0, action_result_seq = 0, bag_responses = 0;
  // PQ-469 (D-235): every ActionResult received, in order (the newest 32), so a
  // frame that polls several still sees each; `action_outcome_count` numbers
  // them. The client matches `seq` against the actions it sent itself.
  struct ActionOutcome {uint64_t number, seq; std::string status;};
  std::deque<ActionOutcome> action_outcomes;
  uint64_t action_outcome_count = 0;
  uint64_t coin_revision = 0;
  double received = 0;
  // PQ-405 (D-208): server refusals received, and the request the last one named.
  uint64_t refusals = 0;
  uint32_t refused_request = 0;
  // PQ-406 (D-209): the last chat, private message, rest or admin refusal, shown
  // in the world on the HUD's message line, and how many have arrived (so the
  // same text again still counts as new).
  std::string notice;
  uint64_t notices = 0;
};
// PQ-405 (D-208): show one server refusal. The general status line always takes
// its detail; once a session exists, only the feature whose request it names in
// Error.request (that request's Envelope field number) takes it too. A movement,
// chat, rest or admin refusal, or one naming no request, reaches no feature line.
// PQ-406 (D-209): a chat, private message, rest or admin refusal becomes the
// world's notice instead; a movement refusal, or one naming no request or an
// unknown one, does not.
inline void refusal(WorldState &s, const Release &r, bool session, const Error &e) {
  ++s.refusals;
  s.refused_request = e.request();
  s.status = e.detail();
  if (!session) {
    s.status += " | F12 RECONNECT";
    return;
  }
  switch (e.request()) {
  case Envelope::kBagRequestFieldNumber:
    if (r.inventory) s.bag_status = e.detail();
    break;
  case Envelope::kStorageAuthRequestFieldNumber:
    if (r.storage_auth) s.storage_auth_status = e.detail();
    [[fallthrough]];
  case Envelope::kStorageRequestFieldNumber:
    if (r.storage) s.storage_status = e.detail();
    break;
  case Envelope::kFriendRequestFieldNumber:
  case Envelope::kFriendPresenceQueryFieldNumber:
    if (r.friends) s.friend_status = e.detail();
    break;
  case Envelope::kPartyRequestFieldNumber:
    if (r.party) s.party_status = e.detail();
    break;
  case Envelope::kChatFieldNumber:
  case Envelope::kPrivateMessageFieldNumber:
  case Envelope::kRestFieldNumber:
  case Envelope::kAdminRequestFieldNumber:
    s.notice = e.detail();
    ++s.notices;
    break;
  default:
    break;
  }
}
class WorldClient {
  Release release;
  Scene scene;
  std::string endpoint, ca;
  std::mutex mutex;
  WorldState state;
  std::deque<Envelope> outgoing;
  float dx = 0, dz = 0;
  uint32_t mode = 0;
  bool turbo = false;
  std::jthread worker;
  void run(std::stop_token);

public:
  WorldClient(const Release &, const Scene &, std::string, std::string);
  ~WorldClient();
  WorldState poll();
  void send(Envelope);
  void direction(float, float, uint32_t = 0, bool = false);
};
} // namespace n3e
