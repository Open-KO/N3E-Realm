#pragma once
// RQ-018 (Q57): a front-end music track and its bounded stream. A track is the
// MPEG audio Layer III frames front-end.bin carries (content/front-end.md
// section 9), checked frame by frame when the package loads; MusicStream
// decodes it one frame at a time (client/third_party/minimp3) and resamples it
// to the mixer's 48 kHz stereo, so a track minutes long never becomes PCM in
// memory: the stream holds one decoded frame (at most 1152 samples a channel).
// No file access, threads or device calls.
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace n3e {
inline constexpr size_t kMusicTrackBytes = 16 * 1024 * 1024;
inline constexpr uint32_t kMusicTracks = 4;
struct MusicTrack {
  uint32_t rate = 0;      // the frames' sample rate (Hz)
  uint32_t channels = 0;  // 1 (mono) or 2
  bool loop = false;      // starts again at its first frame when it ends
  uint32_t frames = 0;    // MPEG frames in `data`
  std::string data;       // the frames, back to back
};
// One MPEG-1 or MPEG-2 Layer III frame header (free format, MPEG 2.5 and the
// reserved values refused): its length in bytes (padding included), sample
// rate and channel count, or nothing.
struct MpegFrame { uint32_t bytes = 0, rate = 0, channels = 0; bool mpeg1 = false; };
std::optional<MpegFrame> mpeg_frame(const unsigned char *p, size_t available);
// Throws std::runtime_error unless `data` is exactly `frames` whole Layer III
// frames, every one at the track's rate and channel count.
void check_music_track(const MusicTrack &track);

class MusicStream {
 public:
  static constexpr unsigned kRate = 48000;
  explicit MusicStream(std::shared_ptr<const MusicTrack> track);
  ~MusicStream();
  MusicStream(const MusicStream &) = delete;
  MusicStream &operator=(const MusicStream &) = delete;
  // Adds up to `frames` 48 kHz stereo frames, times `gain`, to `out`
  // (interleaved left, right); returns the frames written, fewer only when a
  // track that does not loop has ended.
  unsigned mix(float *out, unsigned frames, float gain);
  bool ended() const { return done; }
  const std::shared_ptr<const MusicTrack> &track() const { return source; }
  uint64_t decoded_frames() const { return decoded; }  // MPEG frames, loops included

 private:
  struct Decoder;
  bool next(float &left, float &right);  // the next source sample pair
  bool decode();                          // the next MPEG frame into pcm
  std::shared_ptr<const MusicTrack> source;
  std::unique_ptr<Decoder> decoder;
  std::vector<float> pcm;  // the current frame, interleaved by its channels
  size_t offset = 0, cursor = 0, available = 0;
  unsigned channels = 2;
  double phase = 1, step = 1;
  float a[2]{}, b[2]{};
  uint64_t decoded = 0, pass_samples = 0;
  bool done = false, primed = false, ending = false;
};
}  // namespace n3e
