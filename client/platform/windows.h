#pragma once
// Force-included first into every client translation unit on Windows (CMakeLists.txt,
// MSVC /FI). OpenSSL's headers bring in <winsock2.h> and <windows.h> on their own, and
// those define `near`, `far` and `OPTIONAL` as macros, which the client uses as names
// (camera planes, attachment flags). So every Windows header the client needs is
// included here, before anything else, and those macros are then removed; FAR and NEAR
// stay defined (empty) for any SDK header included later.
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <shellapi.h>
#include <wincrypt.h>
#undef near
#undef far
#undef OPTIONAL
#undef FAR
#undef NEAR
#define FAR
#define NEAR
#endif
