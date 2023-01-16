# Copyright 2022-2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import numpy as np
import matplotlib.pyplot as plt
import subprocess
import re
import os
import pll_vcd

ref_frequency = 48000.0
target_mclk_frequency = 12288000
multiplier = target_mclk_frequency / ref_frequency
ref_to_loop_call_rate = 512          # call comntrol once every n ref clocks
xtal_frequency = 24000000
lut_size = 256

#TMP HACK
def lut_lookup_simple(error):
        ppm = 300 # +- range of LUT

        min_mclk = target_mclk_frequency * (1 - ppm/1000000.0)
        max_mclk = target_mclk_frequency * (1 + ppm/1000000.0)
        mclk_range_hz = max_mclk - min_mclk
        step_size_hz = mclk_range_hz / lut_size

        lut = np.arange(min_mclk, max_mclk, step_size_hz)

        index = (lut_size // 2) - int(error) # Note we subtract for negative feedback
        lock_status = 0
        if index < 0:
            index = 0
            lock_status = -1
        if index > lut_size - 1:
            index = lut_size -1
            lock_status = 1
        return lut[index], lock_status


class app_pll_frac_calc:
    def __init__(self, input_frequency, F_init, R_init, OD_init, ACD_init, f_init, p_init, verbose=False):
        self.input_frequency = input_frequency
        self.F = F_init 
        self.R = R_init  
        self.OD = OD_init
        self.ACD = ACD_init
        self.f = f_init                 # fractional numerator (+1.0)
        self.p = p_init                 # fractional denominator (+1.0)           
        self.output_frequency = None
        self.lock_status_state = 0
        self.verbose = verbose

        self.calc_frequency()

    def calc_frequency(self):
        if self.verbose:
            print(f"F: {self.F} R: {self.R} OD: {self.OD} ACD: {self.ACD} f: {self.f} p: {self.p}")
            print(f"input_frequency: {self.input_frequency}")
        assert self.F >= 1 and self.F <= 8191, f"Invalid F setting {self.F}"
        assert type(self.F) is int, f"Error: F must be an INT"
        assert self.R >= 0 and self.R <= 63, f"Invalid R setting {self.R}"
        assert type(self.R) is int, f"Error: R must be an INT"
        assert self.OD >= 0 and self.OD <= 7, f"Invalid OD setting {self.OD}"
        assert type(self.OD) is int, f"Error: OD must be an INT"

        vco_freq = self.input_frequency * (self.F + 1.0) / 2.0 / (self.R + 1.0)
        assert vco_freq >= 360000000.0 and vco_freq <= 1800000000.0, f"Invalid VCO freq: {vco_freq}"
        # print(f"VCO: {vco_freq}")

        assert type(self.p) is int, f"Error: p must be an INT"
        assert type(self.f) is int, f"Error: f must be an INT"
        assert self.p > self.f, "Error f is not < p: {self.f} {self.p}"

        # From XU316-1024-QF60A-xcore.ai-Datasheet_22.pdf
        self.output_frequency = self.input_frequency * (self.F + 1.0 + ((self.f + 1) / (self.p + 1)) ) / 2.0 / (self.R + 1.0) / (self.OD + 1.0) / (2.0 * (self.ACD + 1))

        return self.output_frequency

    def get_output_freqency(self):
        return self.output_frequency

    def update_pll_all(self, F, R, OD, ACD, f, p):
        self.F = F
        self.R = R 
        self.OD = OD
        self.ACD = ACD
        self.f = f
        self.p = p
        self.calc_frequency()

    def update_pll_frac(self, f, p):
        self.f = f
        self.p = p
        self.calc_frequency()

class lut_lookup_h_file():
    def __init__(self, header_file, verbose=False):        
        with open(header_file) as hdr:
            header = hdr.readlines()
            min_frac = 1.0
            max_frac = 0.0
            for line in header:
                regex_ne = fr"frac_values_?\d*\[(\d+)].*"
                match = re.search(regex_ne, line)
                if match:
                    num_entries = int(match.groups()[0])
                    print(f"num_entries: {num_entries}")
                    lut = np.zeros(num_entries, dtype=np.uint16)

                regex_fr = r"0x([0-9A-F]+).+Index:\s+(\d+).+=\s(0.\d+)"
                match = re.search(regex_fr, line)
                if match:
                    reg, idx, frac = match.groups()
                    reg = int(reg, 16)
                    idx = int(idx)
                    frac = float(frac)
                    min_frac = frac if frac < min_frac else min_frac
                    max_frac = frac if frac > max_frac else max_frac
                    lut[idx] = reg

            print(f"min_frac: {min_frac} max_frac: {max_frac}")

            self.lut_reg = lut
            self.min_frac = min_frac
            self.max_frac = max_frac

    def get_lut(self):
        return self.lut_reg

    def lut_lookup_pre_calc(h_file, error):
        return lut[index], lock_status


class error_lut_from_h(app_pll_frac_calc, lut_lookup_h_file):
    def __init__(self, header_file, input_frequency, F_init, R_init, OD_init, ACD_init, f_init, p_init, verbose=False):
        self.app_pll_frac_calc = app_pll_frac_calc.__init__(self, input_frequency, F_init, R_init, OD_init, ACD_init, f_init, p_init, verbose=False)
        self.lut_lookup_h_file = lut_lookup_h_file.__init__(self, header_file, verbose=False)
        self.verbose = verbose

    def get_output_freqency_from_error(self, error):
        lut = self.get_lut()
        num_entries = np.size(lut)

        set_point = num_entries // 2 - int(error) #  Note negative term for neg feedback
        if set_point < 0:
            set_point = 0
            lock_status = -1
        elif set_point >= num_entries:
            set_point = num_entries - 1
            lock_status = 1
        else:
            set_point = set_point
            lock_status = 0

        register = int(lut[set_point])
        f = (register & 0xff00) >> 8
        p = register & 0xff

        if self.verbose or True:
            print(f"set_point: {set_point}, f: {f}, p: {p}, reg: 0x{register:04x}")
        self.update_pll_frac(f, p)

        return self.get_output_freqency(), lock_status

"""
The was to try to find solutions which are in the middle of a range where the step sizes are minimised
and that is at the very bottom and very top (it is symmetrical) of the range of fractions
then it's all just a tradeoff between jitter and lock range
some other relevant bits are: keeping the ref divider as low as possible keeps jitter low
keeping feedback divider high keeps jitter low (but reduces lock range)
keeping vco freq high lowers jitter
it's quite hard to summarise all of this into an algorithm to pick the "best" setting
"""

def get_pll_solution(input_frequency, target_output_frequency, max_denom=80, ppm_max=1):
    input_frequency_MHz = input_frequency / 1000000.0
    target_output_frequency_MHz = target_output_frequency / 1000000.0

    #                     input freq         one solution, app pll,  max denom,  output freq,   max ppm error,  raw, fractional range, make header
    cmd = f"./pll_calc.py -i {input_frequency_MHz} -s 1 -a -m {max_denom} -t {target_output_frequency_MHz} -e {ppm_max} -r --fracmin 0.8333 --fracmax 0.9876 --header"
    print(f"Running: {cmd}")
    output = subprocess.check_output(cmd.split(), text=True)

    regex = r".+OUT (\d+\.\d+)MHz, VCO (\d+\.\d+)MHz, RD\s+(\d+), FD\s+(\d+.\d*)\s+\(m =\s+(\d+), n =\s+(\d+)\), OD\s+(\d+), FOD\s+(\d+), ERR (-*\d+.\d+)ppm.*"
    match = re.search(regex, output)

    if match:
        vals = match.groups()

        output_frequency = (1000000.0 * float(vals[0]))
        vco_freq = 1000000.0 * float(vals[1])
        RD = int(vals[2])
        FD = float(vals[3])
        m = int(vals[4])
        n = int(vals[5])
        FOD = int(vals[6])
        ppm = int(vals[7])
    
    assert match, f"Could not parse output of: {cmd} output: {output}"

    lut, min_frac, max_frac = parse_h_file("fractions.h", max_denom)

    return output_frequency, vco_freq, RD, FD, FOD, ppm

class sw_pll_ctrl:
    lock_status_lookup = {-1 : "UNLOCKED LOW", 0 : "LOCKED", 1 : "UNLOCKED HIGH"}

    def __init__(self, lut_function, multiplier, ref_to_loop_call_rate, Kp, Ki, Kii=0.0, init_mclk_count=0, init_ref_clk_count=0, verbose=False):
        self.lut_function = lut_function
        self.multiplier = multiplier
        self.ref_to_loop_call_rate = ref_to_loop_call_rate

        self.ref_clk_count = init_mclk_count    # Integer as we run this loop based on the ref clock input count
        self.mclk_count_old = init_mclk_count   # Integer
        self.expected_mclk_count_inc_float = multiplier * ref_to_loop_call_rate
        self.expected_mclk_count_float = 0.0

        self.Kp     = Kp
        self.Ki     = Ki
        self.Kii    = Kii

        self.error_accum = 0.0          #Integral of error
        self.error_accum_accum = 0.0    #Double integral
        self.error = 0.0                #total error

        self.i_windup_limit     = lut_size / Ki if Ki != 0.0 else 0.0
        self.ii_windup_limit    = lut_size / Kii if Kii != 0.0 else 0.0

        self.last_mclk_frequency = target_mclk_frequency

        self.verbose = verbose

        if verbose:
            print(f"Init sw_pll_ctrl, ref_frequency: {ref_frequency}, target_mclk_frequency: {target_mclk_frequency} ref_to_loop_call_rate: {ref_to_loop_call_rate}, Kp: {Kp} Ki: {Ki}")

    def get_expected_mclk_count_inc(self):
        return self.expected_mclk_count_inc_float

    def get_error(self):
        return self.error

    def do_control(self, mclk_count_float, period_fraction=1.0):

        """ Calculate the actual output frequency from the input mclk_count taken at the ref clock time.
            If the time of sampling the mclk_count is not precisely 1.0 x the ref clock time,
            you may pass a fraction to allow for a proportional value using period_fraction. """

        mclk_count_int = int(mclk_count_float)
        mclk_count_inc = mclk_count_int - self.mclk_count_old
        mclk_count_inc = mclk_count_inc / period_fraction

        self.mclk_count_old = mclk_count_int
        self.expected_mclk_count_float += self.expected_mclk_count_inc_float

        self.ref_clk_count += self.ref_to_loop_call_rate

        error = mclk_count_inc - int(self.expected_mclk_count_inc_float)

        self.error_accum += error 
        self.error_accum_accum += self.error_accum

        error_p  = self.Kp * error;
        error_i  = self.Ki * self.error_accum
        error_ii = self.Kii * self.error_accum_accum

        # Clamp integral terms
        error_i = np.clip(error_i, -self.i_windup_limit, self.i_windup_limit)
        error_ii = np.clip(error_ii, -self.ii_windup_limit, self.ii_windup_limit)

        self.error = error_p + error_i + error_ii

        if self.verbose:
            print(f"error_p: {error_p}({self.Kp}) error_i: {error_i}({self.Ki}) error_ii: {error_ii}({self.Kii}) error: {self.error}")


        if self.verbose:
            print(f"expected mclk_count: {self.expected_mclk_count} actual mclk_count: {self.mclk_count} error: {self.error}")

        actual_mclk_frequency, lock_status = self.lut_function(self.error)

        return actual_mclk_frequency, lock_status





def run_sim(ref_frequency, lut_function):
    sw_pll = sw_pll_ctrl(lut_function, multiplier, ref_to_loop_call_rate, 0.1, 1.0, Kii=0.0000, verbose=False)
    mclk_count_end_float = 0.0
    real_time = 0.0
    # actual_mclk_frequency = target_mclk_frequency
    actual_mclk_frequency = target_mclk_frequency * (1 - 200 / 1000000)# initial value which is some PPM off

    freq_log = []
    target_log = []

    vcd = pll_vcd.sw_pll_vdd()

    for count in range(150):
        mclk_count_start_float = mclk_count_end_float
        mclk_count_float_inc = actual_mclk_frequency / ref_frequency * ref_to_loop_call_rate
     
        # Add some jitter to the mclk_count
        mclk_sample_jitter = 0
        mclk_sample_jitter = 100 * (np.random.sample() - 0.5)         
        mclk_count_end_float += mclk_count_float_inc + mclk_sample_jitter
        # Compensate for the jitter
        period_fraction = (mclk_count_float_inc + mclk_sample_jitter) / mclk_count_float_inc

        # print(f"mclk_count_float_inc: {mclk_count_float_inc}, period_fraction: {period_fraction}, ratio: {mclk_count_float_inc / period_fraction}")

        actual_mclk_frequency, lock_status = sw_pll.do_control(mclk_count_end_float, period_fraction = period_fraction)
        
        # vcd.do_vcd(real_time, ref_frequency, mclk_count_start_float, mclk_count_end_float, sw_pll.get_error(), count, lock_status)

        print(f"Loop: count: {count}, actual_mclk_frequency: {actual_mclk_frequency}, lock_status: {sw_pll_ctrl.lock_status_lookup[lock_status]}")
     
        freq_log.append(actual_mclk_frequency)
        target_log.append(ref_frequency * multiplier)

        real_time += ref_to_loop_call_rate / ref_frequency

        if count == 25:
            ref_frequency = 48005

        if count == 50:
            ref_frequency = 48010

        if count == 65:
            ref_frequency = 47995

        if count == 130:
            ref_frequency = 48000

    plt.plot(freq_log, color='red', marker='o', label='actual frequency')
    plt.plot(target_log, color='blue', marker='.', label='target frequency')
    plt.title('PLL tracking', fontsize=14)
    plt.xlabel(f'loop_cycle {ref_to_loop_call_rate}', fontsize=14)
    plt.ylabel('Frequency', fontsize=10)
    plt.legend(loc="upper right")
    plt.grid(True)
    # plt.show()
    plt.savefig("pll.png")


xtal_frequency =24000000.0
F_init = 506
R_init = 3
OD_init = 1
ACD_init = 30
f_init = 19
p_init = 21

header_file = "fractions.h"
if not os.path.exists(header_file):
    output_frequency, vco_freq, RD, FD, FOD, ppm = get_pll_solution(xtal_frequency, target_mclk_frequency)
    print(output_frequency, vco_freq, RD, FD, FOD, ppm)

error_from_h = error_lut_from_h(header_file, xtal_frequency, F_init, R_init, OD_init, ACD_init, f_init, p_init, verbose=False)

for err in range(-163, 164):
    freq = error_from_h.get_output_freqency_from_error(err)
    print(freq)

pll_freq_calc = app_pll_frac_calc(xtal_frequency, F_init, R_init, OD_init, ACD_init, f_init, p_init, verbose=True)
print(f"PLL Output: {pll_freq_calc.get_output_freqency()}")

# run_sim(ref_frequency, lut_lookup_simple)
run_sim(ref_frequency, error_from_h.get_output_freqency_from_error)