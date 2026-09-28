// SPDX-License-Identifier: Apache-2.0
//
// Binary protocol between the Blender add-on and moonray_bridge.
// Keep in sync with addon/moonray_blender/protocol.py
//
// Every message: Header (16 bytes, little endian) + `size` bytes of payload.
#pragma once

#include <cstdint>

namespace mrbridge {

constexpr uint32_t kMagic = 0x3142524D; // "MRB1"
constexpr uint32_t kProtocolVersion = 1;

enum class Msg : uint32_t {
    // client -> bridge
    Hello   = 1,  // "key=value\n" text: threads, fps, exec_mode
    Rdla    = 2,  // RDLA (Lua) text applied to the SceneContext
    Mesh    = 3,  // binary mesh (see Session::applyMesh)
    Start   = 4,  // end of update: (re)start rendering
    Stop    = 5,  // stop the current render
    Clear   = 6,  // name of a Layer/GeometrySet/LightSet to empty
    Ack     = 7,  // the client consumed the last Frame
    Bye     = 9,

    // bridge -> client
    Welcome  = 100, // version text
    Frame    = 101, // FrameHeader + width*height*channels floats
    Log      = 102, // text
    Error    = 104, // text
    Complete = 105, // the frame reached final quality
};

#pragma pack(push, 1)
struct Header {
    uint32_t magic;
    uint32_t type;
    uint64_t size;
};

struct FrameHeader {
    uint32_t width;
    uint32_t height;
    uint32_t channels;  // always 4 (RGBA float32)
    uint32_t flags;     // bit0: frame complete
    float    progress;  // 0..1
    uint32_t reserved;
};
#pragma pack(pop)

static_assert(sizeof(Header) == 16, "Header must be 16 bytes");
static_assert(sizeof(FrameHeader) == 24, "FrameHeader must be 24 bytes");

} // namespace mrbridge
