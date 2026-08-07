cmake_minimum_required(VERSION 3.16)
project(pktcfg VERSION 0.1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
endif()

option(PKTCFG_SANITIZE "Build with AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(PKTCFG_FUZZ     "Build the libFuzzer harness (needs an LLVM clang with libFuzzer)" OFF)
option(PKTCFG_WERROR   "Treat compiler warnings as errors" OFF)

add_library(pktcfg STATIC
  src/parse.c
  src/decode.c
  src/config.c
  src/fuzz_entry.c
)

target_include_directories(pktcfg PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

# Compiler warnings are evidence for this project, so they are on by default
# and captured in the build log rather than suppressed.
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
  target_compile_options(pktcfg PRIVATE -Wall -Wextra -Wshadow -Wconversion)
  if(PKTCFG_WERROR)
    target_compile_options(pktcfg PRIVATE -Werror)
  endif()
endif()

if(PKTCFG_SANITIZE)
  set(PKTCFG_SAN_FLAGS -fsanitize=address,undefined -fno-omit-frame-pointer -fno-optimize-sibling-calls -g)
  target_compile_options(pktcfg PUBLIC ${PKTCFG_SAN_FLAGS})
  target_link_options(pktcfg PUBLIC ${PKTCFG_SAN_FLAGS})
endif()

add_executable(pktcfg_replay tools/pktcfg_replay.c)
target_link_libraries(pktcfg_replay PRIVATE pktcfg)

if(PKTCFG_FUZZ)
  # The library itself has to carry the coverage instrumentation, otherwise
  # libFuzzer runs blind and reports cov: 1.
  target_compile_options(pktcfg PRIVATE -fsanitize=fuzzer-no-link)

  add_executable(pktcfg_fuzz fuzz/pktcfg_fuzz.c)
  target_link_libraries(pktcfg_fuzz PRIVATE pktcfg)
  target_compile_options(pktcfg_fuzz PRIVATE -fsanitize=fuzzer)
  target_link_options(pktcfg_fuzz PRIVATE -fsanitize=fuzzer)
endif()

enable_testing()

set(PKTCFG_TESTS
  test_header
  test_entries
  test_escapes
  test_tab_expansion
  test_truncation
  test_limits
  test_lookup
  test_fuzz_entry
)

foreach(test_name IN LISTS PKTCFG_TESTS)
  add_executable(${test_name} tests/${test_name}.c)
  target_link_libraries(${test_name} PRIVATE pktcfg)
  target_include_directories(${test_name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)
  if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    target_compile_options(${test_name} PRIVATE -Wall -Wextra)
  endif()
  add_test(NAME ${test_name} COMMAND ${test_name})
endforeach()

set_tests_properties(test_tab_expansion PROPERTIES
  LABELS "asymmetry"
)
