// SPDX-License-Identifier: Apache-2.0
//
// moonray_bridge: TCP server that lets Blender render with MoonRay.
//
// Usage: moonray_bridge [--host 127.0.0.1] [--port 5577] [--threads N]
//
// The main process only accepts connections; each client is served in a child
// process with its own RenderContext (MoonRay has global state, so isolating
// sessions in processes is the most robust option).
#include "Net.h"
#include "Session.h"

#include <signal.h>
#include <unistd.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

int
main(int argc, char* argv[])
{
    std::string host = "127.0.0.1";
    int port = 5577;
    unsigned hw = std::thread::hardware_concurrency();
    unsigned threads = hw > 1 ? hw - 1 : 1;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        const bool hasValue = i + 1 < argc;
        if (arg == "--host" && hasValue) host = argv[++i];
        else if (arg == "--port" && hasValue) port = std::atoi(argv[++i]);
        else if (arg == "--threads" && hasValue) threads = static_cast<unsigned>(std::atoi(argv[++i]));
        else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: moonray_bridge [--host 127.0.0.1] [--port 5577] [--threads N]\n";
            return 0;
        } else {
            std::cerr << "Unknown argument: " << arg << "\n";
            return 1;
        }
    }

    if (!std::getenv("RDL2_DSO_PATH")) {
        std::cerr << "Warning: RDL2_DSO_PATH is not set. "
                     "Run 'source /opt/MoonRay/installs/openmoonray/scripts/setup.sh' first.\n";
    }

    // Children exit on their own; we don't want zombies.
    signal(SIGCHLD, SIG_IGN);
    signal(SIGPIPE, SIG_IGN);

    int listenFd;
    try {
        listenFd = mrbridge::net::listenTcp(host, port);
    } catch (const std::exception& e) {
        std::cerr << "Could not listen on " << host << ":" << port << ": " << e.what() << "\n";
        return 1;
    }
    std::cout << "moonray_bridge listening on " << host << ":" << port
              << " (" << threads << " threads per session)" << std::endl;

    for (;;) {
        int fd = mrbridge::net::acceptClient(listenFd);
        if (fd < 0) {
            std::cerr << "accept() failed: " << std::strerror(errno) << "\n";
            continue;
        }

        pid_t pid = fork();
        if (pid == 0) {
            ::close(listenFd);
            signal(SIGCHLD, SIG_DFL);
            std::cout << "[" << getpid() << "] new session" << std::endl;
            try {
                mrbridge::Session(fd, threads).run();
            } catch (const std::exception& e) {
                std::cerr << "[" << getpid() << "] session aborted: " << e.what() << std::endl;
            }
            ::close(fd);
            std::cout << "[" << getpid() << "] session ended" << std::endl;
            // _exit skips MoonRay's global destructors, which can hang
            _exit(0);
        }
        if (pid < 0) std::cerr << "fork() failed: " << std::strerror(errno) << "\n";
        ::close(fd);
    }
}
