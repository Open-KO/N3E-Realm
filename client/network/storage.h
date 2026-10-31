#pragma once
#include <charconv>
#include <string_view>
namespace n3e {
struct StorageCommand {enum Kind {none,invalid,open,retry,deposit,withdraw,move,putcoins,takecoins} kind=none;unsigned source=0,destination=0,quantity=0;};
inline StorageCommand parse_storage(std::string_view text){
 if(text=="/bank")return {StorageCommand::open};
 if(text=="/bankretry")return {StorageCommand::retry};
 StorageCommand q;unsigned count=0;
 if(text.starts_with("/deposit")){text.remove_prefix(8);q.kind=StorageCommand::deposit;count=3;}
 else if(text.starts_with("/withdraw")){text.remove_prefix(9);q.kind=StorageCommand::withdraw;count=3;}
 else if(text.starts_with("/bankmove")){text.remove_prefix(9);q.kind=StorageCommand::move;count=2;}
 else if(text.starts_with("/bankcoins")){text.remove_prefix(10);q.kind=StorageCommand::putcoins;count=1;}
 else if(text.starts_with("/takecoins")){text.remove_prefix(10);q.kind=StorageCommand::takecoins;count=1;}
 else return q;
 unsigned v[3]={};
 for(unsigned i=0;i<count;++i){if(text.empty()||text.front()!=' ')return {StorageCommand::invalid};while(!text.empty()&&text.front()==' ')text.remove_prefix(1);
  auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),v[i]);if(error!=std::errc{}||!v[i]||v[i]>(count==1?2100000000u:i==2?9999u:192u))return {StorageCommand::invalid};text.remove_prefix(end-text.data());
 }if(!text.empty())return {StorageCommand::invalid};
 if(count==1)q.quantity=v[0];else{q.source=v[0]-1;q.destination=v[1]-1;q.quantity=v[2];}return q;
}
}
