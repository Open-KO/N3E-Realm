#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <optional>
#include <utility>

// Package-defined controls. Zero is the unconditional root; IDs are one-based.
// The same visibility predicate owns artwork and hit regions, including parents.
struct HudLayout {
  n3e::Hud data;
  bool running = false, moving = false, primary_active = false, sitting = false;
  std::map<uint32_t,std::array<float,2>> panel_offsets;
  std::array<float,2> panel_offset(uint32_t panel) const {auto it=panel_offsets.find(panel);return it==panel_offsets.end()?std::array<float,2>{0,0}:it->second;}
  bool pointer_active=false;float pointer_x=0,pointer_y=0;
  uint32_t hovered = 0, pressed = 0, panels = 1, input_panel = 0;
  std::map<std::string,std::string> values,items;
  explicit HudLayout(n3e::Hud h) : data(std::move(h)) {}
  const n3e::HudIcon* item_icon(const std::string&key) const {
    auto item=items.find(key);if(item==items.end())return nullptr;
    if((key.starts_with("hotbar:")||key.starts_with("skill:"))){auto action=data.action_icons.find(item->second);if(action!=data.action_icons.end())return &action->second;}
    auto icon=data.item_icons.find(item->second);
    return icon==data.item_icons.end()?nullptr:&icon->second;
  }
  std::string item_label(const std::string&key) const {
    if(!items.contains(key))return {};
    auto value=values.find(item_icon(key)?"count:"+key:key);
    return value==values.end()?std::string{}:value->second;
  }
  float scale(int w, int h) const { return data.pixel_scale ? 1.f : std::min(w / 1024.f, h / 768.f); }
  std::array<float, 4> rectangle(const n3e::HudRecord &q, int w, int h) const {
    float s = scale(w, h);
    auto offset=panel_offset(q.panel);
    // Authored UI uses integer screen edges. Fractional scaled edges can leave
    // a transparent atlas-border column visible between overlapping slices.
    return {std::floor(offset[0]+q.anchor[0] * w + q.rect[0] * s), std::floor(offset[1]+q.anchor[1] * h + q.rect[1] * s),
            std::floor(offset[0]+q.anchor[0] * w + q.rect[2] * s), std::floor(offset[1]+q.anchor[1] * h + q.rect[3] * s)};
  }
  bool visible(uint32_t id) const {
    for (; id; id = data.controls[id - 1].parent) {
      auto v = data.controls[id - 1].visibility;
      if (v == 1 || (v == 2 && !running) || (v == 3 && running) || (v==4 && sitting) || (v==5 && !sitting)) return false;
    }
    return true;
  }
  bool enabled(uint32_t id) const {
    for (; id; id = data.controls[id - 1].parent)
      if (!data.controls[id - 1].enabled) return false;
    return true;
  }
  uint32_t state(uint32_t id) const {
    if (!id) return 0;
    if (!enabled(id)) return 3;
    auto selection = data.controls[id - 1].selection;
    if ((pressed == id && hovered == id) || selection == 1 ||
        (selection == 2 && primary_active) || (selection == 3 && moving)) return 1;
    return hovered == id ? 2 : 0;
  }
  bool visible(const n3e::HudRecord &q) const {
    return (shown_panels() & (1u<<q.panel)) && visible(q.control) && (q.states & (1u << state(q.control)));
  }
  bool contains(const n3e::HudRecord &q, float x, float y, int w, int h) const {
    auto r = rectangle(q, w, h);
    return x >= r[0] && x < r[2] && y >= r[1] && y < r[3];
  }
  std::string hit(float x, float y, int w, int h) const {
    std::string result;
    for (const auto &q : data.records) {
      if ((input_panel && q.panel != input_panel) || q.target || !visible(q) || !contains(q, x, y, w, h)) continue;
      if (q.kind == 2) result = enabled(q.control) ? (q.binding=="action"?q.text:q.binding) : "panel";
      else if (result.empty()) result = "panel";
    }
    return result;
  }
  // Down captures only a visible enabled control. Release/focus/capture cancels it.
  void pointer(float x, float y, int w, int h, bool down = false) {
    pointer_active=true;pointer_x=x;pointer_y=y;
    hovered = 0;
    for (const auto &q : data.records)
      if ((!input_panel || q.panel == input_panel) && q.kind == 2 && !q.target && visible(q) && contains(q, x, y, w, h))
        hovered = enabled(q.control) ? q.control : 0;
    if (down) pressed = hovered;
    if (pressed && (!visible(pressed) || !enabled(pressed))) pressed = 0;
  }
  void cancel_pointer() { hovered = pressed = 0;pointer_active=false;panel_drag.reset(); }
  // Panels 11-14 are persistent HUD panels (N3HC), shown like panel 0; panel
  // 15 is the overview map (N3HD), shown while toggled on (hidden at start, 00561d70).
  bool minimap_open=false;
  uint32_t shown_panels() const {return panels|0x7800u|(minimap_open?0x8000u:0u);}
  struct MinimapMarker{float x,z;uint32_t color;bool top;};
  std::vector<MinimapMarker> minimap_markers;
  std::array<float,3> minimap_self{}; // x, z, heading
  uint32_t panel_of(const std::string&key) const {
    for(const auto&q:data.records)if(q.binding=="item"&&q.text==key)return q.panel;
    return 0;
  }
  // Draggable panels (N3HC). A drag follows the pointer without a viewport
  // clamp; the whole group moves rigidly, and snapping panels are pulled to a
  // horizontal viewport edge within their snap distance.
  std::optional<std::pair<size_t,std::array<float,2>>> panel_drag;
  std::array<float,4> movable_rectangle(const n3e::HudMovable&m,const std::array<float,4>&r,int w,int h) const {
    float s=scale(w,h);auto o=panel_offset(m.panel);
    return {std::floor(o[0]+m.anchor[0]*w+r[0]*s),std::floor(o[1]+m.anchor[1]*h+r[1]*s),
            std::floor(o[0]+m.anchor[0]*w+r[2]*s),std::floor(o[1]+m.anchor[1]*h+r[3]*s)};
  }
  void move_group(uint32_t group,float dx,float dy){
    for(const auto&m:data.movables)if(m.group==group){auto&o=panel_offsets[m.panel];o[0]+=dx;o[1]+=dy;}
  }
  void snap_panels(int w,int h){
    for(const auto&m:data.movables)if(m.snap){
      auto b=movable_rectangle(m,m.bounds,w,h);float snap=float(m.snap);
      if(-snap<b[0]&&b[0]<=snap)move_group(m.group,-b[0],0);
      else if(w-snap<b[2]&&b[2]<w+snap)move_group(m.group,w-b[2],0);
    }
  }
  bool begin_panel_drag(float x,float y,int w,int h){
    if(hovered||input_panel)return false;
    for(size_t i=0;i<data.movables.size();++i){const auto&m=data.movables[i];
      if(!(shown_panels()&(1u<<m.panel)))continue;
      auto r=movable_rectangle(m,m.handle,w,h);
      if(x>=r[0]&&x<r[2]&&y>=r[1]&&y<r[3]){panel_drag=std::pair{i,std::array<float,2>{x,y}};return true;}
    }
    return false;
  }
  void drag_panels(float x,float y,int w,int h){
    if(!panel_drag)return;auto&[i,last]=*panel_drag;
    move_group(data.movables[i].group,x-last[0],y-last[1]);last={x,y};snap_panels(w,h);
  }
  // Saved top-left positions of each keyed group leader. (0,0) keeps the
  // default; others are clamped into the viewport on restore only.
  std::map<std::string,std::array<int,2>> saved_positions(int w,int h) const {
    std::map<std::string,std::array<int,2>> out;
    for(const auto&m:data.movables)if(!m.key.empty()){auto b=movable_rectangle(m,m.bounds,w,h);out[m.key]={int(b[0]),int(b[1])};}
    return out;
  }
  void restore_positions(const std::map<std::string,std::array<int,2>>&saved,int w,int h){
    for(const auto&m:data.movables){
      auto it=m.key.empty()?saved.end():saved.find(m.key);
      if(it==saved.end())continue;
      // 00647210: clamp first; a resolved (0,0) keeps the default position.
      auto b=movable_rectangle(m,m.bounds,w,h);
      float x=std::max(0.f,float(it->second[0])),y=std::max(0.f,float(it->second[1]));
      if(x+(b[2]-b[0])>w)x=w-(b[2]-b[0]);
      if(y+(b[3]-b[1])>h)y=h-(b[3]-b[1]);
      if(x==0&&y==0)continue;
      move_group(m.group,x-b[0],y-b[1]);
    }
    snap_panels(w,h);
  }
};
