#pragma once
#include <algorithm>
#include <string>
#include <string_view>
namespace n3e {
struct PartyCommand {enum Kind{none,invalid,list,invite,accept,decline,leave,kick,disband,hide,block}kind=none;std::string name;};
inline PartyCommand parse_party(std::string_view s,unsigned maximum){
 if(s=="/party")return {PartyCommand::list,{}};
 if(s=="/accept")return {PartyCommand::accept,{}};
 if(s=="/decline")return {PartyCommand::decline,{}};
 if(s=="/leave")return {PartyCommand::leave,{}};
 if(s=="/disband")return {PartyCommand::disband,{}};
 if(s=="/partyhide")return {PartyCommand::hide,{}};
 if(s=="/partyblock")return {PartyCommand::block,{}};
 auto split=s.find_first_of(" \t");auto cmd=s.substr(0,split);
 if(cmd!="/invite"&&cmd!="/kick")return {};
 if(split==std::string_view::npos)return {PartyCommand::invalid,{}};
 auto first=s.find_first_not_of(" \t",split);if(first==std::string_view::npos)return {PartyCommand::invalid,{}};s.remove_prefix(first);
 if(s.empty()||s.size()>maximum||!std::all_of(s.begin(),s.end(),[](unsigned char c){return(c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='-';}))return {PartyCommand::invalid,{}};
 return {cmd=="/invite"?PartyCommand::invite:PartyCommand::kick,std::string(s)};
}
}
