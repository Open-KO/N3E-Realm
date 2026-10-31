#pragma once
// What the client trusts for the realm's TLS certificate: the --ca file when given
// (dev and test realms), else the system's roots — OpenSSL's default paths on
// Linux, the Windows ROOT certificate store on Windows (spec 04 "Build").
#ifdef _WIN32
// Before OpenSSL, whose headers undo wincrypt.h's X509_NAME and OCSP_* macros.
#include <windows.h>
#include <wincrypt.h>
#endif
#include <openssl/ssl.h>
#include <openssl/x509.h>
#include <string>
namespace n3e::tls {
// The number of Windows ROOT certificates added to `store`; 0 when none could be read.
inline int add_system_roots([[maybe_unused]] X509_STORE *store) {
  int added = 0;
#ifdef _WIN32
  HCERTSTORE roots = CertOpenSystemStoreW(0, L"ROOT");
  if (!roots)
    return 0;
  for (PCCERT_CONTEXT c = nullptr; (c = CertEnumCertificatesInStore(roots, c));) {
    const unsigned char *der = c->pbCertEncoded;
    if (X509 *x = d2i_X509(nullptr, &der, long(c->cbCertEncoded))) {
      added += X509_STORE_add_cert(store, x) == 1;
      X509_free(x);
    }
  }
  CertCloseStore(roots, 0);
#endif
  return added;
}
// Loads the trust for `ctx`; false when nothing could be loaded.
inline bool trust(SSL_CTX *ctx, const std::string &ca) {
  if (!ca.empty())
    return SSL_CTX_load_verify_locations(ctx, ca.c_str(), nullptr) == 1;
#ifdef _WIN32
  return add_system_roots(SSL_CTX_get_cert_store(ctx)) > 0;
#else
  return SSL_CTX_set_default_verify_paths(ctx) == 1;
#endif
}
} // namespace n3e::tls
