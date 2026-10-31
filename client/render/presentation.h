#pragma once
#include "nameplates.h"
#include "hud_layout.h"
#include "hotbar.h"
#include "hud_text_layout.h"
#include "progress.h"
#include "target_health.h"
#include "item_tooltip.h"
#include "message_log.h"
#include "network/world.h"
#include "network/chat.h"
#include "platform/gl_load.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <functional>
#include <iostream>

struct HudView : HudLayout {
  std::vector<GLuint> textures;
  // PQ-407 (D-210): the message line's short log (server refusals and the
  // client's own notices), drawn before the `combat` record's own lines.
  n3e::MessageLog messages;
  void post_notice(std::string text){
#if N3E_HARNESS
    // PQ-481: harness builds name each client notice, so a replay can show
    // that a press posted none.
    std::cout<<"NOTICE text='"<<text<<"'"<<std::endl;
#endif
    messages.post(std::move(text),n3e::MessageKind::notice);}
  void post_refusal(std::string text){messages.post(std::move(text),n3e::MessageKind::refusal);}
  // PQ-469 (D-235): a server refusal drawn in the colour its caller gives.
  void post_refusal(std::string text,uint32_t color){messages.post(std::move(text),n3e::MessageKind::refusal,color);}
  // PQ-408 (D-211): the message line's scroll bar (N3HS), its track and thumb
  // records, and the thumb's authored offset in the track.
  const n3e::HudRecord *message_track=nullptr,*message_thumb=nullptr;
  float message_thumb_origin=0;
  n3e::MessagePart message_part(float x,float y,int w,int h) const {
    auto key=hit(x,y,w,h);
    return key=="message_up"?n3e::MessagePart::up:key=="message_down"?n3e::MessagePart::down:
           key=="message_track"?n3e::MessagePart::track:n3e::MessagePart::none;
  }
  // The pointer's offset from the track's top, in HUD units.
  float message_track_y(float y,int w,int h) const {
    return message_track?(y-rectangle(*message_track,w,h)[1])/scale(w,h):0;
  }
  // The thumb's drawn rectangle: its record moved to the log's offset.
  std::array<float,4> message_thumb_rect(int w,int h) const {
    auto r=rectangle(*message_thumb,w,h);
    float d=std::round((messages.thumb-message_thumb_origin)*scale(w,h));
    r[1]+=d;r[3]+=d;return r;
  }
  // A left press on the scroll bar is the scroll bar's (true), not a panel drag.
  bool message_press(float x,float y,int w,int h){
    if(!message_track)return false;
    auto part=message_part(x,y,w,h);
    if(part==n3e::MessagePart::none)return false;
    messages.press(part,message_track_y(y,w,h));return true;
  }
  void message_motion(float x,float y,int w,int h){if(message_track)messages.motion(message_part(x,y,w,h),message_track_y(y,w,h));}
  void message_release(float x,float y,int w,int h){if(message_track)messages.release(message_part(x,y,w,h));}
  // Every frame: a held scroll button repeats while the pointer stays on it.
  void message_frame(float dt,int w,int h){
    if(message_track)messages.frame(pointer_active?message_part(pointer_x,pointer_y,w,h):n3e::MessagePart::none,dt);
  }
  void cancel_pointer(){HudLayout::cancel_pointer();messages.cancel();}
  uint32_t cooldown_texture=0,solid_texture=0;
  std::map<std::string,std::pair<float,int>> cooldowns;
  std::vector<Nameplate> names;
  std::string drag_key;
  uint32_t drag_panel=0;
  std::array<float,4> drag_rect{};
  std::map<std::string,float> meters;
  std::map<std::string,ItemTooltip> tooltips;
  std::map<std::string,uint32_t> colors;
  std::optional<std::array<uint64_t, 10>> thresholds;
  // PQ-178: the package's colour for a chat line the server marked as an
  // operator's (names.operator_chat), and the colour the chat text was last
  // drawn in (read by the test harness).
  std::optional<uint32_t> operator_chat,chat_drawn;
  // PQ-406: the newest message the message line (binding `combat`) last drew,
  // and (PQ-407) every message row it drew with its colour, read by the test
  // harness.
  std::string notice_drawn;
  std::vector<n3e::MessageLine> messages_drawn;
  // PQ-354: the item tooltip drawn last (read by the test harness): its box
  // and each drawn line's origin and drawn width, in window pixels.
  struct DrawnTooltip {std::string key;std::array<float,4> rect{};std::vector<std::array<float,3>> lines;};
  std::optional<DrawnTooltip> drawn_tooltip;
  explicit HudView(n3e::Hud h) : HudLayout(std::move(h)) {
    if(data.messages)messages.set_rows(data.messages->rows);
    if(data.messages&&data.messages->scroll){
      for(const auto&q:data.records){if(q.binding=="message_track")message_track=&q;if(q.binding=="message_thumb")message_thumb=&q;}
      const auto&s=*data.messages->scroll;
      message_thumb_origin=message_thumb->rect[1]-message_track->rect[1];
      messages.scroll({s.records,s.lines,s.line_step,s.page_step,s.repeat},message_track->rect[3]-message_track->rect[1],
                      message_thumb->rect[3]-message_thumb->rect[1],message_thumb_origin);
    }
    cooldown_texture=data.textures.size();
    data.textures.push_back({1,1,{255,255,255,static_cast<unsigned char>(data.cooldown_color>>24)}});
    solid_texture=data.textures.size();
    data.textures.push_back({1,1,{255,255,255,255}});
    for (const auto &t : data.textures) {
      // Artwork uses point sampling (KO UI setup 00578db0), with no mips.
      // The package's substitute font atlas retains its smooth filtering.
      bool name_font=data.nameplates&&std::any_of(data.nameplates->fonts.begin(),data.nameplates->fonts.end(),[&](const auto&font){return font.texture==textures.size();});
      GLint filter = textures.size() == data.font || name_font ? GL_LINEAR : GL_NEAREST;
      GLuint id;
      glGenTextures(1, &id);
      textures.push_back(id);
      glBindTexture(GL_TEXTURE_2D, id);
      glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, t.width, t.height, 0, GL_RGBA,
                   GL_UNSIGNED_BYTE, t.pixels.data());
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    }
  }
  HudView(const HudView&)=delete;
  HudView&operator=(const HudView&)=delete;
  ~HudView() { glDeleteTextures(textures.size(), textures.data()); }
  void render(const n3e::WorldState &world, uint64_t target, int entry,
              const std::string &input, int w, int h,
              const std::function<void(const n3e::HudPortrait&,const std::array<float,4>&)>&portrait = {}) {
    const n3e::Entity *self = nullptr, *enemy = nullptr;
    for (const auto &e : world.world.entities()) {
      if (e.id() == world.world.self())
        self = &e;
      if (e.id() == target)
        enemy = &e;
    }
    auto name = [](std::string s) {
      auto i = s.find_last_of('/');
      return i == std::string::npos ? s : s.substr(i + 1);
    };
    auto ratio = [&](const std::string &b) {
      if (b == "health")
        return self ? float(self->health()) /
                          std::max(1u, world.world.max_health())
                    : 0.f;
      if (b == "resource")
        return self ? float(self->resource()) /
                          std::max(1u, world.world.max_resource())
                    : 0.f;
      if (b == "xp" && thresholds) {
        const auto &inv = world.world.inventory();
        return progress_view(*thresholds, inv.level(), inv.curve_xp()).fraction();
      }
      if (b == "xp")
        return std::fmod(float(world.world.inventory().xp()), data.level_xp) /
               data.level_xp;
      if (b == "target_health")
        return enemy ? target_health_fraction(enemy->health(), enemy->max_health(), data.target_health) : 0.f;
      return 1.f;
    };
    // The message line: the characters a row holds, set by the drawing branch
    // before it asks for the text, and each drawn row's colour.
    size_t combat_columns=0;
    std::vector<uint32_t> row_colors;
    auto text = [&](const n3e::HudRecord &q) {
      const auto &b = q.binding;
      if(b=="value"){auto v=values.find(q.text);return v==values.end()?std::string{}:v->second;}
      if(b=="item_label")return item_label(q.text);
      const auto &inv = world.world.inventory();
      if (b == "health_text")
        return std::to_string(self ? self->health() : 0) + "/" +
               std::to_string(world.world.max_health());
      if (b == "resource_text")
        return std::to_string(self ? self->resource() : 0) + "/" +
               std::to_string(world.world.max_resource());
      if (b == "xp_text" && thresholds) {
        return "Lv " + std::to_string(inv.level()) + " XP " +
               progress_view(*thresholds, inv.level(), inv.curve_xp()).text() +
               " Total " + std::to_string(inv.xp());
      }
      if (b == "xp_text")
        return "Lv " + std::to_string(inv.level()) + "  XP " +
               std::to_string(inv.xp());
      if (b == "position")
        return std::to_string(int(world.predicted[0])) + ", " +
               std::to_string(int(world.predicted[2]));
      if (b == "player_name")
        return self ? self->name() : std::string{};
      if (b == "target_name")
        return enemy ? name(enemy->name()) + "  HP " +
                           std::to_string(enemy->health()) + " " + enemy->strike_result() + " " + std::to_string(enemy->strike_damage())
                     : std::string{};
      if (b == "chat")
        return world.chat;
      if (b == "chat_input")
        return entry == 5 ? "> " + input : std::string("Press Enter to chat");
      if (b == "combat") {
        messages.set_columns(combat_columns);
        messages_drawn = messages.lines(data.messages ? data.messages->refusal : q.color,
                                        data.messages ? data.messages->notice : q.color);
        notice_drawn = messages.newest();
        std::string log;
        row_colors.clear();
        for (const auto &line : messages_drawn) { log += line.text + "\n"; row_colors.push_back(line.color); }
        std::string status = !world.connected ? "Disconnected - F12 to reconnect"
                             : self && !self->health() ? (self->life_state() == n3e::LEGACY ? "Fallen - respawning" : "Fallen - see respawn prompt")
                                                       : world.combat + " " + std::to_string(world.combat_damage);
        return log + status + "\n" + name(inv.item()) + " " +
               std::to_string(inv.count()) + "/" +
               std::to_string(inv.capacity()) +
               (inv.pending() ? "\nReward pending" : "");
      }
      return q.text;
    };
    struct Batch {
      uint32_t texture;
      int start, count;
    };
    std::vector<Batch> batches;
    std::vector<float> verts;
    auto quad = [&](uint32_t tex, std::array<float, 4> r,
                    std::array<float, 4> uv, uint32_t color) {
      if (r[2] <= r[0] || r[3] <= r[1])
        return;
      if (batches.empty() || batches.back().texture != tex)
        batches.push_back({tex, int(verts.size() / 8), 0});
      const int ix[6] = {0, 1, 2, 0, 2, 3};
      const float px[4] = {r[0], r[2], r[2], r[0]},
                  py[4] = {r[1], r[1], r[3], r[3]};
      const float ux[4] = {uv[0], uv[2], uv[2], uv[0]},
                  uy[4] = {uv[1], uv[1], uv[3], uv[3]};
      for (int i : ix)
        verts.insert(verts.end(), {px[i] * 2 / w - 1, 1 - py[i] * 2 / h, 0,
                                   float(color >> 16 & 255) / 255,
                                   float(color >> 8 & 255) / 255,
                                   float(color & 255) / 255, ux[i], uy[i]});
      batches.back().count += 6;
    };
    auto flush=[&](){
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glBufferData(GL_ARRAY_BUFFER, verts.size() * sizeof(float), verts.data(),
                 GL_DYNAMIC_DRAW);
    for (const auto &b : batches) {
      glBindTexture(GL_TEXTURE_2D, textures[b.texture]);
      glDrawArrays(GL_TRIANGLES, b.start, b.count);
    }
    glDisable(GL_BLEND);
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
      verts.clear();batches.clear();
    };
    if(data.nameplates&&entry>=4){
      for(const auto&name:names){
        const auto&font=data.nameplates->fonts[name.font];
        auto draw=[&](int dx,int dy,uint32_t color){
          float x=name.x;
          for(unsigned char c:name.text){unsigned glyph=name_glyph(c);float left=x-2+dx,top=name.y-int(font.top)+dy;
            quad(font.texture,{left,top,left+32,top+32},
                 {(glyph%16)*32/512.f,(glyph/16)*32/192.f,((glyph%16)+1)*32/512.f,((glyph/16)+1)*32/192.f},color);
            x+=font.advances[glyph];
          }
        };
        draw(-1,-1,0);draw(1,1,0);draw(0,0,name.color);
      }
      flush();
    }
    float s = scale(w, h);
    // Overview map (00563ed0/00563240): the image shows a 1/zoom window centred
    // on the player and clamped to the map; markers and the heading arrow are
    // drawn after the map panel's last record, inside the image rectangle.
    size_t map_last=data.records.size();
    for(size_t i=0;i<data.records.size();++i)if(data.records[i].panel==15)map_last=i;
    std::array<float,4> map_rect{};std::array<float,2> map_centre{};
    auto map_point=[&](float x,float z){const auto&m=*data.minimap;
      return std::array<float,2>{map_rect[0]+(map_rect[2]-map_rect[0])*(.5f+((x-m.origin[0])/m.extent-map_centre[0])*m.zoom),
                                 map_rect[1]+(map_rect[3]-map_rect[1])*(.5f+((z-m.origin[1])/m.extent-map_centre[1])*m.zoom)};};
    auto triangle=[&](std::array<std::array<float,2>,3> p,uint32_t color){
      if(batches.empty()||batches.back().texture!=solid_texture)batches.push_back({solid_texture,int(verts.size()/8),0});
      for(auto v:p){verts.insert(verts.end(),{v[0]*2/w-1,1-v[1]*2/h,0,float(color>>16&255)/255,float(color>>8&255)/255,float(color&255)/255,.5f,.5f});++batches.back().count;}
    };
    auto map_overlay=[&](){
      if(!data.minimap||map_rect[2]<=map_rect[0])return;const auto&m=*data.minimap;
      auto markers=[&](bool top){for(const auto&k:minimap_markers)if(k.top==top){auto c=map_point(k.x,k.z);
        if(c[0]<map_rect[0]||c[0]>=map_rect[2]||c[1]<map_rect[1]||c[1]>=map_rect[3])continue;
        quad(solid_texture,{c[0]-m.marker_outer,c[1]-m.marker_outer,c[0]+m.marker_outer,c[1]+m.marker_outer},{0,0,1,1},0);
        quad(solid_texture,{c[0]-m.marker_inner,c[1]-m.marker_inner,c[0]+m.marker_inner,c[1]+m.marker_inner},{0,0,1,1},k.color);}};
      markers(false);
      // Forward motion faces (-sin h, -cos h) in (x, z): rotate the up-pointing arrow by -h.
      auto at=map_point(minimap_self[0],minimap_self[1]);float a=(map_rect[3]-map_rect[1])*m.arrow_ratio,c=std::cos(-minimap_self[2]),sn=std::sin(-minimap_self[2]);
      auto rot=[&](float x,float y){return std::array<float,2>{at[0]+x*c-y*sn,at[1]+y*c+x*sn};};
      triangle({rot(0,-a),rot(0,a/2),rot(-a,a)},m.colors[0]);triangle({rot(0,-a),rot(a,a),rot(0,a/2)},m.colors[0]);
      markers(true);
    };
    for (size_t record = 0; record < data.records.size(); ++record) {
      const auto &q = data.records[record];
      if(record==map_last+1)map_overlay();
      if (!visible(q) || (q.target && !enemy))
        continue;
      auto r = rectangle(q, w, h);
      if(q.binding=="minimap"&&data.minimap){
        const auto&m=*data.minimap;float half=.5f/m.zoom;
        map_centre={std::clamp((minimap_self[0]-m.origin[0])/m.extent,half,1-half),std::clamp((minimap_self[1]-m.origin[1])/m.extent,half,1-half)};
        map_rect=r;quad(q.texture,r,{map_centre[0]-half,map_centre[1]-half,map_centre[0]+half,map_centre[1]+half},0xffffff);
        continue;
      }
      if(q.panel==drag_panel&&q.text==drag_key&&(q.binding=="item"||q.binding=="item_label"))continue;
      if(q.binding=="portrait"){
        if(portrait){flush();portrait(data.portraits.at(q.text),r);}
        continue;
      }
      if (q.kind == 0) {
        if(q.binding=="item"){
          if(auto icon=item_icon(q.text)){
            quad(icon->texture,r,icon->uv,0xffffff);
            if(auto it=cooldowns.find(q.text);it!=cooldowns.end()){
              const auto [remaining,flash]=it->second;
              if(flash>=0&&flash<3)quad(data.cooldown_frames[flash],r,{0,0,1,1},0xffffff);
              else {
                auto polygon=cooldown_polygon(remaining);
                if(polygon.size()>=3){
                  if(batches.empty()||batches.back().texture!=cooldown_texture)batches.push_back({cooldown_texture,int(verts.size()/8),0});
                  for(size_t i=1;i+1<polygon.size();++i)for(auto point:{polygon[0],polygon[i],polygon[i+1]}){
                    float x=r[0]+point[0]*(r[2]-r[0]),y=r[1]+point[1]*(r[3]-r[1]);
                    verts.insert(verts.end(),{x*2/w-1,1-y*2/h,0,float(data.cooldown_color>>16&255)/255,float(data.cooldown_color>>8&255)/255,float(data.cooldown_color&255)/255,.5f,.5f});
                    ++batches.back().count;
                  }
                }
              }
            }
          }
          continue;
        }
        if(&q==message_thumb)r=message_thumb_rect(w,h);
        auto uv = q.uv;
        float amount = std::clamp(q.binding=="meter"?meters[q.text]:ratio(q.binding), 0.f, 1.f);
        r[2] = r[0] + (r[2] - r[0]) * amount;
        uv[2] = uv[0] + (uv[2] - uv[0]) * amount;
        quad(q.texture, r, uv, 0xffffff);
      } else if (q.kind == 1) {
        if (data.font_advance) {
          auto label=q;
          if(q.binding=="item_label"&&item_icon(q.text)){
            label.rect[1]=std::max(label.rect[1],label.rect[3]-16);
            label.rect[0]+=2;label.text_flags=1;
          }
          auto color=colors.contains(q.text)&&q.binding=="value"?colors.at(q.text):q.color;
          if(q.binding=="chat"){color=n3e::chat_line_color(world.chat_operator,operator_chat,color);if(!world.chat.empty())chat_drawn=color;}
          const bool combat=q.binding=="combat";
          if(combat)combat_columns=hud_text_columns(data,label);
          for (const auto &g : hud_text_layout(data,label,text(q))) {
            int i=g.code-32;
            auto offset=panel_offset(q.panel);
            float x=offset[0]+q.anchor[0]*w+g.x*s, y=offset[1]+q.anchor[1]*h+g.y*s;
            quad(data.font,{x,y,x+16*s,y+20*s},
                 {(i%16)*16/256.f,(i/16)*20/128.f,
                  ((i%16)+1)*16/256.f,((i/16)*20+20)/128.f},
                 combat&&size_t(g.row)<row_colors.size()?row_colors[g.row]:color);
          }
          continue;
        }
        float x = r[0], y = r[1];
        const bool combat = q.binding == "combat";
        if (combat) {
          // The same test the loop below wraps by.
          combat_columns = 0;
          for (float at = r[0]; combat_columns < 4096 && !(at + 7.2f * s > r[2]); at += 7.2f * s) ++combat_columns;
        }
        auto value = text(q);
        auto color = q.color;
        size_t row = 0;
        if (q.binding == "chat") {
          color = n3e::chat_line_color(world.chat_operator, operator_chat, color);
          if (!world.chat.empty()) chat_drawn = color;
        }
        if (q.align && value.find('\n') == std::string::npos) {
          float length = value.size() * 7.2f * s;
          x = std::max(r[0], q.align == 2 ? (r[0] + r[2] - length) * .5f
                                          : r[2] - length);
        }
        for (unsigned char c : value) {
          if (c == '\n' || x + 7.2f * s > r[2]) {
            x = r[0];
            y += 16 * s;
            ++row;
            if (c == '\n')
              continue;
          }
          if (y + 12 * s > r[3] + 4 * s)
            break;
          if (c < 32 || c > 126)
            c = '?';
          int i = c - 32;
          quad(data.font, {x, y, x + 16 * s, y + 20 * s},
               {(i % 16) * 16 / 256.f, (i / 16) * 20 / 128.f,
                ((i % 16) + 1) * 16 / 256.f, ((i / 16) * 20 + 20) / 128.f},
               combat && row < row_colors.size() ? row_colors[row] : color);
          x += 7.2f * s;
        }
      }
    }
    if(map_last+1==data.records.size())map_overlay();
    if(data.tooltip&&pointer_active&&!input_panel&&drag_key.empty()&&!pressed){
      auto key=hit(pointer_x,pointer_y,w,h);auto found=tooltips.find(key);
      if(found!=tooltips.end()&&!found->second.empty()){
        const auto&tip=*data.tooltip;auto count=std::min(tip.rows.size(),found->second.size());
        float width=0;for(const auto&line:found->second)width=std::max(width,line.text.size()*data.font_advance);
        auto rect=tooltip_rectangle(pointer_x,pointer_y,(width+tip.width_padding)*s,(tip.rows[count-1][1]-tip.rows[0][0]+tip.height_padding)*s,w,h,tip.gap*s);
        quad(tip.background.texture,rect,tip.background.uv,0xffffff);
        drawn_tooltip=DrawnTooltip{key,rect,{}};
        for(size_t i=0;i<count;++i){const auto&line=found->second[i];
          float x=rect[0]+8*s,y=rect[1]+tip.rows[i][0]*s;
          if(i==0||line.centred)x=std::max(x,(rect[0]+rect[2]-line.text.size()*data.font_advance*s)*.5f);
          float start=x;
          for(unsigned char c:line.text){if(x+data.font_advance*s>rect[2]-8*s||y+data.font_height*s>rect[3])break;
            if(c<32||c>126)c='?';
            int ix=c-32;
            quad(data.font,{x,y,x+16*s,y+20*s},{(ix%16)*16/256.f,(ix/16)*20/128.f,((ix%16)+1)*16/256.f,((ix/16)*20+20)/128.f},line.color);
            x+=data.font_advance*s;
          }
          drawn_tooltip->lines.push_back({start,y,x-start});
        }
      }
    }
    if(!drag_key.empty())if(auto icon=item_icon(drag_key))quad(icon->texture,drag_rect,icon->uv,0xffffff);
    flush();
  }
};

#include "player_pose.h"
