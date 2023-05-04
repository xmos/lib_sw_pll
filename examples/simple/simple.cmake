#**********************
# Gather Sources
#**********************
file(GLOB_RECURSE APP_SOURCES ${CMAKE_CURRENT_LIST_DIR}/src/*.c ${CMAKE_CURRENT_LIST_DIR}/src/*.xc)
set(APP_INCLUDES
    ${CMAKE_CURRENT_LIST_DIR}/src
    ${CMAKE_CURRENT_LIST_DIR}../../modules/lib_xcore_math/lib_xcore_math/api
)

message("My simple message")

#**********************
# Flags
#**********************
set(APP_COMPILER_FLAGS
    -Os
    -g
    -report
    -fxscope
    -mcmodel=large
    -Wno-xcore-fptrgroup
    ${CMAKE_CURRENT_LIST_DIR}/src/config.xscope
    -target=XCORE-AI-EXPLORER
)
set(APP_COMPILE_DEFINITIONS
    DEBUG_PRINT_ENABLE=1
    PLATFORM_SUPPORTS_TILE_0=1
    PLATFORM_SUPPORTS_TILE_1=1
    PLATFORM_SUPPORTS_TILE_2=0
    PLATFORM_SUPPORTS_TILE_3=0
    PLATFORM_USES_TILE_0=1
    PLATFORM_USES_TILE_1=1
)

set(APP_LINK_OPTIONS
    -report
    -target=XCORE-AI-EXPLORER
    ${CMAKE_CURRENT_LIST_DIR}/src/config.xscope
)

#**********************
# Tile Targets
#**********************
add_executable(simple)
target_sources(simple PUBLIC ${APP_SOURCES})
target_include_directories(simple PUBLIC ${APP_INCLUDES})
target_compile_definitions(simple PRIVATE ${APP_COMPILE_DEFINITIONS})
target_compile_options(simple PRIVATE ${APP_COMPILER_FLAGS})
target_link_options(simple PRIVATE ${APP_LINK_OPTIONS})
target_link_libraries(simple PUBLIC io::sw_pll)
