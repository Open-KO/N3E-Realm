//! WebSocket framing (RFC 6455 section 5), only as much as the bridge needs: masked
//! client frames in, unmasked frames out, no extensions (so RSV bits are always 0).

use tokio::io::{AsyncRead, AsyncReadExt};

pub const CONTINUATION: u8 = 0x0;
pub const TEXT: u8 = 0x1;
pub const BINARY: u8 = 0x2;
pub const CLOSE: u8 = 0x8;
pub const PING: u8 = 0x9;
pub const PONG: u8 = 0xA;

/// The largest payload accepted from a client (spec 12: 64 KiB + 1 KiB, else 1009).
pub const MAX_PAYLOAD: usize = 64 * 1024 + 1024;
/// Control frames carry at most this much (RFC 6455 5.5).
pub const MAX_CONTROL: usize = 125;

pub const NORMAL: u16 = 1000;
pub const GOING_AWAY: u16 = 1001;
pub const PROTOCOL_ERROR: u16 = 1002;
pub const UNSUPPORTED: u16 = 1003;
pub const TOO_BIG: u16 = 1009;
pub const INTERNAL: u16 = 1011;

/// One frame read from a client; its unmasked payload is in the caller's buffer.
#[derive(Debug, PartialEq)]
pub enum Read {
    Frame {
        fin: bool,
        opcode: u8,
    },
    /// Close the connection with this status; the word is the close log's reason.
    Refuse(u16, &'static str),
}

/// Reads one client frame into `payload` (cleared first). A frame refused by its header
/// is refused before its payload is read, so an oversize frame costs nothing.
pub async fn read<R: AsyncRead + Unpin>(r: &mut R, payload: &mut Vec<u8>) -> std::io::Result<Read> {
    payload.clear();
    let mut head = [0u8; 2];
    r.read_exact(&mut head).await?;
    let fin = head[0] & 0x80 != 0;
    let opcode = head[0] & 0x0F;
    if head[0] & 0x70 != 0 {
        return Ok(Read::Refuse(PROTOCOL_ERROR, "protocol"));
    }
    if head[1] & 0x80 == 0 {
        return Ok(Read::Refuse(PROTOCOL_ERROR, "unmasked"));
    }
    match opcode {
        TEXT => return Ok(Read::Refuse(UNSUPPORTED, "text")),
        CONTINUATION | BINARY | CLOSE | PING | PONG => {}
        _ => return Ok(Read::Refuse(PROTOCOL_ERROR, "protocol")),
    }
    let length = match head[1] & 0x7F {
        126 => {
            let mut n = [0u8; 2];
            r.read_exact(&mut n).await?;
            u16::from_be_bytes(n) as u64
        }
        127 => {
            let mut n = [0u8; 8];
            r.read_exact(&mut n).await?;
            let n = u64::from_be_bytes(n);
            if n >> 63 != 0 {
                return Ok(Read::Refuse(PROTOCOL_ERROR, "protocol"));
            }
            n
        }
        n => n as u64,
    };
    if opcode >= CLOSE && (!fin || length > MAX_CONTROL as u64) {
        return Ok(Read::Refuse(PROTOCOL_ERROR, "protocol"));
    }
    if length > MAX_PAYLOAD as u64 {
        return Ok(Read::Refuse(TOO_BIG, "oversize"));
    }
    let mut mask = [0u8; 4];
    r.read_exact(&mut mask).await?;
    payload.resize(length as usize, 0);
    r.read_exact(payload).await?;
    for (i, b) in payload.iter_mut().enumerate() {
        *b ^= mask[i & 3];
    }
    Ok(Read::Frame { fin, opcode })
}

/// The header of an unmasked, final frame of `length` bytes: (bytes, used).
pub fn header(opcode: u8, length: usize) -> ([u8; 10], usize) {
    let mut h = [0u8; 10];
    h[0] = 0x80 | opcode;
    if length <= 125 {
        h[1] = length as u8;
        (h, 2)
    } else if length <= u16::MAX as usize {
        h[1] = 126;
        h[2..4].copy_from_slice(&(length as u16).to_be_bytes());
        (h, 4)
    } else {
        h[1] = 127;
        h[2..10].copy_from_slice(&(length as u64).to_be_bytes());
        (h, 10)
    }
}

/// The reply to a client's close payload: its status echoed, or 1002 for a status no
/// endpoint may send (RFC 6455 7.4); an empty close is answered empty.
pub fn close_reply(payload: &[u8]) -> Option<u16> {
    match payload {
        [] => None,
        [_] => Some(PROTOCOL_ERROR),
        [a, b, ..] => {
            let code = u16::from_be_bytes([*a, *b]);
            let sendable = matches!(code, 1000..=1003 | 1007..=1011 | 3000..=4999);
            Some(if sendable { code } else { PROTOCOL_ERROR })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn masked(first: u8, payload: &[u8]) -> Vec<u8> {
        let mask = [0x12, 0x34, 0x56, 0x78];
        let mut f = vec![first];
        match payload.len() {
            n @ 0..=125 => f.push(0x80 | n as u8),
            n @ 126..=65535 => {
                f.push(0x80 | 126);
                f.extend_from_slice(&(n as u16).to_be_bytes());
            }
            n => {
                f.push(0x80 | 127);
                f.extend_from_slice(&(n as u64).to_be_bytes());
            }
        }
        f.extend_from_slice(&mask);
        f.extend(payload.iter().enumerate().map(|(i, b)| b ^ mask[i & 3]));
        f
    }
    async fn one(bytes: Vec<u8>) -> (std::io::Result<Read>, Vec<u8>) {
        let mut p = Vec::new();
        let r = read(&mut bytes.as_slice(), &mut p).await;
        (r, p)
    }

    #[tokio::test]
    async fn frames_and_refusals() {
        let (r, p) = one(masked(0x82, b"hello")).await;
        assert_eq!(
            (r.unwrap(), p.as_slice()),
            (
                Read::Frame {
                    fin: true,
                    opcode: BINARY
                },
                &b"hello"[..]
            )
        );
        let big = vec![7u8; MAX_PAYLOAD];
        let (r, p) = one(masked(0x02, &big)).await;
        assert_eq!(
            (r.unwrap(), p.len()),
            (
                Read::Frame {
                    fin: false,
                    opcode: BINARY
                },
                MAX_PAYLOAD
            )
        );
        let (r, _) = one(masked(0x82, &vec![0u8; MAX_PAYLOAD + 1])).await;
        assert_eq!(r.unwrap(), Read::Refuse(TOO_BIG, "oversize"));
        let (r, _) = one(masked(0x81, b"hi")).await;
        assert_eq!(r.unwrap(), Read::Refuse(UNSUPPORTED, "text"));
        let (r, _) = one(vec![0x82, 0x01, 0x00]).await;
        assert_eq!(r.unwrap(), Read::Refuse(PROTOCOL_ERROR, "unmasked"));
        for bad in [
            masked(0xC2, b"x"),
            masked(0x83, b"x"),
            masked(0x09, b"x"),
            masked(0x89, &[0; 126]),
        ] {
            assert_eq!(
                one(bad).await.0.unwrap(),
                Read::Refuse(PROTOCOL_ERROR, "protocol")
            );
        }
        assert!(
            one(masked(0x82, b"hello")[..6].to_vec()).await.0.is_err(),
            "a short frame is an error"
        );
    }

    #[test]
    fn headers_and_close_replies() {
        assert_eq!(header(BINARY, 5).0[..2], [0x82, 5]);
        assert_eq!(header(BINARY, 16384).0[..4], [0x82, 126, 0x40, 0x00]);
        assert_eq!(header(BINARY, 65536).1, 10);
        assert_eq!(close_reply(&[]), None);
        assert_eq!(close_reply(&[3]), Some(PROTOCOL_ERROR));
        assert_eq!(close_reply(&[0x03, 0xE9, b'x']), Some(1001));
        assert_eq!(
            close_reply(&[0x03, 0xED]),
            Some(PROTOCOL_ERROR),
            "1005 is never sent"
        );
    }
}
