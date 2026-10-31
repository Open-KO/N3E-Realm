#pragma once
// The test-harness boundary of the client (PQ-006).
//
// One source builds two clients. n3e-client, the player build, is compiled with
// N3E_HARNESS=0: it has no replay, smoke, capture or automatic-login mode and
// reads no N3E_TEST_* switch, and tests/player_build.py checks that none of
// those strings reach its binary. n3e-test-client (N3E_HARNESS=1) adds them for
// make test, make live, make live-ko and the developer session tools.
//
// The replays drive the same SDL event queue and the same viewer state a
// player's input reaches, so they live inside viewer() as fragments included
// only into the test build: client/harness/*.inc. Small hooks stay in place in
// viewer.cpp behind `#if N3E_HARNESS`.
//
// Game data never lives in the harness either: a replay that needs a package
// item or a warehouse password takes it from the suite that owns the fixture
// (N3E_TEST_ITEMS, N3E_TEST_STORAGE_PASSWORD, N3E_TEST_STORAGE_REPLACEMENT).
#ifndef N3E_HARNESS
#define N3E_HARNESS 0
#endif

#if N3E_HARNESS
#include <cstdlib>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>

namespace n3e::harness {

// A suite-supplied value the replay cannot run without.
inline const char *required(const char *name) {
  const char *value = std::getenv(name);
  if (!value || !*value)
    throw std::runtime_error(std::string("replay needs ") + name + " from its suite");
  return value;
}

// N3E_TEST_ITEMS="role=package:item/id;role=..." names the package items a replay
// uses by role (potion, mana_potion, blade, twohand, shield), so the client holds
// no game-specific item identifier.
inline const std::string &item(const std::string &role) {
  static const std::map<std::string, std::string> items = [] {
    std::map<std::string, std::string> parsed;
    std::stringstream in(required("N3E_TEST_ITEMS"));
    for (std::string pair; std::getline(in, pair, ';');) {
      auto equals = pair.find('=');
      if (equals == std::string::npos || equals == 0 || equals + 1 == pair.size())
        throw std::runtime_error("N3E_TEST_ITEMS expects role=id;role=id");
      parsed[pair.substr(0, equals)] = pair.substr(equals + 1);
    }
    return parsed;
  }();
  auto found = items.find(role);
  if (found == items.end())
    throw std::runtime_error("N3E_TEST_ITEMS names no " + role);
  return found->second;
}

} // namespace n3e::harness
#endif
