# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.23.1)
project(moonray_bridge LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# MoonRay install locations (see wsl/build_moonray.sh)
set(MOONRAY_ROOT /opt/MoonRay/installs/openmoonray CACHE PATH "OpenMoonRay install")
set(MOONRAY_DEPS_ROOT /opt/MoonRay/installs CACHE PATH "OpenMoonRay dependencies")
set(MOONRAY_SOURCE /opt/MoonRay/source/openmoonray CACHE PATH "OpenMoonRay source tree")
list(APPEND CMAKE_PREFIX_PATH ${MOONRAY_ROOT} ${MOONRAY_DEPS_ROOT})
# MoonRay's Find*.cmake modules (CppUnit, Libuuid, Random123...)
list(APPEND CMAKE_MODULE_PATH ${MOONRAY_SOURCE}/cmake_modules/cmake)

# Same variables the rocky9-release preset sets
foreach(pkg Boost Libuuid CppUnit JsonCpp Libcurl Log4cplus OpenSubDiv OpenVDB Random123 ZLIB)
    set(${pkg}_ROOT ${MOONRAY_DEPS_ROOT})
endforeach()
set(ISPC ${MOONRAY_DEPS_ROOT}/bin/ispc)

# A MoonRay built with GPU support (MOONRAY_USE_OPTIX) links CUDA::cudart and
# OptiX::OptiX; both are optional for a CPU-only MoonRay.
if(EXISTS /usr/local/cuda-11.8)
    set(CUDAToolkit_ROOT /usr/local/cuda-11.8)
endif()
set(OPTIX_ROOT ${MOONRAY_DEPS_ROOT})
find_package(CUDAToolkit QUIET)
if(CUDAToolkit_FOUND)
    find_package(OptiX QUIET)
endif()

find_package(SceneRdl2 REQUIRED)
find_package(Moonray REQUIRED)

add_executable(moonray_bridge
    src/main.cc
    src/Net.cc
    src/Session.cc
)

target_link_libraries(moonray_bridge
    PRIVATE
        Moonray::rendering_rndr
        Moonray::rendering_mcrt_common
        SceneRdl2::scene_rdl2
        SceneRdl2::common_fb_util
)

# Same architecture flags and defines MoonRay uses (its headers need AVX2)
target_compile_options(moonray_bridge PRIVATE -march=core-avx2 -mavx)
target_compile_definitions(moonray_bridge PRIVATE
    BOOST_DISABLE_ASSERTS
    TBB_SUPPRESS_DEPRECATED_MESSAGES
    OPENVDB_USE_BLOSC
    OPENVDB_USE_LOG4CPLUS
    OPENVDB_USE_DEPRECATED_ABI_10
)

set_target_properties(moonray_bridge PROPERTIES
    INSTALL_RPATH "${MOONRAY_ROOT}/lib64;${MOONRAY_ROOT}/lib;${MOONRAY_DEPS_ROOT}/lib64;${MOONRAY_DEPS_ROOT}/lib"
    INSTALL_RPATH_USE_LINK_PATH TRUE
)

install(TARGETS moonray_bridge RUNTIME DESTINATION bin)
