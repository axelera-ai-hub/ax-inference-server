cmake_minimum_required(VERSION 3.12)
project(axinferencenet_grpc_server LANGUAGES CXX VERSION 0.1)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(PkgConfig REQUIRED)

pkg_check_modules(axruntime  REQUIRED axruntime)
pkg_check_modules(opencv4    REQUIRED opencv4)
pkg_check_modules(axstreamer REQUIRED axstreamer)

set(GRPC_AVAILABLE FALSE)
find_package(Protobuf QUIET)
if(Protobuf_FOUND)
    pkg_check_modules(GRPC QUIET grpc++ grpc)
    if(GRPC_FOUND)
        set(GRPC_AVAILABLE TRUE)
        message(STATUS "gRPC dependencies found — axinferencenet_grpc will be built")
    endif()
endif()

if(NOT GRPC_AVAILABLE)
    message(FATAL_ERROR
        "gRPC dependencies not found.\n"
        "Install them with: sudo apt install libgrpc++-dev protobuf-compiler protobuf-compiler-grpc libprotobuf-dev\n"
        "Then re-run cmake.")
endif()

find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp)
if(NOT NLOHMANN_JSON_INCLUDE_DIR)
    message(FATAL_ERROR
        "nlohmann/json.hpp not found.\n"
        "Install with: sudo apt install nlohmann-json3-dev")
endif()

set(USE_SIMD_DECODE_ENV $ENV{USE_SIMD_DECODE})
if(USE_SIMD_DECODE_ENV STREQUAL "1")
    set(USE_SIMD_DECODE ON)
    message(STATUS "SIMD decoding: ENABLED  (USE_SIMD_DECODE=1)")
else()
    set(USE_SIMD_DECODE OFF)
    message(STATUS "SIMD decoding: DISABLED (set USE_SIMD_DECODE=1 to enable)")
endif()

if(USE_SIMD_DECODE)
    find_library(TURBOJPEG_LIBRARY NAMES turbojpeg)
    find_path(TURBOJPEG_INCLUDE_DIR turbojpeg.h)

    if(TURBOJPEG_LIBRARY AND TURBOJPEG_INCLUDE_DIR)
        message(STATUS "  libjpeg-turbo found — SIMD JPEG decoding enabled")
        set(HAVE_TURBOJPEG ON)

        add_library(TurboJPEG::TurboJPEG SHARED IMPORTED)
        set_target_properties(TurboJPEG::TurboJPEG PROPERTIES
            IMPORTED_LOCATION             "${TURBOJPEG_LIBRARY}"
            INTERFACE_INCLUDE_DIRECTORIES "${TURBOJPEG_INCLUDE_DIR}"
        )
    else()
        message(WARNING
            "libjpeg-turbo not found — falling back to OpenCV JPEG decode (slower).\n"
            "Install with:  sudo apt install libjpeg-dev libturbojpeg0-dev")
    endif()
endif()

set(GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY ${GEN_DIR})
set(PROTO_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../proto")

add_custom_command(
    OUTPUT  ${GEN_DIR}/axinfer/v1/inference.pb.cc
            ${GEN_DIR}/axinfer/v1/inference.pb.h
    COMMAND ${Protobuf_PROTOC_EXECUTABLE}
            --proto_path=${PROTO_DIR}
            --cpp_out=${GEN_DIR}
            --experimental_allow_proto3_optional
            ${PROTO_DIR}/axinfer/v1/inference.proto
    DEPENDS ${PROTO_DIR}/axinfer/v1/inference.proto
    COMMENT "Generating C++ protobuf sources"
)

add_custom_command(
    OUTPUT  ${GEN_DIR}/axinfer/v1/inference.grpc.pb.cc
            ${GEN_DIR}/axinfer/v1/inference.grpc.pb.h
    COMMAND ${Protobuf_PROTOC_EXECUTABLE}
            --proto_path=${PROTO_DIR}
            --grpc_out=${GEN_DIR}
            --plugin=protoc-gen-grpc=`which grpc_cpp_plugin`
            --experimental_allow_proto3_optional
            ${PROTO_DIR}/axinfer/v1/inference.proto
    DEPENDS ${PROTO_DIR}/axinfer/v1/inference.proto
    COMMENT "Generating gRPC C++ sources"
)

add_library(axinfer_proto
    ${GEN_DIR}/axinfer/v1/inference.pb.cc
    ${GEN_DIR}/axinfer/v1/inference.grpc.pb.cc
)
target_include_directories(axinfer_proto PUBLIC
    ${GEN_DIR}
    ${Protobuf_INCLUDE_DIRS}
    ${GRPC_INCLUDE_DIRS}
)
target_link_libraries(axinfer_proto PUBLIC
    ${Protobuf_LIBRARIES}
    ${GRPC_LIBRARIES}
)

add_library(axpipeline STATIC
    src/interface/grpc.cpp
    src/pipeline/builder.cpp
    src/nodes/inference.cpp
    src/nodes/filter.cpp
    src/nodes/iter.cpp
    src/nodes/collect.cpp
    src/nodes/guard.cpp
)

target_include_directories(axpipeline PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${axruntime_INCLUDE_DIRS}
    ${opencv4_INCLUDE_DIRS}
    ${axstreamer_INCLUDE_DIRS}
    ${Protobuf_INCLUDE_DIRS}
    ${GRPC_INCLUDE_DIRS}
    ${GEN_DIR}
    ${NLOHMANN_JSON_INCLUDE_DIR}
)
target_link_libraries(axpipeline PUBLIC
    axinfer_proto
    ${axruntime_LIBRARIES}
    ${opencv4_LIBRARIES}
    ${axstreamer_LIBRARIES}
    ${GRPC_LIBRARIES}
    ${Protobuf_LIBRARIES}
)
if(USE_SIMD_DECODE AND HAVE_TURBOJPEG)
    target_link_libraries(axpipeline PUBLIC TurboJPEG::TurboJPEG)
    target_compile_definitions(axpipeline PUBLIC HAVE_TURBOJPEG)
endif()
target_link_directories(axpipeline PUBLIC
    ${axruntime_LIBRARY_DIRS}
    ${opencv4_LIBRARY_DIRS}
    ${axstreamer_LIBRARY_DIRS}
)
target_compile_options(axpipeline PRIVATE
    -Wall
    -Werror
    -Wno-sign-compare
    -Wno-unused-variable
    -Wno-format-security
    $<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-enum-enum-conversion>
    $<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-declarations>
)

add_executable(axinferencenet_grpc src/main.cpp)

target_include_directories(axinferencenet_grpc PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${axruntime_INCLUDE_DIRS}
    ${opencv4_INCLUDE_DIRS}
    ${axstreamer_INCLUDE_DIRS}
    ${Protobuf_INCLUDE_DIRS}
    ${GRPC_INCLUDE_DIRS}
    ${GEN_DIR}
)
target_link_libraries(axinferencenet_grpc PUBLIC
    axpipeline
)
target_compile_options(axinferencenet_grpc PRIVATE
    -Wall
    -Werror
    -Wno-sign-compare
    -Wno-unused-variable
    $<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-enum-enum-conversion>
    $<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-declarations>
)

find_library(TCMALLOC_LIB NAMES tcmalloc_minimal tcmalloc)
if(TCMALLOC_LIB)
    message(STATUS "Found TCMalloc: ${TCMALLOC_LIB}")
    target_link_libraries(axpipeline PUBLIC ${TCMALLOC_LIB})
else()
    message(FATAL_ERROR
        "TCMalloc not found.\n"
        "Install with:  sudo apt install libgoogle-perftools-dev")
endif()

find_library(LIBURING_LIB NAMES uring)
if(LIBURING_LIB)
    message(STATUS "Found liburing: ${LIBURING_LIB}")
    target_link_libraries(axpipeline PUBLIC ${LIBURING_LIB})
else()
    message(FATAL_ERROR
        "liburing not found.\n"
        "Install with:  sudo apt install liburing-dev")
endif()

target_link_libraries(axpipeline PUBLIC dl)

install(TARGETS axinferencenet_grpc RUNTIME DESTINATION bin)

message(STATUS "axinferencenet_grpc configured successfully")
