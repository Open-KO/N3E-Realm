// RQ-018: front-end music (music.h). The decoder is minimp3 (CC0, pinned in
// UPSTREAM.md), Layer III only, float output in [-1, 1].
#include "assets/music.h"
#define MINIMP3_IMPLEMENTATION
#define MINIMP3_ONLY_MP3
#define MINIMP3_FLOAT_OUTPUT
#include "third_party/minimp3/minimp3.h"
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

MusicStream::MusicStream(std::shared_ptr<const MusicTrack> track)
    : source(std::move(track)), decoder(std::make_unique<Decoder>()), pcm(MINIMP3_MAX_SAMPLES_PER_FRAME) {
  need(source != nullptr && source->rate > 0, "music stream without a track");
  mp3dec_init(&decoder->dec);
  step = double(source->rate) / kRate;
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

unsigned MusicStream::mix(float *out, unsigned frames, float gain) {
  if (done) return 0;
  if (!primed) {
    primed = true;
    if (!next(b[0], b[1])) {
      done = true;
      return 0;
    }
  }
  // Linear interpolation from the track's rate (as ko_audio.pcm resamples
  // effect sounds at cook time). At the end of a track that does not loop
  // the last sample is held for its own interval, then the stream ends.
  unsigned i = 0;
  for (; i < frames; ++i) {
    while (phase >= 1) {
      if (ending) {
        done = true;
        return i;
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
    out[i * 2] += gain * (a[0] + (b[0] - a[0]) * t);
    out[i * 2 + 1] += gain * (a[1] + (b[1] - a[1]) * t);
    phase += step;
  }
  return i;
}
}  // namespace n3e
