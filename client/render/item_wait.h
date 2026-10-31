#pragma once
#include "network/world.h"
#include <optional>

// A refresh or another request's reply cannot acknowledge this mutation.
// Keep the exact envelope for bounded idempotent retries; hiding panels is irrelevant.
struct ItemWait {
  std::optional<n3e::Envelope> request;
  uint64_t session=0,entity=0,seen=0;
  double retry_at=0;
  unsigned retries=0;
  std::string notice;
  explicit operator bool()const{return request.has_value();}
  void reset(){request.reset();notice.clear();}
  bool begin(const n3e::Envelope&q,const n3e::WorldState&w,double now){
    if(request)return false;
    request=q;session=w.world.session();entity=w.world.self();
    seen=w.item_result_sequence;retry_at=now+3;retries=0;notice.clear();return true;
  }
  std::optional<n3e::Envelope> sync(const n3e::WorldState&w,double now){
    if(!request)return {};
    if(!w.connected||w.world.session()!=session||w.world.self()!=entity){reset();return {};}
    bool storage=request->has_storage_request();
    const auto&id=storage?request->storage_request().request():request->bag_request().request();
    for(const auto&r:w.item_results)if(r.sequence>seen&&r.storage==storage&&r.request==id){
      if(r.status!="use_pending"&&r.status!="storage_pending"){
        reset();return {};
      }
    }
    seen=w.item_result_sequence;
    if(now<retry_at)return {};
    if(retries==3){
      request.reset();notice="Item result unavailable. Refresh or retry the last operation.";
      n3e::Envelope refresh;refresh.mutable_bag_request();return refresh;
    }
    ++retries;retry_at=now+3;return request;
  }
};
