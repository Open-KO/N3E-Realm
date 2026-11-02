use openssl::sha::sha256;
use std::{collections::{BTreeMap, BTreeSet}, fs, path::Path};
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
pub fn bad(s: &str) -> Box<dyn std::error::Error + Send + Sync> {
    std::io::Error::other(s).into()
}
pub struct Reader {
    pub bytes: Vec<u8>,
    at: usize,
}
pub const MAX_ASSET: u64 = 16 * 1024 * 1024;
// A package's static world asset carries a map-sized atlas and vertex buffer.
// The server never interprets it, but it does hash it with the rest of the
// release, so it needs its own bound rather than a blanket increase.
pub const MAX_WORLD_ASSET: u64 = 32 * 1024 * 1024;
// The chunked encoding (N3W2, PQ-231, D-159) for worlds that do not fit N3W1.
pub const MAX_CHUNKED_WORLD_ASSET: u64 = 384 * 1024 * 1024;
// An N3W2 world's textures (N3WT, PQ-233): 384 MiB of pixels and the headers of
// 4096 textures of 12 levels.
pub const MAX_WORLD_TEXTURES_ASSET: u64 = 8 + 4096 * (4 + 12 * 8) + 384 * 1024 * 1024;
// Maps blended over the near terrain (N3WO, PQ-387, D-204): a 40-byte header,
// 65,536 block keys and 256 MiB of pixels (tools/assetc/world_overlay.py).
pub const MAX_WORLD_OVERLAY_ASSET: u64 = 40 + 65536 * 8 + 256 * 1024 * 1024;
impl Reader {
    pub fn from_bytes(bytes: Vec<u8>) -> Self { Self { bytes, at: 0 } }
    pub fn open(path: &Path) -> Result<Self> {
        Reader::open_bounded(path, MAX_ASSET)
    }
    pub fn open_bounded(path: &Path, limit: u64) -> Result<Self> {
        if fs::metadata(path)?.len() > limit {
            return Err(bad("file bound"));
        }
        Ok(Self {
            bytes: fs::read(path)?,
            at: 0,
        })
    }
    pub fn take(&mut self, n: usize) -> Result<&[u8]> {
        if n > self.bytes.len() - self.at {
            return Err(bad("truncated cooked data"));
        }
        let p = self.at;
        self.at += n;
        Ok(&self.bytes[p..self.at])
    }
    pub fn u(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into()?))
    }
    pub fn f(&mut self) -> Result<f32> {
        let f = f32::from_bits(self.u()?);
        if !f.is_finite() || f.abs() > 1e6 {
            return Err(bad("finite bound"));
        }
        Ok(f)
    }
    pub fn string(&mut self) -> Result<String> {
        let n = self.u()? as usize;
        if n == 0 || n > 200 {
            return Err(bad("string bound"));
        }
        Ok(std::str::from_utf8(self.take(n)?)?.to_owned())
    }
    pub fn end(&self) -> Result<()> {
        if self.at != self.bytes.len() {
            Err(bad("trailing cooked bytes"))
        } else {
            Ok(())
        }
    }
}
// PQ-316 (D-185): postprocess.bin, N3PF and seven f32 (threshold, bloom,
// exposure, saturation, lift, adaptation rate, blur variance), in the bounds
// tools/assetc/postprocess.py cooks; the variance must be above zero.
pub fn postprocess(mut p: Reader) -> Result<[f32; 7]> {
    if p.take(4)? != b"N3PF" {
        return Err(bad("postprocess magic"));
    }
    let mut values = [0f32; 7];
    for v in values.iter_mut() {
        *v = p.f()?;
    }
    p.end()?;
    let bounds = [(0., 1.), (0., 4.), (0., 16.), (0., 4.), (0., 4.), (0., 100.), (0., 16.)];
    if values.iter().zip(bounds).any(|(x, (lo, hi))| !(lo..=hi).contains(x)) || values[6] <= 0. {
        return Err(bad("postprocess bounds"));
    }
    Ok(values)
}
// PQ-354 (D-194): item-heads.bin, N3IH: a token (0-32 bytes, printable
// ASCII 33-126), the head count (0-64; zero only with a token), then per head
// a defined inventory item (each once), its name colour (at most 0xffffff), its
// line count (0-4) and each line's text (1-64 printable ASCII 32-126) and
// colour, as tools/assetc/item_heads.py cooks them. Client presentation: the
// server checks the file and otherwise ignores it. Returns the head count.
pub fn item_heads(mut p: Reader, items: &[&str]) -> Result<usize> {
    if p.take(4)? != b"N3IH" {
        return Err(bad("item heads magic"));
    }
    fn text(p: &mut Reader, lo: usize, hi: usize, first: u8) -> Result<String> {
        let n = p.u()? as usize;
        if n < lo || n > hi {
            return Err(bad("item heads string bound"));
        }
        let b = p.take(n)?;
        if b.iter().any(|&c| !(first..=126).contains(&c)) {
            return Err(bad("item heads text"));
        }
        Ok(String::from_utf8(b.to_vec())?)
    }
    let token = text(&mut p, 0, 32, 33)?;
    let count = p.u()? as usize;
    if count > 64 || (count == 0 && token.is_empty()) {
        return Err(bad("item heads count"));
    }
    let mut seen = BTreeSet::new();
    for _ in 0..count {
        let item = text(&mut p, 1, 128, 33)?;
        if !items.contains(&item.as_str()) || !seen.insert(item) {
            return Err(bad("item head item"));
        }
        let (name, lines) = (p.u()?, p.u()?);
        if name > 0xff_ffff || lines > 4 {
            return Err(bad("item head bounds"));
        }
        for _ in 0..lines {
            text(&mut p, 1, 64, 32)?;
            if p.u()? > 0xff_ffff {
                return Err(bad("item head line colour"));
            }
        }
    }
    p.end()?;
    Ok(count)
}
#[derive(Clone)]
pub struct Release {
    pub appearance: crate::appearance::Policy,
    pub assets: BTreeMap<String,Vec<u8>>,
    pub properties: Vec<crate::wire::Property>,
    pub turbo_multiplier: f32,
    pub protocol: u32,
    pub game: String,
    pub hash: String,
    pub collision: crate::movement::Collision,
    pub rules: crate::rules::Rules,
    /// Most characters an account has in this realm: the front end's slot
    /// count (spec 11, front-end.bin), else 8.
    pub character_slots: u32,
}
/// front-end.bin's bound (spec 11; tools/assetc/main.py FRONT_END_FILE).
pub const MAX_FRONT_END_ASSET: u64 = 64 * 1024 * 1024;
pub fn load(root: &Path) -> Result<Release> {
    let mut r = Reader::open(&root.join("release.bin"))?;
    let hash = sha256(&r.bytes)
        .iter()
        .map(|x| format!("{x:02x}"))
        .collect();
    if r.take(4)? != b"N3R1" || r.u()? != 1 {
        return Err(bad("incompatible release"));
    }
    let engine = r.u()?;
    let protocol = r.u()?;
    // Engines 38 (PQ-253), 39 (PQ-265: N3MM looks models with render
    // states) and 40 (PQ-283: N3NI / N3MI looks models with influence
    // tables) add client presentation only and keep wire 30; so does 41
    // (PQ-272: N3N4 templates with a drawn scale, sent as `Entity.scale`),
    // and 42 (spec 11: the KO front end, front-end.bin).
    if !(1..=42).contains(&engine)
        || if engine >= 38 { protocol != 30 } else if engine >= 15 { protocol != engine - 7 } else if engine >= 13 {
            protocol != 7
        } else if engine == 12 {
            // Engine 12 adds the client's static world asset and retains wire 6.
            protocol != 6
        } else if engine >= 9 {
            protocol != engine - 5
        } else if engine == 8 {
            !(1..=3).contains(&protocol)
        } else if engine == 7 {
            protocol != 3
        } else if engine >= 3 {
            !(1..=2).contains(&protocol)
        } else {
            protocol != engine
        }
    {
        return Err(bad("incompatible release"));
    }
    let game = r.string()?;
    let _version = r.string()?;
    if game.len() > 32
        || !game
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
    {
        return Err(bad("game ID"));
    }
    let n = r.u()?;
    if n == 0 || n > 256 {
        return Err(bad("manifest count"));
    }
    let mut files = BTreeSet::new();
    let mut assets = BTreeMap::new();
    let mut world_magic: Option<u8> = None;
    let root = fs::canonicalize(root)?;
    for _ in 0..n {
        let name = r.string()?;
        if name == "."
            || name == ".."
            || !name
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"_.-".contains(&b))
            || !files.insert(name.clone())
        {
            return Err(bad("manifest path/duplicate"));
        }
        let size = r.u()? as usize;
        let hash = r.take(32)?.to_vec();
        let path = fs::canonicalize(root.join(&name))?;
        if path.parent() != Some(root.as_path()) {
            return Err(bad("asset containment"));
        }
        let f = Reader::open_bounded(
            &path,
            if name == "render-detail.bin" {
                128 * 1024 * 1024
            } else if name == "front-end.bin" {
                MAX_FRONT_END_ASSET
            } else if name == "world.bin" {
                MAX_CHUNKED_WORLD_ASSET
            } else if name == "world-textures.bin" {
                MAX_WORLD_TEXTURES_ASSET
            } else if name == "world-overlay.bin" {
                MAX_WORLD_OVERLAY_ASSET
            } else {
                MAX_ASSET
            },
        )?;
        if f.bytes.len() != size || sha256(&f.bytes).as_slice() != hash {
            return Err(bad("asset hash/length mismatch"));
        }
        if name == "world.bin" {
            // Magic and size only: the server never interprets world geometry.
            world_magic = match f.bytes.get(..4) {
                Some(b"N3W1") if f.bytes.len() as u64 <= MAX_WORLD_ASSET => Some(1),
                // N3W3 (PQ-379, D-201): N3W2 with alpha parts; N3W4 (PQ-382,
                // D-202): N3W3 with the opaque part bits; N3W5 (PQ-388, D-203):
                // N3W4 with single-layer unlit vertices; N3W6 (PQ-394, D-212):
                // N3W5 with texture sequences.
                Some(b"N3W2") | Some(b"N3W3") | Some(b"N3W4") | Some(b"N3W5") | Some(b"N3W6") => Some(2),
                _ => return Err(bad("world asset magic/size")),
            };
        }
        if name == "world-textures.bin" && f.bytes.get(..4) != Some(b"N3WT".as_slice()) {
            return Err(bad("world texture magic"));
        }
        if name == "world-overlay.bin" && f.bytes.get(..4) != Some(b"N3WO".as_slice()) {
            return Err(bad("world overlay magic"));
        }
        assets.insert(name,hash);
    }
    r.end()?;
    if (engine < 9 && files.contains("animation.bin") != (engine == 8)) || (engine>=30 && !files.contains("animation.bin")) {
        return Err(bad("animation compatibility"));
    }
    if files.remove("animation.bin") {
        let mut a = Reader::open(&root.join("animation.bin"))?;
        let count = match a.take(4)? {
            b"N3A1" => 11,
            b"N3A2" => 7,
            b"N3A3" => 14,
            _ => return Err(bad("animation magic")),
        };
        if (count==14)!=(engine>=30){return Err(bad("rest animation compatibility"));}
        if count==14 {for name in ["player-sit-down.bin","player-sit-idle.bin","player-stand-up.bin"]{if !files.remove(name){return Err(bad("rest animation set"));}}}
        for i in 0..count {
            let duration = a.f()?;
            let blend = a.f()?;
            let looping = a.u()?;
            if !(0.001..=3600.).contains(&duration)
                || !(0.0..=2.).contains(&blend)
                || looping > 1
                || ((if count==14 { [2,3,7,9,12,13].contains(&i) } else { [2,3,9,10].contains(&i) }) && looping != 0)
            {
                return Err(bad("animation bounds"));
            }
            for _ in 0..2 {
                let marker = a.f()?;
                if marker != -1. && !(0.0..=duration).contains(&marker) {
                    return Err(bad("animation marker"));
                }
            }
        }
        a.end()?;
        if count >= 11 {
            for name in [
                "npc-idle.bin",
                "npc-walk.bin",
                "npc-attack.bin",
                "npc-death.bin",
            ] {
                if !files.remove(name) {
                    return Err(bad("NPC animation set"));
                }
            }
        }
        for name in [
            "hud.bin",
            "player-run.bin",
            "player-backward.bin",
            "player-ready.bin",
        ] {
            if !files.contains(name) {
                return Err(bad("player animation set"));
            }
        }
    }
    if engine < 4 && files.contains("camera.bin") != (engine == 3) {
        return Err(bad("camera compatibility"));
    }
    if engine < 5 && files.contains("melee.bin") != (engine == 4) {
        return Err(bad("melee compatibility"));
    }
    if engine < 6 && files.contains("damage.bin") != (engine == 5) {
        return Err(bad("damage compatibility"));
    }
    if engine < 7 && files.contains("npc.bin") != (engine == 6) {
        return Err(bad("npc compatibility"));
    }
    if engine < 9
        && files.contains("life.bin")
            != (if engine == 8 {
                protocol == 3
            } else {
                engine == 7
            })
    {
        return Err(bad("life compatibility"));
    }
    if engine >= 10 && !files.contains("life.bin") {
        return Err(bad("loot requires durable life policy"));
    }
    if files.contains("progression.bin") != (engine >= 9) {
        return Err(bad("progression compatibility"));
    }
    let progression = if files.remove("progression.bin") {
        Some(crate::progression::Policy::load(
            &root.join("progression.bin"),
        )?)
    } else {
        None
    };
    let life = if files.remove("life.bin") {
        Some(crate::life::Policy::load(&root.join("life.bin"))?)
    } else {
        None
    };
    let npc_policy = if files.remove("npc.bin") {
        Some(crate::npc_ai::Policy::load(&root.join("npc.bin"))?)
    } else {
        None
    };
    // N3LK (PQ-253, D-166, engine 38): the client's per-template NPC models.
    // The server never draws them; it applies the client's checks so both
    // readers accept the same packages.
    // PQ-317 (D-187): present exactly when the package is engine 38 or later
    // and has NPC templates (an engine 38+ package without templates, such as
    // the Moradon additions package, has no looks table).
    let looks: BTreeSet<String> = npc_policy
        .as_ref()
        .and_then(|p| p.reference.as_ref())
        .map(|r| r.templates.iter().map(|t| t.looks.clone()).collect())
        .unwrap_or_default();
    if files.remove("npc-looks.bin") != (engine >= 38 && !looks.is_empty()) {
        return Err(bad("npc looks compatibility"));
    }
    if engine >= 38 && !looks.is_empty() {
        npc_looks(&root, &game, &looks, &mut files, engine)?;
    }
    let damage_policy = if files.remove("damage.bin") {
        Some(crate::damage::Policy::load(&root.join("damage.bin"))?)
    } else {
        None
    };
    let melee = if files.remove("melee.bin") {
        Some(crate::rules::Melee::load(&root.join("melee.bin"))?)
    } else {
        None
    };
    if files.remove("camera.bin") {
        let mut c = Reader::open(&root.join("camera.bin"))?;
        // N3V2 (PQ-012, D-143) appends the drag axis and three rates.
        let extended = match c.take(4)? {
            b"N3V1" => false,
            b"N3V2" => true,
            _ => return Err(bad("camera magic")),
        };
        let mut v = [0_f32; 14];
        for x in &mut v {
            *x = c.f()?;
        }
        let bounds = [
            (0.05, 1.4),
            (0.05, 1.4),
            (0.05, 1.4),
            (0.5, 32.),
            (0.5, 32.),
            (0.5, 32.),
            (0., 3.),
            (0., 1.),
            (0.0001, 0.05),
            (0.0001, 0.05),
            (0.01, 4.),
            (0.1, 0.5),
            (0.1, 6.3),
            (0., 1.),
        ];
        if v.iter().zip(bounds).any(|(x, (lo, hi))| *x < lo || *x > hi)
            || v[0] < v[1]
            || v[0] > v[2]
            || v[3] < v[4]
            || v[3] > v[5]
            || c.u()? > 1
        {
            return Err(bad("camera policy bounds"));
        }
        if extended {
            let drag = c.u()?;
            let rates = [c.f()?, c.f()?, c.f()?];
            if drag > 1
                || rates
                    .iter()
                    .zip([(0.0001, 0.5), (0., 6.3), (0., 6.3)])
                    .any(|(x, (lo, hi))| !(lo..=hi).contains(x))
            {
                return Err(bad("camera extension bounds"));
            }
        }
        c.end()?;
    }
    if files.contains("player-ready.bin") {
        if engine < 4 || melee.is_none() || !files.contains("hud.bin") {
            return Err(bad("ready pose compatibility"));
        }
        files.remove("player-ready.bin");
    }
    let locomotion = files.contains("player-run.bin") || files.contains("player-backward.bin");
    let presentation = files.contains("hud.bin");
    if presentation {
        for name in [
            "hud.bin",
            "player-idle.bin",
            "player-walk.bin",
            "player-attack.bin",
            "player-death.bin",
        ] {
            if !files.remove(name) {
                return Err(bad("incomplete presentation"));
            }
        }
        if files.contains("player-run.bin") || files.contains("player-backward.bin") {
            if protocol < 2
                || !files.remove("player-run.bin")
                || !files.remove("player-backward.bin")
            {
                return Err(bad("incomplete locomotion presentation"));
            }
        }
    }
    let loot_model=files.remove("loot-model.bin");
    if loot_model && (engine<10 || !presentation || progression.is_none()) {
        return Err(bad("loot model requires durable loot presentation"));
    }
    if files.remove("loot-policy.bin") {
        if !loot_model{return Err(bad("loot policy requires loot model"));}
        let mut p=Reader::open(&root.join("loot-policy.bin"))?;
        if p.take(4)?!=b"N3LP"{return Err(bad("loot policy magic"));}
        let radius=p.f()?;p.end()?;
        if radius<=0.||radius>100.{return Err(bad("loot open radius"));}
    }
    if files.remove("target-marker.bin") && (engine < 33 || !presentation || melee.is_none()) {
        return Err(bad("target marker compatibility"));
    }
    if files.remove("effects.bin") && (engine < 33 || !presentation) {
        return Err(bad("effects compatibility"));
    }
    if files.remove("audio.bin") && (engine < 33 || !presentation) {
        return Err(bad("audio compatibility"));
    }
    // Spec 11: the server reads only front-end.bin's header, for the slot
    // count; the client reads the rest.
    let character_slots = if files.remove("front-end.bin") {
        if engine < 42 || !presentation {
            return Err(bad("front end compatibility"));
        }
        let mut p = Reader::open_bounded(&root.join("front-end.bin"), MAX_FRONT_END_ASSET)?;
        if p.take(4)? != b"N3FE" || p.u()? != 4 {
            return Err(bad("front end magic/version"));
        }
        let slots = p.u()?;
        if !(1..=3).contains(&slots) {
            return Err(bad("front end character slots"));
        }
        slots
    } else {
        8
    };
    // The package input map is client-side (PQ-009, D-136): the server hashes it
    // with the release, checks its magic and otherwise ignores it. N3I2 adds the
    // name display policy (PQ-014), N3I3 the other-player label lifetime (PQ-169),
    // N3I4 the party names (PQ-166), N3I5 the per-class camera distance (PQ-173),
    // N3I6 the NPC label lifetime (PQ-174), N3I7 the NPC info line (PQ-177),
    // N3I8 the operator chat colour (PQ-178).
    if files.remove("input.bin") {
        let mut p = Reader::open(&root.join("input.bin"))?;
        let magic = p.take(4)?;
        if magic != b"N3I1"
            && magic != b"N3I2"
            && magic != b"N3I3"
            && magic != b"N3I4"
            && magic != b"N3I5"
            && magic != b"N3I6"
            && magic != b"N3I7"
            && magic != b"N3I8"
        {
            return Err(bad("input map magic"));
        }
    }
    // The actor pick policy is client presentation (PQ-146, D-138): checked and
    // hashed with the release, otherwise ignored.
    if files.remove("pick.bin") {
        let mut p = Reader::open(&root.join("pick.bin"))?;
        if p.take(4)? != b"N3PK" {
            return Err(bad("pick policy magic"));
        }
        let (box_source, min_extent, pad, mesh_lod) = (p.u()?, p.f()?, p.f()?, p.u()?);
        p.end()?;
        if box_source > 1 || !(0.0..=4.0).contains(&min_extent) || !(0.0..=4.0).contains(&pad) || mesh_lod > 3 {
            return Err(bad("pick policy bounds"));
        }
    }
    // The screen post-process (bloom and tone map) is client presentation
    // (PQ-316, D-185): checked and hashed with the release, otherwise ignored.
    // Threshold, bloom, exposure, saturation, lift, adaptation rate and blur
    // variance (above zero), as tools/assetc/postprocess.py cooks them.
    if files.remove("postprocess.bin") {
        if engine < 33 || !presentation {
            return Err(bad("postprocess compatibility"));
        }
        postprocess(Reader::open(&root.join("postprocess.bin"))?)?;
    }
    let editing = files.remove("editing.bin");
    if editing != (engine >= 11) {
        return Err(bad("editing compatibility"));
    }
    // The world asset is client-side geometry: the server checks that it is
    // present exactly where the engine version says it must be, hashes it with
    // the rest of the release and otherwise ignores its contents.
    let world = files.remove("world.bin");
    let exploration = files.remove("exploration.bin");
    let lod = files.remove("world-lod.bin");
    // N3W2 carries its own parts, so it pairs with exploration and no
    // world-lod.bin, from engine 13 (exploration) on (PQ-231).
    if world_magic == Some(2) {
        if engine < 13 || !exploration || lod { return Err(bad("world/exploration compatibility")); }
    } else if (engine < 15 && (world != (engine >= 12) || exploration != (engine >= 13) || lod != exploration))
        || (engine >= 15 && (lod != exploration || (exploration && !world)))
    { return Err(bad("world/exploration compatibility")); }
    // An N3W2 world's textures are their own asset (PQ-233): present exactly
    // with an N3W2 world; the server checks the magic and hashes the bytes.
    if files.remove("world-textures.bin") != (world_magic == Some(2)) {
        return Err(bad("world textures compatibility"));
    }
    // Maps blended over the near terrain (N3WO, PQ-387, D-204) are client
    // presentation over the world's terrain: present only with a world and an
    // exploration policy; the server checks the magic and hashes the bytes.
    if files.remove("world-overlay.bin") && !(world && exploration) {
        return Err(bad("world overlay compatibility"));
    }
    let detail = files.remove("render-detail.bin");
    if (engine < 15 && detail != (engine == 14)) || (detail && !exploration) { return Err(bad("render detail compatibility")); }
    if detail {
        if !presentation { return Err(bad("render detail requires player presentation")); }
        let mut d = Reader::open_bounded(&root.join("render-detail.bin"), 128*1024*1024)?;
        // N3D3 (PQ-348, D-191) is N3D2 with a render state per appearance
        // entry; the client reads the geometry and the states, the server
        // only the projection below.
        let magic = d.take(4)?;
        if !(if engine >= 29 { magic == b"N3D2" || magic == b"N3D3" } else { magic == b"N3D1" }) {
            return Err(bad("render detail magic"));
        }
        let (fov, near, far) = (d.f()?, d.f()?, d.f()?);
        if !(0.2..=2.5).contains(&fov) || !(0.01..=2.0).contains(&near) || !(10.0..=1000.0).contains(&far) {
            return Err(bad("projection bounds"));
        }
    }
    let turbo_multiplier = if exploration {
        let mut p = Reader::open(&root.join("exploration.bin"))?;
        if p.take(4)? != b"N3X1" {
            return Err(bad("exploration magic"));
        }
        let multiplier = p.f()?;
        let start = p.f()?;
        let end = p.f()?;
        if !(1. ..=10.).contains(&multiplier) || start < 0. || start >= end || end > 1000. {
            return Err(bad("exploration bounds"));
        }
        for _ in 0..3 {
            if !(0. ..=1.).contains(&p.f()?) {
                return Err(bad("fog colour"));
            }
        }
        p.end()?;
        multiplier
    } else {
        1.
    };
    let properties = if editing {
        crate::administration::load(&root.join("editing.bin"), &game)?
    } else {
        vec![]
    };
    let mut inventory = if files.remove("inventory.bin") {
        if engine < 15 { return Err(bad("inventory compatibility")); }
        Some(crate::inventory::Policy::load(&root.join("inventory.bin"), &game)?)
    } else { if (15..=22).contains(&engine) { return Err(bad("inventory required")); } None };
    if files.remove("item-heads.bin") {
        let Some(policy) = inventory.as_ref().filter(|_| engine >= 33 && presentation) else {
            return Err(bad("item heads compatibility"));
        };
        let ids: Vec<&str> = policy.items.iter().map(|i| i.id.as_str()).collect();
        item_heads(Reader::open(&root.join("item-heads.bin"))?, &ids)?;
    }
    let commerce=files.remove("commerce.bin");
    if (engine<23 && commerce!=(engine>=16)) || (commerce&&inventory.is_none()) {return Err(bad("commerce compatibility"));}
    let repair=files.remove("repair.bin");if (engine<23&&repair!=(engine>=17))||(repair&&!commerce){return Err(bad("repair compatibility"));}
    let equipment=files.remove("equipment.bin");if (engine<23&&equipment!=(engine>=18))||(equipment&&!repair){return Err(bad("equipment compatibility"));}
    if equipment {
        let p=inventory.as_mut().unwrap();
        p.equipment=Some(crate::equipment::Policy::load(&root.join("equipment.bin"),p)?);
        let mut identity=p.hash.clone();identity.extend(sha256(&fs::read(root.join("equipment.bin"))?));p.hash=sha256(&identity).to_vec();
    }
    let has_combat_animation=files.remove("combat-animation.bin");
    if has_combat_animation!=(engine>=31){return Err(bad("combat animation compatibility"));}
    let mut combat_animation=if has_combat_animation {Some(crate::combat_animation::Policy::load(&root,&mut files,inventory.as_ref().ok_or_else(||bad("combat inventory required"))?,engine>=32)?)}else{None};
    // PQ-416 (D-216): ranged basic attacks name N3A5 profiles and add to the
    // melee radii (tools/assetc/ranged_attack.py).
    if files.remove("ranged-attack.bin") {
        match (combat_animation.as_mut(), &melee) {
            (Some(policy), Some(_)) => policy.load_ranged(&root.join("ranged-attack.bin"), &inventory.as_ref().ok_or_else(|| bad("ranged attack compatibility"))?.items)?,
            _ => return Err(bad("ranged attack compatibility")),
        }
    }
    let has_skills=files.remove("skills.bin");
    if has_skills!=(engine>=34){return Err(bad("skill compatibility"));}
    // PQ-465 (D-232): a skill's start limit adds both actors' radii from the melee rules.
    let skills=if has_skills{let mut p=crate::skills::Policy::load(&root.join("skills.bin"))?;p.radii=melee.as_ref().map_or(0.,|m|m.actor_radius+m.target_radius);Some(p)}else{None};
    if let Some(policy)=&skills{for skill in &policy.skills{if !files.remove(&format!("player-skill-{}.bin",skill.animation)) && !policy.skills.iter().take_while(|s|s.id!=skill.id).any(|s|s.animation==skill.animation){return Err(bad("skill animation missing"));}}}
    let has_consumables=files.remove("consumables.bin");
    if has_consumables!=(engine>=33){return Err(bad("consumable compatibility"));}
    let consumables=if has_consumables {Some(crate::consumables::Policy::load(&root.join("consumables.bin"),inventory.as_ref().ok_or_else(||bad("consumable inventory"))?)?)}else{None};
    let has_rest=files.remove("rest.bin");
    if has_rest != (engine>=30) {return Err(bad("rest compatibility"));}
    let rest=if has_rest {Some(crate::rest::Policy::load(&root.join("rest.bin"))?)} else {None};
    let has_appearance=files.remove("appearance.bin");
    if has_appearance != (engine>=29) || (has_appearance && (!equipment || !detail)) {return Err(bad("appearance compatibility"));}
    let appearance=if has_appearance {crate::appearance::Policy::load(&root.join("appearance.bin"),inventory.as_ref().unwrap().equipment.as_ref().unwrap())?} else {crate::appearance::Policy::default()};
    // N3AT (PQ-328, D-186): attached characters on appearance keys, client
    // presentation in the looks model formats; checked so both readers accept
    // the same packages, otherwise ignored.
    if files.remove("attachments.bin") {
        if engine < 38 || !has_appearance {return Err(bad("attachment compatibility"));}
        crate::attachments::check(&root, engine, appearance.0.len(), &mut files)?;
    }
    let stats=files.remove("stats.bin");
    if (engine<23&&stats!=(engine>=19))||(stats&&!equipment)||progression.as_ref().is_some_and(|p|p.equipment_stats)!=stats {return Err(bad("stats compatibility"));}
    if stats {
        if damage_policy.is_none(){return Err(bad("stats require damage"));}
        let p=inventory.as_mut().unwrap();
        p.stats=Some(crate::stats::Policy::load(&root.join("stats.bin"),p.equipment.as_ref().unwrap(),&game)?);
        p.thresholds=Some(progression.as_ref().unwrap().thresholds);
        let mut identity=p.hash.clone();identity.extend(sha256(&fs::read(root.join("stats.bin"))?));p.hash=sha256(&identity).to_vec();
        let gear=p.equipment.as_ref().unwrap();
        for level in 1..=10 {p.stats.as_ref().unwrap().calculate(gear,&vec![crate::wire::ItemStack::default();gear.slots.len()],level)?;}
    }
    let wear=files.remove("wear.bin");if (engine<23&&wear!=(engine>=20))||(wear&&!stats){return Err(bad("wear compatibility"));}
    if wear {
        let p=inventory.as_mut().unwrap();p.wear=Some(crate::wear::Policy::load(&root.join("wear.bin"),p.equipment.as_ref().unwrap())?);
        let mut identity=p.hash.clone();identity.extend(sha256(&fs::read(root.join("wear.bin"))?));p.hash=sha256(&identity).to_vec();
    }
    // PQ-421 (D-218): a ranged profile's ammunition leaves in the strike's
    // durable commit, the wear write.
    if !wear && combat_animation.as_ref().is_some_and(|p| !p.ammo.is_empty()) {return Err(bad("ranged ammo compatibility"));}
    let storage=files.remove("storage.bin");if (engine<23&&storage!=(engine>=21))||(storage&&!wear){return Err(bad("storage compatibility"));}
    if storage {
        let p=inventory.as_mut().unwrap();p.storage=Some(crate::storage::Policy::load(&root.join("storage.bin"),&game)?);
        let mut identity=p.hash.clone();identity.extend(sha256(&fs::read(root.join("storage.bin"))?));p.hash=sha256(&identity).to_vec();
    }
    let storage_auth=files.remove("storage-auth.bin");if (engine<23&&storage_auth!=(engine==22))||(storage_auth&&!storage){return Err(bad("storage credential compatibility"));}
    if storage_auth {
        let p=inventory.as_mut().unwrap();p.storage.as_mut().unwrap().credential=Some(crate::storage_auth::Policy::load(&root.join("storage-auth.bin"))?);
        let mut identity=p.hash.clone();identity.extend(sha256(&fs::read(root.join("storage-auth.bin"))?));p.hash=sha256(&identity).to_vec();
    }
    let friends=files.remove("friends.bin");if engine<24&&friends!=(engine==23){return Err(bad("friends compatibility"));}
    let friend_policy=if friends {Some(crate::friends::Policy::load(&root.join("friends.bin"))?)}else{None};
    let party=files.remove("party.bin");if party!=(engine>=24){return Err(bad("party compatibility"));}
    let party_policy=if party {Some(crate::party::Policy::load(&root.join("party.bin"))?)}else{None};
    if files
        != ["collision.bin", "scene.bin", "recipe.json", "gameplay.bin"]
            .map(String::from)
            .into_iter()
            .collect()
    {
        return Err(bad("release asset set"));
    }
    // N3C1 soup or N3C2 heightfield plus gridded objects (PQ-215); both
    // readers refuse anything else.
    let collision = crate::movement::Collision::read(&root.join("collision.bin"))?;
    let mut rules = crate::rules::Rules::load(&root.join("gameplay.bin"), &game)?;
    if (locomotion || exploration) && rules.movement.is_none() {
        return Err(bad("locomotion requires movement"));
    }
    if let Some(p) = &progression {
        if p.item != rules.item
            || p.capacity != rules.slots
            || p.starting != rules.starting_items
            || !p.curve.starts_with(&format!("{game}:"))
        {
            return Err(bad("progression inventory/namespace"));
        }
    }
    if let Some(p) = &inventory { p.validate_reward(&rules.item, rules.slots)?; }
    if commerce {
        let mut policy=crate::commerce::Policy::load(&root.join("commerce.bin"),&game,inventory.as_ref().unwrap(),&rules.item)?;
        for shop in &policy.shops { if !crate::movement::ground(&collision,shop.position[0],shop.position[2]).is_finite(){return Err(bad("shop not on map"));} }
        if repair {policy.repair=Some(crate::repair::Policy::load(&root.join("repair.bin"),inventory.as_ref().unwrap())?);}
        rules.commerce=Some(std::sync::Arc::new(policy));
    }
    rules.friends = friend_policy.map(std::sync::Arc::new);
    if engine<29 && progression.as_ref().is_some_and(|p| p.party_rewards.is_some()) != (engine>=25) { return Err(bad("party reward compatibility")); }
    if engine<29 && progression.as_ref().is_some_and(|p|p.party_loot.is_some()) != (engine>=26) { return Err(bad("party loot compatibility")); }
    if engine<29 && progression.as_ref().is_some_and(|p|p.coins.is_some()) != (engine>=27) {return Err(bad("coin drop compatibility"));}
    if let Some(coins)=progression.as_ref().and_then(|p|p.coins.as_ref()) {
        if inventory.as_ref().is_none_or(|p|p.currency!=coins.currency||p.limit>2100000000) {return Err(bad("coin inventory currency"));}
    }
    if engine<29 && progression.as_ref().is_some_and(|p|p.items.is_some()) != (engine==28) {return Err(bad("item drop compatibility"));}
    if let Some(drops)=progression.as_ref().and_then(|p|p.items.as_ref()) {
        let inventory=inventory.as_ref().ok_or_else(||bad("item drop inventory"))?;
        for i in &drops.items {if !crate::inventory::id(&i.id,&game)||inventory.items.iter().all(|d|d.id!=i.id||d.stack<i.quantity||d.durability!=i.durability){return Err(bad("drop inventory definition"));}}
    }
    rules.party = party_policy.map(std::sync::Arc::new);
    rules.inventory = inventory.map(std::sync::Arc::new);
    rules.progression = progression.map(std::sync::Arc::new);
    rules.life = life;
    if let Some(reference) = npc_policy.as_ref().and_then(|p| p.reference.as_ref()) {
        let corpse = rules.life.map(|p| p.corpse).ok_or_else(|| bad("reference npc requires life policy"))?;
        if engine < 36 || reference.slots.len() != rules.spawns.len() || reference.slots.iter().any(|s| s.respawn < corpse) {
            return Err(bad("reference npc compatibility"));
        }
        // PQ-272 (D-179): N3N4 (templates with a drawn scale) is engine 41, and
        // an engine 41 package's templates are N3N4. Engine 42 adds only the
        // front end (spec 11, Q59), so it keeps whichever table it has.
        if (reference.scaled && engine < 41) || (!reference.scaled && engine == 41) {
            return Err(bad("npc scale compatibility"));
        }
        // N3N3 templates (PQ-249): engine 37 / wire 30, names and looks keys in
        // the package namespace.
        if !reference.templates.is_empty()
            && (engine < 37
                || reference
                    .templates
                    .iter()
                    .any(|t| !crate::rules::rule_id(&t.name, &game) || !crate::rules::rule_id(&t.looks, &game)))
        {
            return Err(bad("npc template compatibility"));
        }
        // Slot points are the fallback placement, so an actor must be able to stand there.
        if rules.spawns.iter().any(|p| !crate::movement::standable(&collision, p[0], p[1])) {
            return Err(bad("reference npc slot not standable"));
        }
    }
    rules.npc_policy = npc_policy;
    rules.melee = melee;
    rules.damage_policy = damage_policy;
    if rules.cost == 0 && rules.melee.is_none() {
        return Err(bad("zero cost requires melee policy"));
    }
    rules.rest=rest.map(std::sync::Arc::new);
    rules.combat_animation=combat_animation.map(std::sync::Arc::new);
    rules.consumables=consumables.map(std::sync::Arc::new);
    if let Some(policy)=&skills {
        if !crate::inventory::id(&policy.archetype,&game)||policy.label.is_empty()||policy.label.len()>80{return Err(bad("skill class"));}
        for skill in &policy.skills {
            if !crate::inventory::id(&skill.id,&game)||skill.class!=policy.archetype||skill.weapons.iter().any(|id|rules.inventory.as_ref().is_none_or(|p|p.items.iter().all(|i|i.id!=*id))){return Err(bad("skill references"));}
        }
    }
    rules.skills=skills.map(std::sync::Arc::new);
    if protocol < 3 && rules.movement.is_some() != (protocol == 2) {
        return Err(bad("movement compatibility"));
    }
    if rules
        .spawns
        .iter()
        .any(|p| !crate::movement::ground(&collision, p[0], p[1]).is_finite())
    {
        return Err(bad("NPC spawn not walkable"));
    }
    if exploration && !crate::movement::ground(&collision,rules.spawn_x,rules.spawn_z).is_finite(){return Err(bad("player spawn not walkable"));}
    Ok(Release {
        appearance,
        assets,
        turbo_multiplier,
        properties,
        protocol,
        rules,
        game,
        hash,
        collision,
        character_slots,
    })
}
/// Most NPC looks entries one package carries (PQ-253): a KO homeland zone's
/// templates use 52 (local OpenKO rows).
pub const MAX_NPC_LOOKS: u32 = 128;
/// Every looks model's atlas bytes together (3 per texel in N3NM and N3NI, 4
/// in N3MM and N3MI),
/// and every model file together.
pub const NPC_LOOKS_TEXTURE_BYTES: u64 = 96 << 20;
pub const NPC_LOOKS_MODEL_BYTES: u64 = 192 << 20;
/// N3LK: exactly the templates' looks keys, each with its N3NM model
/// `npc-looks-<i>.bin` (or, at engine 39, N3MM: PQ-265, D-173; at engine 40,
/// N3NI or N3MI: PQ-283, D-176), inside the atlas and byte budgets.
fn npc_looks(
    root: &Path,
    game: &str,
    templates: &BTreeSet<String>,
    files: &mut BTreeSet<String>,
    engine: u32,
) -> Result<()> {
    let mut k = Reader::open(&root.join("npc-looks.bin"))?;
    if k.take(4)? != b"N3LK" {
        return Err(bad("npc looks magic"));
    }
    let n = k.u()?;
    if n == 0 || n > MAX_NPC_LOOKS {
        return Err(bad("npc looks count"));
    }
    let (mut keys, mut texels, mut bytes) = (BTreeSet::new(), 0u64, 0u64);
    for i in 0..n {
        let key = k.string()?;
        if !crate::rules::rule_id(&key, game) || !keys.insert(key) {
            return Err(bad("npc looks key"));
        }
        if k.u()? > 1 {
            return Err(bad("npc looks flags"));
        }
        for clip in 0..4 {
            let (duration, blend, looping) = (k.f()?, k.f()?, k.u()?);
            if !(0.001..=3600.).contains(&duration) || !(0.0..=2.).contains(&blend) || looping > 1 || (clip >= 2 && looping != 0) {
                return Err(bad("npc looks clip bounds"));
            }
            for _ in 0..2 {
                let marker = k.f()?;
                if marker != -1. && !(0.0..=duration).contains(&marker) {
                    return Err(bad("npc looks clip marker"));
                }
            }
        }
        let name = format!("npc-looks-{i}.bin");
        if !files.remove(&name) {
            return Err(bad("npc looks model"));
        }
        let path = root.join(&name);
        bytes += fs::metadata(&path)?.len();
        let mut head = [0u8; 12];
        std::io::Read::read_exact(&mut fs::File::open(&path)?, &mut head)?;
        let (width, height) = (
            u32::from_le_bytes(head[4..8].try_into()?),
            u32::from_le_bytes(head[8..12].try_into()?),
        );
        let channels = match &head[..4] {
            b"N3NM" => 3,
            b"N3MM" if engine >= 39 => 4,
            b"N3NI" if engine >= 40 => 3,
            b"N3MI" if engine >= 40 => 4,
            _ => return Err(bad("npc looks model header")),
        };
        if !(1..=1024).contains(&width) || !(1..=1024).contains(&height) {
            return Err(bad("npc looks model header"));
        }
        texels += u64::from(width) * u64::from(height) * channels;
    }
    k.end()?;
    if &keys != templates {
        return Err(bad("npc looks must cover exactly the templates' looks keys"));
    }
    if texels > NPC_LOOKS_TEXTURE_BYTES || bytes > NPC_LOOKS_MODEL_BYTES {
        return Err(bad("npc looks byte budget"));
    }
    Ok(())
}
impl Release {
    /// Exploration packages already declare a surveyed spawn in gameplay data.
    pub fn player_spawn(&self)->Result<[f32;3]> {
        if self.assets.contains_key("exploration.bin"){let x=self.rules.spawn_x;let z=self.rules.spawn_z;
            let y=crate::movement::ground(&self.collision,x,z);if !y.is_finite(){return Err(bad("player spawn not walkable"));}Ok([x,y,z])
        }else{crate::movement::spawn(&self.collision)}
    }
    /// Highest surface of any triangle at X/Z, walls included (barycentric).
    pub fn height(&self, x: f32, z: f32) -> f32 {
        let mut best = f32::NEG_INFINITY;
        for t in self.collision.around(x, z, 0.).chunks_exact(3) {
            let (a, b, c) = (t[0], t[1], t[2]);
            let d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]);
            if d.abs() < 1e-8 {
                continue;
            }
            let u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d;
            let v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d;
            if u >= -1e-6 && v >= -1e-6 && u + v <= 1. + 1e-6 {
                best = best.max(u * a[1] + v * b[1] + (1. - u - v) * c[1]);
            }
        }
        best
    }
}

#[cfg(test)]
mod item_heads_tests {
    use super::{item_heads, Reader};
    fn s(b: &mut Vec<u8>, text: &[u8]) {
        b.extend_from_slice(&(text.len() as u32).to_le_bytes());
        b.extend_from_slice(text);
    }
    fn n(b: &mut Vec<u8>, v: u32) {
        b.extend_from_slice(&v.to_le_bytes());
    }
    // token, then (item, name colour, [(text, colour)]).
    fn file(token: &[u8], heads: &[(&[u8], u32, &[(&[u8], u32)])], tail: &[u8]) -> Reader {
        let mut b = b"N3IH".to_vec();
        s(&mut b, token);
        n(&mut b, heads.len() as u32);
        for (item, name, lines) in heads {
            s(&mut b, item);
            n(&mut b, *name);
            n(&mut b, lines.len() as u32);
            for (text, colour) in *lines {
                s(&mut b, text);
                n(&mut b, *colour);
            }
        }
        b.extend_from_slice(tail);
        Reader::from_bytes(b)
    }
    const ITEMS: [&str; 2] = ["demo:item/blade", "demo:item/potion"];
    const KIND: &[(&[u8], u32)] = &[(b"(Reverse unique item)", 0xffad4d)];
    #[test]
    fn accepts_the_cooked_bounds() {
        let blade: &[u8] = b"demo:item/blade";
        assert_eq!(item_heads(file(b"<selfname>", &[(blade, 0xffad4d, KIND)], b""), &ITEMS).unwrap(), 1);
        assert_eq!(item_heads(file(b"<selfname>", &[], b""), &ITEMS).unwrap(), 0);
        assert_eq!(item_heads(file(b"", &[(blade, 0, &[])], b""), &ITEMS).unwrap(), 1);
        let four: &[(&[u8], u32)] = &[(b" " as &[u8], 0xffffff); 4];
        assert!(item_heads(file(&[b'~'; 32], &[(blade, 0xffffff, four)], b""), &ITEMS).is_ok());
    }
    #[test]
    fn refuses_bad_files() {
        let blade: &[u8] = b"demo:item/blade";
        let ok = |tail: &[u8]| file(b"<selfname>", &[(blade, 1, KIND)], tail);
        assert!(item_heads(ok(b""), &ITEMS).is_ok());
        assert!(item_heads(ok(b"\0"), &ITEMS).is_err(), "trailing bytes");
        let mut magic = ok(b"");
        magic.bytes[3] = b'J';
        assert!(item_heads(magic, &ITEMS).is_err(), "magic");
        assert!(item_heads(file(b"", &[], b""), &ITEMS).is_err(), "nothing to do");
        assert!(item_heads(file(&[b'~'; 33], &[], b""), &ITEMS).is_err(), "long token");
        assert!(item_heads(file(b"<self name>", &[], b""), &ITEMS).is_err(), "token space");
        assert!(item_heads(file(b"", &[(b"demo:item/sword", 1, &[])], b""), &ITEMS).is_err(), "undefined item");
        assert!(item_heads(file(b"", &[(blade, 1, &[]), (blade, 2, &[])], b""), &ITEMS).is_err(), "twice");
        assert!(item_heads(file(b"", &[(blade, 0x100_0000, &[])], b""), &ITEMS).is_err(), "name colour");
        let five: &[(&[u8], u32)] = &[(b"x" as &[u8], 0); 5];
        assert!(item_heads(file(b"", &[(blade, 1, five)], b""), &ITEMS).is_err(), "five lines");
        assert!(item_heads(file(b"", &[(blade, 1, &[(b"", 0)])], b""), &ITEMS).is_err(), "empty line");
        assert!(item_heads(file(b"", &[(blade, 1, &[(&[b'x'; 65], 0)])], b""), &ITEMS).is_err(), "long line");
        assert!(item_heads(file(b"", &[(blade, 1, &[(b"tab\there", 0)])], b""), &ITEMS).is_err(), "control byte");
        assert!(item_heads(file(b"", &[(blade, 1, &[(b"x", 0x100_0000)])], b""), &ITEMS).is_err(), "line colour");
        let many: Vec<(&[u8], u32, &[(&[u8], u32)])> = (0..65).map(|_| (blade, 1, KIND)).collect();
        assert!(item_heads(file(b"", &many, b""), &ITEMS).is_err(), "65 heads");
    }
}
#[cfg(test)]
mod postprocess_tests {
    use super::{postprocess, Reader};
    fn file(magic: &[u8], values: &[f32], tail: &[u8]) -> Reader {
        let mut b = magic.to_vec();
        for v in values {
            b.extend_from_slice(&v.to_le_bytes());
        }
        b.extend_from_slice(tail);
        Reader::from_bytes(b)
    }
    const MORADON: [f32; 7] = [0.367, 0.7, 0.1, 1.0, 0.65, 0.3, 1.0];
    #[test]
    fn accepts_the_cooked_bounds() {
        assert_eq!(postprocess(file(b"N3PF", &MORADON, b"")).unwrap(), MORADON);
        let edges = [1.0, 4.0, 16.0, 4.0, 4.0, 100.0, 16.0];
        assert!(postprocess(file(b"N3PF", &edges, b"")).is_ok());
        assert!(postprocess(file(b"N3PF", &[0., 0., 0., 0., 0., 0., 0.01], b"")).is_ok());
    }
    #[test]
    fn refuses_bad_files() {
        assert!(postprocess(file(b"N3PG", &MORADON, b"")).is_err());
        assert!(postprocess(file(b"N3PF", &MORADON[..6], b"")).is_err());
        assert!(postprocess(file(b"N3PF", &MORADON, b"\0")).is_err());
        let high = [1.01, 4.01, 16.01, 4.01, 4.01, 100.01, 16.01];
        for i in 0..7 {
            let mut v = MORADON;
            v[i] = high[i];
            assert!(postprocess(file(b"N3PF", &v, b"")).is_err(), "field {i} above its bound");
            v[i] = -0.01;
            assert!(postprocess(file(b"N3PF", &v, b"")).is_err(), "field {i} below zero");
            v[i] = f32::NAN;
            assert!(postprocess(file(b"N3PF", &v, b"")).is_err(), "field {i} NaN");
        }
        let mut v = MORADON;
        v[6] = 0.;
        assert!(postprocess(file(b"N3PF", &v, b"")).is_err(), "zero blur variance");
    }
}
