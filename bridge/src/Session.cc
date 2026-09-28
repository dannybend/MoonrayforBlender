// SPDX-License-Identifier: Apache-2.0

#include "Session.h"
#include "Net.h"

#include <scene_rdl2/scene/rdl2/AsciiReader.h>
#include <scene_rdl2/scene/rdl2/GeometrySet.h>
#include <scene_rdl2/scene/rdl2/Layer.h>
#include <scene_rdl2/scene/rdl2/LightSet.h>
#include <scene_rdl2/scene/rdl2/SceneContext.h>
#include <scene_rdl2/scene/rdl2/SceneObject.h>
#include <scene_rdl2/scene/rdl2/Types.h>

#include <chrono>
#include <cstring>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace rdl2 = scene_rdl2::rdl2;

namespace mrbridge {

namespace {

double
now()
{
    using namespace std::chrono;
    return duration<double>(steady_clock::now().time_since_epoch()).count();
}

static_assert(sizeof(rdl2::Vec3f) == 3 * sizeof(float), "Vec3f must be 3 contiguous floats");
static_assert(sizeof(rdl2::Vec2f) == 2 * sizeof(float), "Vec2f must be 2 contiguous floats");

// Sequential reader for a little endian binary payload.
class Reader
{
public:
    explicit Reader(const std::string& data) : mP(data.data()), mEnd(data.data() + data.size()) {}

    template <typename T>
    T get()
    {
        T v;
        take(&v, sizeof(T));
        return v;
    }

    std::string str()
    {
        uint32_t n = get<uint32_t>();
        std::string s(n, '\0');
        take(&s[0], n);
        return s;
    }

    template <typename T>
    void array(std::vector<T>& out, size_t count)
    {
        out.resize(count);
        if (count) take(out.data(), count * sizeof(T));
    }

private:
    void take(void* dst, size_t n)
    {
        if (static_cast<size_t>(mEnd - mP) < n) throw std::runtime_error("Truncated Mesh message");
        std::memcpy(dst, mP, n);
        mP += n;
    }

    const char* mP;
    const char* mEnd;
};

} // namespace

Session::Session(int fd, unsigned defaultThreads)
    : mFd(fd)
    , mThreads(defaultThreads)
{
}

void
Session::log(const std::string& text)
{
    std::cout << "[bridge] " << text << std::endl;
    net::sendMessage(mFd, Msg::Log, text);
}

void
Session::error(const std::string& text)
{
    std::cerr << "[bridge] ERROR: " << text << std::endl;
    net::sendMessage(mFd, Msg::Error, text);
}

void
Session::run()
{
    Header header;
    std::string payload;

    for (;;) {
        const bool rendering = mContext && mContext->isFrameRendering();

        // Drain every pending message before looking at the framebuffer, so a
        // batch of changes is applied in one go.
        if (net::waitReadable(mFd, rendering ? 5 : 100)) {
            if (!net::readMessage(mFd, header, payload)) break;
            try {
                if (!handle(header, payload)) break;
            } catch (const std::exception& e) {
                error(e.what());
            }
            continue;
        }

        if (rendering) {
            try {
                pollFrame();
            } catch (const std::exception& e) {
                error(e.what());
            }
        }
    }

    stopRender();
}

bool
Session::handle(const Header& header, const std::string& payload)
{
    switch (static_cast<Msg>(header.type)) {
    case Msg::Hello: hello(payload); break;
    case Msg::Rdla:  applyRdla(payload); break;
    case Msg::Mesh:  applyMesh(payload); break;
    case Msg::Clear: applyClear(payload); break;
    case Msg::Start: startRender(); break;
    case Msg::Stop:  stopRender(); break;
    case Msg::Ack:   mAwaitingAck = false; break;
    case Msg::Bye:   return false;
    default:
        error("Unknown message type: " + std::to_string(header.type));
    }
    return true;
}

void
Session::hello(const std::string& payload)
{
    if (mContext) {
        error("Hello received twice in the same session");
        return;
    }

    std::istringstream in(payload);
    std::string line;
    std::string execMode;
    while (std::getline(in, line)) {
        const auto eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = line.substr(0, eq);
        const std::string value = line.substr(eq + 1);
        if (key == "threads" && std::stoi(value) > 0) mThreads = static_cast<unsigned>(std::stoi(value));
        else if (key == "fps" && std::stof(value) > 0.0f) mFps = std::stof(value);
        else if (key == "exec_mode") execMode = value;
    }

    // scalar | vectorized | xpu | auto. XPU uses the GPU (CUDA/OptiX) and falls
    // back to CPU on its own if there is no GPU or the scene uses unsupported
    // features.
    if (!execMode.empty()) mOptions.setDesiredExecutionMode(execMode);
    mOptions.setThreads(mThreads);
    mOptions.setRenderMode(moonray::rndr::RenderMode::PROGRESSIVE);

    static std::once_flag once;
    std::call_once(once, [this]() { moonray::rndr::initGlobalDriver(mOptions); });

    mContext.reset(new moonray::rndr::RenderContext(mOptions));

    std::ostringstream msg;
    msg << "moonray_bridge protocol " << kProtocolVersion << ", " << mThreads << " threads"
        << ", mode " << (execMode.empty() ? "default" : execMode);
    net::sendMessage(mFd, Msg::Welcome, msg.str());
    log(msg.str());
}

void
Session::applyRdla(const std::string& payload)
{
    if (!mContext) throw std::runtime_error("Rdla before Hello");
    stopRender();
    rdl2::AsciiReader reader(mContext->getSceneContext());
    reader.fromString(payload, "@blender");
}

// Mesh payload layout (little endian):
//   str  name              (u32 length + bytes)
//   u32  flags             bit0: is_subd
//   u32  nverts, nfaces, nindices, nuvs, nnormals, nparts
//   f32  vertices[nverts*3]
//   i32  face_vertex_count[nfaces]
//   i32  vertices_by_index[nindices]
//   f32  uvs[nuvs*2]
//   f32  normals[nnormals*3]
//   str  part_names[nparts]
//   i32  part_face_count[nparts]
//   i32  part_face_indices[sum of part_face_count]
void
Session::applyMesh(const std::string& payload)
{
    if (!mContext) throw std::runtime_error("Mesh before Hello");
    stopRender();

    Reader r(payload);
    const std::string name = r.str();
    const uint32_t flags    = r.get<uint32_t>();
    const uint32_t nverts   = r.get<uint32_t>();
    const uint32_t nfaces   = r.get<uint32_t>();
    const uint32_t nindices = r.get<uint32_t>();
    const uint32_t nuvs     = r.get<uint32_t>();
    const uint32_t nnormals = r.get<uint32_t>();
    const uint32_t nparts   = r.get<uint32_t>();

    rdl2::Vec3fVector vertices;  r.array(vertices, nverts);
    rdl2::IntVector faceCounts;  r.array(faceCounts, nfaces);
    rdl2::IntVector indices;     r.array(indices, nindices);
    rdl2::Vec2fVector uvs;       r.array(uvs, nuvs);
    rdl2::Vec3fVector normals;   r.array(normals, nnormals);

    rdl2::StringVector partNames(nparts);
    for (auto& p : partNames) p = r.str();
    rdl2::IntVector partFaceCounts; r.array(partFaceCounts, nparts);
    size_t totalPartFaces = 0;
    for (int c : partFaceCounts) totalPartFaces += static_cast<size_t>(c);
    rdl2::IntVector partFaceIndices; r.array(partFaceIndices, totalPartFaces);

    rdl2::SceneContext& sc = mContext->getSceneContext();
    rdl2::SceneObject* so = sc.createSceneObject("RdlMeshGeometry", name);

    rdl2::SceneObject::UpdateGuard guard(so);
    so->set("vertex_list_0", vertices);
    so->set("face_vertex_count", faceCounts);
    so->set("vertices_by_index", indices);
    so->set("uv_list", uvs);
    so->set("normal_list", normals);
    so->set("part_list", partNames);
    so->set("part_face_count_list", partFaceCounts);
    so->set("part_face_indices", partFaceIndices);
    so->set("is_subd", static_cast<rdl2::Bool>(flags & 1u));
}

void
Session::applyClear(const std::string& name)
{
    if (!mContext) throw std::runtime_error("Clear before Hello");
    stopRender();

    rdl2::SceneContext& sc = mContext->getSceneContext();
    if (!sc.sceneObjectExists(name)) return;

    rdl2::SceneObject* so = sc.getSceneObject(name);
    rdl2::SceneObject::UpdateGuard guard(so);
    if (auto* layer = so->asA<rdl2::Layer>()) layer->clear();
    else if (auto* gs = so->asA<rdl2::GeometrySet>()) gs->clear();
    else if (auto* ls = so->asA<rdl2::LightSet>()) ls->clear();
    else error("Clear: '" + name + "' is not a Layer, GeometrySet or LightSet");
}

void
Session::startRender()
{
    if (!mContext) throw std::runtime_error("Start before Hello");
    stopRender();

    if (!mContext->isInitialized()) {
        std::stringstream initMessages;
        mContext->initialize(initMessages);
        if (!initMessages.str().empty()) log(initMessages.str());
    }

    mContext->setSceneUpdated();
    mContext->startFrame();

    mCompleteSent = false;
    mLastFilmActivity = ~0u;
    mLastSendTime = 0.0;
}

void
Session::stopRender()
{
    // stopFrame() aborts if no frame is in progress
    if (mContext && mContext->isFrameRendering()) mContext->stopFrame();
}

void
Session::pollFrame()
{
    if (mAwaitingAck || mCompleteSent) return;
    if (!mContext->isFrameReadyForDisplay()) return;

    const bool complete = mContext->isFrameComplete();
    const unsigned film = mContext->getFilmActivity();
    const double t = now();

    if (!complete) {
        if (film == mLastFilmActivity) return;
        if (t - mLastSendTime < 1.0 / mFps) return;
    }

    sendFrame(complete);
    mLastFilmActivity = film;
    mLastSendTime = t;

    if (complete) {
        mCompleteSent = true;
        mContext->stopFrame();
        net::sendMessage(mFd, Msg::Complete, nullptr, 0);
    }
}

void
Session::sendFrame(bool complete)
{
    mContext->snapshotRenderBuffer(&mBuffer, /*untile*/ true, /*parallel*/ true, /*usePrimaryAov*/ true);

    FrameHeader fh{};
    fh.width = mBuffer.getWidth();
    fh.height = mBuffer.getHeight();
    fh.channels = 4;
    fh.flags = complete ? 1u : 0u;
    fh.progress = complete ? 1.0f : mContext->getFrameProgressFraction(nullptr, nullptr);

    const size_t bytes = size_t(fh.width) * fh.height * sizeof(scene_rdl2::fb_util::RenderColor);
    mAwaitingAck = true;
    net::sendMessage2(mFd, Msg::Frame, &fh, sizeof(fh), mBuffer.getData(), bytes);
}

} // namespace mrbridge
