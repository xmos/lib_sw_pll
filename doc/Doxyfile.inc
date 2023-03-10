# This file provides overrides to the Doxyfile configuration

PROJECT_NAME = Software PLL
PROJECT_BRIEF = "Software PLL"

PREDEFINED = __DOXYGEN__=1 
PREDEFINED += DWORD_ALIGNED=
PREDEFINED += __attribute__((weak))=
PREDEFINED += C_API= MA_C_API= C_API_START= C_API_END= EXTERN_C=

# library APIs
INPUT += ../lib_sw_pll/api
