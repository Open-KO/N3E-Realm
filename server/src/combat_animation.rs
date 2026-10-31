//! Package profiles and authoritative intervals selected from committed equipment.
use crate::{content::{bad,Reader,Result},inventory,wire};
use std::{collections::{BTreeMap,BTreeSet},path::Path};
#[derive(Clone,Debug)]
pub struct Policy { slots:Vec<usize>, rows:BTreeMap<Vec<String>,u32>, pub intervals:Vec<u32>, pub layered:bool, pub ranged:BTreeMap<u32,Ranged>,
    /// PQ-421 (D-218): each ranged profile's ammunition (N3RD): the inventory
    /// item a shot needs and the count it removes.
    pub ammo:BTreeMap<u32,(String,u32)>,
    /// Each clip's duration, entry blend and first marker (-1: none), seconds.
    clips:Vec<[f32;3]>,
    /// Each profile's ready clip, attack clips and moving clip (N3A5).
    profiles:Vec<(u32,Vec<u32>,Option<u32>)> }
/// A ranged basic attack on one profile (PQ-416, D-216; `ranged-attack.bin`,
/// N3RB/N3RC): the strike limit is the actor's and the target's radii summed
/// plus `range`, in 3-D; `reach` is the client's approach walk (half the
/// summed radii plus it) and is only bounds-checked here. PQ-420 (D-217):
/// with a cast time (`cast_ms` above 0, N3RC) the shot is held and lands
/// `land` ticks after its acceptance, when the profile's one attack clip,
/// stretched to the cast time, reaches its first marker (1298 `00461ab0`,
/// `004689f0`; the frame waits out the entry blend, `00418b20`).
/// PQ-422 (D-219): `hit` (N3RE) is the profile's type-2 skill hit, which
/// the server resolves a strike on an NPC with (`damage::Policy::
/// resolve_skill_hit`); None: the basic attack's damage.
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Ranged { pub reach:f32, pub range:f32, pub cast_ms:u32, pub land:u32, pub hit:Option<crate::damage::SkillHit>,
    /// PQ-439 (D-223): the N3RG flight's speed in m/s, 0 without a flight;
    /// a held shot with a flight resolves when its arrow arrives.
    pub speed:f32,
    /// PQ-467 (D-233): the N3RH hold, None without one.
    pub hold:Option<Hold> }
/// PQ-467 (D-233): a ranged profile's hold (`ranged-attack.bin` N3RH): the
/// distance, on the ground (x/z) plane when `planar`, the target must be
/// within at the shot's acceptance, its release and its landing (or its
/// arrow's arrival), inclusive. Ebenezer's magic packet `004630a6` calls
/// `004c1dbe` at `004635c8` on each phase of a user's archery row, the
/// flying and effecting phases included, and for a Type1 2 row that passes
/// while dx^2 + dz^2 is at most (the worn item's range / 10)^2 + 1000.0
/// (`004c1fcd`-`004c203d`, `JA`); the package carries the distance that
/// form gives (the glow bow's: sqrt(40^2 + 1000), about 51 m).
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Hold { pub distance:f32, pub planar:bool }
impl Ranged {
    /// PQ-467 (D-233): whether `target` is within the hold of a shot by
    /// `actor` (always, without a hold). A non-finite distance fails.
    pub fn holds(&self,actor:&wire::Entity,target:&wire::Entity)->bool{
        let Some(hold)=self.hold else {return true};
        let (dx,dy,dz)=(actor.x-target.x,actor.y-target.y,actor.z-target.z);
        let sum=if hold.planar {dx*dx+dz*dz} else {dx*dx+dy*dy+dz*dz};
        sum<=hold.distance*hold.distance
    }
}
/// The ticks from a shot's acceptance to its landing: the attack clip's entry
/// blend plus its first marker scaled by cast / duration, rounded up to the
/// 50 ms tick (D-217). The client stretches the clip by the same factor.
pub fn landing_ticks(duration:f32,blend:f32,marker:f32,cast_ms:u32)->u32{
    let seconds=f64::from(blend)+f64::from(marker)*(f64::from(cast_ms)/1000.)/f64::from(duration);
    (seconds*20.).ceil() as u32
}
/// Longest client notice a ranged-attack file carries (printable ASCII).
pub const MAX_RANGED_NOTICE:u32=96;
/// PQ-423 (D-220): longest cast-effect clip key (N3RF; the client's).
pub const MAX_CAST_EFFECT_KEY:u32=64;
impl Policy {
    pub fn load(root:&Path,files:&mut BTreeSet<String>,bag:&inventory::Policy,layered:bool)->Result<Self>{
        let gear=bag.equipment.as_ref().ok_or_else(||bad("combat equipment required"))?;
        let mut r=Reader::open(&root.join("combat-animation.bin"))?;
        if r.take(4)?!=if layered {b"N3A5"}else{b"N3A4"}{return Err(bad("combat animation magic"));}
        let count=r.u()?;if !(1..=64).contains(&count){return Err(bad("combat clip count"));}
        let mut looping=Vec::new();let mut bytes=0;let mut clips=Vec::new();
        for i in 0..count {
            let name=format!("combat-{i}.bin");if !files.remove(&name){return Err(bad("combat clip missing"));}
            bytes+=std::fs::metadata(root.join(name))?.len();if bytes>32*1024*1024{return Err(bad("combat clip byte budget"));}
            let d=r.f()?;let b=r.f()?;let l=r.u()?;
            if !(0.001..=3600.).contains(&d)||!(0.0..=2.).contains(&b)||l>1{return Err(bad("combat clip bounds"));}
            // D-217: the first marker is the one 1298's cast tick tests (clip
            // `+0x34` in `004689f0`).
            let mut first=None;
            for _ in 0..2 {let m=r.f()?;if m != -1. && !(0.0..=d).contains(&m){return Err(bad("combat marker"));}first.get_or_insert(m);}
            looping.push(l);clips.push([d,b,first.unwrap()]);
        }
        let profiles=r.u()?;if !(1..=32).contains(&profiles){return Err(bad("combat profile count"));}
        let mut used=BTreeSet::new();let mut intervals=Vec::new();let mut roles=Vec::new();
        for _ in 0..profiles {
            let ready=r.u()?;let n=r.u()?;if ready>=count||!(1..=4).contains(&n){return Err(bad("combat profile"));}used.insert(ready);
            let mut seen=BTreeSet::new();let mut attacks=Vec::new();
            for _ in 0..n {let i=r.u()?;if i>=count||looping[i as usize]!=0||!seen.insert(i){return Err(bad("combat attack"));}used.insert(i);attacks.push(i);}
            let mut moving_clip=None;
            if layered {let ms=r.u()?;let moving=r.u()?;if !(50..=60000).contains(&ms)||moving>=count||looping[moving as usize]!=0{return Err(bad("combat motion bounds"));}used.insert(moving);intervals.push(ms);moving_clip=Some(moving);}
            roles.push((ready,attacks,moving_clip));
        }
        if used.len()!=count as usize{return Err(bad("unused combat clip"));}
        let n=r.u()?;if !(1..=4).contains(&n){return Err(bad("combat selector count"));}
        let mut slots=Vec::new();for _ in 0..n {let s=r.u()? as usize;if s>=gear.slots.len()||slots.contains(&s){return Err(bad("combat selector slot"));}slots.push(s);}
        let n=r.u()?;if !(1..=256).contains(&n){return Err(bad("combat row count"));}
        let mut rows=BTreeMap::new();
        for _ in 0..n {
            let mut key=Vec::new();
            for &slot in &slots {
                let i=r.u()? as usize;
                if i==0 {key.push(String::new());continue;}
                let item=bag.items.get(i-1).ok_or_else(||bad("combat item index"))?;
                if !gear.items.iter().any(|v|v.id==item.id&&v.slots&(1<<slot)!=0){return Err(bad("combat equipment mapping"));}
                key.push(item.id.clone());
            }
            let profile=r.u()?;if profile==0||profile>profiles||rows.insert(key,profile).is_some(){return Err(bad("combat row"));}
        }
        if !rows.contains_key(&vec![String::new();slots.len()]){return Err(bad("combat empty fallback"));}
        if layered {let n=r.u()?;if !(1..=63).contains(&n){return Err(bad("combat mask count"));}let mut seen=BTreeSet::new();for _ in 0..n {let node=r.u()?;if !(1..64).contains(&node)||!seen.insert(node){return Err(bad("combat upper mask"));}}}
        r.end()?;Ok(Self{slots,rows,intervals,layered,ranged:BTreeMap::new(),ammo:BTreeMap::new(),clips,profiles:roles})
    }
    /// Reads `ranged-attack.bin` (N3RB, or N3RC with a cast time per entry)
    /// onto this N3A5 policy: up to 32 distinct profiles, each with reach
    /// 0..=range and range 0.5..=100 m, and one printable notice of at most 96
    /// bytes (the client's; checked only). PQ-420 (D-217): a cast time of
    /// 101..=10000 ms needs a profile with one attack clip that has a first
    /// marker and that no other profile or role uses (its own moving clip
    /// aside), and a landing within the profile's interval. PQ-421 (D-218):
    /// N3RD adds per entry an ammo item (0, or a 1-based index into `items`,
    /// the inventory's definitions, which must not wear) and its count (0
    /// without ammo, else 1 to the item's stack limit), then a second notice
    /// (the client's line for a shot without ammo; checked only). PQ-422
    /// (D-219): N3RE adds per entry, after the ammo count, `hit` (0: the
    /// basic attack's damage, 1: a type-2 skill hit) and its hit rate
    /// (1-1000), add damage (0-300) and add damage plus (0-10000), all 0
    /// when `hit` is 0. PQ-423 (D-220): N3RF adds per entry, after those,
    /// the client's cast effect (a clip key of 0-64 printable bytes, which
    /// needs a cast time, and 0 joints without a key, else 1-2 distinct
    /// joints, index + 1 up to 128); presentation, checked only. PQ-417
    /// (D-222): N3RG adds per entry, after the cast effect, the client's
    /// flight (a clip key, its source joint and speed, a hit clip key and
    /// joint, a release audio key), checked only, except the speed, which
    /// since PQ-439 (D-223) times the shot's arrival.
    pub fn load_ranged(&mut self,path:&Path,items:&[inventory::Item])->Result<()>{
        if !self.layered{return Err(bad("ranged attack compatibility"));}
        let mut r=Reader::open(path)?;
        let magic=r.take(4)?.to_vec();
        let (cast,ammo,skill,effect,flight)=match magic.as_slice() {b"N3RB"=>(false,false,false,false,false),b"N3RC"=>(true,false,false,false,false),b"N3RD"=>(true,true,false,false,false),b"N3RE"=>(true,true,true,false,false),b"N3RF"=>(true,true,true,true,false),b"N3RG"|b"N3RH"=>(true,true,true,true,true),_=>return Err(bad("ranged attack magic"))};
        let holds=magic==b"N3RH";
        let n=r.u()?;if !(1..=32).contains(&n){return Err(bad("ranged attack count"));}
        let mut ranged=BTreeMap::new();let mut ammunition=BTreeMap::new();
        for _ in 0..n {
            let profile=r.u()?;let reach=r.f()?;let range=r.f()?;let cast_ms=if cast {r.u()?} else {0};
            if profile==0||profile as usize>self.intervals.len()||ranged.contains_key(&profile){return Err(bad("ranged attack profile"));}
            if !(0.5..=100.).contains(&range)||!(0.0..=range).contains(&reach){return Err(bad("ranged attack bounds"));}
            let land=if cast_ms==0 {0} else {self.cast_landing(profile,cast_ms)?};
            if ammo {
                let (index,count)=(r.u()?,r.u()?);
                if index==0 {if count!=0{return Err(bad("ranged ammo count"));}}
                else {
                    let item=items.get(index as usize-1).ok_or_else(||bad("ranged ammo item"))?;
                    if item.durability!=0{return Err(bad("ranged ammo item"));}
                    if !(1..=item.stack).contains(&count){return Err(bad("ranged ammo count"));}
                    ammunition.insert(profile,(item.id.clone(),count));
                }
            }
            let hit=if skill {
                let (kind,hit_rate,add_damage,add_damage_plus)=(r.u()?,r.u()?,r.u()?,r.u()?);
                match kind {
                    0 if hit_rate==0&&add_damage==0&&add_damage_plus==0 => None,
                    1 if (1..=1000).contains(&hit_rate)&&add_damage<=300&&add_damage_plus<=10000 =>
                        Some(crate::damage::SkillHit{hit_rate,add_damage,add_damage_plus}),
                    _ => return Err(bad("ranged skill hit")),
                }
            } else {None};
            if effect {
                // PQ-423 (D-220): the client's cast effect, bounds only: a
                // clip key of 0-64 printable bytes (a key needs a cast time),
                // then 0 joints without a key, else 1-2 distinct joints, each
                // index + 1 (0: the actor's position) up to 128.
                let len=r.u()?;
                if len>MAX_CAST_EFFECT_KEY||!r.take(len as usize)?.iter().all(|b|(b' '..=b'~').contains(b))||(len>0&&cast_ms==0){return Err(bad("ranged cast effect"));}
                let joints=r.u()?;
                if if len==0 {joints!=0} else {!(1..=2).contains(&joints)}{return Err(bad("ranged cast effect joints"));}
                let mut seen=BTreeSet::new();
                for _ in 0..joints {let joint=r.u()?;if joint>128||!seen.insert(joint){return Err(bad("ranged cast effect joints"));}}
            }
            let mut flight_speed=0.;
            if flight {
                // PQ-417 (D-222): the client's flight, bounds only: a clip
                // key of 0-64 printable bytes (a key needs a cast time), its
                // source joint (index + 1, 0: the actor, up to 128) and speed
                // (1-1000 m/s), a hit clip key and joint, a release audio
                // key; without a flight key every field is 0 or empty.
                let key=|r:&mut Reader|->Result<u32>{let len=r.u()?;
                    if len>MAX_CAST_EFFECT_KEY||!r.take(len as usize)?.iter().all(|b|(b' '..=b'~').contains(b)){return Err(bad("ranged flight key"));}Ok(len)};
                let clip=key(&mut r)?;let joint=r.u()?;let speed=r.f()?;let hit=key(&mut r)?;let hit_joint=r.u()?;let release=key(&mut r)?;
                let ok=if clip==0 {joint==0&&speed==0.&&hit==0&&hit_joint==0&&release==0}
                    else {cast_ms>0&&joint<=128&&(1.0..=1000.).contains(&speed)&&hit_joint<=128&&(hit>0||hit_joint==0)};
                if !ok{return Err(bad("ranged flight"));}
                flight_speed=speed;
            }
            // PQ-467 (D-233): N3RH adds per entry, after the flight, the
            // hold: f32 distance (0: none, else 0.5-200 m) and u32 plane (0
            // 3-D, 1 the ground plane; 0 without a hold).
            let hold=if holds {
                let (distance,plane)=(r.f()?,r.u()?);
                if distance==0. {if plane!=0{return Err(bad("ranged hold"));}None}
                else if (0.5..=200.).contains(&distance)&&plane<=1 {Some(Hold{distance,planar:plane==1})}
                else {return Err(bad("ranged hold"));}
            } else {None};
            ranged.insert(profile,Ranged{reach,range,cast_ms,land,hit,speed:flight_speed,hold});
        }
        for _ in 0..if ammo {2} else {1} {
            let len=r.u()?;if len>MAX_RANGED_NOTICE||!r.take(len as usize)?.iter().all(|b|(b' '..=b'~').contains(b)){return Err(bad("ranged attack notice"));}
        }
        r.end()?;self.ranged=ranged;self.ammo=ammunition;Ok(())
    }
    /// PQ-421 (D-218): the item and count a shot under `style` needs, if any.
    pub fn ammo(&self,style:u32)->Option<(&str,u32)>{self.ammo.get(&style).map(|(item,count)|(item.as_str(),*count))}
    /// D-217: the landing ticks of `profile` (1-based) cast over `cast_ms`.
    fn cast_landing(&self,profile:u32,cast_ms:u32)->Result<u32>{
        if !(101..=10000).contains(&cast_ms){return Err(bad("ranged cast time"));}
        let (_,attacks,_)=&self.profiles[profile as usize-1];
        let [clip]=attacks.as_slice() else {return Err(bad("ranged cast clip"))};
        let shared=self.profiles.iter().enumerate().any(|(i,(ready,a,m))|*ready==*clip||(i+1!=profile as usize&&(a.contains(clip)||*m==Some(*clip))));
        let [duration,blend,marker]=self.clips[*clip as usize];
        if shared||marker<0.{return Err(bad("ranged cast clip"));}
        let land=landing_ticks(duration,blend,marker,cast_ms);
        if land==0||land>self.ticks(profile,0){return Err(bad("ranged cast landing"));}
        Ok(land)
    }
    /// The ranged basic attack of a profile, if it is one.
    pub fn ranged(&self,style:u32)->Option<Ranged>{self.ranged.get(&style).copied()}
    pub fn ticks(&self,style:u32,fallback:u32)->u32{self.intervals.get(style.saturating_sub(1) as usize).map_or(fallback,|ms|ms.div_ceil(50))}
    pub fn select(&self,bag:Option<&wire::BagState>)->u32{
        let key=self.slots.iter().map(|&s|bag.and_then(|b|b.equipment.get(s)).filter(|i|i.quantity==1).map_or_else(String::new,|i|i.item.clone())).collect::<Vec<_>>();
        *self.rows.get(&key).unwrap_or_else(||&self.rows[&vec![String::new();self.slots.len()]])
    }
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn intervals_quantize_up_without_mutating_legacy_policy(){
        let p=Policy{intervals:vec![1000,1140,1390],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),clips:vec![],profiles:vec![]};
        assert_eq!((p.ticks(1,5),p.ticks(2,5),p.ticks(3,5)),(20,23,28));assert_eq!(p.ticks(4,5),5);
    }
    #[test] fn equipment_selects_public_profile_without_bag_or_serials(){
        let p=Policy{intervals:vec![],layered:false,ranged:BTreeMap::new(),ammo:BTreeMap::new(),clips:vec![],profiles:vec![],slots:vec![0,1],rows:BTreeMap::from([(vec!["".into(),"".into()],1),(vec!["sword".into(),"".into()],2),(vec!["sword".into(),"sword".into()],3)])};
        let sword=wire::ItemStack{item:"sword".into(),instance:99,quantity:1,..Default::default()};
        let mut b=wire::BagState{slots:vec![sword.clone()],equipment:vec![Default::default();2],..Default::default()};
        assert_eq!(p.select(Some(&b)),1);b.equipment[0]=sword.clone();assert_eq!(p.select(Some(&b)),2);
        b.equipment[1]=sword;assert_eq!(p.select(Some(&b)),3);assert_eq!(p.select(None),1);
        b.equipment[0].item="unknown".into();assert_eq!(p.select(Some(&b)),1);
    }
    /// PQ-416 (D-216): N3RB names layered profiles only, each once, with
    /// reach 0..=range and range 0.5..=100 m, then one printable notice of at
    /// most 96 bytes; anything else (or trailing bytes) is refused.
    #[test] fn ranged_attack_file_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3rb-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        let file=|entries:&[(u32,f32,f32)],notice:&[u8]|{let mut b=b"N3RB".to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,reach,range) in entries{b.extend(p.to_le_bytes());b.extend(reach.to_le_bytes());b.extend(range.to_le_bytes());}
            b.extend((notice.len() as u32).to_le_bytes());b.extend(notice);b};
        let policy=||Policy{intervals:vec![1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),clips:vec![],profiles:vec![]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&[])};
        let mut p=policy();
        load(&file(&[(2,40.,42.)],b"Skill Failed - Too far"),&mut p).unwrap();
        assert_eq!((p.ranged(2),p.ranged(1)),(Some(Ranged{reach:40.,range:42.,cast_ms:0,land:0,hit:None,speed:0.,hold:None}),None));
        load(&file(&[(1,0.,0.5),(2,100.,100.)],b""),&mut policy()).unwrap();
        let notice=[b'a';96];load(&file(&[(1,1.,1.)],&notice),&mut policy()).unwrap();
        for bad in [file(&[(0,1.,2.)],b""),file(&[(3,1.,2.)],b""),file(&[(1,1.,2.),(1,1.,2.)],b""),
                    file(&[(1,3.,2.)],b""),file(&[(1,-0.1,2.)],b""),file(&[(1,0.,0.49)],b""),file(&[(1,0.,100.1)],b""),
                    file(&[(1,f32::NAN,2.)],b""),file(&[(1,0.,f32::NAN)],b""),file(&[],b""),file(&[(1,1.,2.)],&[b'a';97]),
                    file(&[(1,1.,2.)],b"tab\there"),file(&[(1,1.,2.)],&[0xc3,0xa9]),
                    [file(&[(1,1.,2.)],b"").as_slice(),&[0]].concat(),file(&[(1,1.,2.)],b"")[..20].to_vec()]{
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        let mut b=file(&[(1,1.,2.)],b"");b[..4].copy_from_slice(b"N3RA");assert!(load(&b,&mut policy()).is_err());
        let mut flat=policy();flat.layered=false;assert!(load(&file(&[(1,1.,2.)],b""),&mut flat).is_err());
        std::fs::remove_dir_all(&dir).unwrap();
    }
    /// PQ-420 (D-217): N3RC adds a cast time per entry. With one, the
    /// profile's single attack clip, which no other profile or role uses, is
    /// stretched to it and the shot lands when its first marker is reached:
    /// blend + marker x cast / duration, rounded up to the tick, within the
    /// interval. The glow bow (clip 26: 1.6 s, blend 0.2 s, marker 1.3737 s,
    /// cast 1.3 s, interval 1450 ms) lands 27 ticks after the shot.
    #[test] fn ranged_cast_landing_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3rc-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        let file=|entries:&[(u32,u32)]|{let mut b=b"N3RC".to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,cast) in entries{b.extend(p.to_le_bytes());b.extend(40f32.to_le_bytes());b.extend(42f32.to_le_bytes());b.extend(cast.to_le_bytes());}
            b.extend(0u32.to_le_bytes());b};
        // Clips: 0 a ready loop, 1 the bow's shot, 2 and 3 swings, 4 a clip with no first marker.
        let policy=||Policy{intervals:vec![1000,1450,1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),
            clips:vec![[1.,0.2,-1.],[1.600001,0.2,1.373_683],[0.95,0.1,0.555],[0.95,0.1,0.4],[1.,0.2,-1.]],
            profiles:vec![(0,vec![2],Some(2)),(0,vec![1],Some(1)),(0,vec![2,3],Some(2)),(0,vec![4],Some(4))]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&[])};
        let mut p=policy();load(&file(&[(2,1300)]),&mut p).unwrap();
        assert_eq!(p.ranged(2),Some(Ranged{reach:40.,range:42.,cast_ms:1300,land:27,hit:None,speed:0.,hold:None}));
        assert_eq!(landing_ticks(1.600001,0.2,1.373_683,1300),27);
        // A cast of 0 keeps PQ-416's landing at acceptance, also for a shared clip.
        let mut p=policy();load(&file(&[(1,0),(3,0)]),&mut p).unwrap();assert_eq!(p.ranged(1).unwrap().land,0);
        // 1.45 s is the most the 1450 ms interval holds (29 ticks); 1.5 s lands at 30.
        let mut p=policy();load(&file(&[(2,1440)]),&mut p).unwrap();assert_eq!(p.ranged(2).unwrap().land,29);
        for bad in [file(&[(2,100)]),file(&[(2,10001)]),file(&[(2,1500)]),
                    file(&[(3,1300)]),          // two attack clips
                    file(&[(1,600)]),           // clip 2 is also profile 3's attack
                    file(&[(4,600)])]{          // no first marker
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        // A clip that is some profile's ready clip is shared too.
        let mut shared=policy();shared.profiles[0].0=1;assert!(load(&file(&[(2,1300)]),&mut shared).is_err());
        std::fs::remove_dir_all(&dir).unwrap();
    }
    /// PQ-421 (D-218): N3RD adds per entry an ammo item (a 1-based inventory
    /// index that does not wear) and its count (1 to the item's stack limit;
    /// 0 with no item), then the ammo notice. The glow bow: 1298's arrow, 1.
    #[test] fn ranged_ammo_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3rd-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        let file=|entries:&[(u32,u32,u32)],ammo_notice:&[u8]|{let mut b=b"N3RD".to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,item,count) in entries{b.extend(p.to_le_bytes());b.extend(40f32.to_le_bytes());b.extend(42f32.to_le_bytes());b.extend(0u32.to_le_bytes());b.extend(item.to_le_bytes());b.extend(count.to_le_bytes());}
            b.extend(0u32.to_le_bytes());b.extend((ammo_notice.len() as u32).to_le_bytes());b.extend(ammo_notice);b};
        let items=[inventory::Item{id:"g:bow".into(),label:"Bow".into(),stack:1,durability:80,starting:1},
                   inventory::Item{id:"g:arrow".into(),label:"Arrow".into(),stack:9999,durability:0,starting:100}];
        let policy=||Policy{intervals:vec![1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),clips:vec![],profiles:vec![]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&items)};
        let mut p=policy();load(&file(&[(2,2,1),(1,0,0)],b"Skill Failed - Not enough item"),&mut p).unwrap();
        assert_eq!((p.ammo(2),p.ammo(1)),(Some(("g:arrow",1)),None));
        assert_eq!(p.ranged(2),Some(Ranged{reach:40.,range:42.,cast_ms:0,land:0,hit:None,speed:0.,hold:None}));
        let mut p=policy();load(&file(&[(2,2,9999)],b""),&mut p).unwrap();assert_eq!(p.ammo(2),Some(("g:arrow",9999)));
        for bad in [file(&[(2,3,1)],b""),          // no such item
                    file(&[(2,1,1)],b""),          // the bow wears
                    file(&[(2,2,0)],b""),file(&[(2,2,10000)],b""),file(&[(2,0,1)],b""),
                    file(&[(2,2,1)],&[b'a';97]),file(&[(2,2,1)],b"tab\there"),
                    file(&[(2,2,1)],b"")[..file(&[(2,2,1)],b"").len()-4].to_vec(),   // no ammo notice
                    [file(&[(2,2,1)],b"").as_slice(),&[0]].concat()]{
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        std::fs::remove_dir_all(&dir).unwrap();
    }
    /// PQ-422 (D-219): N3RE adds per entry, after the ammo count, a hit kind
    /// (0 the basic attack's damage, 1 a type-2 skill hit) and its hit rate
    /// (1-1000), add damage (0-300) and add damage plus (0-10000), all 0 for
    /// kind 0. The glow bow: 1298's archery rows, 100 / 100 / 0.
    #[test] fn ranged_skill_hit_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3re-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        let file=|entries:&[(u32,[u32;4])]|{let mut b=b"N3RE".to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,hit) in entries{b.extend(p.to_le_bytes());b.extend(40f32.to_le_bytes());b.extend(42f32.to_le_bytes());b.extend(0u32.to_le_bytes());
                b.extend(2u32.to_le_bytes());b.extend(1u32.to_le_bytes());for v in hit{b.extend(v.to_le_bytes());}}
            b.extend(0u32.to_le_bytes());b.extend(0u32.to_le_bytes());b};
        let items=[inventory::Item{id:"g:bow".into(),label:"Bow".into(),stack:1,durability:80,starting:1},
                   inventory::Item{id:"g:arrow".into(),label:"Arrow".into(),stack:9999,durability:0,starting:100}];
        let policy=||Policy{intervals:vec![1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),clips:vec![],profiles:vec![]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&items)};
        let mut p=policy();load(&file(&[(2,[1,100,100,0]),(1,[0,0,0,0])]),&mut p).unwrap();
        let archery=crate::damage::SkillHit{hit_rate:100,add_damage:100,add_damage_plus:0};
        assert_eq!(p.ranged(2),Some(Ranged{reach:40.,range:42.,cast_ms:0,land:0,hit:Some(archery),speed:0.,hold:None}));
        assert_eq!((p.ranged(1).unwrap().hit,p.ammo(2)),(None,Some(("g:arrow",1))));
        let mut p=policy();load(&file(&[(2,[1,1000,300,10000]),(1,[1,1,0,0])]),&mut p).unwrap();
        assert_eq!(p.ranged(1).unwrap().hit,Some(crate::damage::SkillHit{hit_rate:1,add_damage:0,add_damage_plus:0}));
        for bad in [file(&[(2,[2,100,100,0])]),file(&[(2,[1,0,100,0])]),file(&[(2,[1,1001,100,0])]),
                    file(&[(2,[1,100,301,0])]),file(&[(2,[1,100,100,10001])]),file(&[(2,[0,100,0,0])]),
                    file(&[(2,[0,0,0,1])]),file(&[(2,[1,100,100,0])])[..file(&[(2,[1,100,100,0])]).len()-1].to_vec(),
                    [file(&[(2,[1,100,100,0])]).as_slice(),&[0]].concat()]{
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        std::fs::remove_dir_all(&dir).unwrap();
    }
    /// PQ-423 (D-220): N3RF adds per entry, after the skill hit, the
    /// client's cast effect: a clip key (0-64 printable bytes; a key needs a
    /// cast time), then 0 joints without a key, else 1-2 distinct joints,
    /// index + 1 up to 128. The glow bow: "ranged-cast-500" at joint 12 (13).
    #[test] fn ranged_cast_effect_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3rf-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        let file=|entries:&[(u32,u32,&[u8],&[u32])]|{let mut b=b"N3RF".to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,cast,key,joints) in entries{b.extend(p.to_le_bytes());b.extend(40f32.to_le_bytes());b.extend(42f32.to_le_bytes());b.extend(cast.to_le_bytes());
                b.extend([0u32;6].iter().flat_map(|v|v.to_le_bytes()));
                b.extend((key.len() as u32).to_le_bytes());b.extend(*key);b.extend((joints.len() as u32).to_le_bytes());for j in *joints{b.extend(j.to_le_bytes());}}
            b.extend(0u32.to_le_bytes());b.extend(0u32.to_le_bytes());b};
        let policy=||Policy{intervals:vec![1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),
            clips:vec![[1.,0.2,-1.],[1.600001,0.2,1.373_683]],profiles:vec![(0,vec![0],Some(0)),(0,vec![1],Some(1))]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&[])};
        let mut p=policy();load(&file(&[(2,1300,b"ranged-cast-500",&[13])]),&mut p).unwrap();
        assert_eq!(p.ranged(2),Some(Ranged{reach:40.,range:42.,cast_ms:1300,land:27,hit:None,speed:0.,hold:None}));
        let mut p=policy();load(&file(&[(2,1300,b"x",&[0,128]),(1,0,b"",&[])]),&mut p).unwrap();
        assert_eq!(p.ranged(1).unwrap().cast_ms,0);
        let long=[b'k';65];
        for bad in [file(&[(2,1300,b"",&[13])]),            // joints without a key
                    file(&[(2,1300,b"k",&[])]),             // a key without joints
                    file(&[(2,1300,b"k",&[1,2,3])]),        // three joints
                    file(&[(2,1300,b"k",&[13,13])]),        // a repeated joint
                    file(&[(2,1300,b"k",&[129])]),          // past 128
                    file(&[(2,1300,&long,&[13])]),          // a 65-byte key
                    file(&[(2,1300,b"tab\there",&[13])]),   // unprintable
                    file(&[(1,0,b"k",&[13])]),              // no cast time
                    file(&[(2,1300,b"k",&[13])])[..file(&[(2,1300,b"k",&[13])]).len()-1].to_vec(),
                    [file(&[(2,1300,b"k",&[13])]).as_slice(),&[0]].concat()]{
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        std::fs::remove_dir_all(&dir).unwrap();
    }
    /// PQ-417 (D-222): N3RG adds per entry, after the cast effect, the
    /// client's flight: a clip key (0-64 printable bytes; a key needs a cast
    /// time), its source joint (index + 1 up to 128) and speed (1-1000 m/s),
    /// a hit clip key and joint, a release audio key; without a flight key
    /// every field is 0 or empty. The glow bow: "ranged-flight-590" from
    /// joint 12 at 77 m/s, "ranged-hit-550" at joint 0, "ranged-release".
    #[test] fn ranged_flight_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3rg-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        type Flight<'a>=(&'a [u8],u32,f32,&'a [u8],u32,&'a [u8]);
        let file=|entries:&[(u32,u32,Flight)]|{let mut b=b"N3RG".to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,cast,(key,joint,speed,hit,hit_joint,release)) in entries{b.extend(p.to_le_bytes());b.extend(40f32.to_le_bytes());b.extend(42f32.to_le_bytes());b.extend(cast.to_le_bytes());
                b.extend([0u32;8].iter().flat_map(|v|v.to_le_bytes()));
                b.extend((key.len() as u32).to_le_bytes());b.extend(*key);b.extend(joint.to_le_bytes());b.extend(speed.to_le_bytes());
                b.extend((hit.len() as u32).to_le_bytes());b.extend(*hit);b.extend(hit_joint.to_le_bytes());
                b.extend((release.len() as u32).to_le_bytes());b.extend(*release);}
            b.extend(0u32.to_le_bytes());b.extend(0u32.to_le_bytes());b};
        let policy=||Policy{intervals:vec![1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),
            clips:vec![[1.,0.2,-1.],[1.600001,0.2,1.373_683]],profiles:vec![(0,vec![0],Some(0)),(0,vec![1],Some(1))]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&[])};
        let glow:Flight=(b"ranged-flight-590",13,77.,b"ranged-hit-550",1,b"ranged-release");
        let mut p=policy();load(&file(&[(2,1300,glow)]),&mut p).unwrap();
        // PQ-439 (D-223): the server keeps the flight's speed (the arrival).
        assert_eq!(p.ranged(2),Some(Ranged{reach:40.,range:42.,cast_ms:1300,land:27,hit:None,speed:77.,hold:None}));
        let none:Flight=(b"",0,0.,b"",0,b"");
        let mut p=policy();load(&file(&[(2,1300,(b"f",0,1.,b"",0,b"")),(1,0,none)]),&mut p).unwrap();   // the bounds; no flight on a profile without a cast
        assert_eq!((p.ranged(2).unwrap().speed,p.ranged(1).unwrap().speed),(1.,0.));
        let mut p=policy();load(&file(&[(2,1300,(b"f",128,1000.,b"h",128,b"r"))]),&mut p).unwrap();
        let long=[b'k';65];
        for bad in [file(&[(1,0,(b"f",13,77.,b"",0,b""))]),       // no cast time
                    file(&[(2,1300,(b"",13,0.,b"",0,b""))]),       // a joint without a key
                    file(&[(2,1300,(b"",0,77.,b"",0,b""))]),       // a speed without a key
                    file(&[(2,1300,(b"",0,0.,b"h",0,b""))]),       // a hit without a flight
                    file(&[(2,1300,(b"",0,0.,b"",1,b""))]),        // a hit joint without a flight
                    file(&[(2,1300,(b"",0,0.,b"",0,b"r"))]),       // a release without a flight
                    file(&[(2,1300,(b"f",13,77.,b"",1,b""))]),     // a hit joint without a hit clip
                    file(&[(2,1300,(b"f",129,77.,b"",0,b""))]),    // a joint past 128
                    file(&[(2,1300,(b"f",13,77.,b"h",129,b""))]),
                    file(&[(2,1300,(b"f",13,0.5,b"",0,b""))]),     // too slow
                    file(&[(2,1300,(b"f",13,1000.5,b"",0,b""))]),  // too fast
                    file(&[(2,1300,(b"f",13,f32::NAN,b"",0,b""))]),
                    file(&[(2,1300,(&long,13,77.,b"",0,b""))]),
                    file(&[(2,1300,(b"f",13,77.,&long,0,b""))]),
                    file(&[(2,1300,(b"f",13,77.,b"",0,&long))]),
                    file(&[(2,1300,(b"a\tb",13,77.,b"",0,b""))]),
                    file(&[(2,1300,glow)])[..file(&[(2,1300,glow)]).len()-1].to_vec(),
                    [file(&[(2,1300,glow)]).as_slice(),&[0]].concat()]{
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        std::fs::remove_dir_all(&dir).unwrap();
    }
    /// PQ-467 (D-233): N3RH adds per entry, after the flight, the hold: f32
    /// distance (0: none, else 0.5-200 m) and u32 plane (0 3-D, 1 the ground
    /// plane; 0 without a hold). The glow bow: sqrt(40^2 + 1000) on the
    /// ground plane. N3RG still reads, with no hold.
    #[test] fn ranged_hold_bounds(){
        let dir=std::env::temp_dir().join(format!("n3e-n3rh-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join("ranged-attack.bin");
        let file=|magic:&[u8],entries:&[(u32,f32,u32)]|{let mut b=magic.to_vec();b.extend((entries.len() as u32).to_le_bytes());
            for (p,distance,plane) in entries{b.extend(p.to_le_bytes());b.extend(40f32.to_le_bytes());b.extend(42f32.to_le_bytes());b.extend(1300u32.to_le_bytes());
                b.extend([0u32;8].iter().flat_map(|v|v.to_le_bytes()));
                b.extend([0u32;2].iter().flat_map(|v|v.to_le_bytes()));b.extend(0f32.to_le_bytes());b.extend([0u32;3].iter().flat_map(|v|v.to_le_bytes()));
                if magic==b"N3RH"{b.extend(distance.to_le_bytes());b.extend(plane.to_le_bytes());}}
            b.extend(0u32.to_le_bytes());b.extend(0u32.to_le_bytes());b};
        let policy=||Policy{intervals:vec![1000,1450],layered:true,slots:vec![],rows:BTreeMap::new(),ranged:BTreeMap::new(),ammo:BTreeMap::new(),
            clips:vec![[1.,0.2,-1.],[1.600001,0.2,1.373_683]],profiles:vec![(0,vec![0],Some(0)),(0,vec![1],Some(1))]};
        let load=|bytes:&[u8],p:&mut Policy|{std::fs::write(&path,bytes).unwrap();p.load_ranged(&path,&[])};
        let glow=2600f32.sqrt();
        let mut p=policy();load(&file(b"N3RH",&[(2,glow,1)]),&mut p).unwrap();
        assert_eq!(p.ranged(2),Some(Ranged{reach:40.,range:42.,cast_ms:1300,land:27,hit:None,speed:0.,hold:Some(Hold{distance:glow,planar:true})}));
        let mut p=policy();load(&file(b"N3RH",&[(2,0.5,0)]),&mut p).unwrap();assert_eq!(p.ranged(2).unwrap().hold,Some(Hold{distance:0.5,planar:false}));
        let mut p=policy();load(&file(b"N3RH",&[(2,200.,1)]),&mut p).unwrap();assert_eq!(p.ranged(2).unwrap().hold,Some(Hold{distance:200.,planar:true}));
        let mut p=policy();load(&file(b"N3RH",&[(2,0.,0)]),&mut p).unwrap();assert_eq!(p.ranged(2).unwrap().hold,None);
        let mut p=policy();load(&file(b"N3RG",&[(2,0.,0)]),&mut p).unwrap();assert_eq!(p.ranged(2).unwrap().hold,None);   // N3RG: no hold
        let good=file(b"N3RH",&[(2,glow,1)]);
        for bad in [file(b"N3RH",&[(2,0.,1)]),file(b"N3RH",&[(2,0.49,1)]),file(b"N3RH",&[(2,200.5,1)]),file(b"N3RH",&[(2,-1.,0)]),
                    file(b"N3RH",&[(2,f32::NAN,1)]),file(b"N3RH",&[(2,f32::INFINITY,1)]),file(b"N3RH",&[(2,glow,2)]),
                    good[..good.len()-1].to_vec(),[good.as_slice(),&[0]].concat(),
                    [b"N3RG".as_slice(),&good[4..]].concat()]{
            assert!(load(&bad,&mut policy()).is_err(),"{bad:?}");
        }
        // The check itself: within the hold on the ground plane, inclusive.
        let bow=Ranged{reach:40.,range:42.,cast_ms:1300,land:27,hit:None,speed:77.,hold:Some(Hold{distance:5.,planar:true})};
        let a=wire::Entity::default();
        let at=|x,y,z|wire::Entity{x,y,z,..Default::default()};
        assert!(bow.holds(&a,&at(3.,90.,4.))&&!bow.holds(&a,&at(3.,0.,4.01)));
        assert!(Ranged{hold:None,..bow}.holds(&a,&at(300.,0.,0.)));
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
