#include "network/world.h"
#include <fstream>
#include <iomanip>
#include <iostream>
int main(int argc, char **argv) {
  try {
    if (argc != 2 && argc != 8 && argc != 9)
      return 1;
    std::ifstream in(argv[1]);
    size_t n;
    in >> n;
    if (n > 196608 || n % 3)  // the cooker's collision vertex cap
      return 1;
    std::vector<n3e::V> triangles(n);
    for (auto &v : triangles)
      for (auto &f : v)
        in >> f;
    n3e::V p;
    for (auto &f : p)
      in >> f;
    n3e::MovementConfig cfg;
    if (argc >= 8) {
      cfg = {std::stof(argv[2]), std::stof(argv[3]), std::stof(argv[4]),
             std::stof(argv[5]), std::stof(argv[6]), std::stof(argv[7])};
      if (!cfg.valid())
        return 1;
    }
    float multiplier = argc == 9 ? std::stof(argv[8]) : 1;
    n3e::Collision index(triangles);
    float x, z;
    std::cout << std::setprecision(9);
    while (in >> x >> z) {
      uint32_t mode = 0;
      if (argc >= 8 && !(in >> mode))
        return 1;
      // The 9-argument form exercises the gathered path as exploration packages did.
      p = argc >= 8 ? (argc == 9 ? n3e::advance(index, p, x, z, mode, cfg, multiplier) : n3e::advance(triangles, p, x, z, mode, cfg, multiplier))
                    : n3e::walk(triangles, p, x, z);
      std::cout << p[0] << " " << p[1] << " " << p[2] << "\n";
    }
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
