set(LIB_NAME lib_sw_pll)

set(LIB_VERSION 2.4.1)

set(LIB_INCLUDES api src)

set(LIB_COMPILER_FLAGS  -Os
                        -g
                        -Wall
                        -Wextra
                        -Wconversion
                        -Wsign-compare
                        -Wdiv-by-zero
                        -Wfloat-equal
                        -Wshadow)

set(LIB_DEPENDENT_MODULES "")

XMOS_REGISTER_MODULE()
