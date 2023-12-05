cmake_minimum_required(VERSION 3.21.0)

add_executable(test_app_sdm_ctrl EXCLUDE_FROM_ALL main.c)


target_compile_options(
    test_app_sdm_ctrl
    PUBLIC
    -g
    -Os
    -report
    -fxscope
    -target=XCORE-AI-EXPLORER
)

target_link_options(
    test_app_sdm_ctrl
    PUBLIC
    -report
    -target=XCORE-AI-EXPLORER
    -fcmdline-buffer-bytes=10000  # support for command line params
)

target_link_libraries(test_app_sdm_ctrl PUBLIC lib_sw_pll)
