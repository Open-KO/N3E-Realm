#pragma once
// PQ-466 (D-234): the client's own test of a skill's start limit before it
// sends a cast, as 1298's skill start 005819e0 calls 00583780 and, out of
// range, posts text 0xfa9 formatted with the skill's name and casts nothing.
// A hint only: the server checks the same limit on its own positions
// (D-232) and refuses `out_of_range` whatever the client decided.
#include "assets/assets.h"
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <iterator>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace n3e {

// The start limit (D-232): the skill's range, both actors' radii (the
// package's melee radii, 0 without melee rules) and the policy's `start`.
inline float skill_start_limit(const Skill &skill, const SkillReach &reach, float radii) {
  return skill.range + radii + reach.start;
}

// True when `target` lies beyond the start limit from `self`, in 3-D, as
// the server's acceptance measures it (inclusive at the limit).
inline bool skill_too_far(const V &self, const V &target, float limit) {
  const float dx = target[0] - self[0], dy = target[1] - self[1], dz = target[2] - self[2];
  return std::sqrt(dx * dx + dy * dy + dz * dz) > limit;
}

// The package's notice with its one `%s`, if any, replaced by the skill's
// label (1298's 0067429f formats the text with the row's name).
inline std::string skill_notice(const std::string &notice, const std::string &label) {
  std::string text = notice;
  if (const auto at = text.find("%s"); at != std::string::npos) text.replace(at, 2, label);
  return text;
}

// PQ-481 (D-245): why the client holds a skill press back. A held press
// sends nothing and posts nothing.
enum class SkillHold { none, no_target, unseen, dead, not_npc };

inline const char *skill_hold_name(SkillHold hold) {
  switch (hold) {
    case SkillHold::none: return "none";
    case SkillHold::no_target: return "no_target";
    case SkillHold::unseen: return "unseen";
    case SkillHold::dead: return "dead";
    case SkillHold::not_npc: return "not_npc";
  }
  return "none";
}

template <class Id>
struct SkillRecipient {
  Id id;  // the action's target, when `hold` is none
  SkillHold hold;
};

// PQ-481 (D-245): the actor a skill press goes to, or why the press is held
// back, as 1298's skill start 005819e0 chooses it. 1298 looks its target up
// with 006163d0(id, 0) (0 for an id below 0 or one it does not hold, with no
// state test) and dispatches on the row's target type (+0x5c). The package's
// target kinds are 1298's types: kind 1 (a player or self) is type 2, kind 2
// (an NPC) is type 7 (tools/assetc/ko_skills.py checks Moradon's rows so).
// 1298's hostility predicate 006164c0 maps onto "an NPC", as the server's
// target category does.
//  - Kind 1 (type 2, 00582b68-00582c1d): no target, or one the client does
//    not see, goes to the caster (00582b7b); a player the client sees goes
//    to that player whatever its health (00582bdf, after the range check);
//    an NPC goes to the caster (00582c16). The server refuses a dead player
//    `target_dead`, which posts no line (D-243), as Ebenezer drops it
//    (0046e94e).
//  - Kind 2 (type 7, 00582e95-00582ec3): no target holds the press, as do,
//    for a hinted press, a target the client does not see (006163d0 gives
//    0), one it sees dead (state 4 or 5, 00582ea3, 00582eac; PQ-479) and one
//    that is not an NPC (006164c0 at 00582ebc). An unchecked press with a
//    target is sent. 1298's exception for a row whose +0x38 is 113
//    (00582e0f-00582e89) has no n3e skill.
// A hint only: the server checks the target itself.
template <class Entities, class Id>
SkillRecipient<Id> skill_recipient(uint32_t target_kind, bool hint, const Entities &entities, Id self, Id target) {
  std::remove_reference_t<decltype(*std::begin(entities))> *seen = nullptr;
  if (target)
    for (const auto &e : entities)
      if (e.id() == target) seen = &e;
  if (target_kind == 1) return {seen && !seen->npc() ? target : self, SkillHold::none};
  if (!target) return {Id{}, SkillHold::no_target};
  if (!hint) return {target, SkillHold::none};
  if (!seen) return {target, SkillHold::unseen};
  if (!seen->health()) return {target, SkillHold::dead};
  if (!seen->npc()) return {target, SkillHold::not_npc};
  return {target, SkillHold::none};
}

// PQ-469 (D-235): the skills this client sent, by action sequence number, so
// that the server's `out_of_range` refusal of one (an ActionResult echoing
// that number) posts the policy's failed line, as 1298's fail receive
// 00586fa0 posts text 0xfa4 with the row's name on Ebenezer's -103. The
// server decides the refusal; the client only names which of its own
// requests it answered. A melee or ranged action never enters the record.
// PQ-479 (D-243): it also remembers whether the target was an NPC in the
// client's view when it sent the skill, and whether the server has answered
// the action yet. The server's first answer is its acceptance (`cast_pending`)
// or its refusal there; a refusal there posts the policy's refusal line for
// that status and target kind (N3K5), as 1298 posts its own text for the
// refusals it makes before it sends a cast (0057f7f0) and text 0xfa2 on
// Ebenezer's -100 for a casting phase (00586fa0). A refusal after the
// acceptance posts none of them (only `out_of_range` keeps its failed line).
struct SkillFailures {
  static constexpr size_t kept = 16;  // the newest sent skills remembered
  struct Sent {
    uint64_t seq;
    size_t index;  // the skill
    bool npc;  // the target was an NPC in the client's view
    bool answered = false;  // the server's first answer has been read
  };
  // A line to post for one sent skill: the failed line (`line` -1) or the
  // policy's refusal line `line`.
  struct Line {
    size_t skill;
    int line;
    bool operator==(const Line &o) const { return skill == o.skill && line == o.line; }
  };
  std::deque<Sent> sent;
  uint64_t seen = 0;  // the last ActionOutcome number read
  void send(uint64_t seq, size_t index, bool npc = false) {
    sent.push_back({seq, index, npc});
    while (sent.size() > kept) sent.pop_front();
  }
  // A new connection numbers its actions and outcomes from the start again.
  void reset() {
    sent.clear();
    seen = 0;
  }
  // The lines to post for the outcomes not read yet, oldest first; each sent
  // skill posts at most one line. `lines` are the policy's refusal lines.
  template <class Outcomes>
  std::vector<Line> refused(const Outcomes &outcomes, const std::vector<SkillRefusal> &lines = {}) {
    std::vector<Line> out;
    for (const auto &o : outcomes) {
      if (o.number <= seen) continue;
      seen = o.number;
      auto at = sent.begin();
      while (at != sent.end() && at->seq != o.seq) ++at;
      if (at == sent.end()) continue;
      int line = o.status == "out_of_range" ? -1 : -2;
      if (line == -2 && !at->answered)
        for (size_t i = 0; i < lines.size(); ++i)
          if (lines[i].status == o.status && (lines[i].target == 0 || (lines[i].target == 2) == at->npc)) {
            line = int(i);
            break;
          }
      at->answered = true;
      if (line == -2) continue;
      out.push_back({at->index, line});
      sent.erase(at);
    }
    return out;
  }
};

}  // namespace n3e
