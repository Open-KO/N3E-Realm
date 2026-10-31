//! Ephemeral, authoritative posture and package-defined recovery. Durable death
//! continues through life/account transactions; resting never revives an actor.
use crate::{content::{bad,Reader,Result},wire};
use std::path::Path;
#[derive(Clone,Debug)]
pub struct Policy { pub interval:u64, pub cooldown:u64, pub levels:Vec<[u32;4]> }
impl Policy {
    pub fn load(path:&Path)->Result<Self>{
        let mut r=Reader::open(path)?;
        if r.take(4)?!=b"N3E1"{return Err(bad("rest magic"));}
        let interval=r.u()? as u64;let cooldown=r.u()? as u64;let count=r.u()?;
        if !(1..=12000).contains(&interval)||cooldown>1200||!(1..=255).contains(&count){return Err(bad("rest bounds"));}
        let mut levels=Vec::new();
        for _ in 0..count {let row=[r.u()?,r.u()?,r.u()?,r.u()?];if row.iter().any(|v|*v>100000)||row[2]==0{return Err(bad("rest level"));}levels.push(row);}
        r.end()?;Ok(Self{interval,cooldown,levels})
    }
    pub fn recover(&self,e:&mut wire::Entity,level:u64,max_health:u32,max_resource:u32){
        if !e.sitting||e.health==0||e.npc{return;}
        let row=self.levels[level.saturating_sub(1).min(self.levels.len() as u64-1) as usize];
        e.health=e.health.saturating_add(row[0]).min(max_health);
        let resource=(u64::from(max_resource)*u64::from(row[1])/u64::from(row[2])+u64::from(row[3])).min(u32::MAX as u64) as u32;
        e.resource=e.resource.saturating_add(resource).min(max_resource);
    }
}
#[derive(Default)]
pub struct State { pub sequence:u64, pub next_sit:u64, pub next_recovery:u64, pub last_motion:u64 }
impl State {
    pub fn request(&mut self,e:&mut wire::Entity,q:&wire::Rest,session:i64,tick:u64,policy:&Policy,busy:bool)->&'static str{
        if q.session!=session as u64||q.entity!=e.id{return "stale_rest_identity";}
        if q.seq==0||q.seq<=self.sequence||q.seq>=i64::MAX as u64{return "stale_rest_sequence";}
        self.sequence=q.seq;
        if e.health==0||e.npc||busy{return "rest_unavailable";}
        if q.sitting==e.sitting{return "ok";}
        if q.sitting {
            if tick<self.next_sit||tick.saturating_sub(self.last_motion)<3{return "rest_wait";}
            self.next_sit=tick+policy.cooldown;
            self.next_recovery=tick+policy.interval;
        }
        e.sitting=q.sitting;"ok"
    }
    pub fn motion(&mut self,e:&mut wire::Entity,tick:u64){e.sitting=false;self.last_motion=tick;}
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn identity_timing_and_recovery(){
        let p=Policy{interval:101,cooldown:60,levels:vec![[4,5,30,3]]};
        let mut s=State::default();let mut e=wire::Entity{id:7,health:10,resource:0,..Default::default()};
        let mut q=wire::Rest{session:2,seq:1,entity:6,sitting:true};
        assert_eq!(s.request(&mut e,&q,2,10,&p,false),"stale_rest_identity");assert!(!e.sitting);
        q.entity=7;assert_eq!(s.request(&mut e,&q,2,10,&p,false),"ok");assert_eq!(s.next_recovery,111);
        assert_eq!(s.request(&mut e,&q,2,20,&p,false),"stale_rest_sequence");
        p.recover(&mut e,1,12,18);assert_eq!((e.health,e.resource),(12,6));
        s.motion(&mut e,30);q.seq=2;assert_eq!(s.request(&mut e,&q,2,31,&p,false),"rest_wait");
        q.seq=3;assert_eq!(s.request(&mut e,&q,2,80,&p,false),"ok");assert_eq!(s.next_recovery,181);
        e.health=0;p.recover(&mut e,1,12,18);assert_eq!(e.health,0);
        q.seq=4;q.sitting=false;assert_eq!(s.request(&mut e,&q,2,90,&p,false),"rest_unavailable");
    }
}
