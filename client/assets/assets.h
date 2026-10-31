#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <iosfwd>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>
#include "collision.h"
namespace n3e {
using V = std::array<float, 3>;
using Q = std::array<float, 4>;
using M = std::array<float, 16>;
struct MovementConfig {
  float walk = 3, run = 3, backward = 3, radius = .2f, height = 1.6f,
        step_height = .25f;
  bool valid() const;
  float speed(uint32_t mode) const;
};
struct CameraConfig {
  float fov = 1.04719755f, near_plane = .05f, far_plane = 100;
  float pitch = .48f, pitch_min = .15f, pitch_max = 1.15f;
  float distance = 7, distance_min = 2, distance_max = 16;
  float focus_height = .65f, focus_scale = 0;
  float yaw_per_pixel = .006f, pitch_per_pixel = .005f, zoom_per_step = .7f;
  float clearance = .2f, turn_rate = 1.0471976f, hold_delay = .1f;
  uint32_t facing_relative = 0;
  // N3V2 extension (PQ-012, D-143): vertical right-drag moves the distance
  // instead of the pitch; held camera_pitch_up/down and the cursor on the
  // window's outermost column turn at these rates (0: off). N3V1 keeps these.
  uint32_t drag_distance = 0;
  float distance_per_pixel = .01f, key_pitch_rate = 0, edge_yaw_rate = 0;
  bool valid() const;
};
struct MeleeConfig {
  float actor_radius = 1, target_radius = 1, reach = 0, facing_dot = .7f;
  uint32_t cooldown_ticks = 20;
  float range() const { return (actor_radius + target_radius) * .5f + reach; }
  bool valid() const;
};
// Actor pick policy (PQ-146, D-138; package `pick.bin`, N3PK): an actor's
// pick box bounds its model's joint positions (KO) or its skinned vertices; an
// axis shorter than min_extent grows by pad on each side; with several box
// hits, actors at LOD mesh_lod or finer are tested against their drawn
// triangles. A release without it: vertex bounds, no minimum, mesh test at
// every LOD.
struct PickPolicy {
  bool joints = false;
  float min_extent = 0, pad = 0;
  uint32_t mesh_lod = 3;
};
// Screen post-process (PQ-316, D-185; package `postprocess.bin`, N3PF): the
// bloom and tone-map chain's settings for the package's zone. The chain is the
// 2233 client's CN3PostProcess (a 2233/2145 addition; 1298 has none): bright
// pass at `threshold`; luminance reduction adapted by `adapt_rate` per second;
// 4x4 downscale; 9-tap blur of variance `blur_variance` whose normalised
// weights are scaled by `bloom` in each pass; composite with an extended
// Reinhard tone map (white point maximum x (1 + bloom)), `exposure`, `lift`
// and `saturation`. Drawn only when the player turns it on (Option.ini).
struct PostProcess {
  float threshold = 0, bloom = 1, exposure = 1, saturation = 1, lift = 0, adapt_rate = 0, blur_variance = 1;
};
struct Clip {
  float duration = 1, blend = 0;
  bool loop_blend = false;
  std::array<float, 2> markers{-1, -1};
  // PQ-420 (D-217): a ranged cast's attack clip is stretched to the cast time;
  // `duration` and `markers` are already scaled, the clip file's key times are
  // scaled by this factor when it is loaded. 1: not stretched.
  float stretch = 1;
};
// A ranged basic attack on a profile (PQ-416, D-216; package
// `ranged-attack.bin`, N3RB/N3RC): the strike reaches the actor's and the
// target's radii summed plus `range` in 3-D, and a Ctrl or double click walks
// to half the summed radii plus `reach`; `range` 0 means a melee profile.
// `cast_ms` above 0 (PQ-420, D-217): the server holds the shot and its hit
// comes as a kind-6 event; the profile's attack clip is stretched to it.
// `ammo` (PQ-421, D-218; N3RD): the inventory item a shot needs, `ammo_count`
// of it in the first bag slot holding it (empty: none needed). N3RE (PQ-422,
// D-219) adds a type-2 skill hit per entry, which only the server uses.
// PQ-423 (D-220, N3RF): `cast_effect` (empty: none) is an effects clip drawn
// on the caster's `cast_joints` (-1: its position) during the cast.
// PQ-417 (D-222, N3RG): `flight` (empty: none) is the effects clip the
// client flies at the landing from the shooter's `flight_joint` (-1: its
// position) at `flight_speed` m/s to the target's box, then `hit` at the
// target's `hit_joint` (-1: its position); `release` is an audio key played
// at the shooter at the launch (empty: none). PQ-467 (D-233, N3RH) adds a
// hold per entry, which only the server uses; the client bounds it.
struct RangedAttack {float reach=0,range=0;uint32_t cast_ms=0;std::string ammo;uint32_t ammo_count=0;
                     std::string cast_effect;std::vector<int> cast_joints;
                     std::string flight;int flight_joint=-1;float flight_speed=0;std::string hit;int hit_joint=-1;std::string release;};
struct CombatProfile {uint32_t ready;std::vector<uint32_t> attacks;uint32_t interval_ms=0,moving=0;RangedAttack ranged;};
// `ranged_notice`: the package's line for a ranged strike beyond range;
// `ammo_notice` (N3RD): its line for a shot without its ammunition.
struct CombatAnimation {std::vector<Clip> clips;std::vector<CombatProfile> profiles;std::vector<uint32_t> upper_nodes;std::string ranged_notice,ammo_notice;};
struct EditProperty {std::string key; uint32_t kind,target;float initial,min,max;};
struct Exploration {
  float multiplier, fog_start, fog_end;
  V fog_color;
};
struct ItemDefinition { std::string id, label; uint32_t stack, durability, starting; };
// Item tooltip heads (PQ-354, D-194; package `item-heads.bin`, N3IH): for an
// item, the colour of its tooltip's first line (its label) and the lines drawn
// centred right under it; `token` (empty: none) is replaced in the first line
// by the viewer's own character name. The rule is the 2233 client's tooltip
// head (005aa8e0, 004aad90); which colours, lines and token is package data.
struct ItemHeadLine { std::string text; uint32_t color; };
struct ItemHead { uint32_t name_color; std::vector<ItemHeadLine> lines; };
struct ItemHeads { std::string token; std::map<std::string, ItemHead> heads; };
struct EquipmentItem {std::string id;uint32_t slots,blocks,title,race;std::array<uint32_t,5> attributes;bool swappable;};
struct EquipmentPolicy {uint32_t race,title;std::array<uint32_t,5> attributes;std::vector<std::string> slots;std::vector<EquipmentItem> items;};
struct InventoryPolicy { uint32_t capacity; std::string currency; uint32_t limit, coins; std::vector<ItemDefinition> items; };
struct ItemPrice { std::string item; uint32_t weight, price, divisor; };
struct Shop {std::string id,label; V position;float radius;bool remote_sell;std::vector<std::string> items;};
struct RepairPolicy {double power;float linear;uint32_t offset;float multiplier;std::vector<std::string> items;
  std::optional<uint32_t> cost(uint32_t price,uint32_t current,uint32_t maximum) const;};
struct CommercePolicy {uint32_t weight_limit,max_quantity,bulk_price,bulk_quantity;std::vector<ItemPrice> items;std::vector<Shop> shops;std::optional<RepairPolicy> repair;};
struct StorageService {std::string id,label;V position;float radius;bool remote;uint32_t fee;};
struct StoragePolicy {uint32_t capacity,coin_limit;std::vector<StorageService> services;};
struct FriendPolicy {uint32_t capacity,name_bytes,refresh_ticks;};
struct PartyPolicy {uint32_t capacity,name_bytes;double minimum,maximum;uint32_t gap,repeat_ticks;};
struct AppearanceRule {std::string item;uint32_t slot;};
struct Consumable {std::string item;uint32_t health,resource,delay_ms,cooldown_ms;};
struct TargetMarkerPart {
  uint32_t mode; // 0: terrain-conforming, 1: upright camera-facing
  V pivot;
  uint32_t width, height;
  std::vector<unsigned char> texture;
  std::vector<std::array<float,8>> vertices;
  std::vector<uint32_t> indices;
};
struct TargetMarker {
  float diameter_scale, height_scale, ground_lift;
  std::array<std::array<float,2>,2> bounds; // player/NPC: radius, height
  std::vector<TargetMarkerPart> parts;
};
struct EffectTexture {uint32_t width,height;std::vector<unsigned char> pixels;};
struct EffectBatch {
  uint32_t kind,texture,source_blend,destination_blend,flags;
  std::vector<float> records; // triangles:9 floats; camera-facing quads:11
};
// N3E4 (PQ-342): a camera-distance rule on a tail clip's particle batches of
// one material, the 2233 particle tick's live count (00592900): those batches
// hold emission candidates, one per birth sample a frame, and the client draws
// the ones a pool of `count` takes while the taken live ones are at most the
// target (render/effects.h).
struct ParticleThinning {
  uint32_t texture=0,source_blend=0,destination_blend=0,flags=0,count=0;
  float near=0,far=0;
  bool applies(const EffectBatch&b)const{return b.kind==1&&b.texture==texture&&b.source_blend==source_blend
                                               &&b.destination_blend==destination_blend&&b.flags==flags;}
};
struct EffectClip {
  bool scaled;
  uint32_t rate;
  std::vector<std::vector<EffectBatch>> frames;
  std::vector<ParticleThinning> thinning; // N3E4 and N3E5, an appearance tail clip's
};
// N3E2 (PQ-211): an effect drawn on an equipped appearance key, KO's hand-plug
// weapon effect (plug setter 0045c6e0 -> 00415370, drawn by 00415910). Every
// point is in the player's bind (model) space and rigid to `joint`.
struct AppearanceEffect {
  struct Copy {
    float jitter;          // times the signed jitter offset along the jitter axis
    uint32_t frame_offset; // added to the texture frame index
    std::vector<std::array<float,5>> vertices; // triangle list: position, UV
  };
  uint32_t key=0, joint=0;
  std::vector<uint32_t> frames; // effect texture IDs, in sequence
  float fps=0;
  uint32_t phase_steps=1; float phase_step=0; // start phase (rand % steps) x step seconds
  uint32_t source_blend=0, destination_blend=0, flags=0;
  std::vector<Copy> copies;
  float jitter_rate=0, jitter_amplitude=0; // offset (frac(t x rate) x 2 - 1) x amplitude
  std::array<V,2> jitter{};   // the unit jitter axis: origin, tip
  std::array<V,4> tail_box{}; // origin and its x, y, z edge ends
  float tail_low=0; uint32_t tail_steps=1; float tail_step=0; // edge fraction low + (rand % steps) x step
  uint32_t tails=0; std::string tail_clip;
  uint32_t trace_color=0; // carried for the swing trail; not drawn yet
  // N3E5 (PQ-376, D-200): 1298's alpha-list keys. With a sort record, each
  // copy sorts by the eye distance to sort_origin (bind space, rigid to the
  // joint) moved by its jitter, plus sort_bias, and each tail quad on its own.
  bool sorted=false; V sort_origin{}; float sort_bias=0;
};
// N3E3 (PQ-315): an emissive glow on an equipped appearance key's geometry,
// the 2233 client's equipment glow (0056ea30 each tick; 0042cf30 keeps the
// part material's emissive and picks MODULATE2X; a 2233/2145 addition, 1298
// has none). The lit colour of the key's triangles becomes
// min(1, lighting + colour x intensity) x modulate, as Direct3D adds a
// material's emissive to the vertex light and MODULATE2X doubles the texture
// product. The intensity is 1 (steady) or a pulse on the actor's own clock:
// t / rise up to rise, 1 up to hold, falling to 0 at fall, 0 to period, then
// again from 0.
struct AppearanceGlow {
  enum : uint32_t { STEADY = 0, PULSE = 1 };
  uint32_t key = 0;
  std::array<float,3> color{};
  float modulate = 1;  // 1, 2 or 4: the texture product's scale
  uint32_t wave = STEADY;
  float rise = 0, hold = 0, fall = 0, period = 0; // seconds; all 0 when steady
};
struct Effects {
  struct Binding {uint32_t kind;std::string key;uint32_t selector,anchor;std::vector<std::string> clips;};
  std::vector<EffectTexture> textures;
  std::map<std::string,EffectClip> clips;
  std::vector<Binding> bindings;
  std::vector<AppearanceEffect> appearance; // N3E2 to N3E5
  std::vector<AppearanceGlow> glow;         // N3E3 to N3E5
};
Effects load_effects(const std::filesystem::path& path);
struct SoundClip {uint32_t maximum;std::vector<float> samples;};
// Positional sound policy, package data (PQ-013, D-144). N3AU carries none and
// keeps these defaults; N3A2 appends them. Distances are displayed metres.
struct AudioSpatial {
  // 0: the camera hears; 1: the controlled character's position and facing,
  // with the camera as fallback while there is none.
  uint32_t listener=0;
  // Effect sounds start only while the camera eye is strictly nearer than
  // this; 0 disables the start test and effects take the cut-off below.
  float effect_distance=0,effect_distance_min=0,effect_distance_max=0;
  // Other positional sounds fade over the last 5 m before this listener
  // distance and are silent beyond it.
  float cutoff=30;
  // Full gain within this listener distance, inverse distance beyond it.
  float reference=2;
  // A player's integer option, clamped to the package bounds; none: default.
  float start_distance(std::optional<int> option={}) const {
    if(!option||effect_distance<=0)return effect_distance;
    return std::min(std::max(float(*option),effect_distance_min),effect_distance_max);
  }
};
struct Audio {
  std::vector<SoundClip> clips;
  std::map<std::string,uint32_t> bindings;
  std::map<std::pair<uint32_t,uint32_t>,std::vector<float>> timings;
  AudioSpatial spatial;
};
Audio load_audio(const std::filesystem::path& path);
struct Skill {
  std::string id,label,character_class;
  uint32_t level,cost,cast_ms,cooldown_ms,target,amount,survival,attribute,resistance,animation;
  float range;
  std::vector<std::string> weapons;
  std::string cast_effect,target_effect;
  std::vector<int> cast_joints;
  int target_joint;
};
// N3K2 (PQ-465, D-232): the package's range rule, read and bounded as the
// server reads it; the server checks a skill's range. Since PQ-466 (D-234)
// the client also tests the start limit before it sends a cast, as a hint
// only (render/skill_reach.h).
struct SkillReach {float start=0,hold=0;bool planar=false;};
// N3K3 (PQ-466, D-234): N3K2 with `notice`, the line the client posts when
// it sends nothing because the target is beyond the start limit; one `%s`
// takes the skill's label. N3K2: no notice.
// N3K4 (PQ-469, D-235): N3K3 with `failed` and `failed_color`, the line the
// client posts in that colour when the server refuses a skill it sent
// `out_of_range` (1298's 00586fa0 on Ebenezer's -103); one `%s` takes the
// skill's label. N3K2/N3K3: no failed line.
// N3K5 (PQ-479, D-243): N3K4 with `refusals`, the lines the client posts,
// each in its colour, when the server refuses at its acceptance a skill the
// client sent with that status, on a target the client saw as any actor (0),
// a player (1) or an NPC (2); one per status, never `out_of_range` (which has
// the failed line); one `%s` takes the skill's label. N3K2-N3K4: none.
struct SkillRefusal {std::string status;uint32_t target=0;std::string text;uint32_t color=0;};
struct Skills {std::string archetype,label;SkillReach reach;std::string notice;std::vector<Skill> entries;std::string failed;uint32_t failed_color=0;std::vector<SkillRefusal> refusals;};
// N3I1 package input binding (PQ-009, D-136): names from input_names.h.
struct InputBinding {std::string action,key;uint32_t require=0,forbid=0,flags=0;};
// N3I2 name display policy (PQ-014): the state at start and the actor classes
// the names_toggle action hides. N3I1 and releases without a table: every name
// shown, the toggle hides every class.
// N3I3 other-player label lifetime (PQ-169; KO's player-manager tick 00470900):
// a remote player's name is built once it is closer than `acquire` to the
// measuring point and dropped once it is farther than `release`; in between it
// stays as it was. `from` is the measuring point (KO: the local player's
// position, [00818794]+0x98, passed by 005c41b1). Exempt classes keep their
// name at any range. The package's camera draw limit still applies on top.
struct NameLifetimePolicy {
  enum From : uint32_t {self=0,camera=1};
  enum : uint32_t {party=1,all_exempt=1};
  uint32_t from=self;float acquire=0,release=0;uint32_t exempt=0;
  // Release rule. false (N3I3, KO's player loop): drop once farther than
  // `release`. true (KO's NPC loop, PQ-174): drop only while acquire <= d <
  // release; at `release` or farther the label stays as it was.
  bool band=false;
};
// N3I6 NPC label lifetime (PQ-174; KO's manager tick 00470900, NPC loop): an
// NPC's name is built once it is closer than `range.acquire` to the measuring
// point and dropped while it is at least `acquire` but closer than
// `range.release` (range.band); at `release` or farther it stays as it was.
// No name exists when an NPC enters view. `always`: the package's NPCs keep
// their name at any range and skip the camera distance limit (KO: NPC_Looks.tbl
// column 36, looks row +0x14c, = 1; 00470baa, 00459856). `drop_dead`: a dead
// NPC loses its name once its death clip has played (KO: state 5, +0x2fc, moves
// it to the corpse map, 00470b25, entered when the dying clip ends, 00457e57).
struct NpcNameLifetimePolicy {
  NameLifetimePolicy range;
  bool always=false,drop_dead=false;
};
// N3I4 party names (PQ-166; KO other-player +0x7dc, set on each listed member
// in view by the party window tick 0051c5b0): other players in the local
// player's party stay drawn while the toggle hides players (0046ea90), skip the
// style's camera distance limit (0046ea90, unless the zone's Zones.tbl column 23
// is 0) and take `color` (0xRRGGBB; KO 0046e840 sets 0xffffff00) when their
// label is refreshed.
struct PartyNamePolicy {
  bool while_hidden=false,beyond_distance=false;
  std::optional<uint32_t> color;
};
// N3I5 camera distance by class (PQ-173): a limit for self, other players or
// NPCs that replaces the nameplate style's `distance` (KO 0046ea90: 33.0,
// 006a4250, instead of 48.0, 006a40dc, for other players in zone key 0x140;
// self 0046b5a0 and NPC 00459820 always 48.0).
// N3I7 NPC info line (PQ-177; KO's NPC label refresh 00465070 formats
// "ID(%d) : TYPE(%d)", 006d44f0, in 0xff00ff00 when the local MyInfo authority
// byte +0x4a4 is 0, and 00459820 draws it above the name): `text` is the
// package's line, whose one `{id}` the client replaces with the NPC's entity
// id and whose optional `{state}` or `{state:FALLBACK}` (PQ-186) with the
// traced NPC's server AI state, or with the package's FALLBACK (default empty)
// while none was reported; `color` is 0xRRGGBB. The engine draws it only while
// the capability set the server projects (Registry.capabilities) holds
// server.inspect; a package can style the line but never enable it.
struct NpcInfoPolicy {
  uint32_t color=0;
  std::string text;
};
// The state placeholder in `text`: where it starts, its length and the
// package's fallback. FALLBACK is 1-16 printable ASCII bytes without braces.
struct NpcInfoState {size_t at=std::string::npos,size=0;std::string fallback;};
inline NpcInfoState npc_info_state(const std::string&text){
  NpcInfoState out;
  if(auto at=text.find("{state}");at!=std::string::npos){out.at=at;out.size=7;return out;}
  auto at=text.find("{state:");
  if(at==std::string::npos)return out;
  auto close=text.find('}',at);
  if(close==std::string::npos)return out;
  auto fallback=text.substr(at+7,close-at-7);
  if(fallback.empty()||fallback.size()>16||fallback.find_first_of("{}")!=std::string::npos)return out;
  for(unsigned char c:fallback)if(c<32||c>126)return out;
  out.at=at;out.size=close-at+1;out.fallback=fallback;
  return out;
}
// 1-64 printable ASCII bytes, exactly one `{id}`, at most one state
// placeholder and no other brace.
inline bool npc_info_text_valid(const std::string&text){
  if(text.empty()||text.size()>64)return false;
  for(unsigned char c:text)if(c<32||c>126)return false;
  auto at=text.find("{id}");
  if(at==std::string::npos)return false;
  std::string rest=text.substr(0,at)+"\n"+text.substr(at+4);
  if(auto state=npc_info_state(rest);state.at!=std::string::npos)rest.replace(state.at,state.size,"\n");
  return rest.find_first_of("{}")==std::string::npos;
}
// The line for one NPC: the package text with `{id}` replaced by the entity id
// (KO: the NPC's wire ID +0x474, 004650a4) and the state placeholder by the last
// state the server reported for it (KO: byte +0x7c0, set by opcode 0x5d at
// 005c6316), or by the package's fallback when there is none.
inline std::string npc_info_line(const NpcInfoPolicy&info,uint64_t entity,const std::string&state={}){
  auto text=info.text;auto at=text.find("{id}");
  if(at!=std::string::npos)text.replace(at,4,std::to_string(entity));
  if(auto placeholder=npc_info_state(text);placeholder.at!=std::string::npos)
    text.replace(placeholder.at,placeholder.size,state.empty()?placeholder.fallback:state);
  return text;
}
struct NameDisplayPolicy {
  enum : uint32_t {self=1,players=2,npcs=4,all=7};
  bool shown=true;uint32_t hides=all;
  std::optional<NameLifetimePolicy> lifetime;
  std::optional<PartyNamePolicy> party;
  std::array<std::optional<float>,3> distance; // self, other players, NPCs
  std::optional<NpcNameLifetimePolicy> npc_lifetime;
  std::optional<NpcInfoPolicy> npc_info;
  // N3I8 (PQ-178; KO's chat handler 005cac80 sets 0xffcd9bff, 005cb2f5): the
  // colour (0xRRGGBB) of a chat line the server marks as an operator's
  // (Chat.from_operator). The package styles the line; it cannot mark one.
  std::optional<uint32_t> operator_chat;
};
Skills load_skills(const std::filesystem::path&path);
// N3LK per-template NPC presentation (PQ-253, D-166): one entry per looks key a
// package's NPC templates use, each with its own model npc-looks-<i>.bin (N3NM)
// and the clip timing of its four states (idle, walk, attack, death). KO keeps
// one NPC_Looks row per NPC: NPC-in (005cd620) looks the record's resource ID
// up in the looks table (005cdc58) and hands the row to 0045dda0, which stores
// it at actor +0x274 and passes two of the row's files (the skeleton and
// animation columns, by inference) to 0041b260 and 0041bd30, which get them
// through resource managers that create an
// object only when the name's lookup finds none (0041d740, 0041e540); that one
// loaded object per file name is shared is an inference (reference-counted).
// `name_always` is the row's byte +0x14c (NPC_Looks.tbl column 36): the manager
// tick refreshes the NPC's name every tick (00470baa) and the name callback
// skips the camera distance test (00459856).
inline constexpr uint32_t MAX_NPC_LOOKS = 128;
inline constexpr uint64_t NPC_LOOKS_TEXTURE_BYTES = 96ull << 20, NPC_LOOKS_MODEL_BYTES = 192ull << 20;
struct NpcLooks {
  std::string key;
  bool name_always = false;
  std::array<Clip, 4> clips;
  bool materials = false;  // the model is N3MM or N3MI (engine 39, PQ-265): RGBA atlas and render runs
  bool influences = false;  // the model is N3NI or N3MI (engine 40, PQ-283): an influence table
};
// N3AT attached characters (PQ-328, D-186): a model drawn on every player
// whose public appearance keys include the entry's key, placed on the wearer's
// skin joint `joint` at `scale`, playing its own clip for the wearer's state
// (idle, walk, attack, death, as a looks model's four), and lit by a pulse on
// one clock per wearer. A 2233/2145 addition: the 2233 client's CPlayerWing
// (0056a710, 00569590; KO 1298 has none); which items attach what, where and
// how they light is package data. The model is attachment-<i>.bin in a looks
// model format (N3NM; N3MM at engine 39; N3NI, N3MI at 40).
//
// A PLUG entry (PQ-317, D-187) is a skeletal hand plug, the 2233 client's
// CN3ChrTypePlug: the model sits at the joint times `placement` (the plug
// matrix, 0042d800), never optional, lit or pulsed, and plays its own clock
// with the slot `clip_map` names for the wearer's drawn clip (0042df00,
// 00432760). Kinds: 0 a wearer pose state (0-9), 1 a combat-animation clip,
// 2 a skill animation.
struct PlugClip {
  static constexpr uint32_t STATE = 0, COMBAT = 1, SKILL = 2;
  uint32_t kind = 0, id = 0, slot = 0;
  bool once = false;
};
struct Attachment {
  static constexpr uint32_t OPTIONAL = 1, EMISSIVE = 2, PLUG = 4;
  uint32_t key = 0, joint = 0, group = 0, flags = 0;
  float scale = 1, modulate = 1;
  uint32_t lit = 0;  // the leading indices drawn with the shade
  std::array<Clip, 4> clips;
  bool materials = false, influences = false;
  // PLUG only: rows of a 3x4 matrix (model frame in the joint's, column
  // vectors), and the clip map.
  std::array<float, 12> placement{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0};
  std::vector<PlugClip> clip_map;
};
struct Attachments {
  bool per_attachment = false;  // each attachment advances its wearer's clock (00569590)
  float rise = 1, hold = 1, fall = 1, period = 1;
  std::array<float, 3> color{};
  std::vector<Attachment> entries;
};
inline constexpr uint32_t MAX_ATTACHMENTS = 16, MAX_ATTACHMENT_GROUPS = 16, MAX_PLUG_CLIPS = 64;
inline constexpr uint64_t ATTACHMENT_TEXTURE_BYTES = 32ull << 20, ATTACHMENT_MODEL_BYTES = 64ull << 20;
struct Release {
  std::string game, version, hash;
  std::filesystem::path root;
  std::vector<EditProperty> editing;
  std::optional<std::vector<Clip>> animation;
  std::vector<NpcLooks> npc_looks; // N3LK, engine 38; entry i's model is npc-looks-<i>.bin
  std::optional<std::array<uint64_t, 10>> thresholds;
  std::optional<CombatAnimation> combat_animation;
  std::vector<Consumable> consumables;
  bool rest = false;
  bool presentation = false;
  bool loot_model = false;
  std::optional<float> loot_open_radius;
  std::optional<TargetMarker> target_marker;
  std::optional<Effects> effects;
  std::optional<PostProcess> postprocess;
  std::optional<Audio> audio;
  bool front_end = false;  // front-end.bin (N3FE, engine 42, spec 11); load_front_end reads it
  std::optional<Skills> skills;
  std::optional<std::vector<InputBinding>> input;
  NameDisplayPolicy names;
  bool world = false;
  bool world_chunked = false;  // world.bin is N3W2
  bool world_textures = false; // world-textures.bin (N3WT), exactly with N3W2 (PQ-233)
  bool world_overlay = false;  // world-overlay.bin (N3WO, PQ-387): with a world and exploration
  bool render_detail = false;
  bool locomotion = false;
  bool ready_pose = false;
  bool requested_respawn = false;
  uint32_t protocol = 1;
  uint32_t npc_health = 1;
  float claim_radius=3;
  std::optional<InventoryPolicy> inventory;
  std::optional<ItemHeads> item_heads;
  std::optional<StoragePolicy> storage;
  bool storage_auth=false;
  bool equipment_stats=false;
  std::map<std::string,std::array<uint32_t,11>> item_stats;
  std::optional<FriendPolicy> friends;
  std::optional<PartyPolicy> party;
  std::optional<EquipmentPolicy> equipment;
  std::vector<AppearanceRule> appearance;
  std::optional<Attachments> attachments;  // N3AT (PQ-328)
  std::optional<CommercePolicy> commerce;
  std::optional<Exploration> exploration;
  std::optional<MovementConfig> movement;
  CameraConfig camera;
  std::optional<MeleeConfig> melee;
  PickPolicy pick;
};
Release load_release(const std::filesystem::path &root);
PostProcess load_postprocess(const std::filesystem::path &path);
struct Node {
  bool operator==(const Node &) const = default;
  int parent;
  V t, s;
  Q q;
};
struct Joint {
  bool operator==(const Joint &) const = default;
  uint32_t node;
  M inverse;
};
struct Key {
  float time;
  Q value;
};
struct Track {
  uint32_t node, path;
  std::vector<Key> keys;
};
struct Vertex {
  bool operator==(const Vertex &) const = default;
  V p, n;
  std::array<float, 2> uv;
  std::array<uint32_t, 4> joints;
  Q weights;
  // Further influences past the four slots (N3NI / N3MI looks models,
  // PQ-283): Scene::influences[first_influence, first_influence + influences).
  uint32_t first_influence = 0, influences = 0;
};
// A further joint influence of a vertex (PQ-283, D-176; tools/assetc/gltf.py
// N3SI). KO's CPU skinning 00419f00 sums every influence of a vertex, however
// many its skin load 004286f0 read.
struct Influence {
  bool operator==(const Influence &) const = default;
  uint32_t joint;
  float weight;
};
// One run of an N3MM looks model's indices drawn with one render state
// (PQ-265, D-173; tools/assetc/gltf.py N3SM). KO's part renderer 00412570
// draws each character part with its material's flags: alpha blending with
// the material's two factors, cull off, lighting off (n3e carries these three;
// KO's fog-off flag is refused by the converter); alpha test is
// on for every part (0043ade0), so a texel of alpha 0 is never drawn.
struct MaterialRun {
  static constexpr uint32_t BLEND = 1, DOUBLE_SIDED = 2, UNLIT = 4;
  uint32_t first = 0, count = 0, flags = 0;
  float alpha_reference = 0;  // drawn only where the texture alpha is above it
  uint32_t source = 0, destination = 0;  // tools/assetc/gltf.py BLEND_FACTORS indices
};
struct Scene {
  uint32_t width, height, attachment;
  uint32_t channels = 3;  // 3: RGB atlas; 4: RGBA (N3MM)
  std::vector<unsigned char> texture;
  std::vector<MaterialRun> runs;  // N3MM only; empty: one opaque draw
  std::vector<Node> nodes;
  std::vector<Joint> joints;
  std::vector<Track> tracks;
  std::vector<Vertex> vertices;
  std::vector<Influence> influences;  // N3NI / N3MI only: further influences, by vertex
  std::vector<uint32_t> indices;
  V scale;
  Collision collision;
  std::vector<Node> sample(float time) const;
  V joint_position(const std::vector<Node>&pose,unsigned joint) const;
  // The joint's posed model-space matrix with the instance scale (PQ-328):
  // instance x the joint node's accumulated TRS, column-major.
  M joint_matrix(const std::vector<Node>&pose,unsigned joint) const;
  // Skinned mesh vertices followed by the three attachment-marker vertices.
  std::vector<float> skin(const std::vector<Node> &pose) const;
  std::vector<float> skin(const std::vector<Node> &pose, std::span<const uint32_t> active_indices) const;
  // skin(sample(time)) followed by the collision hull as a flat stand-in surface.
  std::vector<float> animate(float time) const;
  bool compatible(const Scene &other) const;
  float ground_height(float x, float z) const;
};
Scene load_scene(const Release &release, const std::string &name = "scene.bin");
// One looks entry's model (N3NM; N3MM at engine 39; N3NI, N3MI at 40): four scenes, one per
// state, sharing one skeleton. Only the first carries the atlas, the mesh and
// the render runs; the others hold the nodes, joints and their own tracks,
// which is all a pose sample reads.
std::vector<Scene> load_npc_looks(const Release &release, size_t index);
// Attachment entry i's model (PQ-328), read as a looks model; its lit index
// count must fit the mesh and, with render runs, end on a run.
std::vector<Scene> load_attachment(const Release &release, size_t index);
// Skinned vertices (8 floats: position, normal, uv) carried into another
// frame (PQ-328): each position scaled by `scale` then through `m`, each normal
// through `m`'s inverse transpose.
void transform_skinned(std::vector<float> &vertices, const M &m, float scale);
// A plug entry's placement rows (r00 r01 r02 t0, r10 .., r20 ..) as a
// column-major matrix (PQ-317), and the column-major product a x b.
M placement_matrix(const std::array<float, 12> &rows);
M multiply(const M &a, const M &b);
Collision load_collision(const std::filesystem::path &path);
// A package's static world: the visible map geometry and its own atlas, in one
// buffer uploaded once. Separate from Scene because it is never posed, never
// skinned and carries two texture layers per vertex.
struct WorldLevel { float distance; uint32_t first, count; };
struct MeshControl { float distance; uint32_t vertices; };
struct MeshSplit { uint32_t indices, changes, vertices, first, grouped, target; };
struct ProgressiveMesh {
  uint32_t base=0, vertices=0, indices=0, maximum=0, step=0;
  std::vector<MeshControl> controls;
  std::vector<MeshSplit> splits;
  std::vector<uint32_t> edits;
};
struct WorldParent { V position; float distance_radius; V center; float radius; };
struct TerrainDetail {
  V origin{};
  float patch_size=0, far_factor=0, bias=0;
  uint32_t minimum=0, band=0, width=0;
};
// D-201 (PQ-379): an N3L4 / N3W3 alpha part (flag bit 4) is left out of the
// world pass and drawn in the frame's one far-to-near alpha pass, keyed by the
// eye distance to `sort_point`, with these blend factors (Direct3D numbering,
// 1..10) and state bits (1 blend, 0x40 unlit, 0x80 diffuse alpha, 0x100 no
// depth write, 0x400 no depth test; fog and culling stay no_fog, two_sided).
struct WorldAlpha { uint32_t source=0, destination=0, state=0; V sort_point{}; };
inline constexpr uint32_t WORLD_ALPHA_PART = 16;
inline constexpr uint32_t WORLD_ALPHA_STATES = 0x1 | 0x40 | 0x80 | 0x100 | 0x400;
// D-202 (PQ-382): an N3L5 / N3W4 part that is not an alpha part may be cut only
// where its texture's 8-bit alpha is 0 (bit 5; otherwise below one half) and
// drawn without light (bit 6).
inline constexpr uint32_t WORLD_CUT_ZERO = 32;
inline constexpr uint32_t WORLD_UNLIT = 64;
// D-203 (PQ-388): an N3W5 vertex whose second slot is this is a single-layer
// unlit vertex: drawn as its first layer's texel, without a second layer or
// light. The native texture remaps keep it.
inline constexpr float WORLD_UNLIT_VERTEX = -1.f;
// D-212 (PQ-394): an N3W6 kind 0 or 1 part with flag bit 7 carries a texture
// sequence after its alpha record: u32 frame count, f32 fps, u32 slot per frame.
// Frame k draws its slot in place of the first-layer slot of the part's
// vertices. `index` is the client's running state (world_lod::sequence_advance).
inline constexpr uint32_t WORLD_SEQUENCE_PART = 128;
inline constexpr uint32_t WORLD_SEQUENCE_FRAMES_MIN = 2, WORLD_SEQUENCE_FRAMES_MAX = 64;
inline constexpr float WORLD_SEQUENCE_FPS_MAX = 1000.f;
struct WorldSequence { std::vector<float> slots; float fps=0; float index=0; uint32_t advances=0; };
// N3W2, N3W3 (D-201), N3W4 (D-202), N3W5 (D-203) and N3W6 (D-212): the chunked
// world magics.
inline bool world_chunk_magic(std::string_view magic) {
  return magic == "N3W2" || magic == "N3W3" || magic == "N3W4" || magic == "N3W5" || magic == "N3W6";
}
struct WorldPart {
  V center; float radius, scale; bool no_fog, mirrored, radial_cull;
  std::vector<WorldLevel> levels;
  uint32_t kind=0, parent=0, patch_x=0, patch_z=0;
  bool two_sided=false, cut_zero=false, unlit=false;
  ProgressiveMesh progressive;
  std::optional<WorldAlpha> alpha;
  std::optional<WorldSequence> sequence;
};
// A self-contained piece of the world: its own vertices, chunk-local indices,
// parents and parts. N3W1 loads as one unbounded chunk; each N3W2 chunk
// (PQ-231) has a box covering every part sphere it holds, culled first.
struct WorldChunk {
  uint32_t x=0, z=0;                   // grid cell (N3W2)
  bool bounded=false;
  bool resident=true;                  // false: a streamed chunk not loaded (PQ-232)
  V lo{}, hi{};
  std::vector<WorldPart> parts;
  std::vector<WorldParent> parents;
  std::vector<float> vertices;         // WORLD_FLOATS per vertex
  std::vector<uint32_t> indices;
};
struct WorldMesh {
  TerrainDetail terrain;
  // N3W1's atlas; zero and empty for N3W2, whose textures are N3WT (PQ-233).
  uint32_t width = 0, height = 0;  // atlas size
  uint32_t cell = 0, pad = 0;      // atlas grid: cell stride and its wrapped border
  std::vector<unsigned char> texture;  // RGBA
  std::vector<WorldChunk> chunks;
};
// position, normal, two UV layers and the atlas slot each layer samples. UVs
// are cell-local and may leave [0, 1]: a surface tiles inside its own cell.
// Most spawn points (N3G2/N3G3), reference NPC slots (N3N2/N3N3) and editing
// spawn targets one package carries; server/src/rules.rs MAX_SPAWNS (PQ-250).
inline constexpr uint32_t MAX_SPAWNS = 2048;
inline constexpr int WORLD_FLOATS = 12;
WorldMesh load_world(const Release &release);
// N3W2 streaming (PQ-232): where each chunk body lies in world.bin, so a chunk
// can be read and validated on its own. `patches` is the number of terrain
// patches whose centre falls in the chunk's cell: the chunk must hold exactly
// those, so coverage is checked chunk by chunk.
struct WorldChunkEntry { uint32_t x=0, z=0; V lo{}, hi{}; uint64_t offset=0, bytes=0; uint32_t patches=0; };
struct WorldTable {
  std::filesystem::path path;
  std::string version;  // N3W2, N3W3 with alpha parts (D-201), N3W4 (D-202), N3W5 (D-203), N3W6 (D-212)
  double ox=0, oz=0, size=0;
  uint32_t side=0;
  bool terrain=false;
  float slots=0;
  std::vector<WorldChunkEntry> entries;
};
// The header and chunk table of an N3W2 world, without any chunk body:
// every chunk is a placeholder (grid cell and box, resident = false).
WorldMesh load_world_index(const Release &release, WorldTable &table);
// One chunk body read from `file` (world.bin) and checked on its own: every
// per-chunk bound load_world applies. `work` receives its progressive split work.
WorldChunk load_world_chunk(std::istream &file, const WorldTable &table, const TerrainDetail &terrain,
                            size_t index, uint64_t *work = nullptr);
struct TextureMip { uint32_t width, height; std::vector<unsigned char> pixels; };
using TextureChain = std::vector<TextureMip>;
// N3WT (PQ-233): an N3W2 world's textures, authored RGBA8 mip chains as N3D1
// carries them. Levels point into `bytes` (the file, read once) rather than
// being copied; the uploader frees it.
inline constexpr uint32_t WORLD_TEXTURES = 4096;
inline constexpr uint32_t WORLD_TEXTURE_LEVELS = 12;
inline constexpr uint64_t WORLD_TEXTURE_PIXELS = 384ull * 1024 * 1024;
inline constexpr uint32_t WORLD_TEXTURE_BANK_LAYERS = 2048;  // also the slot encoding's stride
inline constexpr uint32_t WORLD_TEXTURE_BANKS = 8;           // the shader's native samplers
inline constexpr uint64_t WORLD_TEXTURES_BOUND = 8 + uint64_t(WORLD_TEXTURES) * (4 + WORLD_TEXTURE_LEVELS * 8) + WORLD_TEXTURE_PIXELS;
struct WorldTextureLevel { uint32_t width, height; size_t offset; };
struct WorldTextures {
  std::vector<unsigned char> bytes;
  std::vector<std::vector<WorldTextureLevel>> chains;
  uint64_t pixels = 0;
};
// One array bank: textures with one top size and level count, at most `layers`
// of them. Groups in (width, height, levels) order, each split into banks of
// `layers`, textures in index order.
struct WorldTextureBank { uint32_t width, height, levels; std::vector<uint32_t> textures; };
std::vector<WorldTextureBank> world_texture_banks(const WorldTextures &textures, uint32_t layers);
// Every bound above, banks counted at WORLD_TEXTURE_BANK_LAYERS.
WorldTextures load_world_textures(const Release &release);
// N3WO (PQ-387, D-204): maps blended over the near terrain patches around the
// eye (tools/assetc/world_overlay.py). Block (bx, bz), `width` a side, covers
// terrain tiles [bx * block_tiles, +block_tiles) x [bz * block_tiles, ...) in
// the terrain policy's tile grid (patch_tiles a patch side); its map is
// `levels` RGBA8 levels from side x side, level 0 at `maps[bz * width + bx]`
// in `bytes`, the levels back to back.
inline constexpr uint32_t WORLD_OVERLAY_PATCH_TILES = 64, WORLD_OVERLAY_BLOCKS_PER_PATCH = 4;
inline constexpr uint32_t WORLD_OVERLAY_WINDOW = 2, WORLD_OVERLAY_LAYERS = 256;
inline constexpr uint32_t WORLD_OVERLAY_WIDTH = 4096, WORLD_OVERLAY_MAPS = 65536;
inline constexpr uint64_t WORLD_OVERLAY_PIXELS = 256ull * 1024 * 1024;
inline constexpr uint64_t WORLD_OVERLAY_BOUND = 40 + uint64_t(WORLD_OVERLAY_MAPS) * 8 + WORLD_OVERLAY_PIXELS;
struct WorldOverlay {
  uint32_t patch_tiles = 0, block_tiles = 0, window = 0, side = 0, cell = 0, inset = 0, levels = 0, width = 0;
  std::vector<unsigned char> bytes;
  std::map<uint32_t, size_t> maps;
  // Blocks a patch side, and the window's array layers.
  uint32_t per_patch() const { return patch_tiles / block_tiles; }
  uint32_t layers() const { return (2 * window + 1) * (2 * window + 1) * per_patch() * per_patch(); }
};
// Every bound world_overlay.py checks, and its grid against the terrain policy.
WorldOverlay load_world_overlay(const Release &release, const TerrainDetail &terrain);
struct DetailMesh { Scene scene; std::vector<uint32_t> slots; };
struct DetailAttachment { DetailMesh mesh; WorldPart part; };
// N3D3 (PQ-348, D-191): an appearance entry's render state, MaterialRun's
// fields without a range (flags BLEND and DOUBLE_SIDED, no UNLIT; the alpha
// reference; blend factors). An N3D2 entry has none and draws as every key
// did before.
struct AppearanceState {uint32_t flags=0;float alpha_reference=0;uint32_t source=0,destination=0;};
struct AppearanceMesh {std::vector<uint32_t> replaces;std::vector<DetailMesh> levels;std::optional<AppearanceState> state;};
struct RenderDetail {
  std::array<std::array<float,4>,4> thresholds;
  std::array<uint32_t,3> workload;
  uint32_t world_textures;
  float radius;
  std::vector<TextureChain> textures;
  std::vector<DetailMesh> levels;
  std::vector<DetailAttachment> attachments;
  std::vector<AppearanceMesh> appearances;
};
RenderDetail load_render_detail(const Release &release, const Scene &skeleton);
struct HudTexture {
  uint32_t width, height;
  std::vector<unsigned char> pixels;
};
struct HudRecord {
  uint32_t kind, texture, color, target, align;
  uint32_t control = 0, states = 15, text_flags = 0, panel = 0;
  std::array<float, 2> anchor;
  std::array<float, 4> rect, uv;
  std::string binding, text;
};
struct HudControl {
  // Visibility: always/hidden/running/walking. Selection: none/always/primary/moving.
  uint32_t parent, visibility, selection, enabled;
};
struct HudIcon {
  uint32_t texture;
  std::array<float,4> uv;
};
struct HudPortrait { float yaw, pitch, framing; };
// N3HC draggable panel: a left press on the handle (where no control takes the
// click) moves every panel of the group; snap pulls the bounds to a horizontal
// viewport edge within that many pixels; a non-empty key saves the position.
struct HudMovable {uint32_t panel,group;std::array<float,2> anchor;std::array<float,4> handle,bounds;uint32_t snap;std::string key;};
// N3HD overview map: u=(x-origin.x)/extent, v=(z-origin.z)/extent. A zoom Z
// shows 1/Z of the map centred on the player (clamped at edges); colours are
// self arrow, hostile NPC, other NPC, party member, other player.
struct HudMinimap {uint32_t texture;std::array<float,2> origin;float extent,zoom,arrow_ratio,marker_outer,marker_inner;std::array<uint32_t,5> colors;};
struct HudTooltip {HudIcon background;float width_padding,height_padding,gap;std::vector<std::array<float,2>> rows;};
struct NameFont {
  uint32_t texture, height, top;
  std::array<float,95> advances;
};
struct NameplateProfile {float height;uint32_t root;};
struct NameplateStyle {
  float distance, padding, gap, seated_fraction;
  std::array<uint32_t,3> colors; // self, other player, NPC
  std::array<NameFont,2> fonts; // regular, bold; printable ASCII atlas
  std::array<NameplateProfile,2> profiles; // player, NPC
};
// PQ-407 (D-210): the optional message block (N3HM) at the end of any HUD: the
// rows the message line keeps and draws before the `combat` record's own lines,
// and the colour of each message kind (ARGB, as a text record's colour).
// PQ-408 (D-211): the optional scroll block (N3HS) after it: the message
// records and wrapped lines kept, the scroll bar's line and page steps and its
// buttons' hold delay (seconds). The HUD then holds one each of the click
// records `message_up`, `message_down` and `message_track` and the image
// `message_thumb`, the thumb inside the track and shorter than it.
struct HudMessageScroll {
  uint32_t records = 1, lines = 1, line_step = 1, page_step = 1;
  float repeat = 0.5f;
};
struct HudMessages {
  uint32_t rows = 1, refusal = 0, notice = 0;
  std::optional<HudMessageScroll> scroll;
};
struct Hud {
  bool dialogs = false, hotbar = false;
  std::optional<HudMessages> messages;
  // N3HA/N3HB scale policy: false fits the 1024x768 reference to the viewport;
  // true keeps authored pixel sizes and only resolves anchors.
  bool pixel_scale = false;
  std::vector<HudMovable> movables;
  std::optional<HudMinimap> minimap;
  uint32_t font;
  float font_advance = 0;
  uint32_t font_height = 0, font_top = 0;
  float target_health, level_xp;
  std::vector<HudTexture> textures;
  std::vector<HudRecord> records;
  std::vector<HudControl> controls;
  std::map<std::string,HudIcon> item_icons, action_icons;
  std::array<uint32_t,3> cooldown_frames{};
  uint32_t cooldown_color=0;
  std::map<std::string,HudPortrait> portraits;
  std::optional<HudTooltip> tooltip;
  std::optional<NameplateStyle> nameplates;
};
Hud load_hud(const Release &release);
// Spec 11's KO front end (content/front-end.md, tools/assetc/ko_front_end.py).
inline constexpr size_t kFrontEndFile = 64 * 1024 * 1024;
enum class FrontAction : uint32_t {
  none, login, exit, login_group, realm_group, realm_list, realm_connect, notice, select_prev,
  select_next, back, char_info, create_confirm, name_field, char_view, class_desc, progress,
  version, info, message, ok, count
};
enum class FrontScreen : uint32_t { login, select, create, loading, message, count };
enum class FrontString : uint32_t { select_info, select_hint, class_name, class_desc, loading_info, version, count };
struct FrontNode {
  static constexpr uint32_t IMAGE = 0, TEXT = 1, BUTTON = 2, EDIT = 3, PROGRESS = 4, GROUP = 5, AREA = 6, LIST = 7;
  static constexpr uint32_t FIXED_ON = 1, FIXED_DISABLED = 2, FOREGROUND = 4;
  uint32_t kind = 0, parent = 0, flags = 0, mask = 15;
  FrontAction action = FrontAction::none;
  std::array<float, 4> rect{}, uv{};
  std::string id, text;
  uint32_t texture = 0, font = 0, color = 0, style = 0;
};
struct FrontFont {
  uint32_t texture = 0, pixels = 0, height = 0, top = 0;
  std::array<float, 95> advances{};
};
struct FrontLight {
  static constexpr uint32_t POINT = 1, SPOT = 2, DIRECTIONAL = 3;
  uint32_t kind = POINT;
  V diffuse{}, ambient{}, position{}, direction{};
  float range = 0, falloff = 0;
  std::array<float, 3> attenuation{};
  float theta = 0, phi = 0;
};
struct FrontCamera { V eye{}, at{}, up{}; float fov = 1, near_plane = .1f, far_plane = 100; };
struct FrontMesh {
  static constexpr uint32_t DOUBLE_SIDED = 1, ALPHA_TEST = 2;
  uint32_t texture = 0, flags = 0;
  V diffuse{}, ambient{};
  std::vector<float> vertices;  // position, normal, uv
  std::vector<uint32_t> indices;
};
struct FrontPlug { uint32_t joint = 0; FrontMesh mesh; };
// A scene's model: the first clip in `model`, each further clip's tracks after.
struct FrontScene {
  FrontCamera camera;
  std::vector<FrontLight> lights;
  V ambient{};
  Scene model;
  std::vector<std::vector<Track>> clips;  // clips[0] is model.tracks
  std::vector<FrontPlug> plugs;
};
struct FrontSlot { V position{}; float yaw = 0; V eye{}; FrontLight spot; };
struct FrontEnd {
  uint32_t character_slots = 0, canvas_width = 0, canvas_height = 0;
  std::vector<HudTexture> textures;
  std::vector<FrontFont> fonts;
  std::array<std::vector<FrontNode>, size_t(FrontScreen::count)> screens;
  std::array<std::string, size_t(FrontString::count)> strings;
  FrontScene intro, select;
  uint32_t backdrop = 0;
  std::array<float, 4> backdrop_rect{};  // 1024 x 768 units
  std::vector<FrontSlot> slots;
  std::vector<FrontMesh> hall;
};
FrontEnd load_front_end(const Release &release);
} // namespace n3e
