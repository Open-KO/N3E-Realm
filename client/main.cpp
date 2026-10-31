#include "assets/assets.h"
#include <iostream>
int viewer(const n3e::Release &, int, char **);
int self_test(const n3e::Release &, int, char **);
void handshake(const n3e::Release &, const std::string &, const std::string &);
int main(int argc, char **argv) {
  try {
    if (argc < 2)
      throw std::runtime_error(
#if N3E_HARNESS
          "n3e-test-client PACKAGE [--smoke | --connect HOST:PORT --ca CA.pem [--auto-login] [replay]] "
          "[--fixed-window WIDTHxHEIGHT] [--capture FILE.ppm] | PACKAGE --self-test --realm realm.json");
#else
          "n3e-client PACKAGE [--realm realm.json | --connect HOST:PORT] [--ca CA.pem] "
          "[--fixed-window WIDTHxHEIGHT [--fullscreen]] | PACKAGE --self-test --realm realm.json");
#endif
    auto release = n3e::load_release(argv[1]);
    std::cout << "release=" << release.hash << " game=" << release.game << "\n";
    if (argc >= 3 && std::string(argv[2]) == "--self-test")
      return self_test(release, argc, argv);
    if (argc == 6 && std::string(argv[2]) == "--connect" &&
        std::string(argv[4]) == "--ca") {
      return viewer(release, argc, argv);
    }
    return viewer(release, argc, argv);
  } catch (const std::exception &e) {
    std::cerr << "client: " << e.what() << "\n";
    return 1;
  }
}
