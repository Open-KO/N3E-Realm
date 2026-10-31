#pragma once
// N3W2 chunk streaming (PQ-232, D-159). Engine behaviour, not KO's: KO loads a
// zone whole and bounds per-frame work instead (terrain window 0059b6f0 /
// 0059b890, object cells 005b5680; KnightOnLine.exe).
//
// One worker thread reads and validates chunk bodies; the render thread asks
// for chunks by distance, takes a bounded number of finished ones per frame
// and evicts chunks beyond reach plus hysteresis. Which chunks are wanted, kept
// and evicted depends only on the chunk table, the camera and these limits;
// only when a requested chunk arrives depends on the worker. No GL here: the
// caller uploads and frees.
#include "assets/assets.h"
#include <condition_variable>
#include <deque>
#include <fstream>
#include <mutex>
#include <thread>

namespace n3e {
// Fixed client limits. Resident counts chunks uploaded or in flight, and bytes
// are their chunk-body bytes (which bound the vertex and index bytes uploaded).
inline constexpr size_t STREAM_CHUNKS = 1024;
inline constexpr uint64_t STREAM_BYTES = uint64_t(256) << 20;
inline constexpr size_t STREAM_IN_FLIGHT = 8;                       // queued, loading or awaiting upload
inline constexpr size_t STREAM_UPLOADS = 4;                         // per frame
inline constexpr uint64_t STREAM_UPLOAD_BYTES = uint64_t(32) << 20; // per frame, at least one chunk
inline constexpr float STREAM_MARGIN = 64;                          // load within reach + this
inline constexpr float STREAM_HYSTERESIS = 128;                     // evict beyond reach + this

// Distance from a point to an axis-aligned box (0 inside).
float box_distance(const V &lo, const V &hi, const V &p);
// How far the view can reach from the eye: the far plane's corner distance,
// far * sqrt(1 + (aspect * tan(fov / 2))^2 + tan(fov / 2)^2).
float view_reach(float far, float aspect, float fov);

class WorldStream {
 public:
  struct Upload { size_t index; WorldChunk chunk; };
  struct Step {
    std::vector<size_t> evict;   // free these chunks' buffers
    std::vector<Upload> upload;  // upload these, then they are resident
  };
  struct Stats {
    size_t resident = 0, in_flight = 0, limited = 0, wanted = 0;
    uint64_t bytes = 0;
    size_t uploaded = 0, evicted = 0, discarded = 0;  // totals since start
    size_t max_resident = 0; uint64_t max_bytes = 0;
  };
  // slot_map: when non-empty, each vertex texture slot s is replaced by
  // slot_map[s] (the bank/layer slot of the world's N3WT texture s, PQ-233);
  // s must be in range.
  // Throws for a table entry larger than STREAM_BYTES: such a chunk could
  // never be held, so the package is refused as a bad one. With every entry
  // within the limits the nearest chunk to the eye is always held.
  WorldStream(WorldTable table, TerrainDetail terrain, std::vector<float> slot_map = {});
  ~WorldStream();  // stops and joins the worker
  WorldStream(const WorldStream &) = delete;
  WorldStream &operator=(const WorldStream &) = delete;
  // One frame. reach: view_reach(...). Throws when a chunk fails validation:
  // the caller stops as for a bad package, and the chunk is never drawn.
  Step update(const V &eye, float reach);
  // Every chunk within reach + margin that the limits admit is resident and
  // nothing is in flight.
  bool settled() const { return settled_; }
  const Stats &stats() const { return stats_; }
  const WorldTable &table() const { return table_; }

 private:
  struct Result { size_t index; WorldChunk chunk; std::string error; };
  void run();
  WorldTable table_;
  TerrainDetail terrain_;
  std::vector<float> slot_map_;
  std::ifstream file_;  // the worker's; opened before it starts
  std::vector<uint8_t> state_;  // 0 absent, 1 in flight, 2 resident
  Stats stats_;
  bool settled_ = false;
  std::mutex mutex_;
  std::condition_variable wake_;
  std::deque<size_t> requests_;
  std::deque<Result> results_;
  std::deque<Result> ready_;  // render thread only: finished, awaiting upload
  bool stop_ = false;
  std::thread worker_;
};
}  // namespace n3e
