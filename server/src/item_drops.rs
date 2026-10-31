//! Ordered, package-defined item drops. Evidence and remaining gates: content/item-drops.md.
use crate::content::{bad, Reader, Result};
use std::collections::BTreeSet;

#[derive(Clone, Debug)]
pub struct Item {
    pub id: String,
    pub quantity: u32,
    pub durability: u32,
}
#[derive(Clone, Debug)]
pub struct Row {
    pub chance: u32,
    pub level_penalty: u32,
    pub premium: bool,
    /// A direct row has one entry and consumes no group draw.
    pub group: bool,
    /// One-based catalog indices; zero is an empty physical group slot.
    pub slots: Vec<u32>,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub multiplier: u32,
    pub increment: u32,
    pub seed: u32,
    pub group_bound: u32,
    pub event_percent: u32,
    pub event_unit: f32,
    pub premium_rate: f32,
    pub items: Vec<Item>,
    pub rows: Vec<Row>,
}
impl Policy {
    pub fn read(r: &mut Reader) -> Result<Self> {
        let mut p = Self {
            multiplier:r.u()?, increment:r.u()?, seed:r.u()?, group_bound:r.u()?,
            event_percent:r.u()?, event_unit:r.f()?, premium_rate:r.f()?,
            items:Vec::new(), rows:Vec::new(),
        };
        let n=r.u()?;
        if !(1..=64).contains(&n) {return Err(bad("drop item count"));}
        for _ in 0..n {p.items.push(Item{id:r.string()?,quantity:r.u()?,durability:r.u()?});}
        let n=r.u()?;
        if !(1..=6).contains(&n) {return Err(bad("drop row count"));}
        for _ in 0..n {
            let chance=r.u()?; let level_penalty=r.u()?; let premium=r.u()?; let group=r.u()?; let n=r.u()?;
            if premium>1 || group>1 || !(1..=30).contains(&n) {return Err(bad("drop row flags/count"));}
            let mut slots=Vec::new();for _ in 0..n {slots.push(r.u()?);}
            p.rows.push(Row{chance,level_penalty,premium:premium==1,group:group==1,slots});
        }
        p.validate()?;Ok(p)
    }
    pub fn encode(&self, b:&mut Vec<u8>) {
        for v in [self.multiplier,self.increment,self.seed,self.group_bound,self.event_percent] {b.extend(v.to_le_bytes());}
        b.extend(self.event_unit.to_le_bytes());b.extend(self.premium_rate.to_le_bytes());
        b.extend((self.items.len() as u32).to_le_bytes());
        for i in &self.items {b.extend((i.id.len() as u32).to_le_bytes());b.extend(i.id.as_bytes());b.extend(i.quantity.to_le_bytes());b.extend(i.durability.to_le_bytes());}
        b.extend((self.rows.len() as u32).to_le_bytes());
        for r in &self.rows {
            for v in [r.chance,r.level_penalty,r.premium as u32,r.group as u32,r.slots.len() as u32] {b.extend(v.to_le_bytes());}
            for v in &r.slots {b.extend(v.to_le_bytes());}
        }
    }
    pub fn validate(&self) -> Result<()> {
        if !(1..=32767).contains(&self.group_bound) || self.event_percent>255
            || !self.event_unit.is_finite() || !(0.0..=1.0).contains(&self.event_unit)
            || !self.premium_rate.is_finite() || !(0.0..=1.0).contains(&self.premium_rate)
            || !(1..=64).contains(&self.items.len()) || !(1..=6).contains(&self.rows.len()) {
            return Err(bad("drop policy bounds"));
        }
        let mut ids=BTreeSet::new();
        for i in &self.items {
            if i.id.is_empty() || i.id.len()>129 || !ids.insert(&i.id) || !(1..=9999).contains(&i.quantity) || i.durability>65535 {
                return Err(bad("drop item definition"));
            }
        }
        for r in &self.rows {
            if r.chance>10000 || r.level_penalty>10000 || !(1..=30).contains(&r.slots.len())
                || (!r.group && (r.slots.len()!=1 || r.slots[0]==0))
                || r.slots.iter().any(|v|*v as usize>self.items.len()) {return Err(bad("drop row definition"));}
        }
        Ok(())
    }
    /// x87 uses the exact promoted binary32 constants, with binary64 operations.
    pub fn chance(&self,row:&Row,npc_level:u32,player_level:u32,premium:bool)->Result<i32> {
        if !(1..=255).contains(&npc_level) || !(1..=255).contains(&player_level) {return Err(bad("drop level input"));}
        let mut chance=row.chance as i32;
        if self.event_percent>0 {
            let rate=self.event_percent as f64*self.event_unit as f64;
            chance=(chance as f64+chance as f64*rate).trunc() as i32;
        }
        chance-=player_level.saturating_sub(npc_level) as i32*row.level_penalty as i32;
        if premium && row.premium && chance<10000 {
            chance=((chance as f64+chance as f64*self.premium_rate as f64).trunc() as i32).min(10000);
        }
        Ok(chance)
    }
    /// Replays frozen draws without reading random state or mutable entitlement data.
    pub fn replay(&self,rolls:&[Roll],npc_level:u32,player_level:u32,premium:bool,coins:bool)->Result<Vec<Entry>> {
        self.validate()?;
        let mut entries=Vec::new();let mut consumed=0;
        for (index,row) in self.rows.iter().enumerate() {
            if entries.len()+usize::from(coins)==6 {break;}
            let roll=rolls.get(consumed).ok_or_else(||bad("missing frozen drop draw"))?;consumed+=1;
            if !(1..=10000).contains(&roll.chance) {return Err(bad("drop chance draw"));}
            let passed=roll.chance as i32<=self.chance(row,npc_level,player_level,premium)?;
            if !passed {if roll.group.is_some(){return Err(bad("unused group draw"));}continue;}
            let slot=if row.group {
                let draw=roll.group.ok_or_else(||bad("missing group draw"))?;
                if draw>=self.group_bound {return Err(bad("group draw bound"));}
                draw as usize%row.slots.len()
            } else {if roll.group.is_some(){return Err(bad("direct group draw"));}0};
            if let Some(item)=row.slots[slot].checked_sub(1) {entries.push(Entry{row:index as u32,item});}
        }
        if consumed!=rolls.len() {return Err(bad("trailing frozen drop draws"));}
        Ok(entries)
    }
    pub fn generate(&self,random:&mut crate::drop_generation::Random,group:&mut GroupRandom,npc:u32,player:u32,premium:bool,coins:bool)->Result<Outcome> {
        self.validate()?;let mut rolls=Vec::new();let mut entries=0;
        for row in &self.rows {
            if entries+usize::from(coins)==6 {break;}
            let chance=random.draw(1,10000)?;
            let passed=chance as i32<=self.chance(row,npc,player,premium)?;
            let draw=if passed&&row.group {Some(group.draw(self.group_bound)?)}else{None};
            if passed && row.slots[draw.map_or(0,|v|v as usize%row.slots.len())]>0 {entries+=1;}
            rolls.push(Roll{chance,group:draw});
        }
        let entries=self.replay(&rolls,npc,player,premium,coins)?;
        Ok(Outcome{player_level:player,premium,rolls,entries})
    }
}
#[derive(Clone, Debug, PartialEq)]
pub struct Roll {pub chance:u32,pub group:Option<u32>}
#[derive(Clone, Debug, PartialEq)]
pub struct Entry {pub row:u32,pub item:u32}
#[derive(Clone, Debug)]
pub struct Outcome {pub player_level:u32,pub premium:bool,pub rolls:Vec<Roll>,pub entries:Vec<Entry>}
impl Outcome {
    pub fn encode(&self,b:&mut Vec<u8>)->Result<()> {
        if !(1..=255).contains(&self.player_level)||self.rolls.len()>6||self.entries.len()>6 {return Err(bad("item outcome bounds"));}
        b.extend(self.player_level.to_le_bytes());b.extend((self.premium as u32).to_le_bytes());
        b.extend((self.rolls.len() as u32).to_le_bytes());
        for r in &self.rolls {
            if !(1..=10000).contains(&r.chance)||r.group.is_some_and(|v|v>=32767) {return Err(bad("item outcome draw"));}
            b.extend(r.chance.to_le_bytes());b.extend(r.group.unwrap_or(u32::MAX).to_le_bytes());
        }
        b.extend((self.entries.len() as u32).to_le_bytes());
        for e in &self.entries {if e.row>=6||e.item>=64{return Err(bad("item outcome index"));}b.extend(e.row.to_le_bytes());b.extend(e.item.to_le_bytes());}
        Ok(())
    }
}
/// Independent bounded-state stream; parameters are package data, not game IDs.
pub struct GroupRandom {state:u32,multiplier:u32,increment:u32}
impl GroupRandom {
    pub fn new(p:&Policy)->Self {Self{state:p.seed,multiplier:p.multiplier,increment:p.increment}}
    pub fn draw(&mut self,bound:u32)->Result<u32> {
        if !(1..=32767).contains(&bound){return Err(bad("group random bound"));}
        self.state=self.state.wrapping_mul(self.multiplier).wrapping_add(self.increment)%(bound*2);
        Ok(self.state>>1)
    }
}

pub fn claim_payload(operation:u64,encounter:u64,owner:i64,item:&str,quantity:u32,durability:u32)->Result<Vec<u8>> {
    if operation==0||operation>i64::MAX as u64||encounter==0||encounter>i64::MAX as u64||owner<=0||item.is_empty()||item.len()>129||!(1..=9999).contains(&quantity)||durability>65535 {return Err(bad("item claim payload"));}
    let mut b=b"N3C3".to_vec();for v in [operation,encounter,owner as u64]{b.extend(v.to_le_bytes());}
    b.extend((item.len() as u32).to_le_bytes());b.extend(item.as_bytes());b.extend(quantity.to_le_bytes());b.extend(durability.to_le_bytes());Ok(b)
}
pub fn expire(t:&mut postgres::Transaction<'_>,o:&crate::accounts::Owner,op:i64)->Result<crate::wire::ClaimResult> {
    let d=t.query_one("SELECT owner,encounter,item,quantity,durability,state,clock_timestamp()>=expires_at FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2 AND kind=2 FOR UPDATE",&[&o.realm,&op])?;
    let owner:i64=d.get(0);
    if d.get::<_,String>(5)!="available" {return crate::loot::stored(t,o,owner,op);}
    if !d.get::<_,bool>(6){return Ok(crate::loot::response(op as u64,"available"));}
    let encounter:i64=d.get(1);
    let payload=claim_payload(op as u64,encounter as u64,owner,&d.get::<_,String>(2),d.get::<_,i32>(3) as u32,d.get::<_,i32>(4) as u32)?;
    let p=t.query_one("SELECT p.count,r.revision FROM character_progress p JOIN character_reward_progress r USING(character_id) WHERE p.character_id=$1 AND r.realm=$2 FOR UPDATE OF p,r",&[&owner,&o.realm])?;
    crate::loot::fault("before_mutation");
    t.execute("INSERT INTO loot_claim_results(realm,claim_operation,encounter,owner,payload,digest,status,result_count,revision) VALUES($1,$2,$3,$4,$5,$6,'expired',$7,$8)",&[&o.realm,&op,&encounter,&owner,&payload,&&openssl::sha::sha256(&payload)[..],&p.get::<_,i32>(0),&p.get::<_,i64>(1)])?;
    crate::loot::fault("during_mutation");
    t.execute("UPDATE loot_entitlements SET state='expired',revision=revision+1,result_operation=claim_operation WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?;
    crate::loot::stored(t,o,owner,op)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn policy()->Policy {Policy{multiplier:0x7059,increment:0xe0b2,seed:0x5b88,group_bound:10000,event_percent:10,event_unit:0.01,premium_rate:0.3,
        items:vec![Item{id:"test:item/a".into(),quantity:20,durability:100}],
        rows:vec![Row{chance:1000,level_penalty:100,premium:true,group:true,slots:vec![0,1,0]}]}}
    #[test]
    fn independent_stream_precision_and_order()->Result<()> {
        let p=policy();let mut rng=GroupRandom::new(&p);
        let draws=[10000,1000,10000,10000,1000,10000].map(|b|rng.draw(b).unwrap());
        assert_eq!(draws,[2637,518,6959,6560,921,7642]);
        assert!(rng.draw(0).is_err());assert!(rng.draw(32768).is_err());
        assert_eq!(p.chance(&p.rows[0],10,10,false)?,1099); // f64 .01 would incorrectly give1100.
        assert_eq!(p.chance(&p.rows[0],10,12,true)?,1168); // event, level penalty, premium, truncation.
        assert_eq!(p.chance(&p.rows[0],10,30,true)?,-1171); // Negative chance never wins a positive draw.
        let hit=[Roll{chance:1099,group:Some(4)}];
        assert_eq!(p.replay(&hit,10,10,false,false)?,[Entry{row:0,item:0}]);
        assert!(p.replay(&[Roll{chance:1099,group:Some(3)}],10,10,false,false)?.is_empty());
        assert!(p.replay(&[Roll{chance:1100,group:None}],10,10,false,false)?.is_empty());
        assert!(p.replay(&hit,10,11,false,false).is_err()); // Failed chance must not consume group stream.
        assert!(p.replay(&[Roll{chance:1,group:Some(10000)}],10,10,false,false).is_err());
        assert!(p.replay(&[],10,10,false,false).is_err());
        Ok(())
    }
    #[test]
    fn full_bundle_and_exact_replay()->Result<()> {
        let mut p=policy();p.event_percent=0;p.rows=vec![Row{chance:10000,level_penalty:0,premium:false,group:false,slots:vec![1]};6];
        let rolls=vec![Roll{chance:10000,group:None};6];
        assert_eq!(p.replay(&rolls,1,1,false,false)?.len(),6);
        assert_eq!(p.replay(&rolls[..5],1,1,false,true)?.len(),5);
        assert!(p.replay(&rolls,1,1,false,true).is_err());
        let mut b=Vec::new();p.encode(&mut b);let mut reader=Reader::from_bytes(b.clone());
        let decoded=Policy::read(&mut reader)?;reader.end()?;
        let mut restored=Vec::new();decoded.encode(&mut restored);assert_eq!(restored,b);
        assert_eq!(decoded.replay(&rolls,1,1,false,false)?,p.replay(&rolls,1,1,false,false)?);
        let mut rng=crate::drop_generation::Random::new()?;let mut group=GroupRandom::new(&p);
        let out=p.generate(&mut rng,&mut group,1,1,false,true)?;
        assert_eq!(out.entries.len(),5);assert_eq!(out.rolls.len(),5);
        Ok(())
    }
    #[test]
    fn whole_stack_fits_without_loss_and_empty_precedence() {
        use crate::{inventory::drop_slot,wire};
        let mut bag=wire::BagState{slots:vec![wire::ItemStack{instance:1,item:"test:item/a".into(),quantity:9990,durability:5},wire::ItemStack::default()],..Default::default()};
        assert_eq!(drop_slot(&bag,"test:item/a",20,9999),Some(1));
        bag.slots.pop();assert_eq!(drop_slot(&bag,"test:item/a",20,9999),None);
        assert_eq!(drop_slot(&bag,"test:item/a",9,9999),Some(0));
        assert_eq!(drop_slot(&bag,"test:item/b",1,9999),None);
        assert_eq!(drop_slot(&bag,"test:item/a",30000,9999),None);
    }
}
