#**********************
# Gather Sources
#**********************
file(GLOB_RECURSE APP_SOURCES ${CMAKE_CURRENT_LIST_DIR}/src/*.c ${CMAKE_CURRENT_LIST_DIR}/src/*.xc)
set(APP_INCLUDES
    ${CMAKE_CURRENT_LIST_DIR}/src
)

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
    ${CMAKE_CURRENT_LIST_DIR}/src/xvf3800_qf60.xn
)

set(APP_COMPILE_DEFINITIONS
)

set(APP_LINK_OPTIONS
    -report
    ${CMAKE_CURRENT_LIST_DIR}/src/config.xscope
    ${CMAKE_CURRENT_LIST_DIR}/src/xvf3800_qf60.xn
)

#**********************
# Tile Targets
#**********************
add_executable(i2s_slave_lut)
target_sources(i2s_slave_lut PUBLIC ${APP_SOURCES})
target_include_directories(i2s_slave_lut PUBLIC ${APP_INCLUDES})
target_compile_definitions(i2s_slave_lut PRIVATE ${APP_COMPILE_DEFINITIONS})
target_compile_options(i2s_slave_lut PRIVATE ${APP_COMPILER_FLAGS})
target_link_options(i2s_slave_lut PRIVATE ${APP_LINK_OPTIONS})
target_link_libraries(i2s_slave_lut PUBLIC lib_sw_pll lib_i2s)
