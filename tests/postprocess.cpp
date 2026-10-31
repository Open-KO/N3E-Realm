// PQ-316 (D-185): the screen post-process's CPU side. The rules are the 2233
// client's CN3PostProcess (a 2233/2145 addition), read with their addresses in
// docs/implementation/evidence/pq-316-hdr-bloom-post-process-2233.md: the
// blur weights (004759f0), the adaptation step (00476690), the composite's
// tone map (2145 pp.fx P6, set up by 00474b50), n3e's floor on the average and
// maximum (the D-185 correction), the N3PF reader and the Option.ini key.
//
//   n3e-postprocess-check            the checks below
//   n3e-postprocess-check FILE...    read each postprocess.bin as the client
//                                    does; exit 1 at the first refusal
#define N3E_POSTPROCESS_NO_GL
#include "render/postprocess.h"
#include "render/options.h"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unistd.h>

namespace {
void need(bool value, const char *what) {
  if (!value) throw std::runtime_error(std::string("postprocess check: ") + what);
}
bool near(double a, double b, double e = 1e-5) { return std::abs(a - b) <= e; }

void weights() {
  // 004759f0 with 2233's variance 1.0 (+0x80, 00477bd0) and its default scale
  // 1.5 (+0x8c, 00b91a54): exp(-x^2 / 2) over -4..4, normalised, times 1.5.
  auto w = n3e::post::blur_weights(1, 1.5f);
  double sum = 0, raw = 0;
  for (int i = -4; i <= 4; ++i) raw += std::exp(-i * i / 2.0);
  for (int i = 0; i < 9; ++i) {
    sum += w[i];
    need(near(w[i], std::exp(-(i - 4) * (i - 4) / 2.0) / raw * 1.5), "weight value");
    need(near(w[i], w[8 - i]), "symmetric weights");
  }
  need(near(sum, 1.5), "weights sum to the scale");
  need(near(w[4], 0.398943 / 0.999932 * 1.5, 1e-4), "centre weight");
  // A wider variance spreads the same total.
  auto wide = n3e::post::blur_weights(4, 1.5f);
  need(wide[4] < w[4] && wide[0] > w[0], "variance widens the blur");
  double wide_sum = 0;
  for (auto x : wide) wide_sum += x;
  need(near(wide_sum, 1.5), "wide weights sum to the scale");
  std::cout << "PASS blur weights: 004759f0's nine taps exp(-i^2 / 2v), normalised to 1, times the bloom scale\n";
}

void adaptation() {
  using n3e::post::adapt;
  // 00476690: the gap closes by the step while it is at least the step...
  need(near(adapt(.2f, .8f, .1f), .3f), "step up");
  need(near(adapt(.8f, .2f, .1f), .7f), "step down");
  need(near(adapt(.5f, .5f, .1f), .5f), "already there");
  // ...and snaps when it is smaller (including a gap equal to the step).
  need(near(adapt(.75f, .8f, .1f), .8f), "snap up");
  need(near(adapt(.85f, .8f, .1f), .8f), "snap down");
  need(near(adapt(.7f, .8f, .1f), .8f, 1e-6) || near(adapt(.7f, .8f, .1f), .8f), "a gap of the step");
  // A zero step (rate 0 or no time) holds the value except at the target.
  need(near(adapt(.2f, .8f, 0), .2f), "zero step holds");
  // 0.3 per second for 60 frames of 1/60 s moves 0.3.
  float a = 0;
  for (int i = 0; i < 60; ++i) a = adapt(a, 1, .3f / 60);
  need(near(a, .3f, 1e-4), "0.3 per second");
  std::cout << "PASS adaptation: 00476690 steps by rate x dt toward the measured value and snaps inside a step\n";
}

void tone_map() {
  using n3e::post::tone_map;
  // 2233's no-row defaults (00476f50): exposure 1.2, lift 0, bloom scale 1.5,
  // saturation 1.2.
  n3e::PostProcess s;
  s.threshold = 0;
  s.bloom = 1.5f;
  s.exposure = 1.2f;
  s.saturation = 1.2f;
  s.lift = 0;
  // A grey at the average: Lm = 1.2, W = 1 x 2.5, k = 1.2 (1 + 1.2 / 6.25) / 2.2.
  auto t = tone_map({.5f, .5f, .5f}, .5f, 1, s);
  double k = 1.2 * (1 + 1.2 / 6.25) / 2.2;
  for (auto x : t) need(near(x, .5 * k), "grey composite");
  // Saturation scales the difference from the result's luminance.
  auto c = tone_map({.8f, .2f, .2f}, .5f, 1, s);
  double l = .299 * .8 + .587 * .2 + .114 * .2, lm = l / .5 * 1.2, kk = lm * (1 + lm / 6.25) / (1 + lm);
  double g = l * kk;
  need(near(c[0], 1.2 * (.8 * kk - g) + g) && near(c[1], 1.2 * (.2 * kk - g) + g), "saturation");
  // The lift adds to k: a black pixel stays black, any colour gains c x lift.
  s.lift = .65f;
  auto lifted = tone_map({.2f, .2f, .2f}, .5f, 1, s), black = tone_map({0, 0, 0}, .5f, 1, s);
  need(near(black[0], 0) && lifted[0] > .2 * .65, "lift");
  // D-185: the floor the drawn composite and this reference share.
  auto f0 = n3e::post::floored(0, 0), f1 = n3e::post::floored(.5f, .7f);
  need(f0[0] == n3e::post::FLOOR && f0[1] == n3e::post::FLOOR && f1[0] == .5f && f1[1] == .7f, "floored");
  // D-185: an average or maximum of 0 (2233 would divide by zero) tone-maps
  // as the smallest read-back, 1/255, and stays finite.
  auto zero = tone_map({.3f, .3f, .3f}, 0, 0, s), floor = tone_map({.3f, .3f, .3f}, 1.f / 255, 1.f / 255, s);
  for (int i = 0; i < 3; ++i) need(std::isfinite(zero[i]) && near(zero[i], floor[i]), "floor at 1/255");
  std::cout << "PASS tone map: pp.fx P6's extended Reinhard with white point max x (1 + scale), exposure, lift, saturation; average and maximum floored at 1/255\n";
}

void options() {
  auto file = std::filesystem::temp_directory_path() / ("n3e-hdr-options-" + std::to_string(::getpid()) + ".ini");
  auto write = [&](const std::string &text) { std::ofstream(file) << text; };
  need(!ClientOptions::load(file.string() + ".missing").hdr, "HDR defaults off");
  write("[Addition2233]\nHDR=1\n");
  need(ClientOptions::load(file).hdr && ClientOptions::load(file).equipment_glow, "HDR=1 turns it on alone");
  write("[addition2233]\n hdr = 2 ; on\n");
  need(ClientOptions::load(file).hdr, "case-blind name, any non-zero integer");
  write("[Addition2233]\nHDR=on\n");
  need(!ClientOptions::load(file).hdr, "no leading integer: 0");
  write("[Addition2233]\nEquipmentGlow=0\n");
  need(!ClientOptions::load(file).hdr, "another key leaves it off");
  std::filesystem::remove(file);
  std::cout << "PASS client options: Addition2233.HDR defaults off and turns on only by its own key\n";
}

void reader() {
  auto dir = std::filesystem::temp_directory_path() / ("n3e-postprocess-" + std::to_string(::getpid()));
  std::filesystem::create_directories(dir);
  auto file = [&](const std::string &magic, std::vector<float> v, const std::string &tail = "") {
    auto path = dir / "postprocess.bin";
    std::ofstream out(path, std::ios::binary);
    out << magic;
    for (float x : v) out.write(reinterpret_cast<const char *>(&x), 4);
    out << tail;
    return path;
  };
  std::vector<float> moradon{.367f, .7f, .1f, 1.f, .65f, .3f, 1.f};
  auto pp = n3e::load_postprocess(file("N3PF", moradon));
  need(near(pp.threshold, .367f) && near(pp.bloom, .7f) && near(pp.exposure, .1f) && near(pp.saturation, 1) &&
           near(pp.lift, .65f) && near(pp.adapt_rate, .3f) && near(pp.blur_variance, 1),
       "field order");
  auto refused = [&](const std::filesystem::path &path) {
    try {
      n3e::load_postprocess(path);
    } catch (const std::exception &) {
      return true;
    }
    return false;
  };
  need(refused(file("N3PG", moradon)), "magic");
  need(refused(file("N3PF", {moradon.begin(), moradon.end() - 1})), "truncated");
  need(refused(file("N3PF", moradon, std::string(1, '\0'))), "trailing byte");
  const std::vector<float> high{1.01f, 4.01f, 16.01f, 4.01f, 4.01f, 100.01f, 16.01f};
  for (size_t i = 0; i < moradon.size(); ++i) {
    auto v = moradon;
    v[i] = high[i];
    need(refused(file("N3PF", v)), "above a bound");
    v[i] = -.01f;
    need(refused(file("N3PF", v)), "below zero");
    v[i] = std::nanf("");
    need(refused(file("N3PF", v)), "NaN");
  }
  auto v = moradon;
  v[6] = 0;
  need(refused(file("N3PF", v)), "zero blur variance");
  std::filesystem::remove_all(dir);
  std::cout << "PASS N3PF reader: field order, magic, size, trailing bytes, every bound and NaN refused\n";
}
}  // namespace

int main(int argc, char **argv) {
  try {
    if (argc > 1) {
      for (int i = 1; i < argc; ++i) {
        auto pp = n3e::load_postprocess(argv[i]);
        std::cout << "PASS postprocess " << argv[i] << " threshold=" << pp.threshold << " bloom=" << pp.bloom
                  << " exposure=" << pp.exposure << " saturation=" << pp.saturation << " lift=" << pp.lift
                  << " adapt_rate=" << pp.adapt_rate << " blur_variance=" << pp.blur_variance << "\n";
      }
      return 0;
    }
    weights();
    adaptation();
    tone_map();
    options();
    reader();
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
