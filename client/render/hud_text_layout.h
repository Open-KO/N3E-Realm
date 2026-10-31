#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <string_view>

// `row`: the glyph's line in a multi-line record (0 in a single-line one), so a
// caller can colour a line of its own (the message line, PQ-407).
struct HudGlyph { unsigned char code; int x, y, row = 0; };

// Positions are computed in integer layout units before viewport scaling.
// Single-line alignment/truncation follows the measured-extent path at 0040def0.
inline std::vector<HudGlyph> hud_text_layout(const n3e::Hud &h,
                                            const n3e::HudRecord &q,
                                            std::string_view text) {
  std::vector<HudGlyph> glyphs;
  const int left=int(q.rect[0]), top=int(q.rect[1]);
  const int width=int(q.rect[2])-left, height=int(q.rect[3])-top;
  const float advance=h.font_advance;
  const int line=int(h.font_height);
  if (!advance || !line || width < advance) return glyphs;
  text=text.substr(0,4096);
  int x=left, y=top;
  if (q.text_flags & 1) {
    text=text.substr(0,text.find('\n'));
    const int measured=int(std::ceil(text.size()*advance));
    if (measured<=width) {
      if (q.align==1) x+=width-measured;
      else if (q.align==2) x+=(width-measured)/2;
    }
    if (q.text_flags & 2) y+=height-line;
    else if (q.text_flags & 4) y+=(height-line)/2;
    // Binary single-line overflow keeps the left origin and truncates by extent;
    // it does not wrap, or discard the line just because its height exceeds the box.
    text=text.substr(0,size_t(width/advance));
  }
  int column=0, origin=x, row=0;
  for (unsigned char c:text) {
    x=origin+int(std::round(column*advance));
    if (!(q.text_flags & 1)) {
      if (c=='\n' || int(std::ceil((column+1)*advance))>width) {
        x=left; origin=left; column=0; y+=line; ++row;
        if (c=='\n') continue;
      }
      if (y+line>top+height) break;
    }
    if (c<32 || c>126) c='?';
    glyphs.push_back({c,x,y-int(h.font_top),row});
    ++column;
  }
  return glyphs;
}

// The characters a multi-line record's line holds before hud_text_layout wraps
// it, by the same test.
inline size_t hud_text_columns(const n3e::Hud &h, const n3e::HudRecord &q) {
  const int width=int(q.rect[2])-int(q.rect[0]);
  const float advance=h.font_advance;
  if (!advance || width < advance) return 0;
  size_t column=0;
  while (column<4096 && !(int(std::ceil((column+1)*advance))>width)) ++column;
  return column;
}
