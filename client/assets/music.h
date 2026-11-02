#pragma once
// RQ-018 (Q57): a front-end music track and its bounded stream. A track is the
// MPEG audio Layer III frames front-end.bin carries (content/front-end.md
// section 9), checked frame by frame when the package loads; MusicStream
// decodes it one frame at a time (client/third_party/minimp3) and resamples it
// to the mixer's 48 kHz stereo, so a track minutes long never becomes PCM in
// memory: the stream holds one decoded frame (at most 1152 samples a channel).
// RQ-083 (N3FE version 5): a track can instead be 16-bit PCM (KO 1097's WAV
// tracks), streamed 1152 sample frames at a time the same way, and can restart
// at its first sample every `restart` seconds of playback (KO 1097's login
// tick, 005248f5-00524957). RQ-096 (Q75): that clock is the track's for the
// process, as KO 1097's and 1264's login timer is (006e0344, 007ac9d0, which
// no Init resets): a stream can start at a saved phase, silent until the
// period, and reports its phase for the next one. That applies only when
// AudioMixer::carry_music_clock is on (off by default since RQ-105, Q75 (a):
// otherwise every stream starts at phase 0). No file access, threads or
// device calls.
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace n3e {
inline constexpr size_t kMusicTrackBytes = 16 * 1024 * 1024;
inline constexpr uint32_t kMusicTracks = 4;
// A PCM track's sample rate bounds (Hz), as tools/assetc/ko_audio.py's WAVs.
inline constexpr uint32_t kMusicPcmMinRate = 8000, kMusicPcmMaxRate = 96000;
// A restart period's bounds (seconds); 0 is none.
inline constexpr float kMusicMinRestart = 0.1f, kMusicMaxRestart = 3600;
struct MusicTrack {
  enum class Kind : uint32_t { mpeg = 0, pcm = 1 };
  Kind kind = Kind::mpeg;
  uint32_t rate = 0;      // the sample rate (Hz)
  uint32_t channels = 0;  // 1 (mono) or 2
  bool loop = false;      // starts again at its first frame when it ends
  // Seconds of playback after which the track starts again at its first
  // sample, ended or not (0: never). Takes precedence over `loop`.
  float restart = 0;
  uint32_t frames = 0;    // MPEG frames, or PCM sample frames, in `data`
  std::string data;       // the MPEG frames back to back, or s16le samples interleaved
};
// One MPEG-1 or MPEG-2 Layer III frame header (free format, MPEG 2.5 and the
// reserved values refused): its length in bytes (padding included), sample
// rate and channel count, or nothing.
struct MpegFrame { uint32_t bytes = 0, rate = 0, channels = 0; bool mpeg1 = false; };
std::optional<MpegFrame> mpeg_frame(const unsigned char *p, size_t available);
// Throws std::runtime_error unless the restart period is 0 or within its
// bounds and, for an MPEG track, `data` is exactly `frames` whole Layer III
// frames, every one at the track's rate and channel count; for a PCM track,
// exactly `frames` 16-bit sample frames of `channels` at a rate within bounds.
void check_music_track(const MusicTrack &track);

class MusicStream {
 public:
  static constexpr unsigned kRate = 48000;
  // `phase`: 48 kHz frames of a restarting track's period already counted
  // (0: start at the first sample now). A stream that starts part way is
  // silent until its period and then starts at its first sample; a track
  // without a restart period ignores it.
  explicit MusicStream(std::shared_ptr<const MusicTrack> track, uint64_t phase = 0);
  ~MusicStream();
  MusicStream(const MusicStream &) = delete;
  MusicStream &operator=(const MusicStream &) = delete;
  // Adds up to `frames` 48 kHz stereo frames, times `gain`, to `out`
  // (interleaved left, right); returns the frames written, fewer only when a
  // track that neither loops nor restarts has ended. A restarting track that
  // has ended is silent until its restart.
  unsigned mix(float *out, unsigned frames, float gain);
  bool ended() const { return done && restart_frames == 0; }
  const std::shared_ptr<const MusicTrack> &track() const { return source; }
  // Source frames decoded (MPEG frames, or PCM sample frames), loops and
  // restarts included.
  uint64_t decoded_frames() const { return decoded; }
  uint64_t restarts() const { return restarted; }
  // A restarting track's frames into its period (0 for any other track).
  bool restarting() const { return restart_frames != 0; }
  uint64_t period_phase() const { return restart_frames ? played : 0; }

 private:
  struct Decoder;
  bool output(float &left, float &right); // the next 48 kHz frame of this pass
  bool next(float &left, float &right);  // the next source sample pair
  bool decode();                          // the next MPEG frame (or PCM run) into pcm
  void rewind();                          // back to the first sample
  std::shared_ptr<const MusicTrack> source;
  std::unique_ptr<Decoder> decoder;
  std::vector<float> pcm;  // the current frame, interleaved by its channels
  size_t offset = 0, cursor = 0, available = 0;
  unsigned channels = 2;
  double phase = 1, step = 1;
  float a[2]{}, b[2]{};
  uint64_t decoded = 0, pass_samples = 0, restarted = 0;
  uint64_t restart_frames = 0, played = 0;  // 48 kHz frames; 0: no restart
  bool done = false, primed = false, ending = false;
};
}  // namespace n3e
