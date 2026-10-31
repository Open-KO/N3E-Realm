#pragma once
#include <string>
#include <string_view>
#include <algorithm>
namespace n3e {
struct FriendCommand {enum Kind{none,invalid,list,add,remove,retry,hide}kind=none;std::string name;};
inline FriendCommand parse_friend(std::string_view s,unsigned maximum){
 if(s=="/friends")return {FriendCommand::list,{}};
 if(s=="/friendretry")return {FriendCommand::retry,{}};
 if(s=="/friendhide")return {FriendCommand::hide,{}};
 auto split=s.find_first_of(" \t");auto command=s.substr(0,split);
 if(command!="/friend"&&command!="/unfriend")return {};
 if(split==std::string_view::npos)return {FriendCommand::invalid,{}};
 auto first=s.find_first_not_of(" \t",split);if(first==std::string_view::npos)return {FriendCommand::invalid,{}};s.remove_prefix(first);
 if(s.empty()||s.size()>maximum||!std::all_of(s.begin(),s.end(),[](unsigned char c){return(c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='-';}))return {FriendCommand::invalid,{}};
 return {command=="/friend"?FriendCommand::add:FriendCommand::remove,std::string(s)};
}
}
