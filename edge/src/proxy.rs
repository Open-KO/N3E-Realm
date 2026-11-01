//! The PROXY protocol v2 header `realm-edge` writes first on each upstream connection,
//! in the form the server's parser accepts (`server/src/admission.rs`, `origin` and
//! `proxied`): version 2, command PROXY, TCP over IPv4 (0x11) or IPv6 (0x21).

use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};

pub const SIGNATURE: [u8; 12] = *b"\r\n\r\n\0\r\nQUIT\n";
/// Version 2, command PROXY.
const PROXY: u8 = 0x21;
const TCP4: u8 = 0x11;
const TCP6: u8 = 0x21;

/// `source` is the player (port 0: `CF-Connecting-IP` names no port); `destination` the
/// upstream address the bridge reached. Both addresses take the player's family; a
/// destination of the other family is mapped (IPv4 into IPv6) or unspecified.
pub fn header(source: IpAddr, destination: SocketAddr) -> Vec<u8> {
    let mut h = Vec::with_capacity(16 + 36);
    h.extend_from_slice(&SIGNATURE);
    h.push(PROXY);
    match crate::config::canonical(source) {
        IpAddr::V4(src) => {
            let dst = match crate::config::canonical(destination.ip()) {
                IpAddr::V4(d) => d,
                IpAddr::V6(_) => Ipv4Addr::UNSPECIFIED,
            };
            h.push(TCP4);
            h.extend_from_slice(&12u16.to_be_bytes());
            h.extend_from_slice(&src.octets());
            h.extend_from_slice(&dst.octets());
        }
        IpAddr::V6(src) => {
            let dst: Ipv6Addr = match destination.ip() {
                IpAddr::V4(d) => d.to_ipv6_mapped(),
                IpAddr::V6(d) => d,
            };
            h.push(TCP6);
            h.extend_from_slice(&36u16.to_be_bytes());
            h.extend_from_slice(&src.octets());
            h.extend_from_slice(&dst.octets());
        }
    }
    h.extend_from_slice(&0u16.to_be_bytes());
    h.extend_from_slice(&destination.port().to_be_bytes());
    h
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A mirror of the server's byte expectations (`admission::origin` then `proxied`;
    /// the server crate is not a dependency here): the 12-byte signature, a body of at
    /// most 216 bytes, command 0x21, family nibble 1 (>= 12 bytes) or 2 (>= 36 bytes).
    fn server_reads(bytes: &[u8]) -> Option<IpAddr> {
        let head: &[u8; 16] = bytes.get(..16)?.try_into().ok()?;
        let length = u16::from_be_bytes([head[14], head[15]]) as usize;
        if head[..12] != SIGNATURE || length > 216 || bytes.len() != 16 + length {
            return None;
        }
        let body = &bytes[16..];
        match (head[12], head[13] >> 4) {
            (0x21, 1) if body.len() >= 12 => Some(IpAddr::V4(Ipv4Addr::new(
                body[0], body[1], body[2], body[3],
            ))),
            (0x21, 2) if body.len() >= 36 => {
                let a: [u8; 16] = body[..16].try_into().ok()?;
                Some(IpAddr::V6(Ipv6Addr::from(a)))
            }
            _ => None,
        }
    }

    #[test]
    fn ipv4_header_bytes() {
        let h = header(
            "203.0.113.7".parse().unwrap(),
            "172.18.0.5:7777".parse().unwrap(),
        );
        let mut want = SIGNATURE.to_vec();
        want.extend_from_slice(&[
            0x21, 0x11, 0, 12, 203, 0, 113, 7, 172, 18, 0, 5, 0, 0, 0x1e, 0x61,
        ]);
        assert_eq!(h, want);
        assert_eq!(server_reads(&h), Some("203.0.113.7".parse().unwrap()));
    }

    #[test]
    fn ipv6_header_bytes() {
        let h = header(
            "2001:db8::9".parse().unwrap(),
            "[fd00::5]:7777".parse().unwrap(),
        );
        assert_eq!(h.len(), 16 + 36);
        assert_eq!(&h[12..16], &[0x21, 0x21, 0, 36]);
        assert_eq!(&h[48..52], &[0, 0, 0x1e, 0x61]);
        assert_eq!(server_reads(&h), Some("2001:db8::9".parse().unwrap()));
    }

    #[test]
    fn mixed_families_take_the_players() {
        let h = header(
            "2001:db8::9".parse().unwrap(),
            "10.0.0.2:7777".parse().unwrap(),
        );
        assert_eq!(h[13], 0x21);
        assert_eq!(
            &h[32..48],
            &"::ffff:10.0.0.2".parse::<Ipv6Addr>().unwrap().octets()
        );
        assert_eq!(server_reads(&h), Some("2001:db8::9".parse().unwrap()));
        let h = header(
            "198.51.100.1".parse().unwrap(),
            "[fd00::5]:7777".parse().unwrap(),
        );
        assert_eq!((h[13], &h[20..24]), (0x11, &[0u8, 0, 0, 0][..]));
        assert_eq!(server_reads(&h), Some("198.51.100.1".parse().unwrap()));
        // A mapped player address is forwarded as IPv4, so the server's per-IP
        // buckets see one address however Cloudflare wrote it.
        let h = header(
            "::ffff:198.51.100.1".parse().unwrap(),
            "10.0.0.2:7777".parse().unwrap(),
        );
        assert_eq!(server_reads(&h), Some("198.51.100.1".parse().unwrap()));
    }
}
