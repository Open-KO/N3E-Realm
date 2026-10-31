//! Static collision: a native heightfield plus object triangles in a uniform
//! grid (N3C2, PQ-215), or the legacy N3C1 triangle soup.
//!
//! Every query gathers the candidate triangles whose padded X/Z bounds meet a
//! box, and the movement code runs its exact triangle tests on that subset.
//! The grid only accelerates the gather: membership is decided per triangle
//! from its own bounds, so the answer does not depend on cell boundaries, and
//! the C++ client gathers the same set with the same rule.
use crate::content::{bad, Reader, Result};
use std::path::Path;

/// N3C1's vertex cap (the cooker's historical limit).
pub const N3C1_POINTS: u32 = 196_608;
/// N3C2: samples a side, metres a side, object vertices.
pub const MAX_SAMPLES: u32 = 513;
pub const MAX_EXTENT: f32 = 4096.;
pub const MAX_OBJECT_POINTS: u32 = 393_216;
/// Grid: nominal cell, cells a side, and the cells one triangle may join
/// before it is kept in the always-scanned list instead. The grid never
/// refuses a package: memberships are at most SPREAD per triangle and the
/// triangle count is bounded by the format, so memory is bounded by
/// construction; a query scans at most every triangle, the full scan's cost.
const CELL: f32 = 4.;
const MAX_CELLS: f32 = 1024.;
const SPREAD: usize = 64;

/// Slack added to a triangle's bounds before a box test. It covers the
/// narrow phase's barycentric edge tolerance (1e-6 of the triangle) and f32
/// rounding, so a triangle the full scan would accept is never left out.
pub fn pad(extent: f32) -> f32 {
    0.25 + extent * 1e-4
}

#[derive(Clone, Debug)]
pub struct Terrain {
    width: usize,
    depth: usize,
    ox: f32,
    oz: f32,
    spacing: f32,
    diagonal: u32,
    heights: Vec<f32>,
}
impl Terrain {
    fn vertex(&self, i: usize, j: usize) -> [f32; 3] {
        // f64 then one rounding: the same value in both readers.
        [
            (f64::from(self.ox) + i as f64 * f64::from(self.spacing)) as f32,
            self.heights[j * self.width + i],
            (f64::from(self.oz) + j as f64 * f64::from(self.spacing)) as f32,
        ]
    }
    /// The cooker's split (`heightfield_triangles`): fixed, or by (i + j) parity.
    fn cell(&self, i: usize, j: usize, out: &mut Vec<[f32; 3]>) {
        let (a, b, c, d) = (
            self.vertex(i, j),
            self.vertex(i, j + 1),
            self.vertex(i + 1, j),
            self.vertex(i + 1, j + 1),
        );
        let phase = usize::from(self.diagonal == 2);
        if self.diagonal != 0 && (i + j + phase) % 2 == 1 {
            out.extend([a, b, d, a, d, c]);
        } else {
            out.extend([a, b, c, c, b, d]);
        }
    }
    fn range(&self, lo: f32, hi: f32, origin: f32, samples: usize) -> Option<(usize, usize)> {
        let s = f64::from(self.spacing);
        let ring = (f64::from(pad(self.spacing)) / s).ceil() + 1.;
        let a = ((f64::from(lo) - f64::from(origin)) / s).floor() - ring;
        let b = ((f64::from(hi) - f64::from(origin)) / s).floor() + ring;
        let last = (samples - 2) as f64;
        if b < 0. || a > last {
            return None;
        }
        Some((a.max(0.) as usize, b.min(last) as usize))
    }
}

#[derive(Clone, Debug, Default)]
struct Grid {
    x0: f32,
    z0: f32,
    cell: f32,
    nx: usize,
    nz: usize,
    start: Vec<u32>,
    ids: Vec<u32>,
    large: Vec<u32>,
    bounds: Vec<[f32; 4]>,
}
impl Grid {
    fn build(t: &[[f32; 3]]) -> Self {
        let bounds: Vec<[f32; 4]> = t
            .chunks_exact(3)
            .map(|v| {
                let lo = |a: usize| v.iter().map(|p| p[a]).fold(f32::INFINITY, f32::min);
                let hi = |a: usize| v.iter().map(|p| p[a]).fold(f32::NEG_INFINITY, f32::max);
                let m = pad((hi(0) - lo(0)).max(hi(2) - lo(2)));
                [lo(0) - m, lo(2) - m, hi(0) + m, hi(2) + m]
            })
            .collect();
        if bounds.is_empty() {
            return Self::default();
        }
        let x0 = bounds.iter().map(|b| b[0]).fold(f32::INFINITY, f32::min);
        let z0 = bounds.iter().map(|b| b[1]).fold(f32::INFINITY, f32::min);
        let x1 = bounds.iter().map(|b| b[2]).fold(f32::NEG_INFINITY, f32::max);
        let z1 = bounds.iter().map(|b| b[3]).fold(f32::NEG_INFINITY, f32::max);
        let cell = CELL.max((x1 - x0).max(z1 - z0) / MAX_CELLS);
        let nx = ((x1 - x0) / cell) as usize + 1;
        let nz = ((z1 - z0) / cell) as usize + 1;
        let mut g = Self { x0, z0, cell, nx, nz, bounds, ..Self::default() };
        let mut count = vec![0usize; nx * nz];
        let mut spans = Vec::with_capacity(g.bounds.len());
        for (i, b) in g.bounds.iter().enumerate() {
            let (cx, cz) = (g.span(b[0], b[2], true), g.span(b[1], b[3], false));
            if (cx.1 - cx.0 + 1) * (cz.1 - cz.0 + 1) > SPREAD {
                g.large.push(i as u32);
                spans.push(None);
                continue;
            }
            for z in cz.0..=cz.1 {
                for x in cx.0..=cx.1 {
                    count[z * nx + x] += 1;
                }
            }
            spans.push(Some((cx, cz)));
        }
        let total: usize = count.iter().sum();
        g.start = Vec::with_capacity(nx * nz + 1);
        let mut at = 0u32;
        for c in &count {
            g.start.push(at);
            at += *c as u32;
        }
        g.start.push(at);
        let mut fill: Vec<u32> = g.start[..nx * nz].to_vec();
        g.ids = vec![0; total];
        for (i, s) in spans.iter().enumerate() {
            if let Some((cx, cz)) = s {
                for z in cz.0..=cz.1 {
                    for x in cx.0..=cx.1 {
                        let k = z * nx + x;
                        g.ids[fill[k] as usize] = i as u32;
                        fill[k] += 1;
                    }
                }
            }
        }
        g
    }
    /// Cell range a closed interval covers, clamped to the grid.
    fn span(&self, lo: f32, hi: f32, x: bool) -> (usize, usize) {
        let (o, n) = if x { (self.x0, self.nx) } else { (self.z0, self.nz) };
        let c = |v: f32| (((v - o) / self.cell).floor().max(0.) as usize).min(n - 1);
        (c(lo), c(hi))
    }
    /// Listed triangles first (ascending), then the cells' (ascending, once
    /// each); a triangle is in one or the other, never both.
    fn query(&self, t: &[[f32; 3]], b: [f32; 4], out: &mut Vec<[f32; 3]>) {
        if self.bounds.is_empty() {
            return;
        }
        let meets = |i: u32| {
            let r = self.bounds[i as usize];
            r[0] <= b[2] && r[2] >= b[0] && r[1] <= b[3] && r[3] >= b[1]
        };
        let push = |i: u32, out: &mut Vec<[f32; 3]>| {
            let i = i as usize * 3;
            out.extend_from_slice(&t[i..i + 3]);
        };
        for &i in &self.large {
            if meets(i) {
                push(i, out);
            }
        }
        let x1 = self.x0 + self.nx as f32 * self.cell;
        let z1 = self.z0 + self.nz as f32 * self.cell;
        if !(b[2] >= self.x0 && b[0] <= x1 && b[3] >= self.z0 && b[1] <= z1) {
            return;
        }
        let mut ids = Vec::new();
        let (cx, cz) = (self.span(b[0], b[2], true), self.span(b[1], b[3], false));
        for z in cz.0..=cz.1 {
            for x in cx.0..=cx.1 {
                let k = z * self.nx + x;
                ids.extend_from_slice(&self.ids[self.start[k] as usize..self.start[k + 1] as usize]);
            }
        }
        ids.sort_unstable();
        ids.dedup();
        for i in ids {
            if meets(i) {
                push(i, out);
            }
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Collision {
    terrain: Option<Terrain>,
    objects: Vec<[f32; 3]>,
    grid: Grid,
}
impl Collision {
    /// An N3C1 package (or a test's own triangles): the whole soup as objects.
    pub fn soup(objects: Vec<[f32; 3]>) -> Result<Self> {
        if objects.len() % 3 != 0 {
            return Err(bad("collision triangles"));
        }
        let grid = Grid::build(&objects);
        Ok(Self { terrain: None, objects, grid })
    }
    pub fn read(path: &Path) -> Result<Self> {
        let mut c = Reader::open(path)?;
        let magic: [u8; 4] = c.take(4)?.try_into()?;
        let out = match &magic {
            b"N3C1" => {
                let n = c.u()?;
                if n == 0 || n > N3C1_POINTS || n % 3 != 0 {
                    return Err(bad("collision count"));
                }
                let mut v = Vec::with_capacity(n as usize);
                for _ in 0..n {
                    v.push([c.f()?, c.f()?, c.f()?]);
                }
                c.end()?;
                Self::soup(v)?
            }
            b"N3C2" => {
                let (w, d) = (c.u()?, c.u()?);
                if !(2..=MAX_SAMPLES).contains(&w) || !(2..=MAX_SAMPLES).contains(&d) {
                    return Err(bad("collision heightfield samples"));
                }
                let (ox, oz, spacing) = (c.f()?, c.f()?, c.f()?);
                let extent = |n: u32| (n - 1) as f32 * spacing;
                if !(spacing > 0. && spacing <= 100.)
                    || extent(w) > MAX_EXTENT
                    || extent(d) > MAX_EXTENT
                    || (ox + extent(w)).abs() > 1e6
                    || (oz + extent(d)).abs() > 1e6
                {
                    return Err(bad("collision heightfield extent"));
                }
                let diagonal = c.u()?;
                if diagonal > 2 {
                    return Err(bad("collision heightfield diagonal"));
                }
                let mut heights = Vec::with_capacity((w * d) as usize);
                for _ in 0..w * d {
                    heights.push(c.f()?);
                }
                let n = c.u()?;
                if n > MAX_OBJECT_POINTS || n % 3 != 0 {
                    return Err(bad("collision count"));
                }
                let mut v = Vec::with_capacity(n as usize);
                for _ in 0..n {
                    v.push([c.f()?, c.f()?, c.f()?]);
                }
                c.end()?;
                let mut out = Self::soup(v)?;
                out.terrain = Some(Terrain {
                    width: w as usize,
                    depth: d as usize,
                    ox,
                    oz,
                    spacing,
                    diagonal,
                    heights,
                });
                out
            }
            _ => return Err(bad("collision magic")),
        };
        Ok(out)
    }
    /// Candidate triangles for the closed X/Z box: terrain cells first (row
    /// major), then objects in file order. Each is a superset of the
    /// triangles a full scan could find within the box.
    pub fn near(&self, x0: f32, z0: f32, x1: f32, z1: f32) -> Vec<[f32; 3]> {
        let mut out = Vec::new();
        if ![x0, z0, x1, z1].iter().all(|v| v.is_finite()) || x0 > x1 || z0 > z1 {
            return out;
        }
        if let Some(t) = &self.terrain {
            if let (Some(i), Some(j)) = (t.range(x0, x1, t.ox, t.width), t.range(z0, z1, t.oz, t.depth)) {
                for jj in j.0..=j.1 {
                    for ii in i.0..=i.1 {
                        t.cell(ii, jj, &mut out);
                    }
                }
            }
        }
        self.grid.query(&self.objects, [x0, z0, x1, z1], &mut out);
        out
    }
    pub fn around(&self, x: f32, z: f32, reach: f32) -> Vec<[f32; 3]> {
        self.near(x - reach, z - reach, x + reach, z + reach)
    }
    /// Every triangle in the same order as `near`, without materialising them.
    pub fn each(&self, mut f: impl FnMut(&[[f32; 3]]) -> bool) {
        let mut cell = Vec::with_capacity(6);
        if let Some(t) = &self.terrain {
            for j in 0..t.depth - 1 {
                for i in 0..t.width - 1 {
                    cell.clear();
                    t.cell(i, j, &mut cell);
                    for tri in cell.chunks_exact(3) {
                        if !f(tri) {
                            return;
                        }
                    }
                }
            }
        }
        for tri in self.objects.chunks_exact(3) {
            if !f(tri) {
                return;
            }
        }
    }
    pub fn triangles(&self) -> usize {
        self.terrain.as_ref().map_or(0, |t| (t.width - 1) * (t.depth - 1) * 2) + self.objects.len() / 3
    }
    pub fn has_terrain(&self) -> bool {
        self.terrain.is_some()
    }
    /// Bytes held: heights, object vertices, grid.
    pub fn memory(&self) -> usize {
        self.terrain.as_ref().map_or(0, |t| t.heights.len() * 4)
            + self.objects.len() * 12
            + self.grid.bounds.len() * 16
            + (self.grid.start.len() + self.grid.ids.len() + self.grid.large.len()) * 4
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn n3c2(w: u32, d: u32, spacing: f32, diagonal: u32, heights: &[f32], objects: &[[f32; 3]]) -> Vec<u8> {
        let mut b = b"N3C2".to_vec();
        for v in [w, d] {
            b.extend(v.to_le_bytes());
        }
        for v in [-8f32, -8., spacing] {
            b.extend(v.to_le_bytes());
        }
        b.extend(diagonal.to_le_bytes());
        for h in heights {
            b.extend(h.to_le_bytes());
        }
        b.extend((objects.len() as u32 * 3).to_le_bytes());
        for p in objects.iter().flat_map(|p| p.iter()) {
            b.extend(p.to_le_bytes());
        }
        b
    }
    fn load(bytes: &[u8]) -> Result<Collision> {
        let dir = std::env::temp_dir().join(format!("n3e-collision-{}-{}", std::process::id(), bytes.len()));
        std::fs::write(&dir, bytes)?;
        let r = Collision::read(&dir);
        let _ = std::fs::remove_file(&dir);
        r
    }
    #[test]
    fn malformed_n3c2_is_refused() {
        let good = n3c2(3, 3, 8., 1, &[0.; 9], &[]);
        let c = load(&good).unwrap();
        assert_eq!(c.triangles(), 8);
        for (offset, value) in [(4, 1u32), (4, 514), (8, 1), (24, 3)] {
            let mut b = good.clone();
            b[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
            assert!(load(&b).is_err(), "{offset} {value}");
        }
        for spacing in [0., -1., 100.5, f32::NAN] {
            assert!(load(&n3c2(3, 3, spacing, 0, &[0.; 9], &[])).is_err());
        }
        // 513 samples at 8 m is 4096 m (accepted); at 8.1 m it is not.
        assert!(load(&n3c2(513, 2, 8.1, 0, &vec![0.; 1026], &[])).is_err());
        assert!(load(&n3c2(513, 2, 8., 0, &vec![0.; 1026], &[])).is_ok());
        let mut nan = good.clone();
        nan[28..32].copy_from_slice(&f32::NAN.to_le_bytes());
        assert!(load(&nan).is_err());
        assert!(load(&good[..good.len() - 1]).is_err());
        assert!(load(&[good.as_slice(), &[0]].concat()).is_err());
        let mut odd = good.clone();
        let n = odd.len() - 4;
        odd[n..].copy_from_slice(&2u32.to_le_bytes());
        assert!(load(&odd).is_err());
        assert!(load(b"N3C3").is_err());
    }
    #[test]
    fn grid_gathers_every_reachable_triangle() {
        // A long thin wall far bigger than the spread limit lands in the
        // always-scanned list; small triangles in cells. Both are found.
        let mut t = vec![[-500., 0., 0.], [500., 0., 0.], [500., 3., 0.]];
        for i in 0..100 {
            let x = i as f32 * 3.;
            t.extend([[x, 0., 10.], [x + 1., 0., 10.], [x, 0., 11.]]);
        }
        let c = Collision::soup(t.clone()).unwrap();
        assert_eq!(c.grid.large, vec![0]);
        let near = c.around(30.2, 10.2, 0.1);
        assert!(near.contains(&[30., 0., 10.]) && !near.contains(&[-500., 0., 0.]));
        assert!(!near.contains(&[60., 0., 10.]));
        // The listed wall is still filtered by its own padded bounds.
        assert!(c.around(400., 0.3, 0.).contains(&[-500., 0., 0.]));
        assert!(!c.around(400., 0.4, 0.).contains(&[-500., 0., 0.]));
        assert!(c.near(f32::NAN, 0., 1., 1.).is_empty());
    }
}
