// RQ-018: front-end music (music.h). The decoder is minimp3 (CC0, pinned in
// UPSTREAM.md), Layer III only, float output in [-1, 1].
#include "assets/music.h"
#define MINIMP3_IMPLEMENTATION
#define MINIMP3_ONLY_MP3
#define MINIMP3_FLOAT_OUTPUT
#include "third_party/minimp3/minimp3.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace n3e {
namespace {
void need(bool ok, const char *what) {
  if (!ok) throw std::runtime_error(what);
}
}  // namespace

std::optional<MpegFrame> mpeg_frame(const unsigned char *p, size_t available) {
  // ISO/IEC 11172-3 and 13818-3 Layer III bitrates (kbit/s) and rates (Hz).
  static constexpr uint32_t mpeg1_kbps[15] = {0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320};
  static constexpr uint32_t mpeg2_kbps[15] = {0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160};
  static constexpr uint32_t mpeg1_hz[3] = {44100, 48000, 32000};
  if (available < 4 || p[0] != 0xff || (p[1] & 0xe0) != 0xe0) return std::nullopt;
  const unsigned version = (p[1] >> 3) & 3, layer = (p[1] >> 1) & 3, bitrate = p[2] >> 4,
                 rate = (p[2] >> 2) & 3, padding = (p[2] >> 1) & 1;
  // version 3 MPEG-1, 2 MPEG-2; layer 1 is Layer III.
  if ((version != 3 && version != 2) || layer != 1 || bitrate == 0 || bitrate == 15 || rate == 3)
    return std::nullopt;
  MpegFrame f;
  f.mpeg1 = version == 3;
  f.rate = f.mpeg1 ? mpeg1_hz[rate] : mpeg1_hz[rate] / 2;
  f.channels = (p[3] >> 6) == 3 ? 1 : 2;
  const uint32_t kbps = f.mpeg1 ? mpeg1_kbps[bitrate] : mpeg2_kbps[bitrate];
  f.bytes = (f.mpeg1 ? 144000 : 72000) * kbps / f.rate + padding;
  if (f.bytes > available) return std::nullopt;
  return f;
}

void check_music_track(const MusicTrack &track) {
  need(track.channels == 1 || track.channels == 2, "music channels");
  need(!track.data.empty() && track.data.size() <= kMusicTrackBytes, "music track bytes");
  need(track.restart == 0 || (track.restart >= kMusicMinRestart && track.restart <= kMusicMaxRestart),
       "music restart");
  if (track.kind == MusicTrack::Kind::pcm) {
    // RQ-083: 16-bit sample frames, nothing else.
    need(track.rate >= kMusicPcmMinRate && track.rate <= kMusicPcmMaxRate, "music pcm rate");
    need(track.frames > 0 && uint64_t(track.frames) * track.channels * 2 == track.data.size(), "music pcm frames");
    return;
  }
  need(track.kind == MusicTrack::Kind::mpeg, "music kind");
  const auto *p = reinterpret_cast<const unsigned char *>(track.data.data());
  size_t at = 0;
  uint32_t frames = 0;
  std::optional<bool> mpeg1;
  while (at < track.data.size()) {
    const auto f = mpeg_frame(p + at, track.data.size() - at);
    need(f.has_value(), "music frame");
    need(f->rate == track.rate && f->channels == track.channels && (!mpeg1 || *mpeg1 == f->mpeg1),
         "music frame format");
    mpeg1 = f->mpeg1;
    at += f->bytes;
    ++frames;
  }
  need(frames == track.frames, "music frame count");
}

struct MusicStream::Decoder { mp3dec_t dec; };

MusicStream::MusicStream(std::shared_ptr<const MusicTrack> track, uint64_t phase)
    : source(std::move(track)), decoder(std::make_unique<Decoder>()), pcm(MINIMP3_MAX_SAMPLES_PER_FRAME) {
  need(source != nullptr && source->rate > 0, "music stream without a track");
  mp3dec_init(&decoder->dec);
  step = double(source->rate) / kRate;
  if (source->restart > 0) restart_frames = std::max<uint64_t>(1, uint64_t(std::llround(double(source->restart) * kRate)));
  // RQ-096 (Q75): part way into the period, KO's login tick has not played
  // the new stream yet (it plays only when its timer is 0): silent until the
  // period, then mix() rewinds to the first sample.
  if (restart_frames && phase > 0) {
    played = std::min(phase, restart_frames);
    done = true;
  }
}
MusicStream::~MusicStream() = default;

bool MusicStream::decode() {
  const auto &data = source->data;
  const auto *p = reinterpret_cast<const unsigned char *>(data.data());
  // Each round consumes one frame; a whole pass without a sample ends the
  // stream, so a track that decodes to nothing cannot spin.
  for (;;) {
    if (offset >= data.size()) {
      if (!source->loop || pass_samples == 0) return false;
      offset = 0;
      pass_samples = 0;
      mp3dec_init(&decoder->dec);
    }
    if (source->kind == MusicTrack::Kind::pcm) {
      // RQ-083: up to 1152 sample frames (one MPEG-1 frame's worth) at a time,
      // as floats in [-1, 1); check_music_track made the data whole frames.
      channels = source->channels;
      const size_t width = size_t(channels) * 2;
      const size_t n = std::min<size_t>(1152, (data.size() - offset) / width);
      for (size_t i = 0; i < n * channels; ++i) {
        const auto *s = p + offset + i * 2;
        pcm[i] = float(int16_t(uint16_t(s[0] | (s[1] << 8)))) / 32768.f;
      }
      offset += n * width;
      decoded += n;
      available = n;
      cursor = 0;
      pass_samples += n;
      return true;
    }
    const auto frame = mpeg_frame(p + offset, data.size() - offset);
    if (!frame) return false;  // check_music_track ran at load
    mp3dec_frame_info_t info{};
    const int samples = mp3dec_decode_frame(&decoder->dec, p + offset, int(frame->bytes), pcm.data(), &info);
    offset += frame->bytes;
    ++decoded;
    if (samples > 0 && (info.channels == 1 || info.channels == 2)) {
      channels = unsigned(info.channels);
      available = size_t(samples);
      cursor = 0;
      pass_samples += uint64_t(samples);
      return true;
    }
  }
}

bool MusicStream::next(float &left, float &right) {
  while (cursor >= available)
    if (!decode()) return false;
  left = pcm[cursor * channels];
  right = channels == 2 ? pcm[cursor * channels + 1] : left;
  ++cursor;
  return true;
}

void MusicStream::rewind() {
  mp3dec_init(&decoder->dec);
  offset = cursor = available = 0;
  phase = 1;
  a[0] = a[1] = b[0] = b[1] = 0;
  pass_samples = played = 0;
  done = primed = ending = false;
  ++restarted;
}

bool MusicStream::output(float &left, float &right) {
  if (done) return false;
  if (!primed) {
    primed = true;
    if (!next(b[0], b[1])) {
      done = true;
      return false;
    }
  }
  // Linear interpolation from the track's rate (as ko_audio.pcm resamples
  // effect sounds at cook time). At the end of a track that does not loop
  // the last sample is held for its own interval, then the pass ends.
  while (phase >= 1) {
    if (ending) {
      done = true;
      return false;
    }
    a[0] = b[0];
    a[1] = b[1];
    if (!next(b[0], b[1])) {
      b[0] = a[0];
      b[1] = a[1];
      ending = true;
    }
    phase -= 1;
  }
  const auto t = float(phase);
  left = a[0] + (b[0] - a[0]) * t;
  right = a[1] + (b[1] - a[1]) * t;
  phase += step;
  return true;
}

unsigned MusicStream::mix(float *out, unsigned frames, float gain) {
  for (unsigned i = 0; i < frames; ++i) {
    // RQ-083: a restarting track starts again at its first sample once it
    // has played `restart` seconds, and is silent meanwhile if it ended.
    if (restart_frames && played >= restart_frames) rewind();
    float left, right;
    if (output(left, right)) {
      out[i * 2] += gain * left;
      out[i * 2 + 1] += gain * right;
    } else if (!restart_frames) {
      return i;
    }
    ++played;
  }
  return frames;
}
}  // namespace n3e
