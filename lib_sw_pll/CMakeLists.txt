## Source files
file(GLOB_RECURSE LIB_C_SOURCES   src/*.c )
file(GLOB_RECURSE LIB_CXX_SOURCES src/*.cc)
file(GLOB_RECURSE LIB_XC_SOURCES  src/*.xc)
file(GLOB_RECURSE LIB_ASM_SOURCES src/*.S )

## cmake doesn't recognize .S files as assembly by default
set_source_files_properties(LIB_ASM_SOURCES PROPERTIES LANGUAGE ASM)

## Assume all asm is XS3A for now
set(XCORE_XS3A_SOURCES ${LIB_ASM_SOURCES})

## Set any local library compile options
set(LIB_COMPILE_FLAGS "-Os" "-g")

## Includes files
set(LIB_PUBLIC_INCLUDES  api src)
set(LIB_PRIVATE_INCLUDES src)

## Gather library sources
set(LIB_PUBLIC_SOURCES   "")
set(LIB_PRIVATE_SOURCES  ${LIB_C_SOURCES} ${LIB_CXX_SOURCES} ${LIB_XC_SOURCES})

## Append platform specific sources
list(APPEND LIB_PRIVATE_SOURCES ${${CMAKE_SYSTEM_NAME}_SOURCES})

## Create library target
add_library(lib_sw_pll STATIC)
target_sources(lib_sw_pll
    PUBLIC
        ${LIB_PUBLIC_SOURCES}
    PRIVATE
        ${LIB_PRIVATE_SOURCES}
)
target_include_directories(lib_sw_pll
    PUBLIC
        ${LIB_PUBLIC_INCLUDES}
    PRIVATE
        ${LIB_PRIVATE_INCLUDES}
)
target_compile_options(lib_sw_pll
    PRIVATE
        ${LIB_COMPILE_FLAGS}
)
