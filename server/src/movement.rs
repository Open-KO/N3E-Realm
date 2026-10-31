//! Fixed 50ms kinematic movement. Legacy step retained; mode-aware steps are bounded.
use crate::content::{bad, Result};
pub fn direction(x: f32, z: f32) -> Result<[f32; 2]> {
    if !x.is_finite() || !z.is_finite() || x.abs() > 1. || z.abs() > 1. {
        return Err(bad("invalid movement"));
    }
    let length = (x * x + z * z).sqrt().max(1.);
    Ok([x / length, z / length])
}
fn normal(t: &[[f32; 3]]) -> [f32; 3] {
    let a = [t[1][0] - t[0][0], t[1][1] - t[0][1], t[1][2] - t[0][2]];
    let b = [t[2][0] - t[0][0], t[2][1] - t[0][1], t[2][2] - t[0][2]];
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn walkable(t: &[[f32; 3]]) -> bool {
    let n = normal(t);
    n[1].abs() >= 0.707107 * (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt()
}
pub use crate::collision::Collision;
/// Each public query gathers the triangles within its own reach (support at
/// the point, wall capsules within the radius of every point the move can
/// visit) and runs the full-scan `*_soup` test on them; `Collision::near` pads
/// each triangle's bounds, so no triangle the full scan would use is left out.
pub fn ground(c: &Collision, x: f32, z: f32) -> f32 {
    ground_soup(&c.around(x, z, 0.), x, z)
}
pub(crate) fn ground_soup(triangles: &[[f32; 3]], x: f32, z: f32) -> f32 {
    support(triangles, x, z, f32::INFINITY).0
}
fn support(triangles: &[[f32; 3]], x: f32, z: f32, max_y: f32) -> (f32, f32) {
    let mut y = f32::NEG_INFINITY;
    let mut ceiling = f32::INFINITY;
    for t in triangles.chunks_exact(3) {
        if !walkable(t) {
            continue;
        }
        let (a, b, c) = (t[0], t[1], t[2]);
        let d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]);
        if d.abs() < 1e-8 {
            continue;
        }
        let u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d;
        let v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d;
        if u >= -1e-6 && v >= -1e-6 && u + v <= 1. + 1e-6 {
            let surface = u * a[1] + v * b[1] + (1. - u - v) * c[1];
            // A roof is not reachable support. Retain it for headroom rejection.
            if surface <= max_y {
                y = y.max(surface);
            } else {
                ceiling = ceiling.min(surface);
            }
        }
    }
    (y, ceiling)
}
fn allowed(triangles: &[[f32; 3]], old: [f32; 3], x: f32, z: f32, cfg: Config) -> Option<[f32; 3]> {
    let (y, ceiling) = support(triangles, x, z, old[1] + cfg.step_height);
    if !y.is_finite() || (y - old[1]).abs() > cfg.step_height || ceiling < y + cfg.height {
        return None;
    }
    for t in triangles.chunks_exact(3) {
        if walkable(t) {
            continue;
        }
        let lo = t.iter().map(|v| v[1]).fold(f32::INFINITY, f32::min);
        let hi = t.iter().map(|v| v[1]).fold(f32::NEG_INFINITY, f32::max);
        // A reachable riser must not block the body before its centre can step up.
        if hi <= y + cfg.step_height || lo >= y + cfg.height {
            continue;
        }
        // Conservative projected edge capsule for vertical/steep static triangles.
        for i in 0..3 {
            let a = t[i];
            let b = t[(i + 1) % 3];
            let dx = b[0] - a[0];
            let dz = b[2] - a[2];
            let q = (((x - a[0]) * dx + (z - a[2]) * dz) / (dx * dx + dz * dz).max(1e-12))
                .clamp(0., 1.);
            if (x - a[0] - q * dx).powi(2) + (z - a[2] - q * dz).powi(2) < cfg.radius * cfg.radius {
                return None;
            }
        }
    }
    Some([x, y, z])
}
/// Whether an actor capsule can stand at the highest walkable support here:
/// support exists, headroom is clear and no static geometry overlaps the body.
pub fn standable(c: &Collision, x: f32, z: f32) -> bool {
    standable_soup(&c.around(x, z, Config::default().radius), x, z)
}
pub(crate) fn standable_soup(triangles: &[[f32; 3]], x: f32, z: f32) -> bool {
    let y = ground_soup(triangles, x, z);
    y.is_finite() && allowed(triangles, [x, y, z], x, z, Config::default()).is_some()
}
/// Legacy fixed step: at most 0.15 m per axis times the direction, plus the radius.
pub fn step(c: &Collision, p: [f32; 3], d: [f32; 2]) -> [f32; 3] {
    let reach = 0.15 * d[0].abs().max(d[1].abs()) + Config::default().radius;
    if !reach.is_finite() {
        return p;
    }
    step_soup(&c.around(p[0], p[2], reach), p, d)
}
pub(crate) fn step_soup(triangles: &[[f32; 3]], p: [f32; 3], d: [f32; 2]) -> [f32; 3] {
    let (dx, dz) = (d[0] * 0.15, d[1] * 0.15);
    if let Some(q) = allowed(triangles, p, p[0] + dx, p[2] + dz, Config::default()) {
        return q;
    }
    let q = allowed(triangles, p, p[0] + dx, p[2], Config::default()).unwrap_or(p);
    allowed(triangles, q, q[0], q[2] + dz, Config::default()).unwrap_or(q)
}
pub fn spawn(c: &Collision) -> Result<[f32; 3]> {
    let y = ground(c, 0., 0.);
    if y.is_finite() {
        return Ok([0., y, 0.]);
    }
    let mut found = None;
    c.each(|t| {
        if walkable(t) {
            found = Some([
                (t[0][0] + t[1][0] + t[2][0]) / 3.,
                (t[0][1] + t[1][1] + t[2][1]) / 3.,
                (t[0][2] + t[1][2] + t[2][2]) / 3.,
            ]);
        }
        found.is_none()
    });
    found.ok_or_else(|| bad("package has no walkable spawn"))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn speed_and_invalid() {
        assert!(direction(f32::NAN, 0.).is_err());
        assert!(direction(f32::INFINITY, 0.).is_err());
        assert!(direction(1.01, 0.).is_err());
        let d = direction(1., 1.).unwrap();
        assert!((d[0] * d[0] + d[1] * d[1] - 1.).abs() < 1e-6);
    }
    #[test]
    fn walls_bounds_and_slide() {
        let mut t = vec![
            [-2., 0., -2.],
            [2., 0., -2.],
            [2., 0., 2.],
            [-2., 0., -2.],
            [2., 0., 2.],
            [-2., 0., 2.],
        ];
        let c = Collision::soup(t.clone()).unwrap();
        assert_eq!(step(&c, [2., 0., 0.], [1., 0.]), [2., 0., 0.]);
        t.extend([
            [0.5, 0., -2.],
            [0.5, 2., -2.],
            [0.5, 2., 2.],
            [0.5, 0., -2.],
            [0.5, 2., 2.],
            [0.5, 0., 2.],
        ]);
        let c = Collision::soup(t).unwrap();
        let mut p = [0., 0., 0.];
        for _ in 0..10 {
            p = step(&c, p, direction(1., 1.).unwrap());
        }
        assert!(p[0] <= 0.3 && p[2] > 0.9);
    }
    /// Deterministic generator (xorshift) so failures reproduce.
    struct Rng(u64);
    impl Rng {
        fn f(&mut self) -> f32 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            (self.0 >> 40) as f32 / (1u64 << 24) as f32
        }
    }
    /// A hostile-ish N3C1 soup: rolling terrain with steep cells, thin walls,
    /// low ledges, bridges (overhead support) and one huge sloped plate.
    fn soup(rng: &mut Rng) -> Vec<[f32; 3]> {
        let mut t = Vec::new();
        let h = |x: f32, z: f32| (x * 0.31).sin() * 1.5 + (z * 0.17).cos() * 2. + if (x as i32 + z as i32) % 7 == 0 { 3. } else { 0. };
        for j in -16..16 {
            for i in -16..16 {
                let (x, z) = (i as f32 * 2., j as f32 * 2.);
                let (a, b, c, d) = ([x, h(x, z), z], [x, h(x, z + 2.), z + 2.], [x + 2., h(x + 2., z), z], [x + 2., h(x + 2., z + 2.), z + 2.]);
                t.extend([a, b, c, c, b, d]);
            }
        }
        for _ in 0..120 {
            let (x, z, y) = (rng.f() * 60. - 30., rng.f() * 60. - 30., rng.f() * 4. - 1.);
            let (dx, dz) = (rng.f() * 6. - 3., rng.f() * 6. - 3.);
            match (rng.f() * 3.) as u32 {
                0 => t.extend([[x, y, z], [x, y + 2.5, z], [x + dx, y + 2.5, z + dz], [x, y, z], [x + dx, y + 2.5, z + dz], [x + dx, y, z + dz]]),
                1 => t.extend([[x, y, z], [x + dx.abs() + 0.5, y, z], [x, y, z + dz.abs() + 0.5]]),
                _ => t.extend([[x, y + 1.9, z], [x, y + 1.9, z + 4.], [x + 4., y + 2.0, z]]),
            }
        }
        t.extend([[-900., -5., -900.], [900., 40., -900.], [-900., 40., 900.]]);
        t
    }
    #[test]
    fn gathered_answers_equal_the_full_scan() {
        let mut rng = Rng(0x9e37_79b9_7f4a_7c15);
        for _ in 0..2 {
            let t = soup(&mut rng);
            let c = Collision::soup(t.clone()).unwrap();
            let cfg = Config { walk: 3., run: 6., backward: 1.5, radius: 0.35, height: 1.8, step_height: 0.4 };
            let mut checked = 0;
            for _ in 0..400 {
                let (x, z) = (rng.f() * 70. - 35., rng.f() * 70. - 35.);
                assert_eq!(ground(&c, x, z).to_bits(), ground_soup(&t, x, z).to_bits(), "{x} {z}");
                assert_eq!(standable(&c, x, z), standable_soup(&t, x, z));
                let y = ground_soup(&t, x, z);
                if !y.is_finite() {
                    continue;
                }
                let p = [x, y, z];
                let d = direction(rng.f() * 2. - 1., rng.f() * 2. - 1.).unwrap();
                assert_eq!(step(&c, p, d), step_soup(&t, p, d));
                let (mode, multiplier) = ((rng.f() * 3.) as u32, if checked % 8 == 0 { 1. + rng.f() * 9. } else { 1. });
                assert_eq!(
                    advance_scaled(&c, p, d[0], d[1], mode, cfg, multiplier).unwrap(),
                    advance_soup(&t, p, d[0], d[1], mode, cfg, multiplier).unwrap()
                );
                checked += 1;
            }
            assert!(checked > 100);
            assert_eq!(spawn(&c).unwrap(), {
                let y = ground_soup(&t, 0., 0.);
                [0., y, 0.]
            });
        }
    }
    /// The native heightfield answers exactly as the triangles the cooker
    /// would have written for it, for each diagonal convention.
    #[test]
    fn heightfield_answers_equal_its_triangles() {
        let mut rng = Rng(7);
        for diagonal in 0..3u32 {
            let (w, d, s, ox, oz) = (40usize, 33usize, 1.5f32, -30f32, -20f32);
            let heights: Vec<f32> = (0..w * d).map(|i| ((i % w) as f32 * 0.4).sin() * 2. + if i % 11 == 0 { 2.5 } else { 0. }).collect();
            let mut bytes = b"N3C2".to_vec();
            for v in [w as u32, d as u32] {
                bytes.extend(v.to_le_bytes());
            }
            for v in [ox, oz, s] {
                bytes.extend(v.to_le_bytes());
            }
            bytes.extend(diagonal.to_le_bytes());
            for h in &heights {
                bytes.extend(h.to_le_bytes());
            }
            let wall = [[0f32, -3., 0.], [0., 6., 0.], [0., 6., 8.], [0., -3., 0.], [0., 6., 8.], [0., -3., 8.]];
            bytes.extend((wall.len() as u32).to_le_bytes());
            for p in wall.iter().flatten() {
                bytes.extend(p.to_le_bytes());
            }
            let path = std::env::temp_dir().join(format!("n3e-hf-{}-{diagonal}", std::process::id()));
            std::fs::write(&path, &bytes).unwrap();
            let c = Collision::read(&path).unwrap();
            std::fs::remove_file(&path).unwrap();
            // The cooker's soup for the same grid (main.heightfield_triangles).
            let mut t = Vec::new();
            let v = |i: usize, j: usize| [(f64::from(ox) + i as f64 * f64::from(s)) as f32, heights[j * w + i], (f64::from(oz) + j as f64 * f64::from(s)) as f32];
            for j in 0..d - 1 {
                for i in 0..w - 1 {
                    let (a, b, cc, dd) = (v(i, j), v(i, j + 1), v(i + 1, j), v(i + 1, j + 1));
                    let phase = usize::from(diagonal == 2);
                    if diagonal != 0 && (i + j + phase) % 2 == 1 {
                        t.extend([a, b, dd, a, dd, cc]);
                    } else {
                        t.extend([a, b, cc, cc, b, dd]);
                    }
                }
            }
            t.extend(wall);
            assert_eq!(c.triangles(), t.len() / 3);
            let mut all = Vec::new();
            c.each(|tri| {
                all.extend_from_slice(tri);
                true
            });
            assert_eq!(all, t);
            let cfg = Config::default();
            for _ in 0..400 {
                let (x, z) = (rng.f() * 64. - 34., rng.f() * 54. - 24.);
                assert_eq!(ground(&c, x, z).to_bits(), ground_soup(&t, x, z).to_bits());
                assert_eq!(standable(&c, x, z), standable_soup(&t, x, z));
                let y = ground_soup(&t, x, z);
                if y.is_finite() {
                    let dir = direction(rng.f() * 2. - 1., rng.f() * 2. - 1.).unwrap();
                    assert_eq!(advance(&c, [x, y, z], dir[0], dir[1], 1, cfg).unwrap(), advance_soup(&t, [x, y, z], dir[0], dir[1], 1, cfg, 1.).unwrap());
                }
            }
            // Off the map there is no support at all.
            assert!(!ground(&c, -40., 0.).is_finite());
        }
    }
}

/// Generic package policy. These dimensions are synthetic, not a KO radius.
#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub walk: f32,
    pub run: f32,
    pub backward: f32,
    pub radius: f32,
    pub height: f32,
    pub step_height: f32,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            walk: 3.,
            run: 3.,
            backward: 3.,
            radius: 0.2,
            height: 1.6,
            step_height: 0.25,
        }
    }
}
impl Config {
    pub fn validate(self) -> Result<Self> {
        if ![self.walk, self.run, self.backward]
            .iter()
            .all(|v| (0.01..=6.).contains(v))
            || !(0.1..=1.).contains(&self.radius)
            || !(0.5..=3.).contains(&self.height)
            || !(0.05..=0.5).contains(&self.step_height)
            || self.step_height >= self.height
            || self.backward > self.walk
            || self.walk > self.run
        {
            return Err(bad("movement policy bounds"));
        }
        Ok(self)
    }
    pub fn speed(self, mode: u32) -> Result<f32> {
        match mode {
            0 => Ok(self.walk),
            1 => Ok(self.run),
            2 => Ok(self.backward),
            _ => Err(bad("invalid movement mode")),
        }
    }
}
/// x/z are world-space intent, including backward direction; mode sets magnitude only.
pub fn advance(
    t: &Collision,
    p: [f32; 3],
    x: f32,
    z: f32,
    mode: u32,
    cfg: Config,
) -> Result<[f32; 3]> {
    advance_scaled(t, p, x, z, mode, cfg, 1.)
}
pub fn advance_scaled(
    c: &Collision,
    p: [f32; 3],
    x: f32,
    z: f32,
    mode: u32,
    cfg: Config,
    multiplier: f32,
) -> Result<[f32; 3]> {
    if !(1. ..=10.).contains(&multiplier) {
        return Err(bad("movement multiplier"));
    }
    let cfg = cfg.validate()?;
    direction(x, z)?;
    // Every substep stays within `distance` of p on each axis.
    let reach = cfg.speed(mode)? * multiplier * 0.05 + cfg.radius;
    advance_soup(&c.around(p[0], p[2], reach), p, x, z, mode, cfg, multiplier)
}
pub(crate) fn advance_soup(
    t: &[[f32; 3]],
    mut p: [f32; 3],
    x: f32,
    z: f32,
    mode: u32,
    cfg: Config,
    multiplier: f32,
) -> Result<[f32; 3]> {
    if !(1. ..=10.).contains(&multiplier) {
        return Err(bad("movement multiplier"));
    }
    let cfg = cfg.validate()?;
    let d = direction(x, z)?;
    let distance = cfg.speed(mode)? * multiplier * 0.05;
    // <=6 substeps with the published bounds. Each is <= half the wall radius.
    let count = (distance / (cfg.radius * 0.5).min(0.05)).ceil() as u32;
    if count > 61 {
        return Err(bad("movement substep budget"));
    }
    let dx = d[0] * distance / count as f32;
    let dz = d[1] * distance / count as f32;
    for _ in 0..count {
        if let Some(q) = allowed(t, p, p[0] + dx, p[2] + dz, cfg) {
            p = q;
        } else {
            p = allowed(t, p, p[0] + dx, p[2], cfg).unwrap_or(p);
            p = allowed(t, p, p[0], p[2] + dz, cfg).unwrap_or(p);
        }
    }
    Ok(p)
}
