// SPDX-License-Identifier: Apache-2.0
//
// Minimal TCP socket helpers (POSIX).
#pragma once

#include "Protocol.h"

#include <cstddef>
#include <string>

namespace mrbridge {
namespace net {

int listenTcp(const std::string& host, int port);
int acceptClient(int listenFd);

// Waits up to `timeoutMs` for incoming data. Returns true if there is some.
bool waitReadable(int fd, int timeoutMs);

bool readAll(int fd, void* data, size_t size);
bool writeAll(int fd, const void* data, size_t size);

// Reads a whole message. Returns false if the client closed the connection or
// the message is invalid.
bool readMessage(int fd, Header& header, std::string& payload);

bool sendMessage(int fd, Msg type, const void* data, size_t size);
bool sendMessage(int fd, Msg type, const std::string& text);

// Sends header + two payload blocks without copying them into one buffer.
bool sendMessage2(int fd, Msg type, const void* a, size_t aSize, const void* b, size_t bSize);

} // namespace net
} // namespace mrbridge
