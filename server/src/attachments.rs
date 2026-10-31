//! N3AT attached characters on appearance keys (PQ-328, D-186): client
//! presentation that the server never draws. It applies the client's checks of
//! the table and the model headers so both readers accept the same packages,
//! and stays the authority for what is worn through equipment and appearance,
//! which it already projects from committed equipment only.
use crate::content::{bad, Reader, Result};
use std::{
    collections::BTreeSet,
    fs,
    path::Path,
};

pub const MAX_ATTACHMENTS: u32 = 16;
pub const MAX_GROUPS: u32 = 16;
pub const TEXTURE_BYTES: u64 = 32 << 20;
pub const MODEL_BYTES: u64 = 64 << 20;
/// Entry flag bit 2: a skeletal hand plug (PQ-317, D-187).
pub const PLUG: u32 = 4;
pub const MAX_PLUG_CLIPS: u32 = 64;

/// The table: flags, pulse timing, colour, then 1-16 entries on distinct keys
/// within the package's `keys` appearance keys. Removes each entry's model from
/// `files` and returns the entry count.
pub fn check(root: &Path, engine: u32, keys: usize, files: &mut BTreeSet<String>) -> Result<u32> {
    let mut r = Reader::open(&root.join("attachments.bin"))?;
    let n = table(&mut r, keys)?;
    let (mut texels, mut bytes) = (0u64, 0u64);
    for i in 0..n {
        let name = format!("attachment-{i}.bin");
        if !files.remove(&name) {
            return Err(bad("attachment model"));
        }
        let path = root.join(&name);
        bytes += fs::metadata(&path)?.len();
        texels += model_header(&path, engine)?;
    }
    if texels > TEXTURE_BYTES || bytes > MODEL_BYTES {
        return Err(bad("attachment byte budget"));
    }
    Ok(n)
}

fn table(r: &mut Reader, keys: usize) -> Result<u32> {
    if r.take(4)? != b"N3AT" {
        return Err(bad("attachment magic"));
    }
    if r.u()? > 1 {
        return Err(bad("attachment flags"));
    }
    let (rise, hold, fall, period) = (r.f()?, r.f()?, r.f()?, r.f()?);
    if !(rise > 0. && rise <= hold && hold <= fall && fall <= period && period <= 60.) {
        return Err(bad("attachment clock"));
    }
    for _ in 0..3 {
        if !(0.0..=1.0).contains(&r.f()?) {
            return Err(bad("attachment colour"));
        }
    }
    let n = r.u()?;
    if n == 0 || n > MAX_ATTACHMENTS {
        return Err(bad("attachment count"));
    }
    let mut seen = BTreeSet::new();
    for _ in 0..n {
        let key = r.u()?;
        if key == 0 || key as usize > keys || !seen.insert(key) {
            return Err(bad("attachment appearance key"));
        }
        let (joint, scale, group, flags, modulate, lit) = (r.u()?, r.f()?, r.u()?, r.u()?, r.f()?, r.u()?);
        if joint >= 64
            || !(0.01..=100.).contains(&scale)
            || group >= MAX_GROUPS
            || flags > 7
            || ![1., 2., 4.].contains(&modulate)
            || lit % 3 != 0
        {
            return Err(bad("attachment entry bounds"));
        }
        for clip in 0..4 {
            let (duration, blend, looping) = (r.f()?, r.f()?, r.u()?);
            if !(0.001..=3600.).contains(&duration)
                || !(0.0..=2.).contains(&blend)
                || looping > 1
                || (clip >= 2 && looping != 0)
            {
                return Err(bad("attachment clip bounds"));
            }
            for _ in 0..2 {
                let marker = r.f()?;
                if marker != -1. && !(0.0..=duration).contains(&marker) {
                    return Err(bad("attachment clip marker"));
                }
            }
        }
        if flags & PLUG != 0 {
            plug(r, flags, modulate, lit)?;
        }
    }
    r.end()?;
    Ok(n)
}

/// A skeletal plug's placement and clip map (PQ-317, D-187): never optional,
/// lit or emissive; a 3x4 placement with finite terms of at most 100 and a
/// determinant of at least 1e-6 in size; 1-64 rows of (kind 0 a pose state
/// 0-9, 1 a combat clip, 2 a skill animation; id; slot 0-3; once 0 or 1), each
/// (kind, id) once. The client also checks the combat and skill ids.
fn plug(r: &mut Reader, flags: u32, modulate: f32, lit: u32) -> Result<()> {
    if flags != PLUG || lit != 0 || modulate != 1. {
        return Err(bad("attachment plug flags"));
    }
    let mut m = [0f32; 12];
    for v in &mut m {
        *v = r.f()?;
        if !(v.abs() <= 100.) {
            return Err(bad("attachment plug placement"));
        }
    }
    let det = m[0] * (m[5] * m[10] - m[6] * m[9]) - m[1] * (m[4] * m[10] - m[6] * m[8])
        + m[2] * (m[4] * m[9] - m[5] * m[8]);
    if !(det.abs() >= 1e-6) {
        return Err(bad("attachment plug placement"));
    }
    let rows = r.u()?;
    if rows == 0 || rows > MAX_PLUG_CLIPS {
        return Err(bad("attachment plug clip map"));
    }
    let mut seen = BTreeSet::new();
    for _ in 0..rows {
        let (kind, id, slot, once) = (r.u()?, r.u()?, r.u()?, r.u()?);
        if kind > 2 || (kind == 0 && id > 9) || slot > 3 || once > 1 || !seen.insert((kind, id)) {
            return Err(bad("attachment plug clip map"));
        }
    }
    Ok(())
}

/// A model's magic for the engine (the looks model kinds) and its atlas size;
/// returns its atlas bytes.
fn model_header(path: &Path, engine: u32) -> Result<u64> {
    let mut head = [0u8; 12];
    std::io::Read::read_exact(&mut fs::File::open(path)?, &mut head)?;
    let (width, height) = (
        u32::from_le_bytes(head[4..8].try_into()?),
        u32::from_le_bytes(head[8..12].try_into()?),
    );
    let channels = match &head[..4] {
        b"N3NM" => 3,
        b"N3MM" if engine >= 39 => 4,
        b"N3NI" if engine >= 40 => 3,
        b"N3MI" if engine >= 40 => 4,
        _ => return Err(bad("attachment model header")),
    };
    if !(1..=1024).contains(&width) || !(1..=1024).contains(&height) {
        return Err(bad("attachment model header"));
    }
    Ok(u64::from(width) * u64::from(height) * channels)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn f(v: &mut Vec<u8>, x: &[f32]) {
        for x in x {
            v.extend(x.to_le_bytes());
        }
    }
    fn u(v: &mut Vec<u8>, x: &[u32]) {
        for x in x {
            v.extend(x.to_le_bytes());
        }
    }
    /// One entry on key 1, as tools/assetc/attachments.py writes it.
    fn entry(key: u32, joint: u32, scale: f32, group: u32, flags: u32, modulate: f32, lit: u32) -> Vec<u8> {
        let mut v = vec![];
        u(&mut v, &[key, joint]);
        f(&mut v, &[scale]);
        u(&mut v, &[group, flags]);
        f(&mut v, &[modulate]);
        u(&mut v, &[lit]);
        for clip in 0..4u32 {
            f(&mut v, &[1., 0.]);
            u(&mut v, &[u32::from(clip < 2)]);
            f(&mut v, &[-1., -1.]);
        }
        v
    }
    fn file(flags: u32, clock: [f32; 4], color: [f32; 3], entries: &[Vec<u8>]) -> Vec<u8> {
        let mut v = b"N3AT".to_vec();
        u(&mut v, &[flags]);
        f(&mut v, &clock);
        f(&mut v, &color);
        u(&mut v, &[entries.len() as u32]);
        for e in entries {
            v.extend(e);
        }
        v
    }
    const KO: [f32; 4] = [1., 3., 5., 5.5];

    #[test]
    fn table_bounds_match_the_cook() {
        let good = file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36), entry(2, 0, 1.1, 1, 0, 1., 0)]);
        assert_eq!(table(&mut Reader::from_bytes(good.clone()), 2).unwrap(), 2);
        // The key must exist, once.
        assert!(table(&mut Reader::from_bytes(good.clone()), 1).is_err());
        let duplicate = file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36), entry(1, 0, 1., 1, 0, 1., 0)]);
        assert!(table(&mut Reader::from_bytes(duplicate), 2).is_err());
        let zero = file(1, KO, [1., 1., 1.], &[entry(0, 2, 1., 0, 3, 2., 36)]);
        assert!(table(&mut Reader::from_bytes(zero), 2).is_err());
        let mut trailing = good.clone();
        trailing.push(0);
        assert!(table(&mut Reader::from_bytes(trailing), 2).is_err());
        assert!(table(&mut Reader::from_bytes(good[..good.len() - 1].to_vec()), 2).is_err());
        for bad_file in [
            file(2, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36)]),
            file(1, [0., 3., 5., 5.5], [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36)]),
            file(1, [1., 3., 5., 61.], [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36)]),
            file(1, [3., 1., 5., 5.5], [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36)]),
            file(1, KO, [1.5, 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36)]),
            file(1, KO, [1., 1., 1.], &[]),
            file(1, KO, [1., 1., 1.], &vec![entry(1, 2, 1., 0, 3, 2., 36); 17]),
            file(1, KO, [1., 1., 1.], &[entry(1, 64, 1., 0, 3, 2., 36)]),
            file(1, KO, [1., 1., 1.], &[entry(1, 2, 0., 0, 3, 2., 36)]),
            file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 16, 3, 2., 36)]),
            file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 4, 2., 36)]),
            file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 3., 36)]),
            file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 35)]),
        ] {
            assert!(table(&mut Reader::from_bytes(bad_file), 20).is_err());
        }
        // A looping attack clip is refused, as N3LK refuses it.
        let mut looping = entry(1, 2, 1., 0, 3, 2., 36);
        let attack = 4 * 7 + 2 * 20 + 8;
        looping[attack..attack + 4].copy_from_slice(&1u32.to_le_bytes());
        assert!(table(&mut Reader::from_bytes(file(1, KO, [1., 1., 1.], &[looping])), 2).is_err());
    }

    /// A plug entry (PQ-317): the base fields with flag 4, then the placement
    /// and the clip map rows.
    fn plug_entry(key: u32, placement: [f32; 12], rows: &[[u32; 4]], flags: u32, lit: u32) -> Vec<u8> {
        let mut v = entry(key, 2, 1., 2, flags, 1., lit);
        f(&mut v, &placement);
        u(&mut v, &[rows.len() as u32]);
        for row in rows {
            u(&mut v, row);
        }
        v
    }
    const PLACED: [f32; 12] = [0., -0.9, 0., 0.02, 0.9, 0., 0., 0.05, 0., 0., 0.9, -0.05];

    #[test]
    fn plug_entries_carry_a_placement_and_a_clip_map() {
        let rows = [[0, 0, 0, 0], [0, 2, 1, 1], [1, 3, 1, 1], [2, 16, 2, 1]];
        let good = file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36), plug_entry(2, PLACED, &rows, PLUG, 0)]);
        assert_eq!(table(&mut Reader::from_bytes(good.clone()), 2).unwrap(), 2);
        let mut flat = PLACED;
        flat[5] = 0.;
        flat[4] = 0.;
        let mut huge = PLACED;
        huge[3] = 101.;
        let mut nan = PLACED;
        nan[0] = f32::NAN;
        for bad_entry in [
            plug_entry(2, PLACED, &rows, PLUG | 1, 0),   // optional
            plug_entry(2, PLACED, &rows, PLUG | 2, 0),   // emissive
            plug_entry(2, PLACED, &rows, PLUG, 3),       // lit
            plug_entry(2, flat, &rows, PLUG, 0),         // singular
            plug_entry(2, huge, &rows, PLUG, 0),
            plug_entry(2, nan, &rows, PLUG, 0),
            plug_entry(2, PLACED, &[], PLUG, 0),
            plug_entry(2, PLACED, &vec![[0, 0, 0, 0]; 65], PLUG, 0),
            plug_entry(2, PLACED, &[[3, 0, 0, 0]], PLUG, 0),  // unknown kind
            plug_entry(2, PLACED, &[[0, 10, 0, 0]], PLUG, 0), // pose state past 9
            plug_entry(2, PLACED, &[[0, 0, 4, 0]], PLUG, 0),  // slot past 3
            plug_entry(2, PLACED, &[[0, 0, 0, 2]], PLUG, 0),  // once not 0 or 1
            plug_entry(2, PLACED, &[[0, 1, 0, 0], [0, 1, 1, 1]], PLUG, 0), // the same clip twice
        ] {
            let bytes = file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 36), bad_entry]);
            assert!(table(&mut Reader::from_bytes(bytes), 2).is_err());
        }
        // A plug entry's map is part of the table: cut short, it is refused.
        assert!(table(&mut Reader::from_bytes(good[..good.len() - 4].to_vec()), 2).is_err());
        // The same entry without the plug flag leaves its plug bytes as trailing data.
        let plain = plug_entry(2, PLACED, &rows, 0, 0);
        assert!(table(&mut Reader::from_bytes(file(1, KO, [1., 1., 1.], &[plain])), 2).is_err());
    }

    #[test]
    fn models_are_looks_models_inside_the_budget() -> Result<()> {
        let dir = std::env::temp_dir().join(format!("n3e-attachments-{}", std::process::id()));
        fs::create_dir_all(&dir)?;
        fs::write(dir.join("attachments.bin"), file(1, KO, [1., 1., 1.], &[entry(1, 2, 1., 0, 3, 2., 0)]))?;
        let header = |magic: &[u8; 4], w: u32, h: u32| {
            let mut v = magic.to_vec();
            u(&mut v, &[w, h]);
            v
        };
        let run = |engine: u32, model: Option<Vec<u8>>| -> Result<u32> {
            let mut files: BTreeSet<String> = ["attachments.bin".to_string()].into();
            if let Some(m) = model {
                fs::write(dir.join("attachment-0.bin"), m)?;
                files.insert("attachment-0.bin".into());
            } else {
                let _ = fs::remove_file(dir.join("attachment-0.bin"));
            }
            let n = check(&dir, engine, 1, &mut files)?;
            assert!(!files.contains("attachment-0.bin"));
            Ok(n)
        };
        assert_eq!(run(38, Some(header(b"N3NM", 4, 4)))?, 1);
        assert!(run(38, Some(header(b"N3MM", 4, 4))).is_err());
        assert_eq!(run(39, Some(header(b"N3MM", 4, 4)))?, 1);
        assert!(run(39, Some(header(b"N3MI", 4, 4))).is_err());
        assert_eq!(run(40, Some(header(b"N3MI", 4, 4)))?, 1);
        assert!(run(41, Some(header(b"N3S1", 4, 4))).is_err());
        assert!(run(41, Some(header(b"N3NM", 0, 4))).is_err());
        assert!(run(41, Some(header(b"N3NM", 1025, 4))).is_err());
        assert!(run(41, None).is_err());
        fs::remove_dir_all(&dir)?;
        Ok(())
    }
}
