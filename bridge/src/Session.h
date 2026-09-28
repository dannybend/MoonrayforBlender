// SPDX-License-Identifier: Apache-2.0
//
// A session = one Blender connection (viewport or final render) with its own
// MoonRay RenderContext. Each session runs in an isolated child process.
#pragma once

#include "Protocol.h"

#include <moonray/rendering/rndr/RenderContext.h>
#include <moonray/rendering/rndr/RenderOptions.h>
#include <scene_rdl2/common/fb_util/FbTypes.h>

#include <memory>
#include <string>

namespace mrbridge {

class Session
{
public:
    Session(int fd, unsigned defaultThreads);
    void run();

private:
    bool handle(const Header& header, const std::string& payload);

    void hello(const std::string& payload);
    void applyRdla(const std::string& payload);
    void applyMesh(const std::string& payload);
    void applyClear(const std::string& payload);
    void startRender();
    void stopRender();

    void pollFrame();
    void sendFrame(bool complete);

    void log(const std::string& text);
    void error(const std::string& text);

    int mFd;
    unsigned mThreads;
    float mFps = 20.0f;

    moonray::rndr::RenderOptions mOptions;
    std::unique_ptr<moonray::rndr::RenderContext> mContext;
    scene_rdl2::fb_util::RenderBuffer mBuffer;

    bool mAwaitingAck = false;      // flow control: at most one frame in flight
    bool mCompleteSent = false;
    unsigned mLastFilmActivity = ~0u;
    double mLastSendTime = 0.0;
};

} // namespace mrbridge
