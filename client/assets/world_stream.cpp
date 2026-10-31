#include "assets/world_stream.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace n3e {
float box_distance(const V &lo, const V &hi, const V &p) {
  double s = 0;
  for (int a = 0; a < 3; ++a) {
    double d = std::max({double(lo[a]) - p[a], 0.0, double(p[a]) - hi[a]});
    s += d * d;
  }
  return float(std::sqrt(s));
}

float view_reach(float far, float aspect, float fov) {
  const double t = std::tan(double(fov) / 2), tx = double(aspect) * t;
  return float(double(far) * std::sqrt(1 + tx * tx + t * t));
}

WorldStream::WorldStream(WorldTable table, TerrainDetail terrain, std::vector<float> slot_map)
    : table_(std::move(table)), terrain_(terrain), slot_map_(std::move(slot_map)),
      file_(table_.path, std::ios::binary), state_(table_.entries.size(), 0) {
  for (const auto &e : table_.entries)
    if (e.bytes > STREAM_BYTES)
      throw std::runtime_error("world chunk " + std::to_string(e.x) + "," + std::to_string(e.z) +
                               ": larger than the stream byte limit");
  if (!file_) throw std::runtime_error("asset read");
  worker_ = std::thread([this] { run(); });
}

WorldStream::~WorldStream() {
  {
    std::lock_guard lock(mutex_);
    stop_ = true;
  }
  wake_.notify_all();
  worker_.join();
}

void WorldStream::run() {
  for (;;) {
    size_t index;
    {
      std::unique_lock lock(mutex_);
      wake_.wait(lock, [&] { return stop_ || !requests_.empty(); });
      if (stop_) return;
      index = requests_.front();
      requests_.pop_front();
    }
    Result result{index, {}, {}};
    try {
      result.chunk = load_world_chunk(file_, table_, terrain_, index);
      if (!slot_map_.empty())
        for (size_t i = 0; i < result.chunk.vertices.size(); i += WORLD_FLOATS)
          for (size_t j = 10; j < 12; ++j) {
            // D-203: a single-layer unlit vertex keeps its marker.
            if (j == 11 && result.chunk.vertices[i + j] == WORLD_UNLIT_VERTEX) continue;
            auto slot = size_t(result.chunk.vertices[i + j]);
            if (slot >= slot_map_.size()) throw std::runtime_error("world native texture slot");
            result.chunk.vertices[i + j] = slot_map_[slot];
          }
      // D-212: a texture sequence's frames name world textures too.
      if (!slot_map_.empty())
        for (auto &part : result.chunk.parts)
          if (part.sequence)
            for (auto &slot : part.sequence->slots) {
              if (size_t(slot) >= slot_map_.size()) throw std::runtime_error("world native texture slot");
              slot = slot_map_[size_t(slot)];
            }
    } catch (const std::exception &e) {
      result.error = e.what();
      result.chunk = {};
    }
    std::lock_guard lock(mutex_);
    results_.push_back(std::move(result));
  }
}

WorldStream::Step WorldStream::update(const V &eye, float reach) {
  Step step;
  const auto &entries = table_.entries;
  const size_t n = entries.size();
  const float load = reach + STREAM_MARGIN, hold = reach + STREAM_HYSTERESIS;
  std::vector<float> distance(n);
  std::vector<size_t> order;
  for (size_t i = 0; i < n; ++i) {
    distance[i] = box_distance(entries[i].lo, entries[i].hi, eye);
    if (distance[i] <= hold) order.push_back(i);
  }
  std::sort(order.begin(), order.end(), [&](size_t a, size_t b) {
    return distance[a] != distance[b] ? distance[a] < distance[b] : a < b;
  });
  // The chunks to hold: the nearest within reach + hysteresis, up to the first
  // that does not fit the limits (none farther is held). Without the limits
  // binding, that is every chunk in reach; the nearest always fits.
  std::vector<uint8_t> keep(n, 0);
  size_t count = 0, wanted = 0, limited = 0;
  uint64_t bytes = 0;
  bool full = false;
  for (size_t i : order) {
    const bool near = distance[i] <= load;
    wanted += near;
    if (!full && count < STREAM_CHUNKS && bytes + entries[i].bytes <= STREAM_BYTES) {
      keep[i] = 1; ++count; bytes += entries[i].bytes;
    } else {
      full = true;
      limited += near;
    }
  }
  // Counted against the limits: resident and in flight.
  size_t counted = 0; uint64_t counted_bytes = 0; size_t flying = 0;
  for (size_t i = 0; i < n; ++i) {
    if (state_[i] == 2 && !keep[i]) {
      state_[i] = 0;
      step.evict.push_back(i);
      ++stats_.evicted;
    }
    if (state_[i]) { ++counted; counted_bytes += entries[i].bytes; }
    flying += state_[i] == 1;
  }
  // Finished chunks, in request order. A chunk that failed validation stops
  // the client here, before anything of it is uploaded.
  std::deque<Result> finished;
  {
    std::lock_guard lock(mutex_);
    finished.swap(results_);
  }
  for (const auto &r : finished)
    if (!r.error.empty())
      throw std::runtime_error("world chunk " + std::to_string(entries[r.index].x) + "," +
                               std::to_string(entries[r.index].z) + ": " + r.error);
  for (auto &r : finished) ready_.push_back(std::move(r));
  uint64_t upload_bytes = 0;
  for (auto it = ready_.begin(); it != ready_.end();) {
    const size_t i = it->index;
    if (!keep[i]) {  // out of reach since it was asked for
      state_[i] = 0; --counted; counted_bytes -= entries[i].bytes; --flying;
      ++stats_.discarded;
      it = ready_.erase(it);
    } else if (step.upload.size() < STREAM_UPLOADS &&
               (step.upload.empty() || upload_bytes + entries[i].bytes <= STREAM_UPLOAD_BYTES)) {
      state_[i] = 2; --flying;
      upload_bytes += entries[i].bytes;
      step.upload.push_back({i, std::move(it->chunk)});
      ++stats_.uploaded;
      it = ready_.erase(it);
    } else {
      ++it;
    }
  }
  // New requests, nearest first, while the pipeline and the limits allow.
  bool asked = false;
  for (size_t i : order) {
    if (!keep[i] || distance[i] > load || state_[i]) continue;
    if (flying >= STREAM_IN_FLIGHT || counted + 1 > STREAM_CHUNKS ||
        counted_bytes + entries[i].bytes > STREAM_BYTES)
      break;
    state_[i] = 1; ++flying; ++counted; counted_bytes += entries[i].bytes;
    {
      std::lock_guard lock(mutex_);
      requests_.push_back(i);
    }
    asked = true;
  }
  if (asked) wake_.notify_one();
  size_t resident = 0; uint64_t resident_bytes = 0; bool missing = false;
  for (size_t i = 0; i < n; ++i) {
    if (state_[i] == 2) { ++resident; resident_bytes += entries[i].bytes; }
    if (keep[i] && distance[i] <= load && state_[i] != 2) missing = true;
  }
  settled_ = !missing && flying == 0 && ready_.empty();
  stats_.resident = resident; stats_.bytes = resident_bytes;
  stats_.in_flight = flying; stats_.wanted = wanted; stats_.limited = limited;
  stats_.max_resident = std::max(stats_.max_resident, counted);
  stats_.max_bytes = std::max(stats_.max_bytes, counted_bytes);
  return step;
}
}  // namespace n3e
