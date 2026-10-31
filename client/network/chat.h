#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace n3e {
// Parse before constructing an envelope. Malformed or unknown commands must not
// fall through to local chat and reveal text intended for a private recipient.
struct ChatInput {
  enum Kind { invalid, local, whisper } kind = invalid;
  std::string recipient, text;
};
inline ChatInput parse_chat(std::string_view input) {
  if (input.empty()) return {};
  if (input.front() != '/') return {ChatInput::local, {}, std::string(input)};
  if (input.starts_with("//")) return {ChatInput::local, {}, std::string(input.substr(1))};
  const auto separator = input.find_first_of(" \t");
  const auto command = input.substr(0, separator);
  if (command != "/w" && command != "/whisper") return {};
  if (separator == std::string_view::npos) return {};
  const auto first = input.find_first_not_of(" \t", separator);
  if (first == std::string_view::npos) return {};
  const auto last = input.find_first_of(" \t", first);
  if (last == std::string_view::npos) return {};
  const auto text = input.find_first_not_of(" \t", last);
  if (text == std::string_view::npos) return {};
  return {ChatInput::whisper, std::string(input.substr(first, last-first)), std::string(input.substr(text))};
}
// PQ-178: the colour of a received chat line. The server marks a line whose
// sender holds a current server.inspect lease (Chat.from_operator); the package
// may style marked lines (input table names.operator_chat, 0xRRGGBB). The client
// never decides who is an operator: an unmarked line, or a package without the
// style, keeps `base`. A marked line keeps base's top (alpha) byte.
inline uint32_t chat_line_color(bool from_operator, const std::optional<uint32_t> &operator_color, uint32_t base) {
  return from_operator && operator_color ? (base & 0xff000000u) | (*operator_color & 0xffffffu) : base;
}
} // namespace n3e
