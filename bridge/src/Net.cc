// SPDX-License-Identifier: Apache-2.0

#include "Net.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <stdexcept>

namespace mrbridge {
namespace net {

namespace {
// Payload size limit (4 GB): avoids huge allocations if garbage arrives on
// the socket.
constexpr uint64_t kMaxPayload = 4ull << 30;
}

int
listenTcp(const std::string& host, int port)
{
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) throw std::runtime_error(std::string("socket(): ") + std::strerror(errno));

    int yes = 1;
    ::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) != 1) {
        ::close(fd);
        throw std::runtime_error("Invalid address: " + host);
    }
    if (::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(fd);
        throw std::runtime_error(std::string("bind(): ") + std::strerror(errno));
    }
    if (::listen(fd, 8) < 0) {
        ::close(fd);
        throw std::runtime_error(std::string("listen(): ") + std::strerror(errno));
    }
    return fd;
}

int
acceptClient(int listenFd)
{
    for (;;) {
        int fd = ::accept(listenFd, nullptr, nullptr);
        if (fd >= 0) {
            int yes = 1;
            ::setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
            return fd;
        }
        if (errno != EINTR) return -1;
    }
}

bool
waitReadable(int fd, int timeoutMs)
{
    pollfd p{fd, POLLIN, 0};
    int r = ::poll(&p, 1, timeoutMs);
    return r > 0 && (p.revents & (POLLIN | POLLHUP | POLLERR));
}

bool
readAll(int fd, void* data, size_t size)
{
    char* p = static_cast<char*>(data);
    while (size > 0) {
        ssize_t n = ::recv(fd, p, size, 0);
        if (n == 0) return false;
        if (n < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        p += n;
        size -= static_cast<size_t>(n);
    }
    return true;
}

bool
writeAll(int fd, const void* data, size_t size)
{
    const char* p = static_cast<const char*>(data);
    while (size > 0) {
        ssize_t n = ::send(fd, p, size, MSG_NOSIGNAL);
        if (n < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        p += n;
        size -= static_cast<size_t>(n);
    }
    return true;
}

bool
readMessage(int fd, Header& header, std::string& payload)
{
    if (!readAll(fd, &header, sizeof(header))) return false;
    if (header.magic != kMagic || header.size > kMaxPayload) return false;
    payload.resize(header.size);
    return header.size == 0 || readAll(fd, &payload[0], header.size);
}

bool
sendMessage2(int fd, Msg type, const void* a, size_t aSize, const void* b, size_t bSize)
{
    Header h{kMagic, static_cast<uint32_t>(type), aSize + bSize};
    return writeAll(fd, &h, sizeof(h)) &&
           (aSize == 0 || writeAll(fd, a, aSize)) &&
           (bSize == 0 || writeAll(fd, b, bSize));
}

bool
sendMessage(int fd, Msg type, const void* data, size_t size)
{
    return sendMessage2(fd, type, data, size, nullptr, 0);
}

bool
sendMessage(int fd, Msg type, const std::string& text)
{
    return sendMessage(fd, type, text.data(), text.size());
}

} // namespace net
} // namespace mrbridge
