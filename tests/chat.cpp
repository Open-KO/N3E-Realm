#include "network/chat.h"
#include "network/inventory.h"
#include "network/storage.h"
#include "network/friends.h"
#include "network/party.h"
#include <iostream>
#include <stdexcept>
int main() {
  using namespace n3e;
  for(const auto input:{"/invite","/kick ","/invite A B","/kick ../A","/invite Name!"})if(parse_party(input,20).kind!=PartyCommand::invalid)throw std::runtime_error("party command bounds");
  if(parse_party("/invite Peer",20).name!="Peer"||parse_party("/accept",20).kind!=PartyCommand::accept||parse_party("/leave",20).kind!=PartyCommand::leave||parse_party("/disband",20).kind!=PartyCommand::disband||parse_party("/partyblock",20).kind!=PartyCommand::block)throw std::runtime_error("party commands");
  for (const auto input : {"", "/w", "/w ", "/w Peer", "/w Peer ", "/whisper", "/W Peer secret", "/unknown secret"})
    if (parse_chat(input).kind != ChatInput::invalid) throw std::runtime_error("private intent leaked as local");
  for (const auto input : {"/w Peer secret", "/whisper Peer secret", "/w\tPeer\tsecret", "/w   Peer    secret"}) {
    const auto chat = parse_chat(input);
    if (chat.kind != ChatInput::whisper || chat.recipient != "Peer" || chat.text != "secret") throw std::runtime_error("private command parsing");
  }
  if (parse_chat("hello").kind != ChatInput::local || parse_chat("//w Peer secret").text != "/w Peer secret") throw std::runtime_error("local chat parsing");
  for(const auto input:{"/swap", "/swap 0 2", "/swap 1 65", "/swap 1 1", "/swap 1 2 extra", "/swap1 2", "/swap -1 2", "/swap 999999999999999999 2"})
    if(parse_bag(input).kind!=BagCommand::invalid) throw std::runtime_error("inventory command bounds");
  for(const auto input:{"/deposit", "/deposit 0 1 1", "/withdraw 193 1 1", "/bankmove 1 2 extra", "/bankcoins 2100000001", "/takecoins -1", "/deposit 1 1 10000"})if(parse_storage(input).kind!=StorageCommand::invalid)throw std::runtime_error("storage bounds");
  for(const auto input:{"/friend","/friend ","/friend A B","/unfriend ../A","/friend Name!"})if(parse_friend(input,20).kind!=FriendCommand::invalid)throw std::runtime_error("friend command bounds");
  if(parse_friend("/friend Peer",20).name!="Peer"||parse_friend("/unfriend Peer",20).kind!=FriendCommand::remove||parse_friend("/friends",20).kind!=FriendCommand::list||parse_friend("/friendretry",20).kind!=FriendCommand::retry)throw std::runtime_error("friend commands");
  auto deposit=parse_storage("/deposit 64 192 9999");if(deposit.kind!=StorageCommand::deposit||deposit.source!=63||deposit.destination!=191||deposit.quantity!=9999||parse_storage("/bankcoins 2100000000").quantity!=2100000000)throw std::runtime_error("storage command");
  auto swap=parse_bag("/swap  1  64");
  if(swap.kind!=BagCommand::swap || swap.source!=0 || swap.destination!=63 || parse_bag("/bag").kind!=BagCommand::list || parse_bag("/retry").kind!=BagCommand::retry || parse_bag("hello").kind!=BagCommand::none) throw std::runtime_error("inventory commands");
  for(const auto input:{"/buy", "/buy 1 0 1", "/buy 1 2 0", "/buy 65 2 1", "/buy 1 2 10000", "/sell 0 1", "/sell 1 2 extra"})
    if(parse_bag(input).kind!=BagCommand::invalid)throw std::runtime_error("commerce command bounds");
  auto buy=parse_bag("/buy 2 3 4");auto sell=parse_bag("/sell 4 5");
  if(buy.kind!=BagCommand::buy||buy.source!=2||buy.destination!=1||buy.quantity!=4||sell.kind!=BagCommand::sell||sell.source!=3||sell.quantity!=5||parse_bag("/shop").kind!=BagCommand::shop)throw std::runtime_error("commerce commands");
  for(const auto input:{"/repair", "/repair 0", "/repair 65", "/repair 1 extra", "/repairgear", "/repairgear 0", "/repairgear 65", "/repairgear1"})if(parse_bag(input).kind!=BagCommand::invalid)throw std::runtime_error("repair command bounds");
  if(parse_bag("/repairgear 1").kind!=BagCommand::repairgear)throw std::runtime_error("equipped repair command");
  auto repair=parse_bag("/repair  64");if(repair.kind!=BagCommand::repair||repair.source!=63)throw std::runtime_error("repair command");
  for(const auto input:{"/equip", "/equip 0 1", "/unequip 1 65", "/gearswap 1 1", "/equip 1 2 extra"})if(parse_bag(input).kind!=BagCommand::invalid)throw std::runtime_error("equipment command bounds");
  if(parse_bag("/equip 1 1").kind!=BagCommand::equip||parse_bag("/unequip 1 1").kind!=BagCommand::unequip||parse_bag("/gearswap 1 2").kind!=BagCommand::gearswap||parse_bag("/equipment").kind!=BagCommand::equipment)throw std::runtime_error("equipment commands");
  // PQ-178: only a line the server marked takes the package's operator colour;
  // without the package style a marked line keeps the chat text's colour.
  const std::optional<uint32_t> lavender = 0xcd9bffu;
  if (chat_line_color(false, lavender, 0xffffffu) != 0xffffffu || chat_line_color(true, std::nullopt, 0xffffffu) != 0xffffffu ||
      chat_line_color(false, std::nullopt, 0x123456u) != 0x123456u || chat_line_color(true, lavender, 0xffffffu) != 0xcd9bffu ||
      chat_line_color(true, lavender, 0xffffffffu) != 0xffcd9bffu || chat_line_color(false, lavender, 0xffffffffu) != 0xffffffffu)
    throw std::runtime_error("operator chat colour");
  std::cout << "PASS private command parser never broadcasts malformed/unknown intent; explicit literal escape; operator colour only on a server-marked line\n";
}
