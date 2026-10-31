#include "render/feature_ui.h"
#include "render/portrait.h"
#include "render/loot_ui.h"
#include "render/item_wait.h"
#include "render/appearance.h"
#include "render/hud_layout.h"
#include "render/hud_text_layout.h"
#include "render/target_health.h"
#include <iostream>
#include <stdexcept>
#include <source_location>

void require(bool ok, std::source_location at=std::source_location::current()) { if (!ok) throw std::runtime_error("HUD state regression at line "+std::to_string(at.line())); }
int main(int argc, char **argv) {
  try {
    {
      // PQ-249: the target bar divides by a templated NPC's own maximum
      // (Entity.max_health), else by the package's NPC health.
      n3e::Entity templated;templated.set_health(3);templated.set_max_health(6);
      require(target_health_fraction(templated.health(),templated.max_health(),300.f)==.5f);
      n3e::Entity plain;plain.set_health(150);
      require(plain.max_health()==0&&target_health_fraction(plain.health(),plain.max_health(),300.f)==.5f);
      require(target_health_fraction(0,6,300.f)==0.f&&target_health_fraction(6,6,300.f)==1.f);
      require(target_health_fraction(5,0,0.f)==0.f);
      std::cout<<"PASS target bar: templated maximum 3/6, package maximum 150/300\n";
    }
    n3e::WorldState item_world;item_world.connected=true;item_world.world.set_session(4);item_world.world.set_self(9);
    n3e::Envelope swap;auto*q=swap.mutable_bag_request();q->set_request("swap-1");q->set_operation(1);q->set_expected_revision(7);q->set_instance(123);q->set_destination(2);
    ItemWait wait;require(wait.begin(swap,item_world,0));
    ++item_world.bag_responses;++item_world.storage_responses;
    item_world.item_result(false,"other","committed");item_world.item_result(true,"swap-1","committed");
    require(!wait.sync(item_world,1)&&bool(wait)&&!wait.begin(swap,item_world,1));
    auto retry=wait.sync(item_world,3);require(retry&&retry->SerializeAsString()==swap.SerializeAsString());
    item_world.item_result(false,"swap-1","use_pending");require(!wait.sync(item_world,4)&&bool(wait));
    item_world.item_result(false,"swap-1","committed");require(!wait.sync(item_world,5)&&!wait);
    // Cached replies from a previous attempt do not complete a new send.
    require(wait.begin(swap,item_world,6));require(!wait.sync(item_world,6)&&bool(wait));
    item_world.item_result(false,"swap-1","revision_conflict");require(!wait.sync(item_world,7)&&!wait);
    n3e::Envelope deposit;deposit.mutable_storage_request()->set_request("bank-1");deposit.mutable_storage_request()->set_operation(1);
    require(wait.begin(deposit,item_world,8));item_world.item_result(true,"bank-1","storage_pending");
    require(!wait.sync(item_world,9)&&bool(wait));item_world.item_result(true,"bank-1","locked");require(!wait.sync(item_world,10)&&!wait);
    require(wait.begin(deposit,item_world,11));item_world.world.set_session(5);require(!wait.sync(item_world,12)&&!wait);
    require(wait.begin(deposit,item_world,13));item_world.connected=false;require(!wait.sync(item_world,14)&&!wait);
    item_world.connected=true;require(wait.begin(swap,item_world,15));
    for(double now:{18,21,24}){auto resend=wait.sync(item_world,now);require(resend&&resend->SerializeAsString()==swap.SerializeAsString());}
    auto item_refresh=wait.sync(item_world,27);require(item_refresh&&item_refresh->has_bag_request()&&!item_refresh->bag_request().operation()&&!wait&&!wait.notice.empty());
    for(unsigned i=0;i<100;++i)item_world.item_result(false,"refresh","ok");require(item_world.item_results.size()==32);
    std::cout<<"PASS request-specific item completion, unrelated refreshes, exact bounded retries, pending/rejected responses and session recovery\n";
    n3e::Hud h{};
    // Hidden parent, visible child, overlapping walk/run, selected and disabled.
    h.controls = {{0,1,0,1}, {1,0,0,1}, {0,2,0,1}, {0,3,0,1},
                  {0,0,1,1}, {0,0,0,0}, {0,0,2,1}};
    auto record = [&](uint32_t id, uint32_t kind, uint32_t states, float x, const char *binding) {
      n3e::HudRecord q{}; q.control=id; q.kind=kind; q.states=states;
      q.rect={x,10,x+20,30}; q.binding=binding; h.records.push_back(q);
    };
    record(2,2,15,10,"hidden");
    record(3,2,15,50,"walk"); record(4,2,15,50,"run");
    record(5,2,15,90,"selected"); record(6,2,15,130,"disabled");
    record(7,2,15,170,"action");
    for (unsigned s=0;s<4;++s) record(7,0,1u<<s,170,"art");
    HudLayout v(std::move(h));
    require(v.hit(15,15,1026,768).empty());
    require(v.hit(55,15,1026,768)=="run");
    v.running=true;
    require(v.hit(55,15,1026,768)=="walk");
    require(v.hit(135,15,1026,768)=="panel");
    v.pointer(135,15,1026,768,true); require(!v.hovered && !v.pressed);
    require(v.state(5)==1 && v.state(6)==3);
    auto check_state = [&](unsigned expected) {
      unsigned visible=0;
      for (const auto &q:v.data.records) if (q.kind==0 && v.visible(q)) {
        ++visible; require(q.states==(1u<<expected));
      }
      require(visible==1 && v.state(7)==expected);
    };
    check_state(0); v.pointer(175,15,1026,768); check_state(2);
    v.pointer(175,15,1026,768,true); check_state(1);
    v.pointer(250,15,1026,768); check_state(0);
    v.pointer(175,15,1026,768); check_state(1);
    v.pressed=0; check_state(2);
    v.cancel_pointer(); check_state(0);
    v.primary_active=true; check_state(1);
    v.primary_active=false;
    v.pointer(55,15,1026,768,true); require(v.pressed==3);
    v.running=false; v.pointer(55,15,1026,768); require(v.pressed==0 && v.hovered==4);
    // Same selection under scaling and the half-open right/bottom edge.
    require(v.hit(27.5f,7.5f,513,384)=="run");
    require(v.hit(35,15,513,384).empty());
    v.cancel_pointer(); v.primary_active=false;
    std::erase_if(v.data.records, [](const auto &q) { return q.kind==0 && q.states==4; });
    v.pointer(175,15,1026,768);
    for(const auto &q:v.data.records) if(q.kind==0) require(!v.visible(q));
    // UIF dialogs share visibility between drawing and hits; a closed panel
    // cannot steal a click, and modal bounds cover underlying controls.
    n3e::Hud dialogs{};dialogs.dialogs=true;
    n3e::HudRecord root{};root.kind=2;root.states=15;root.rect={0,0,200,200};root.binding="action";root.text="panel";root.panel=1;
    dialogs.records.push_back(root);root.rect={10,10,50,30};root.text="bag:0";dialogs.records.push_back(root);
    root.rect={0,0,200,200};root.text="panel";root.panel=8;dialogs.records.push_back(root);
    root.rect={60,60,100,80};root.text="confirm";dialogs.records.push_back(root);
    HudLayout dialog_view(std::move(dialogs));
    require(dialog_view.hit(20,20,1024,768).empty());
    dialog_view.panels=3;require(dialog_view.hit(20,20,1024,768)=="bag:0");
    require(dialog_view.hit(120,120,1024,768)=="panel");
    dialog_view.panels|=256;require(dialog_view.hit(20,20,1024,768)=="panel");
    require(dialog_view.hit(70,70,1024,768)=="confirm");
    require(dialog_view.hit(35,35,512,384)=="confirm");
    std::cout << "PASS HUD hidden descendants/hits, exclusive modes, selected/disabled, pointer lifecycle and scale\n";
    {
      // Pixel policy: authored size at every viewport; anchors alone follow the edges.
      n3e::Hud pixel{};pixel.pixel_scale=true;
      n3e::HudRecord bar{};bar.kind=2;bar.states=15;bar.anchor={.5f,1};bar.rect={-513,-58,513,0};bar.binding="action";bar.text="bar";
      pixel.records.push_back(bar);HudLayout view(std::move(pixel));
      for(auto [w,h]:{std::pair{1024,768},std::pair{1280,1024},std::pair{1600,1200}}){
        auto r=view.rectangle(view.data.records[0],w,h);
        require(view.scale(w,h)==1&&r[0]==(w-1026)/2&&r[2]-r[0]==1026&&r[1]==h-58&&r[3]==h);
        require(view.hit(r[0]+1,r[1]+1,w,h)=="bar"&&view.hit(r[0]-1,r[1]+1,w,h).empty());
      }
      std::cout << "PASS HUD pixel scale keeps authored sizes and binary edge/center anchoring at 1024/1280/1600\n";
    }
    {
      // Draggable panels: controls take a press first; handles move their whole
      // group without a viewport clamp; the hotkey snaps to side edges; restore
      // clamps and treats (0,0) as the default.
      n3e::Hud d{};d.pixel_scale=true;d.dialogs=true;
      n3e::HudRecord art{};art.kind=0;art.states=15;art.rect={0,-145,541,0};art.anchor={0,1};art.panel=11;d.records.push_back(art);
      art.rect={0,-145,323,0};art.panel=12;d.records.push_back(art);
      n3e::HudRecord button{};button.kind=2;button.states=15;button.anchor={0,1};button.rect={0,-20,40,0};button.binding="action";button.text="chat_mode";button.panel=11;button.control=1;
      d.controls.push_back({0,0,0,1});d.records.push_back(button);
      art.anchor={0,0};art.rect={0,65,80,415};art.panel=13;d.records.push_back(art);
      d.movables.push_back({11,1,{0,1},{0,-22,84,-1},{0,-145,541,0},0,"chat"});
      d.movables.push_back({12,1,{0,1},{541,-22,626,-1},{541,-145,864,0},0,""});
      d.movables.push_back({13,2,{0,0},{0,65,57,90},{0,65,80,415},10,"hotkey"});
      HudLayout v(std::move(d));int w=1280,h=1024;
      v.pointer(10,h-10,w,h,true);require(v.pressed==1&&!v.begin_panel_drag(10,h-10,w,h));v.cancel_pointer();
      v.pointer(60,h-10,w,h,true);require(!v.pressed&&v.begin_panel_drag(60,h-10,w,h));
      v.drag_panels(-40,h-310,w,h);
      auto chat=v.movable_rectangle(v.data.movables[0],v.data.movables[0].bounds,w,h),msg=v.movable_rectangle(v.data.movables[1],v.data.movables[1].bounds,w,h);
      require(chat[0]==-100&&chat[1]==h-445&&msg[0]==chat[2]&&msg[1]==chat[1]);
      v.panel_drag.reset();
      require(v.begin_panel_drag(20,70,w,h));v.drag_panels(25,70,w,h);
      auto hot=v.movable_rectangle(v.data.movables[2],v.data.movables[2].bounds,w,h);require(hot[0]==0);
      v.drag_panels(1220,300,w,h);hot=v.movable_rectangle(v.data.movables[2],v.data.movables[2].bounds,w,h);require(hot[2]==w);
      v.drag_panels(900,300,w,h);hot=v.movable_rectangle(v.data.movables[2],v.data.movables[2].bounds,w,h);require(hot[2]<w-10);
      v.panel_drag.reset();
      auto saved=v.saved_positions(w,h);require(saved.size()==2&&saved.at("chat")==std::array<int,2>{-100,h-445});
      HudLayout fresh(v.data);fresh.restore_positions(saved,w,h);
      chat=fresh.movable_rectangle(fresh.data.movables[0],fresh.data.movables[0].bounds,w,h);require(chat[0]==0&&chat[1]==h-445);
      HudLayout zero(v.data);zero.restore_positions({{"chat",{-5,-5}},{"hotkey",{400,5000}}},w,h);
      chat=zero.movable_rectangle(zero.data.movables[0],zero.data.movables[0].bounds,w,h);require(chat[0]==0&&chat[1]==h-145);
      hot=zero.movable_rectangle(zero.data.movables[2],zero.data.movables[2].bounds,w,h);require(hot[0]==400&&hot[3]==h);
      std::cout << "PASS HUD draggable groups, control precedence, unclamped drag, hotkey edge snap and clamped restore with (0,0) default\n";
    }
    FeatureUI features; n3e::Release rules{}; n3e::WorldState world{};
    world.bag.set_capacity(32);world.bag.set_revision(7);world.storage.set_revision(9);
    for(int i=0;i<32;++i)world.bag.add_slots();
    auto*item=world.bag.mutable_slots(0);item->set_instance(111);item->set_item("original:blade");item->set_quantity(1);
    world.bag.add_equipment();
    features.act("bag:0",rules,world,nullptr,false,false);require(!features.prompt);
    features.act("gear:0",rules,world,nullptr,false,false);
    require(features.prompt&&features.prompt->prefix=="/equip 1 1"&&features.prompt->mode==2&&features.prompt->bag==7);
    features.clear();features.act("bag:0",rules,world,nullptr,false,false);
    item->set_instance(222);features.act("gear:0",rules,world,nullptr,false,false);
    require(!features.prompt); // Stale selected serial must not operate on its replacement.
    features.clear();features.act("bag_next",rules,world,nullptr,false,false);
    features.act("bag:0",rules,world,nullptr,false,false);require(features.index==28);
    features.act("bag_next",rules,world,nullptr,false,false);require(features.bag_page==1);
    features.act("deposit_coins",rules,world,nullptr,true,false);
    require(features.prompt->prefix=="/bankcoins "&&features.prompt->mode==1&&features.prompt->bank==9);
    features.clear();features.bag_page=0;world.storage.set_capacity(192);for(int i=0;i<192;++i)world.storage.add_slots();
    features.act("bank_next",rules,world,nullptr,true,false);features.act("bag:0",rules,world,nullptr,true,false);
    features.act("bank:0",rules,world,nullptr,true,false);require(features.prompt->prefix=="/deposit 1 25 ");
    require(!features.confirm(world,"/admin")&&features.prompt.has_value());
    world.bag.set_revision(8);require(!features.confirm(world,"1")&&!features.prompt);
    features.ask(world,"Coins","/bankcoins ","1",1);require(!features.confirm(world,"0"));
    require(features.confirm(world,"25")==std::optional<std::string>("/bankcoins 25"));
    dialog_view.input_panel=8;require(dialog_view.hit(20,20,1024,768)=="panel");
    require(dialog_view.hit(300,300,1024,768).empty());
    std::cout<<"PASS UIF slot selection, stale serial rejection, bounded pages and transaction confirmation intents\n";
    // Stock pages must select absolute catalog indices, clear stale/off-page
    // offers, and remain independent of the player's inventory page.
    FeatureUI stock; n3e::Shop shop{};shop.id="original:store";
    for(unsigned i=0;i<25;++i)shop.items.push_back("offer"+std::to_string(i));
    stock.act("buy",rules,world,&shop,false,true);require(!stock.prompt);
    stock.act("offer:23",rules,world,&shop,false,true);
    stock.act("buy",rules,world,&shop,false,true);require(stock.prompt->prefix=="/buy 24 2 ");
    stock.act("offer_next",rules,world,&shop,false,true);require(!stock.prompt&&stock.selected.empty());
    stock.update(rules,world,&shop);require(stock.values.at("offer_page")=="2"&&stock.values.at("offer:0")=="offer2"&&!stock.values.contains("offer:1"));
    stock.act("bag_next",rules,world,&shop,false,true);require(stock.bag_page==1&&stock.offer_page==1);
    stock.act("offer:0",rules,world,&shop,false,true);require(stock.offer==24);
    stock.act("buy",rules,world,&shop,false,true);require(stock.confirm(world,"1")==std::optional<std::string>("/buy 25 2 1"));
    stock.act("offer:1",rules,world,&shop,false,true);stock.act("buy",rules,world,&shop,false,true);require(!stock.prompt);
    for(unsigned i=0;i<20;++i)stock.act("offer_next",rules,world,&shop,false,true);
    require(stock.offer_page==11);stock.update(rules,world,&shop);require(stock.values.at("offer_page")=="12"&&!stock.values.contains("offer:0"));
    for(unsigned i=0;i<20;++i)stock.act("offer_prev",rules,world,&shop,false,true);
    require(stock.offer_page==0);stock.act("offer:0",rules,world,&shop,false,true);
    auto other_shop=shop;other_shop.id="original:other";
    stock.act("buy",rules,world,&other_shop,false,true);require(!stock.prompt&&stock.selected.empty());
    stock.act("offer:0",rules,world,&other_shop,false,true);stock.act("buy",rules,world,&other_shop,false,true);
    stock.update(rules,world,nullptr);require(!stock.prompt&&stock.selected.empty());
    std::cout<<"PASS shop stock indices, partial/empty pages, boundaries, independent bag pages and stale offer rejection\n";
    FeatureUI drag;world.connected=true;world.world.set_self(5);world.world.set_session(6);
    rules.inventory=n3e::InventoryPolicy{};
    rules.inventory->items.push_back({"original:blade","Blade",1,80,0});
    rules.inventory->items.push_back({"offer0","Stack",99,0,0});
    auto start=[&](const std::string&key,unsigned panel){require(drag.begin_drag(key,panel,world,&shop));};
    start("bag:0",1);require(drag.drop("gear:0",1,rules,world,&shop)=="/equip 1 1"&&!drag.prompt);
    start("bag:0",1);require(!drag.drop("bag:0",1,rules,world,&shop));
    start("bag:0",1);require(!drag.drop("panel",1,rules,world,&shop));
    start("bag:0",1);require(!drag.drop("bank:0",4,rules,world,&shop));
    start("bag:0",1);world.bag.set_revision(9);require(!drag.drop("bag:1",1,rules,world,&shop));
    start("bag:0",1);world.bag.mutable_slots(0)->set_instance(333);require(!drag.drop("bag:1",1,rules,world,&shop));
    start("bag:0",1);++drag.bag_page;require(!drag.drop("bag:1",1,rules,world,&shop));drag.bag_page=0;
    start("bag:0",1);world.world.set_session(7);require(!drag.drop("bag:1",1,rules,world,&shop));
    start("bag:0",1);world.connected=false;require(!drag.drop("bag:1",1,rules,world,&shop));world.connected=true;
    require(!drag.begin_drag("bag:1",1,world,&shop)&&!drag.begin_drag("offer:24",3,world,&shop));
    start("bag:0",3);require(drag.drop("bag:1",3,rules,world,&shop)=="/swap 1 2");
    start("offer:0",3);require(!drag.drop("bag:2",3,rules,world,&shop)&&drag.prompt);
    require(drag.confirm(world,"2",&shop)=="/buy 1 3 2");
    start("offer:0",3);require(!drag.drop("bag:2",3,rules,world,&other_shop));
    start("offer:0",3);require(!drag.drop("bag:2",3,rules,world,&shop)&&drag.prompt);
    require(!drag.confirm(world,"2",&other_shop)&&!drag.prompt);
    drag.offer_page=1;start("offer:0",3);require(drag.drop("bag:2",3,rules,world,&shop)=="/buy 25 3 1");
    start("bag:0",3);require(drag.drop("offer:23",3,rules,world,&shop)=="/sell 1 1");
    drag.bank_page=1;start("bag:0",4);require(drag.drop("bank:0",4,rules,world,&shop)=="/deposit 1 25 1");
    world.storage.mutable_slots(24)->CopyFrom(world.bag.slots(0));
    start("bank:0",4);require(drag.drop("bank:1",4,rules,world,&shop)=="/bankmove 25 26");
    start("bank:0",4);require(drag.drop("bag:1",4,rules,world,&shop)=="/withdraw 25 2 1");
    world.storage.mutable_slots(24)->set_item("offer0");world.storage.mutable_slots(24)->set_quantity(3);
    start("bank:0",4);require(!drag.drop("bag:1",4,rules,world,&shop)&&drag.prompt);
    world.storage.set_revision(10);require(!drag.confirm(world,"2"));
    world.storage.mutable_slots(24)->Clear();
    std::cout<<"PASS drag intents, page/serial/revision/session/service guards, invalid-drop cancellation and stack prompts\n";
    rules.equipment=n3e::EquipmentPolicy{};
    rules.equipment->slots={"Right","Left"};
    rules.equipment->items.push_back({"original:blade",3,0,0,0,{},true});
    rules.equipment->items.push_back({"original:twohand",1,2,0,0,{},true});
    world.bag.mutable_equipment()->Clear();world.bag.add_equipment();world.bag.add_equipment();
    require(drag.right_click("bag:0",rules,world)=="/equip 1 1");
    world.bag.mutable_equipment(0)->CopyFrom(world.bag.slots(0));
    require(drag.right_click("bag:0",rules,world)=="/equip 1 2");
    world.bag.mutable_equipment(0)->set_item("original:twohand");
    require(drag.right_click("bag:0",rules,world)=="/equip 1 1");
    require(drag.right_click("gear:0",rules,world)=="/unequip 1 2");
    require(!drag.right_click("bag:1",rules,world));
    rules.equipment.reset();world.bag.mutable_equipment(0)->Clear();
    HudLayout rest_hud(n3e::Hud{});rest_hud.data.controls={{0,4,0,1},{0,5,0,1}};
    require(rest_hud.visible(1)&&!rest_hud.visible(2));rest_hud.sitting=true;
    require(!rest_hud.visible(1)&&rest_hud.visible(2));
    std::cout<<"PASS right-click dual-slot choice, blocking equipment replacement, unequip and sit visibility\n";
    rules.inventory.reset();
    // Rebinding snapshots must move icons with instances and clear empty/off-page
    // slots. Missing artwork keeps the label; known art gets only a stack count.
    FeatureUI icon_ui; n3e::Hud icon_hud{};
    icon_hud.item_icons.emplace("original:blade",n3e::HudIcon{3,{0,0,.5f,.5f}});
    HudLayout icon_view(std::move(icon_hud));
    world.bag.mutable_slots(0)->set_quantity(5);
    rules.commerce=n3e::CommercePolicy{};rules.commerce->items.push_back({"original:blade",20,120,6});
    world.world.mutable_stats()->set_carry_limit(500);
    auto refresh=[&](){icon_ui.update(rules,world,&shop);icon_view.items=icon_ui.items;icon_view.values=icon_ui.values;};
    refresh();require(icon_view.item_icon("bag:0")->texture==3&&icon_view.item_label("bag:0")=="5");
    require(!icon_view.item_icon("bag:1")&&icon_view.item_label("bag:1").empty());
    require(!icon_view.item_icon("offer:0")&&icon_view.item_label("offer:0")=="offer0");
    require(icon_ui.values.at("weight")=="100 / 500");
    world.bag.mutable_equipment(0)->Swap(world.bag.mutable_slots(0));
    refresh();require(!icon_view.item_icon("bag:0")&&icon_view.item_label("bag:0").empty()&&icon_view.item_icon("gear:0"));
    require(icon_ui.values.at("weight")=="100 / 500");
    world.storage.mutable_slots(24)->Swap(world.bag.mutable_equipment(0));icon_ui.bank_page=1;
    refresh();require(!icon_view.item_icon("gear:0")&&icon_view.item_icon("bank:0")&&icon_view.item_label("bank:0")=="5");
    require(icon_ui.values.at("weight")=="0 / 500");
    icon_ui.bank_page=0;icon_ui.offer_page=1;refresh();
    require(!icon_view.item_icon("bank:0")&&icon_view.items.at("offer:0")=="offer24"&&!icon_view.items.contains("offer:1"));
    std::cout<<"PASS live bag/equipment/storage/stock icon rebinding, empty clearing, stack counts and missing-art fallback\n";
    n3e::Hud font{};font.font_advance=7;font.font_height=14;font.font_top=5;
    n3e::HudRecord label{};label.rect={10,20,90,38};label.align=2;label.text_flags=5;
    auto glyphs=hud_text_layout(font,label,"Trade");
    require(glyphs.size()==5 && glyphs.front().x==32 && glyphs.front().y==17);
    require(glyphs.back().x==60); // Same measured advance drives layout and rendering.
    label.text_flags=3;label.align=1;
    glyphs=hud_text_layout(font,label,"Trade");
    require(glyphs.front().x==55 && glyphs.front().y==19);
    label.rect={10,20,30,30};label.text_flags=5;
    glyphs=hud_text_layout(font,label,"Trade");
    require(glyphs.size()==2 && glyphs.front().x==10 && glyphs.front().y==13);
    require(hud_text_layout(font,label,"T\nrade").size()==1);
    label.text_flags=0;label.rect={10,20,30,48};
    glyphs=hud_text_layout(font,label,"Trade");
    require(glyphs.size()==4 && glyphs[2].x==10 && glyphs[2].y==29);
    // Actual Trade boxes have the same integer origin with the measured fixture.
    label.text_flags=5;label.align=2;label.rect={639,31,714,47};
    auto normal=hud_text_layout(font,label,"Trade");
    label.rect={641,32,713,46};auto hover=hud_text_layout(font,label,"Trade");
    require(normal[0].x==hover[0].x && normal[0].y==hover[0].y);
    // Preserve authored state rectangles: odd measured widths can legitimately
    // differ by a pixel. Do not silently substitute the normal state's position.
    label.rect={208,30,281,46};normal=hud_text_layout(font,label,"Character");
    label.rect={207,30,281,46};hover=hud_text_layout(font,label,"Character");
    require(normal[0].x==hover[0].x+1 && normal[0].y==hover[0].y);
    // Fractional font advances must accumulate before rounding, and alignment
    // uses the whole string extent rather than a rounded single-glyph width.
    font.font_advance=7.203125f;
    label.rect={0,0,100,20};
    glyphs=hud_text_layout(font,label,"Character");
    require(glyphs.front().x==17 && glyphs.back().x==75);
    label.rect={0,0,36,20};
    require(hud_text_layout(font,label,"Trade").size()==4);
    std::cout<<"PASS HUD measured integer alignment, vertical flags, overflow truncation and state boxes\n";
    n3e::Release tip_rules;tip_rules.inventory=n3e::InventoryPolicy{};
    tip_rules.inventory->items.push_back({"test:item/blade","Blade",1,80,0});
    tip_rules.commerce=n3e::CommercePolicy{};tip_rules.commerce->items.push_back({"test:item/blade",20,120,6});
    tip_rules.equipment=n3e::EquipmentPolicy{};tip_rules.equipment->attributes[0]=60;
    n3e::EquipmentItem tip_gear{};tip_gear.id="test:item/blade";tip_gear.attributes[0]=61;tip_rules.equipment->items.push_back(tip_gear);
    tip_rules.item_stats[tip_gear.id][0]=40;
    auto info=item_tooltip(tip_rules,tip_gear.id,1,0,100,true,false,false);
    auto has=[&](const std::string&label,uint32_t color){return std::any_of(info.begin(),info.end(),[&](const auto&line){return line.text==label&&line.color==color;});};
    require(has("Attack: 40",0xffffff)&&has("Durability: 0 / 80",0xff3c3c)&&has("Required strength: 61",0xff3c3c)&&has("Buy price: 120",0xff3c3c));
    info=item_tooltip(tip_rules,tip_gear.id,1,80,100,false,true,false);
    require(has("Sell price: 20",0xffffff)&&!has("Buy price: 120",0xff3c3c));
    require(item_tooltip(tip_rules,"unknown",1,0,0,false,false,false).empty());
    std::cout<<"PASS supported tooltip stats, broken durability, unmet requirements and buy/sell context\n";
    // PQ-354 (D-194): the item head (N3IH). Without a head file the first line
    // is the label in yellow, the token kept; with one, the token is the
    // viewer's name, the label takes the head's name colour and the head's lines
    // follow it, centred, before the rest.
    require(info[0].text=="Blade"&&info[0].color==0xffff00&&info[0].centred&&!info[1].centred);
    tip_rules.inventory->items[0].label="<me>'s Blade";
    info=item_tooltip(tip_rules,tip_gear.id,1,80,100,false,false,false,"Viewer");
    require(info[0].text=="<me>'s Blade"&&info[0].color==0xffff00);
    tip_rules.item_heads=n3e::ItemHeads{"<me>",{}};
    info=item_tooltip(tip_rules,tip_gear.id,1,80,100,false,false,false,"Viewer");
    require(info[0].text=="Viewer's Blade"&&info[0].color==0xffff00&&info[1].text=="Attack: 40");
    tip_rules.item_heads->heads[tip_gear.id]=n3e::ItemHead{0xffad4d,{{"(Reverse unique item)",0xffad4d},{"Second",0x112233}}};
    info=item_tooltip(tip_rules,tip_gear.id,1,80,100,false,false,false,"Viewer");
    require(info.size()>3&&info[0].text=="Viewer's Blade"&&info[0].color==0xffad4d&&info[0].centred);
    require(info[1].text=="(Reverse unique item)"&&info[1].color==0xffad4d&&info[1].centred);
    require(info[2].text=="Second"&&info[2].color==0x112233&&info[2].centred&&info[3].text=="Attack: 40"&&!info[3].centred);
    // No name yet (no self entity) or one the server would not accept: the token stays.
    require(item_tooltip(tip_rules,tip_gear.id,1,80,100,false,false,false)[0].text=="<me>'s Blade");
    for(const char*bad:{"<me>","has space","x/y","a<me>","1234567890123456789012345"})
      require(self_named("<me>'s Blade","<me>",bad)=="<me>'s Blade");
    // Each occurrence once, left to right; 128-byte bound. A name holding the
    // token at offset 1 or more is not searched again: ("ab","b","bb") gives
    // "abb", where 004aad90 would loop (it searches again from the found
    // position + 1; BINARY-POLICY). A name that is not a server-accepted name
    // (here "<b", equal to the token) is not used at all.
    require(self_named("<me><me> and <me>","<me>","Ab_-9")=="Ab_-9Ab_-9 and Ab_-9");
    require(self_named("ab","b","bb")=="abb"&&self_named("a<b","<b","<b")=="a<b"&&self_named("ab","","x")=="ab");
    require(self_named(std::string(64,'t'),"t","123456789012345678901234").size()==128);
    require(self_named(std::string(60,'x')+"t","t","123456789012345678901234")==std::string(60,'x')+"123456789012345678901234");
    std::cout<<"PASS item tooltip head: label colour, centred head lines, the self-name token and its bounds\n";
    // PQ-361 (D-196, BINARY-POLICY "Tooltip name colour correction"): 1298's
    // 004d6320 keeps line 0's colour when the new name equals the text the line
    // shows (004d66f6), so the second of two same-named items of different
    // attributes takes the first's colour. n3e draws each item's own head every
    // time: the same label, shown alternately, keeps each item's colours.
    {
      n3e::Release same;same.inventory=n3e::InventoryPolicy{};
      same.inventory->items.push_back({"test:item/burning","Short Blade(+8)",1,80,0});
      same.inventory->items.push_back({"test:item/strong","Short Blade(+8)",1,80,0});
      same.item_heads=n3e::ItemHeads{"",{}};
      same.item_heads->heads["test:item/burning"]=n3e::ItemHead{0xc87cc7,{{"(Upgrade Item)",0xc87cc7},{"One-handed Sword",0xffffff}}};
      same.item_heads->heads["test:item/strong"]=n3e::ItemHead{0x8080ff,{{"(Magic Item)",0x8080ff},{"One-handed Sword",0xffffff}}};
      for(const char*id:{"test:item/burning","test:item/strong","test:item/burning","test:item/strong"}){
        auto shown=item_tooltip(same,id,1,80,0,false,false,false);
        bool burning=std::string(id)=="test:item/burning";
        require(shown.size()>=3&&shown[0].text=="Short Blade(+8)"&&shown[0].color==(burning?0xc87cc7u:0x8080ffu));
        require(shown[1].text==(burning?"(Upgrade Item)":"(Magic Item)")&&shown[1].color==shown[0].color);
        require(shown[2].text=="One-handed Sword"&&shown[2].color==0xffffff&&shown[2].centred);
      }
    }
    std::cout<<"PASS item tooltip head: two items with the same label keep their own head colours, shown alternately\n";
    // Composition is shared by world and portrait: unequip restores the base,
    // competing keys cannot render two pieces in one slot, missing LOD falls back.
    n3e::RenderDetail detail;detail.levels.resize(4);detail.appearances.resize(2);
    for(auto&base:detail.levels){base.slots={1,1,1};base.scene.indices={0,1,2};}
    for(auto&part:detail.appearances){part.replaces={1};part.levels.resize(4);part.levels[0].scene.indices={0,1,2,0,1,2};}
    std::vector<n3e::AppearanceRule> mappings={{"blade",0},{"armor",0}};
    auto composition=[&](std::vector<uint32_t>keys,unsigned level){size_t count=0;n3e::draw_appearance(detail,mappings,keys,level,[&](const auto&,auto indices){count+=indices.size();});return count;};
    require(composition({},0)==3&&composition({1},0)==6&&composition({1,2},0)==6&&composition({999},0)==3&&composition({1},3)==6);
    for(auto [x,y]:{std::pair{0.f,0.f},std::pair{1023.f,767.f},std::pair{1000.f,10.f}}){auto box=tooltip_rectangle(x,y,254,200,1024,768,26);require(box[0]>=0&&box[1]>=0&&box[2]<=1024&&box[3]<=768);}
    auto giant=tooltip_rectangle(100,100,2000,2000,1024,768,26);require(giant[2]==1024&&giant[3]==768);
    n3e::WorldState loot_world;loot_world.connected=true;
    for(unsigned i=1;i<=3;++i){auto*d=loot_world.loot.add_drops();d->set_operation(i);d->set_encounter(5);d->set_item("blade");d->set_quantity(1);}
    LootUI pickup;require(pickup.open(loot_world,3,100,100));pickup.down("loot:0");
    loot_world.loot.mutable_drops()->DeleteSubrange(0,1);pickup.sync(loot_world,3);
    require(!pickup.up("loot:0")&&pickup.slots[1].operation()==2);
    pickup.down("loot:1");require(pickup.up("loot:1")->operation()==2);pickup.down("loot:2");require(!pickup.up("loot:2"));
    loot_world.claim.set_operation(2);loot_world.claim.set_status("inventory_full_not_committed");++loot_world.claim_responses;pickup.sync(loot_world,3);
    pickup.down("loot:1");require(pickup.up("loot:1")->operation()==2);
    loot_world.predicted[0]=10;pickup.sync(loot_world,3);require(!pickup.encounter);
    require(!pickup.open(loot_world,3,0,0));
    std::cout<<"PASS appearance restore/replacement/LOD, tooltip edge bounds and stable pickup slots/retry/range\n";
    if (argc>=2) {
      auto release=n3e::load_release(argv[1]);
      HudLayout package(n3e::load_hud(release));
      if(argc==3&&std::string(argv[2])=="--audit-dialogs"){
        require(package.data.dialogs);
        if(!package.data.portraits.empty()){
          auto model=n3e::load_scene(release,"player-idle.bin");
          const auto&view=package.data.portraits.begin()->second;
          auto vertices=portrait_vertices(model,0,view,{100,100,274,358},1024,768);
          require(!vertices.empty()&&vertices.size()==model.indices.size()*8);
          for(size_t i=0;i<vertices.size();i+=8){
            require(std::isfinite(vertices[i])&&vertices[i]>=100*2/1024.f-1&&vertices[i]<=274*2/1024.f-1);
            require(vertices[i+1]>=1-358*2/768.f&&vertices[i+1]<=1-100*2/768.f&&std::abs(vertices[i+2])<=1);
          }
          model.collision=n3e::Collision(std::vector<n3e::V>{{-10000,-10000,-10000},{10000,10000,10000},{0,10000,0}});
          require(vertices==portrait_vertices(model,0,view,{100,100,274,358},1024,768));
          std::cout<<"PASS paperdoll mesh/depth/rectangle bounds exclude world collision and debug attachments\n";
        }
        for(auto size:{std::pair{1024,768},std::pair{1280,1024},std::pair{1600,1200}}){
          auto [w,h]=size;float scale=package.scale(w,h);
          for(unsigned panel:{1u,2u,3u,4u,5u,6u,8u}){
            package.panels=1u<<panel;
            auto root=std::find_if(package.data.records.begin(),package.data.records.end(),[&](const auto&q){return q.panel==panel&&q.kind==2&&q.text=="panel"&&!q.control;});
            require(root!=package.data.records.end());auto r=package.rectangle(*root,w,h);
            if(panel==2||panel==5)require(r[0]==0&&r[1]==std::floor(80*scale));
            // The source prompt has an odd width; flooring its two edges can
            // leave its center exactly one pixel from the viewport center.
            else if(panel==8)require(std::abs((r[0]+r[2])*.5f-w*.5f)<=1&&std::abs((r[1]+r[3])*.5f-h*.5f)<=1);
            else require(r[2]==w&&r[1]==std::floor((panel==6?40:10)*scale));
            require(r[0]>=0&&r[1]>=0&&r[2]<=w&&r[3]<=h);
            if(panel==3){
              require(std::abs(r[2]-r[0]-370*scale)<1&&std::abs(r[3]-r[1]-578*scale)<1);
              unsigned offers=0,bag=0,pages=0,close=0;
              for(const auto&q:package.data.records)if(q.panel==3&&q.kind==2&&q.text!="panel"){
                auto hit=package.rectangle(q,w,h);
                require(package.hit((hit[0]+hit[2])*.5f,(hit[1]+hit[3])*.5f,w,h)==q.text);
                if(q.text.starts_with("offer:"))++offers;
                if(q.text.starts_with("bag:"))++bag;
                if(q.text=="offer_prev"||q.text=="offer_next")++pages;
                if(q.text=="close:3")++close;
              }
              require(offers==24&&bag==28&&pages==2&&close==1);
            }
            if(panel==2||panel==5){
              for(const auto&q:package.data.records)if(q.panel==panel&&q.kind==2&&q.text.starts_with("tab:")){
                require(package.state(q.control)==((q.text=="tab:state")==(panel==2)?1u:0u));
                auto tab=package.rectangle(q,w,h);require(package.hit((tab[0]+tab[2])*.5f,(tab[1]+tab[3])*.5f,w,h)==q.text);
              }
            }
          }
        }
        std::cout<<"PASS imported dialog anchors, centered prompt, selected tab artwork and hits at three viewports\n";
      }
      for (bool running:{false,true}) {
        package.running=running;
        size_t draws=0,hits=0;
        for (const auto &q:package.data.records) if(package.visible(q)) {
          if(q.kind==2) ++hits; else ++draws;
          if(q.binding=="walk" || q.binding=="run")
            require(q.binding==(running?"walk":"run"));
        }
        std::cout << "HUD mode=" << (running?"run":"walk") << " draws=" << draws << " hits=" << hits << '\n';
      }
    }
  } catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
