# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import subprocess
import re
from pathlib import Path
from sw_pll.pll_calc import print_regs
from contextlib import redirect_stdout
import io

register_file = "register_setup.h" # can be changed as needed. This contains the register setup params and is accessible via C in the firmware


class app_pll_frac_calc:
    """ 
        This class uses the formulae in the XU316 datasheet to calculate the output frequency of the
        application PLL (sometimes called secondary PLL) from the register settings provided.
        It uses the checks specified in the datasheet to ensure the settings are valid, and will assert if not.
        To keep the inherent jitter of the PLL output down to a minimum, it is recommended that R be kept small,
        ideally = 0 (which equiates to 1) but reduces lock range.
    """

    frac_enable_mask = 0x80000000

    def __init__(self, input_frequency, F_init, R_init, f_init, p_init, OD_init, ACD_init, verbose=False):
        """
        Constructor initialising a PLL instance
        """
        self.input_frequency = input_frequency
        self.F = F_init 
        self.R = R_init  
        self.OD = OD_init
        self.ACD = ACD_init
        self.f = f_init                 # fractional multiplier (+1.0)
        self.p = p_init                 # fractional divider (+1.0)           
        self.output_frequency = None
        self.fractional_enable = True
        self.verbose = verbose

        self.calc_frequency()

    def calc_frequency(self):
        """
        Calculate the output frequency based on current object settings
        """
        if self.verbose:
            print(f"F: {self.F} R: {self.R} OD: {self.OD} ACD: {self.ACD} f: {self.f} p: {self.p}")
            print(f"input_frequency: {self.input_frequency}")
        assert self.F >= 1 and self.F <= 8191, f"Invalid F setting {self.F}"
        assert type(self.F) is int, f"Error: F must be an INT"
        assert self.R >= 0 and self.R <= 63, f"Invalid R setting {self.R}"
        assert type(self.R) is int, f"Error: R must be an INT"
        assert self.OD >= 0 and self.OD <= 7, f"Invalid OD setting {self.OD}"
        assert type(self.OD) is int, f"Error: OD must be an INT"

        intermediate_freq = self.input_frequency * (self.F + 1.0) / 2.0 / (self.R + 1.0)
        assert intermediate_freq >= 360000000.0 and intermediate_freq <= 1800000000.0, f"Invalid VCO freq: {intermediate_freq}"
        # print(f"intermediate_freq: {intermediate_freq}")

        assert type(self.p) is int, f"Error: r must be an INT"
        assert type(self.f) is int, f"Error: f must be an INT"

        # From XU316-1024-QF60A-xcore.ai-Datasheet_22.pdf
        if self.fractional_enable:
            # assert self.p > self.f, "Error f is not < p: {self.f} {self.p}" # This check has been removed as Joe found it to be OK in RTL/practice
            pll_ratio = (self.F + 1.0 + ((self.f + 1) / (self.p + 1)) ) / 2.0 / (self.R + 1.0) / (self.OD + 1.0) / (2.0 * (self.ACD + 1))
        else:
            pll_ratio = (self.F + 1.0) / 2.0 / (self.R + 1.0) / (self.OD + 1.0) / (2.0 * (self.ACD + 1))

        self.output_frequency = self.input_frequency * pll_ratio

        return self.output_frequency

    def get_output_frequency(self):
        """
        Get last calculated frequency
        """
        return self.output_frequency

    def update_all(self, F, R, OD, ACD, f, p):
        """
        Reset all App PLL vars
        """
        self.F = F
        self.R = R 
        self.OD = OD
        self.ACD = ACD
        self.f = f
        self.p = p
        return self.calc_frequency()

    def update_frac(self, f, p, fractional=None):
        """
        Update only the fractional parts of the App PLL
        """
        self.f = f
        self.p = p
        # print(f"update_frac f:{self.f} p:{self.p}")
        if fractional is not None:
            self.fractional_enable = fractional

        return self.calc_frequency()

    def update_frac_reg(self, reg):
        """
        Determine f and p from the register number and recalculate frequency
        Assumes fractional is set to true
        """
        f = int((reg >> 8) & ((2**8)-1))
        p = int(reg & ((2**8)-1))

        self.fractional_enable = True if (reg & self.frac_enable_mask) else False

        return self.update_frac(f, p)


    def get_frac_reg(self):
        """
        Returns the fractional reg value from current setting
        """
        # print(f"get_frac_reg f:{self.f} p:{self.p}")
        reg = self.p | (self.f << 8)
        if self.fractional_enable:
            reg |= self.frac_enable_mask 

        return reg

    def gen_register_file_text(self):
        """
        Helper used to generate text for the register setup h file
        """
        text = f"/* Input freq: {self.input_frequency}\n"
        text += f"   F: {self.F}\n"
        text += f"   R: {self.R}\n"
        text += f"   f: {self.f}\n"
        text += f"   p: {self.p}\n"
        text += f"   OD: {self.OD}\n"
        text += f"   ACD: {self.ACD}\n"
        text += "*/\n\n"

        # This is a way of calling a printing function from another module and capturing the STDOUT
        class args:
            app = True
        f = io.StringIO()
        with redirect_stdout(f):
            # in pll_calc, op_div = OD, fb_div = F, f, p, ref_div = R, fin_op_div = ACD
            print_regs(args, self.OD + 1, [self.F + 1, self.f + 1, self.p + 1] , self.R + 1, self.ACD + 1)
        text += f.getvalue().replace(" ", "_").replace("REG_0x", "REG 0x").replace("APP_PLL", "#define APP_PLL")

        return text

                                                              # see /doc/sw_pll.rst for guidance on these settings
def get_pll_solution(input_frequency, target_output_frequency, max_denom=80, min_F=200, ppm_max=2, fracmin=0.65, fracmax=0.95):
    """
        This is a wrapper function for pll_calc.py and allows it to be called programatically.
        It contains sensible defaults for the arguments and abstracts some of the complexity away from 
        the underlying script. Configuring the PLL is not an exact science and there are many tradeoffs involved.
        See sw_pll.rst for some of the tradeoffs involved and some example paramater sets.

        Once run, this function saves two output files:
        - fractions.h which contains the fractional term lookup table, which is guarranteed monotonic (important for PI stability)
        - register_setup.h which contains the PLL settings in comments as well as register settings for init in the application 

        This function and the underlying call to pll_calc may take several seconds to complete since it searches a range
        of possible solutions numerically.
        
        input_frequency         - The xcore clock frequency, normally the XTAL frequency
        nominal_ref_frequency   - The nominal input reference frequency
        target_output_frequency - The nominal target output frequency
        max_denom               - (Optional) The maximum fractional denominator. See/doc/sw_pll.rst for guidance  
        min_F                   - (Optional) The minimum integer numerator. See/doc/sw_pll.rst for guidance
        ppm_max                 - (Optional) The allowable PPM deviation for the target nominal frequency. See/doc/sw_pll.rst for guidance
        fracmin                 - (Optional) The minimum  fractional multiplier. See/doc/sw_pll.rst for guidance
        fracmax                 - (Optional) The maximum fractional multiplier. See/doc/sw_pll.rst for guidance

    """



    input_frequency_MHz = input_frequency / 1000000.0
    target_output_frequency_MHz = target_output_frequency / 1000000.0

    calc_script = Path(__file__).parent/"pll_calc.py"

    #                       input freq,           app pll,  max denom,  output freq,  min phase comp freq, max ppm error,  raw, fractional range, make header
    cmd = f"{calc_script} -i {input_frequency_MHz}  -a -m {max_denom} -t {target_output_frequency_MHz} -p 6.0 -e {int(ppm_max)} -r --fracmin {fracmin} --fracmax {fracmax} --header"
    print(f"Running: {cmd}")
    output = subprocess.check_output(cmd.split(), text=True)

    # Get each solution
    solutions = []
    Fs = []
    regex = r"Found solution.+\nAPP.+\nAPP.+\nAPP.+"
    matches = re.findall(regex, output)

    for solution in matches:
        F = int(float(re.search(r".+FD\s+(\d+.\d+).+", solution).groups()[0]))
        solutions.append(solution)
        Fs.append(F)

    possible_Fs = sorted(set(Fs))
    print(f"Available F values: {possible_Fs}")

    # Find first solution with F greater than F
    idx = next(x for x, val in enumerate(Fs) if val > min_F)    
    solution = matches[idx]

    # Get actual PLL register bitfield settings and info 
    regex = r".+OUT (\d+\.\d+)MHz, VCO (\d+\.\d+)MHz, RD\s+(\d+), FD\s+(\d+.\d*)\s+\(m =\s+(\d+), n =\s+(\d+)\), OD\s+(\d+), FOD\s+(\d+), ERR (-*\d+.\d+)ppm.*"
    match = re.search(regex, solution)

    if match:
        vals = match.groups()

        output_frequency = (1000000.0 * float(vals[0]))
        vco_freq = 1000000.0 * float(vals[1])

        # Now convert to actual settings in register bitfields
        F = int(float(vals[3]) - 1)     # PLL integer multiplier
        R = int(vals[2]) - 1            # PLL integer divisor
        f = int(vals[4]) - 1            # PLL fractional multiplier
        p = int(vals[5]) - 1            # PLL fractional divisor
        OD = int(vals[6]) - 1           # PLL output divider
        ACD = int(vals[7]) - 1          # PLL application clock divider
        ppm = float(vals[8])            # PLL PPM error for requrested set frequency
    
    assert match, f"Could not parse output of: {cmd} output: {solution}"

    # Now get reg values and save to file
    with open(register_file, "w") as reg_vals:
        reg_vals.write(f"/* Autogenerated by {Path(__file__).name} using command:\n")
        reg_vals.write(f"   {cmd}\n")
        reg_vals.write(f"   Picked output solution #{idx}\n")
        # reg_vals.write(f"\n{solution}\n\n") # This is verbose and contains the same info as below
        reg_vals.write(f"   Input freq: {input_frequency}\n")
        reg_vals.write(f"   F: {F}\n")
        reg_vals.write(f"   R: {R}\n")
        reg_vals.write(f"   f: {f}\n")
        reg_vals.write(f"   p: {p}\n")
        reg_vals.write(f"   OD: {OD}\n")
        reg_vals.write(f"   ACD: {ACD}\n")
        reg_vals.write(f"   Output freq: {output_frequency}\n")
        reg_vals.write(f"   VCO freq: {vco_freq} */\n")
        reg_vals.write("\n")


        for reg in ["APP PLL CTL REG", "APP PLL DIV REG", "APP PLL FRAC REG"]:
            regex = rf"({reg})\s+(0[xX][A-Fa-f0-9]+)"
            match = re.search(regex, solution)
            if match:
                val = match.groups()[1]
                reg_name = reg.replace(" ", "_")
                line = f"#define {reg_name}  \t{val}\n"
                reg_vals.write(line)


    return output_frequency, vco_freq, F, R, f, p, OD, ACD, ppm 

class pll_solution:
    """
    Access to all the info from get_pll_solution, cleaning up temp files. 
    intended for programatic access from the tests. Creates a PLL setup and LUT and reads back the generated LUT
    """
    def __init__(self, *args, **kwargs):
        self.output_frequency, self.vco_freq, self.F, self.R, self.f, self.p, self.OD, self.ACD, self.ppm = get_pll_solution(*args, **kwargs)
        from .dco_model import lut_dco
        dco = lut_dco("fractions.h")
        self.lut, min_frac, max_frac = dco._read_lut_header("fractions.h")


if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    input_frequency = 24000000
    output_frequency = 12288000
    print(f"get_pll_solution input_frequency: {input_frequency} output_frequency: {output_frequency}...")
    output_frequency, vco_freq, F, R, f, p, OD, ACD, ppm = get_pll_solution(input_frequency, output_frequency)
    print(f"got solution: \noutput_frequency: {output_frequency}\nvco_freq: {vco_freq}\nF: {F}\nR: {R}\nf: {f}\np: {p}\nOD: {OD}\nACD: {ACD}\nppm: {ppm}")

    app_pll = app_pll_frac_calc(input_frequency, F, R, f, p, OD, ACD)
    print(f"Got output frequency: {app_pll.calc_frequency()}")
    p = 10
    for f in range(p):
        for frac_enable in [True, False]:
            print(f"For f: {f} frac_enable: {frac_enable} got frequency: {app_pll.update_frac(f, p, frac_enable)}")

