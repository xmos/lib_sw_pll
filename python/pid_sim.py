import numpy as np
import matplotlib.pyplot as plt
import subprocess
import re
from vcd import VCDWriter 


ref_frequency = 48000.0
target_mclk_frequency = 12288000
multiplier = target_mclk_frequency / ref_frequency
ref_to_loop_call_rate = 512          # call comntrol once every n ref clocks
xtal_frequency = 24000000
lut_size = 256

#TMP HACK
def lut_lookup(error):
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


"""
my approach was to try to find solutions which are in the middle of a range where the step sizes are minimised
and that is at the very bottom and very top (it is symmetrical) of the range of fractions
then it's all just a tradeoff between jitter and lock range
some other relevant bits are: keeping the ref divider as low as possible keeps jitter low
keeping feedback divider high keeps jitter low (but reduces lock range)
keeping vco freq high lowers jitter
it's quite hard to summarise all of this into an algorithm to pick the "best" setting
"""

def parse_h_file(header_file, max_denom):
    header_file = "fractions.h"
    with open(header_file) as hdr:
        header = hdr.readlines()
        min_frac = 1.0
        max_frac = 0.0
        for line in header:
            regex_ne = fr"frac_values_{max_denom}\[(\d+)].*"
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

        return lut, min_frac, max_frac

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

    def __init__(self, multiplier, ref_to_loop_call_rate, Kp, Ki, Kii=0.0, init_mclk_count=0, init_ref_clk_count=0, verbose=False):
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

        self.i_windup_limit     = lut_size / Ki 
        self.ii_windup_limit    = lut_size / Kii

        self.last_mclk_frequency = target_mclk_frequency

        self.verbose = verbose

        if verbose:
            print(f"Init sw_pll_ctrl, ref_frequency: {ref_frequency}, target_mclk_frequency: {target_mclk_frequency} ref_to_loop_call_rate: {ref_to_loop_call_rate}, Kp: {Kp} Ki: {Ki}")

    def get_expected_mclk_count_inc(self):
        return self.expected_mclk_count_inc_float

    def get_error(self):
        return self.error

    def do_control(self, mclk_count_float):

        mclk_count_int = int(mclk_count_float)
        mclk_count_inc = mclk_count_int - self.mclk_count_old
        self.mclk_count_old = mclk_count_int
        self.expected_mclk_count_float += self.expected_mclk_count_inc_float

        self.ref_clk_count += self.ref_to_loop_call_rate

        error = mclk_count_inc - int(self.expected_mclk_count_inc_float)
        print(f"mclk_count_inc: {mclk_count_inc} expected_mclk_count_inc: {self.expected_mclk_count_inc_float} mclk_count: {mclk_count_float}")

        self.error_accum += error 
        self.error_accum_accum += self.error_accum

        error_p  = self.Kp * error;
        error_i  = self.Ki * self.error_accum
        error_ii = self.Kii * self.error_accum_accum

        # Clamp integral terms
        error_i = np.clip(error_i, -self.i_windup_limit, self.i_windup_limit)
        error_ii = np.clip(error_ii, -self.ii_windup_limit, self.ii_windup_limit)

        self.error = error_p + error_i + error_ii

        print(f"error_p: {error_p}({self.Kp}) error_i: {error_i}({self.Ki}) error_ii: {error_ii}({self.Kii}) error: {self.error }")


        if self.verbose:
            print(f"expected mclk_count: {self.expected_mclk_count} actual mclk_count: {self.mclk_count} error: {self.error }")

        actual_mclk_frequency, lock_status = lut_lookup(self.error)

        return actual_mclk_frequency, lock_status





class app_pll_frac_calc:
    def __init__(self, input_frequency, F_init, R_init, OD_init, ACD_init, f_init, p_init, verbose=False):
        self.input_frequency = input_frequency
        self.F = F_init 
        self.R = R_init  
        self.OD = OD_init
        self.ACD = ACD_init
        self.f = f_init
        self.p = p_init
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
        print(f"VCO: {vco_freq}")

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

    def update_pll_frac(f, p):
        self.f = f
        self.p = p
        self.calc_frequency()


class sw_pll_vdd:
    def __init__(self):
        self.vcd_file = open("pll.vcd", "w")
        self.vcd_writer = VCDWriter(self.vcd_file, timescale='1 ns', date='today')

        ref_clock_var = self.vcd_writer.register_var('pll', 'refclk', 'integer', size=1)     
        mclk_clock_var = self.vcd_writer.register_var('pll', 'mclk', 'integer', size=1)     
        recovered_ref_clk = self.vcd_writer.register_var('pll', 'recovered_ref_clk', 'integer', size=1)
        error_var = self.vcd_writer.register_var('pll', 'error', 'real')
        control_loop_event = self.vcd_writer.register_var('pll', 'control', 'event')
        mclk_freq_var = self.vcd_writer.register_var('pll', 'mclk_freq', 'real')
        ref_clock_freq_var = self.vcd_writer.register_var('pll', 'ref_clock_freq', 'real')
        loop_count_var = self.vcd_writer.register_var('pll', 'loop_count', 'real')
        lock_status_var = self.vcd_writer.register_var('pll', 'lock_status', 'string')

        self.vcd_vars = {
                        'ref_clock_var':ref_clock_var,
                        'mclk_clock_var':mclk_clock_var,
                        "recovered_ref_clk":recovered_ref_clk,
                        "mclk_freq_var":mclk_freq_var,
                        "ref_clock_freq_var":ref_clock_freq_var,
                        "error_var":error_var,
                        "control_loop_event":control_loop_event,
                        "loop_count_var":loop_count_var,
                        "lock_status_var":lock_status_var}


    def do_vcd(self, real_time, ref_frequency, mclk_count_start_float, mclk_count_end_float, error, loop_count, lock_status):
        time_period = ref_to_loop_call_rate / ref_frequency 
        end_time = real_time + time_period
        mclk_count_float_inc = mclk_count_end_float - mclk_count_start_float
        
        print(f"mclk_count_start_float:{mclk_count_start_float} mclk_count_end_float:{mclk_count_end_float} mclk_count_float_inc:{mclk_count_float_inc}")

        mclk_period = time_period / mclk_count_float_inc

        print(f"time_period: {time_period} mclk_period: {mclk_period}")
        mclk_start_frac = np.ceil(mclk_count_start_float) - mclk_count_start_float  # fractional amount of mclks at start 
        mclk_end_frac = mclk_count_end_float - np.floor(mclk_count_end_float)       # fractional amount of mclks at end
        print(f"mclk_start_frac: {mclk_start_frac} mclk_end_frac: {mclk_end_frac}")

        extra_transitions = 0

        if mclk_start_frac > 0.5:
            next_mclk_val = 0
            mclk_first_transition = real_time + (mclk_start_frac - 0.5) * mclk_period
            extra_transitions += 1
        else:
            next_mclk_val = 1
            mclk_first_transition = real_time +  mclk_start_frac * mclk_period

        if mclk_end_frac > 0.5:
            mclk_last_transition = end_time - (mclk_end_frac - 0.5) * mclk_period
            extra_transitions += 1
        else:
            mclk_last_transition = end_time - mclk_end_frac * mclk_period


        mclk_num_toggles = 2 * (np.floor(mclk_count_end_float) - np.ceil(mclk_count_start_float)) + extra_transitions

        # print(f"mclk_first_transition:{mclk_first_transition} mclk_last_transition:{mclk_last_transition} mclk_num_toggles:{mclk_num_toggles}")

        ns = 1000000000
        mclk_transitions = np.arange(mclk_first_transition * ns, mclk_last_transition * ns, (mclk_last_transition - mclk_first_transition) / mclk_num_toggles * ns)
        recovered_ref_clk_transitions = np.arange(mclk_first_transition * ns, mclk_last_transition * ns, (mclk_last_transition - mclk_first_transition) / mclk_num_toggles * ns * multiplier)

        ref_clock_fall_period = time_period / ref_to_loop_call_rate
        ref_clk_transitions = np.arange(real_time * ns, end_time * ns, ref_clock_fall_period / 2 * ns)
        ref_clk_val = 1


        recovered_ref_clk_start_float = mclk_count_start_float / multiplier
        recovered_ref_clk_start_float_frac = recovered_ref_clk_start_float - np.floor(mclk_count_start_float)
        next_recovered_ref_val = 1 if recovered_ref_clk_start_float_frac < 0.5 else 0

        # print(f"ref_clk_transitions: {ref_clk_transitions}")
        # print(f"mclk_transitions: {mclk_transitions}")
        self.vcd_writer.change(self.vcd_vars["control_loop_event"], real_time * ns, True)
        self.vcd_writer.change(self.vcd_vars["loop_count_var"], real_time * ns, loop_count)
        self.vcd_writer.change(self.vcd_vars["error_var"], real_time * ns, error)
        self.vcd_writer.change(self.vcd_vars["ref_clock_freq_var"], real_time * ns, ref_frequency)
        self.vcd_writer.change(self.vcd_vars["mclk_freq_var"], real_time * ns, 1 / mclk_period)
        self.vcd_writer.change(self.vcd_vars["lock_status_var"], real_time * ns, sw_pll_ctrl.lock_status_lookup[lock_status])

        # This is needed because vcd writer wants things in time order
        # mclk is the fastest clock so use that as the loop var and then add transitions of other vars
        
        for mclk_transition in mclk_transitions:

            if ref_clk_transitions.size > 0:
                ref_clk_transition = ref_clk_transitions[0]
            else:
                ref_clk_transition = end_time * ns 

            if recovered_ref_clk_transitions.size > 0:
                recovered_ref_clk_transition = recovered_ref_clk_transitions[0]
            else:
                recovered_ref_clk_transition = end_time * ns

            if ref_clk_transition < recovered_ref_clk_transition:
                if(ref_clk_transition <= mclk_transition):
                    # print(f"ref_clk_transition {ref_clk_transition}")
                    self.vcd_writer.change(self.vcd_vars["ref_clock_var"], ref_clk_transition, ref_clk_val)
                    ref_clk_val = 0 if ref_clk_val == 1 else 1
                    ref_clk_transitions = np.delete(ref_clk_transitions, 0)

                if(recovered_ref_clk_transition <= mclk_transition):
                    # print(f"recovered_ref_clk_transitions {recovered_ref_clk_transitions}")
                    self.vcd_writer.change(self.vcd_vars["recovered_ref_clk"], recovered_ref_clk_transition, next_recovered_ref_val)
                    next_recovered_ref_val = 0 if next_recovered_ref_val == 1 else 1
                    recovered_ref_clk_transitions = np.delete(recovered_ref_clk_transitions, 0)
            else:
                if(recovered_ref_clk_transition <= mclk_transition):
                    # print(f"recovered_ref_clk_transitions {recovered_ref_clk_transitions}")
                    self.vcd_writer.change(self.vcd_vars["recovered_ref_clk"], recovered_ref_clk_transition, next_recovered_ref_val)
                    next_recovered_ref_val = 0 if next_recovered_ref_val == 1 else 1
                    recovered_ref_clk_transitions = np.delete(recovered_ref_clk_transitions, 0)
                if(ref_clk_transition <= mclk_transition):
                    # print(f"ref_clk_transition {ref_clk_transition}")
                    self.vcd_writer.change(self.vcd_vars["ref_clock_var"], ref_clk_transition, ref_clk_val)
                    ref_clk_val = 0 if ref_clk_val == 1 else 1
                    ref_clk_transitions = np.delete(ref_clk_transitions, 0)

            # print(f"mclk_transition {mclk_transition}")
            self.vcd_writer.change(self.vcd_vars["mclk_clock_var"], mclk_transition, next_mclk_val)
            next_mclk_val = 0 if next_mclk_val == 1 else 1



def run_sim(ref_frequency):
    sw_pll = sw_pll_ctrl(multiplier, ref_to_loop_call_rate, 1.0, 2.0, Kii=0.01, verbose=False)
    mclk_count_end_float = 0.0
    real_time = 0.0
    # actual_mclk_frequency = target_mclk_frequency
    actual_mclk_frequency = target_mclk_frequency * (1 - 200 / 1000000)# initial value which is some PPM off

    freq_log = []
    target_log = []

    vcd = sw_pll_vdd()
    for count in range(125):
        print(f"Loop: count: {count}")
        mclk_count_start_float = mclk_count_end_float
        mclk_count_float_inc = actual_mclk_frequency / ref_frequency * ref_to_loop_call_rate
     
        mclk_count_end_float += mclk_count_float_inc
        actual_mclk_frequency, lock_status = sw_pll.do_control(mclk_count_end_float)
        
        # vcd.do_vcd(real_time, ref_frequency, mclk_count_start_float, mclk_count_end_float, sw_pll.get_error(), count, lock_status)

        print(f"actual_mclk_frequency: {actual_mclk_frequency}, lock_status: {sw_pll_ctrl.lock_status_lookup[lock_status]}")
     
        freq_log.append(actual_mclk_frequency)
        target_log.append(ref_frequency * multiplier)

        real_time += ref_to_loop_call_rate / ref_frequency

        if count == 25:
            ref_frequency = 48010

        if count == 50:
            ref_frequency = 48020

        if count == 65:
            ref_frequency = 47990

        if count == 100:
            ref_frequency = 48000

        print()

    plt.plot(freq_log, color='red', marker='o', label='actual frequency')
    plt.plot(target_log, color='blue', marker='.', label='target frequency')
    plt.title('PLL tracking', fontsize=14)
    plt.xlabel(f'loop_cycle {ref_to_loop_call_rate}', fontsize=14)
    plt.ylabel('Frequency', fontsize=10)
    plt.legend(loc="upper right")
    plt.grid(True)
    plt.show()
    # plt.savefig("pll.png")


pll_set = app_pll_frac_calc(24000000.0, 506, 3, 1, 30, 19, 21, verbose=True)
print(pll_set.get_output_freqency())

# output_frequency, vco_freq, RD, FD, FOD, ppm = get_pll_solution(xtal_frequency, target_mclk_frequency)
# print(output_frequency, vco_freq, RD, FD, FOD, ppm)

parse_h_file("fractions.h", 80)

run_sim(ref_frequency)