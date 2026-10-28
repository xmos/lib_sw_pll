# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from sw_pll.app_pll_model import register_file, app_pll_frac_calc
import math
from numbers import Integral
import matplotlib.pyplot as plt
import numpy as np
import os
import re
from pathlib import Path

"""
This file contains implementations of digitally controlled oscillators.
The LUT and software SDM implementations use app_pll_model to turn a control
signal into a calculated output frequency. MASH supports both its average
transfer function and the hardware accumulator/carry sequence.

It currently contains three implementations of DCO:

-   A lookup table version which is efficient in computation and offers
    a range of frequencies based on a pre-calculated look up table (LUT)
-   A Sigma Delta Modulator which typically uses a dedicated thread to
    run the modulator but results in lower noise in the audio spectrum
-   A hardware MASH DCO for xcore-400, controlled by a raw 20-bit fractional
    word, with average-frequency and clock-stepped modulation interfaces
"""


# PLL macro limits in Hz: VCO is before the fixed /2; output is after output_div.
PLL_VCO_MIN_HZ = 720e6
PLL_VCO_MAX_HZ = 3600e6
PLL_OUTPUT_MAX_HZ = 800e6

lock_status_lookup = {-1 : "UNLOCKED LOW", 0 : "LOCKED", 1 : "UNLOCKED HIGH"}
lock_count_threshold = 10

##############################
# LOOK UP TABLE IMPLEMENTATION
##############################

class lut_dco:
    """ 
        This class parses a pre-generated fractions.h file and builds a lookup table so that the values can be
        used by the sw_pll simulation. It may be used directly but is generally used a sub class of error_to_pll_output_frequency.
    """

    def __init__(self, header_file = "fractions.h", verbose=False):   # fixed header_file name by pll_calc.py 
        """
        Constructor for the LUT DCO. Reads the pre-calculated header filed and produces the LUT which contains
        the pll fractional register settings (16b) for each of the entries. Also a
        """

        self.lut, self.min_frac, self.max_frac = self._read_lut_header(header_file)
        input_freq, F, R, f, p, OD, ACD = self._parse_register_file(register_file)
        self.app_pll = app_pll_frac_calc(input_freq, F, R, f, p, OD, ACD)

        a = self.lut[self.get_lut_size() // 2]
        b = app_pll_frac_calc.frac_enable_mask

        self.last_output_frequency = self.app_pll.update_frac_reg(self.lut[self.get_lut_size() // 2].astype(int) | app_pll_frac_calc.frac_enable_mask)
        self.lock_status = -1
        self.lock_count = lock_count_threshold

    def _read_lut_header(self, header_file):
        """
        read and parse the pre-written LUT
        """
        if not os.path.exists(header_file):
            assert False, f"Please initialize a lut_dco to produce a parsable header file {header_file}"

        with open(header_file) as hdr:
            header = hdr.readlines()
            min_frac = 1.0
            max_frac = 0.0
            for line in header:
                regex_ne = fr"frac_values_?\d*\[(\d+)].*"
                match = re.search(regex_ne, line)
                if match:
                    num_entries = int(match.groups()[0])
                    # print(f"num_entries: {num_entries}")
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

        # print(f"min_frac: {min_frac} max_frac: {max_frac}")
        return lut, min_frac, max_frac

    def _parse_register_file(self, register_file):
        """
            This method reads the pre-saved register setup comments from get_pll_solution and parses them into parameters that
            can be used for later simulation.
        """
        if not os.path.exists(register_file):
            assert False, f"Please initialize a lut_dco to produce a parsable register setup file {register_file}"

        with open(register_file) as rf:
            reg_file = rf.read().replace('\n', '')
            input_freq = int(re.search(r".+Input freq:\s+(\d+).+", reg_file).groups()[0])
            F = int(re.search(r".+F:\s+(\d+).+", reg_file).groups()[0])
            R = int(re.search(r".+R:\s+(\d+).+", reg_file).groups()[0])
            f = int(re.search(r".+f:\s+(\d+).+", reg_file).groups()[0])
            p = int(re.search(r".+p:\s+(\d+).+", reg_file).groups()[0])
            OD = int(re.search(r".+OD:\s+(\d+).+", reg_file).groups()[0])
            ACD = int(re.search(r".+ACD:\s+(\d+).+", reg_file).groups()[0])

        return input_freq, F, R, f, p, OD, ACD

    def get_lut(self):
        """
        Return the look up table
        """
        return self.lut

    def get_lut_size(self):
        """
        Return the size of look up table
        """
        return np.size(self.lut)

    def print_stats(self, target_output_frequency):
        """
        Returns a summary of the LUT range and steps.
        """
        lut = self.get_lut()
        steps = np.size(lut)

        register = int(lut[0])
        min_freq = self.app_pll.update_frac_reg(register | app_pll_frac_calc.frac_enable_mask)

        register = int(lut[steps // 2])
        mid_freq = self.app_pll.update_frac_reg(register | app_pll_frac_calc.frac_enable_mask)

        register = int(lut[-1])
        max_freq = self.app_pll.update_frac_reg(register | app_pll_frac_calc.frac_enable_mask)

        ave_step_size = (max_freq - min_freq) / steps

        print(f"LUT min_freq: {min_freq:.0f}Hz")
        print(f"LUT mid_freq: {mid_freq:.0f}Hz")
        print(f"LUT max_freq: {max_freq:.0f}Hz")
        print(f"LUT entries: {steps} ({steps*2} bytes)")
        print(f"LUT average step size: {ave_step_size:.6}Hz, PPM: {1e6 * ave_step_size/mid_freq:.6}")
        print(f"PPM range: {1e6 * (1 - target_output_frequency / min_freq):.6}")
        print(f"PPM range: +{1e6 * (max_freq / target_output_frequency - 1):.6}")

        return min_freq, mid_freq, max_freq, steps


    def plot_freq_range(self):
        """
        Generates a plot of the frequency range of the LUT and
        visually shows the spacing of the discrete frequencies
        that it can produce.
        """

        frequencies = []
        for step in range(self.get_lut_size()):
            register = int(self.lut[step])
            self.app_pll.update_frac_reg(register | app_pll_frac_calc.frac_enable_mask)
            frequencies.append(self.app_pll.get_output_frequency())

        plt.clf()
        plt.plot(frequencies, color='green', marker='.', label='frequency')
        plt.title('PLL fractional range', fontsize=14)
        plt.xlabel(f'LUT index', fontsize=14)
        plt.ylabel('Frequency', fontsize=10)
        plt.legend(loc="upper right")
        plt.grid(True)
        # plt.show()
        plt.savefig("lut_dco_range.png", dpi=150)

    def get_frequency_from_dco_control(self, dco_ctrl):
        """
        given a set_point, a LUT, and an APP_PLL, calculate the frequency
        """

        if dco_ctrl is None:
            return self.last_output_frequency, self.lock_status

        num_entries = self.get_lut_size()

        set_point = int(dco_ctrl)
        if set_point < 0:
            set_point = 0
            self.lock_status = -1
            self.lock_count = lock_count_threshold
        elif set_point >= num_entries:
            set_point = num_entries - 1
            self.lock_status = 1
            self.lock_count = lock_count_threshold
        else:
            set_point = set_point
            if self.lock_count > 0:
                self.lock_count -= 1
            else:
                self.lock_status = 0

        register = int(self.lut[set_point])

        output_frequency = self.app_pll.update_frac_reg(register | app_pll_frac_calc.frac_enable_mask)
        self.last_output_frequency = output_frequency
        return output_frequency, self.lock_status



######################################
# HARDWARE MASH IMPLEMENTATION
######################################

class mash:
    """Integer model of the RTL's 20-bit MASH 1-1-1 modulator.

    Each do_mash_int call samples the combinational correction immediately
    before a selected int_clk rising edge, then commits the nonblocking
    register updates. Clock selection (i_fben normally, i_refclk in test mode)
    is the caller's responsibility; Python calls do not represent wall time.
    The low-level model accepts the full 20-bit hardware input range, unlike
    the DCO interface's narrower firmware policy window.
    """

    mash_scale = 1 << 20

    def __init__(self):
        self.reset_mash()

    def reset_mash(self):
        """Apply the RTL reset state, including its first-accumulator LSB seed."""
        self.delay0_q = 1
        self.delay1_q = 0
        self.delay2_q = 0
        self.carry1_q = 0
        self.carry2_q = 0
        self.carry2_q_q = 0
        self.mash_out = 0

    def do_mash_int(self, mash_in, enable=True):
        """Return a signed -3..+4 correction and advance one enabled cycle.

        This models only the MASH block, not the independent PWM branch or
        the final PLL field-width wrapping. Disabling gates the correction to
        zero and freezes all accumulator and delayed-carry registers.
        """
        if not isinstance(mash_in, Integral) or not 0 <= int(mash_in) < self.mash_scale:
            raise ValueError("MASH input must be an unsigned 20-bit integer")
        if not enable:
            self.mash_out = 0
            return self.mash_out

        # Each adder exposes a carry and passes only its 20-bit remainder to
        # the next stage. Calculate all sums from the old register state.
        mask = self.mash_scale - 1
        sum0 = int(mash_in) + self.delay0_q
        sum1 = (sum0 & mask) + self.delay1_q
        sum2 = (sum1 & mask) + self.delay2_q
        carry0 = sum0 >> 20
        carry1 = sum1 >> 20
        carry2 = sum2 >> 20
        self.mash_out = (carry0 + carry1 - self.carry1_q + carry2
                         - 2 * self.carry2_q + self.carry2_q_q)

        # Commit simultaneously, matching the RTL's nonblocking assignments.
        self.delay0_q = sum0 & mask
        self.delay1_q = sum1 & mask
        self.delay2_q = sum2 & mask
        self.carry1_q = carry1
        self.carry2_q_q = self.carry2_q
        self.carry2_q = carry2
        return self.mash_out


class mash_dco(mash):
    """Model average and clock-stepped xcore-400 MASH DCO frequencies, in Hz.

    Register arguments are the generated APP_PLL_CTL_REG, APP_PLL_DIV_REG,
    and raw APP_PLL_MASH_REG values, not physical divider ratios. Hardware
    enable bits are ignored when decoding the integer dividers: construction
    represents an enabled MASH-only PLL, with PWM disabled.

    get_frequency_from_dco_control models software control updates using the
    average transfer function. do_modulate advances one hardware MASH cycle
    and returns the ideal frequency implied by its divider correction. Neither
    interface models analog PLL dynamics or predicts physical output jitter.
    """

    mash_scale = 1 << 20
    # Match the inward-rounded firmware limits in sw_pll_mash.h.
    mash_in_min = 0x1999A
    mash_in_max = 0xE6666

    def __init__(self, app_pll_ctl_reg_val, app_pll_div_reg_val,
                 nominal_mash_val, input_frequency=24000000, verbose=False):
        for name, value in (("app_pll_ctl_reg_val", app_pll_ctl_reg_val),
                            ("app_pll_div_reg_val", app_pll_div_reg_val)):
            if not isinstance(value, Integral) or not 0 <= int(value) <= 0xFFFFFFFF:
                raise ValueError(f"{name} must be an unsigned 32-bit register value")
        if not math.isfinite(input_frequency) or input_frequency <= 0:
            raise ValueError("input_frequency must be positive and finite (Hz)")
        if not isinstance(nominal_mash_val, Integral) or not self.mash_in_min <= int(nominal_mash_val) <= self.mash_in_max:
            raise ValueError("nominal_mash_val must be an integer inside the firmware MASH window")

        self.app_pll_ctl_reg_val = int(app_pll_ctl_reg_val)
        self.app_pll_div_reg_val = int(app_pll_div_reg_val)
        self.input_frequency = input_frequency
        self.nominal_mash_val = int(nominal_mash_val)
        self.verbose = verbose
        # Decode minus-one encoded fields; the MASH payload has no such offset.
        self.F = (self.app_pll_ctl_reg_val >> 8) & 0x1FFF
        self.R = self.app_pll_ctl_reg_val & 0x3F
        self.OD = (self.app_pll_ctl_reg_val >> 23) & 0x7
        self.ACD = self.app_pll_div_reg_val & 0xFFFF
        if not 4 <= self.F <= 8187:
            raise ValueError("F must leave room for instantaneous MASH corrections (-3..+4)")
        self.step_hz = self.input_frequency / (
            4 * (self.R + 1) * (self.OD + 1) * (self.ACD + 1) * self.mash_scale)
        # Validate the intended usable range, not only the nominal point. An
        # averaged model must not silently accept tuning outside macro limits.
        for word in (self.mash_in_min, self.mash_in_max):
            vco_freq = self.input_frequency * (self.F + 1 + word / self.mash_scale) / (self.R + 1)
            if not PLL_VCO_MIN_HZ <= vco_freq <= PLL_VCO_MAX_HZ or vco_freq / (2 * (self.OD + 1)) > PLL_OUTPUT_MAX_HZ:
                raise ValueError("MASH tuning window exceeds VCO or PLL-output limits")

        self.current_mash_val = self.nominal_mash_val
        self.last_output_frequency = self._word_to_frequency(self.current_mash_val)
        self.lock_status = -1
        self.lock_count = lock_count_threshold
        super().__init__()

    @classmethod
    def from_register_file(cls, header_file=register_file, input_frequency=24000000, verbose=False):
        """Read the three literal register definitions generated by pll_calc.

        Input frequency is supplied explicitly in Hz; generated headers need
        not contain the comment metadata required by the legacy LUT parser.
        C expressions are deliberately not evaluated as executable Python.
        """
        text = Path(header_file).read_text()
        registers = {}
        for name in ("APP_PLL_CTL_REG", "APP_PLL_DIV_REG", "APP_PLL_MASH_REG"):
            matches = re.findall(
                r"^[ \t]*#define[ \t]+" + name
                + r"[ \t]+(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]*[ \t]*"
                + r"(?://[^\r\n]*|/\*[^\r\n]*\*/[ \t]*)?\r?$",
                text, re.MULTILINE)
            if len(matches) != 1:
                raise ValueError(f"Expected one literal definition of {name} in {header_file}")
            literal = matches[0]
            registers[name] = int(literal, 16 if literal.lower().startswith("0x") else 10)
        return cls(registers["APP_PLL_CTL_REG"], registers["APP_PLL_DIV_REG"],
                   registers["APP_PLL_MASH_REG"], input_frequency, verbose)

    def _word_to_frequency(self, mash_word):
        """Include the macro /2 and the application duty-cycle /2 exactly once."""
        return self.step_hz * ((self.F + 1) * self.mash_scale + mash_word)

    def do_modulate(self, dco_ctrl=None, enable=True):
        """Advance one feedback-clock cycle and return ideal divider-derived Hz.

        Call once per simulated MASH clock rising edge: i_fben in normal mode,
        or i_refclk in test mode. If i_fben marks each completed feedback divide,
        its locked rate is approximately input_frequency / (R + 1), e.g. 24 MHz
        for a 24 MHz input and encoded R=0; confirm the macro's fben timing.
        This is not the software controller update rate. Calls need not execute
        in real time, but spectral analysis must use the simulated clock rate.

        An optional absolute word is truncated and clipped like a firmware
        control request; None reuses the last word, but still clocks MASH.
        Software lock-count state is deliberately not advanced at this much
        faster rate. Inspect mash_out for the signed divider correction.
        reset_mash() reseeds the modulator without changing the tuning word.

        Disabled modulation returns the unmodified base-divider frequency.
        This is not the actual analog output response to a divider change.
        """
        if dco_ctrl is not None:
            if not math.isfinite(dco_ctrl):
                raise ValueError("MASH control must be finite")
            self.current_mash_val = min(self.mash_in_max, max(self.mash_in_min, int(dco_ctrl)))
            self.last_output_frequency = self._word_to_frequency(self.current_mash_val)
        correction = self.do_mash_int(self.current_mash_val, enable=enable)
        return self._word_to_frequency(correction * self.mash_scale)

    def get_frequency_from_dco_control(self, dco_ctrl):
        """Return (average Hz, lock status) for an absolute MASH control word.

        Like lut_dco, None holds both frequency and lock-counter state. A
        controller forms its absolute word as nominal_mash_val minus PI error.
        Clipping and the lock countdown follow sw_pll_mash_do_control_from_error;
        reported lock is a saturation/countdown heuristic, not a phase check.
        """
        if dco_ctrl is None:
            return self.last_output_frequency, self.lock_status
        if not math.isfinite(dco_ctrl):
            raise ValueError("MASH control must be finite")
        requested_word = int(dco_ctrl)
        self.current_mash_val = min(self.mash_in_max, max(self.mash_in_min, requested_word))
        if requested_word < self.mash_in_min:
            self.lock_status = -1
            self.lock_count = lock_count_threshold
        elif requested_word > self.mash_in_max:
            self.lock_status = 1
            self.lock_count = lock_count_threshold
        elif self.lock_count > 0:
            self.lock_count -= 1
        else:
            self.lock_status = 0
        self.last_output_frequency = self._word_to_frequency(self.current_mash_val)
        return self.last_output_frequency, self.lock_status

    def print_stats(self):
        """Report the average tuning range without changing control/lock state."""
        min_freq = self._word_to_frequency(self.mash_in_min)
        nominal_freq = self._word_to_frequency(self.nominal_mash_val)
        max_freq = self._word_to_frequency(self.mash_in_max)
        steps = self.mash_in_max - self.mash_in_min + 1
        symmetric_ppm = min(nominal_freq - min_freq, max_freq - nominal_freq) / nominal_freq * 1e6
        print(f"MASH min_freq: {min_freq:.9f}Hz")
        print(f"MASH nominal_freq: {nominal_freq:.9f}Hz")
        print(f"MASH max_freq: {max_freq:.9f}Hz")
        print(f"MASH step size: {self.step_hz:.9f}Hz, settings: {steps}")
        print(f"MASH symmetric range: +/-{symmetric_ppm:.3f}ppm")
        return min_freq, nominal_freq, max_freq, steps


######################################
# SIGMA DELTA MODULATOR IMPLEMENTATION
######################################

class sdm:
    """
    Experimental - taken from lib_xua synchronous branch
    Third order, 9 level output delta sigma. 20 bit unsigned input.
    """
    # Limits for SDM modulator for stability
    sdm_in_max = 980000
    sdm_in_min = 60000

    def __init__(self):
        # Delta sigma modulator state
        self.sdm_x1 = 0
        self.sdm_x2 = 0
        self.sdm_x3 = 0

    # # generalized version without fixed point shifts. WIP!!
    # # takes a Q20 number from 60000 to 980000 (or 0.0572 to 0.934)
    # # This is work in progress - the integer model matches the firmware better
    # def do_sigma_delta(self, sdm_in):
    #     if sdm_in > self.sdm_in_max:
    #         print(f"SDM Pos clip: {sdm_in}, {self.sdm_in_max}")
    #         sdm_in = self. sdm_in_max
    #         self.lock_status = 1

    #     elif sdm_in < self.sdm_in_min:
    #         print(f"SDM Neg clip: {sdm_in}, {self.sdm_in_min}")
    #         sdm_in = self.sdm_in_min
    #         self.lock_status = -1

    #     else:
    #         self.lock_status = 0

    #     sdm_out = int(self.sdm_x3 * 0.002197265625)

    #     if sdm_out > 8:
    #         sdm_out = 8
    #     if sdm_out < 0:
    #         sdm_out = 0
        
    #     self.sdm_x3 += int((self.sdm_x2 * 0.03125) - (sdm_out * 768))
    #     self.sdm_x2 += int((self.sdm_x1 * 0.03125) - (sdm_out * 16384))
    #     self.sdm_x1 += int(sdm_in - (sdm_out * 131072))

    #     return int(sdm_out), self.lock_status

    def do_sigma_delta_int(self, sdm_in):
        # takes a Q20 number from 60000 to 980000 (or 0.0572 to 0.934)
        # Third order, 9 level output delta sigma. 20 bit unsigned input.
        sdm_in = int(sdm_in)

        sdm_out = ((self.sdm_x3<<4) + (self.sdm_x3<<1)) >> 13

        if sdm_out > 8:
            sdm_out = 8
        if sdm_out < 0:
            sdm_out = 0

        self.sdm_x3 += (self.sdm_x2>>5) - (sdm_out<<9) - (sdm_out<<8)
        self.sdm_x2 += (self.sdm_x1>>5) - (sdm_out<<14)
        self.sdm_x1 += sdm_in - (sdm_out<<17)

        return sdm_out


class sigma_delta_dco(sdm):
    """
    DCO based on the sigma delta modulator
    PLL solution profiles depending on target output clock

    These are designed to work with a SDM either running at
    1MHz:
    - 10ps jitter 100Hz-40kHz with very low freq noise floor -100dBc 
    or 500kHz:
    - 50ps jitter 100Hz-40kHz with low freq noise floor -93dBc.

    """

    profiles = {"24.576_1M": {"input_freq":24000000, "F":int(147.455 - 1), "R":1 - 1, "f":5 - 1, "p":11 - 1, "OD":6 - 1, "ACD":6 - 1, "output_frequency":24.576e6, "mod_init":478151, "sdm_rate":1000000},
                "22.5792_1M": {"input_freq":24000000, "F":int(135.474 - 1), "R":1 - 1, "f":9 - 1, "p":19 - 1, "OD":6 - 1, "ACD":6 - 1, "output_frequency":22.5792e6, "mod_init":498283, "sdm_rate":1000000},
                "24.576_500k": {"input_freq":24000000, "F":int(278.529 - 1), "R":2 - 1, "f":9 - 1, "p":17 - 1, "OD":2 - 1, "ACD":17 - 1, "output_frequency":24.576e6, "mod_init":553648, "sdm_rate":500000},
                "22.5792_500k": {"input_freq":24000000, "F":int(293.529 - 1), "R":2 - 1, "f":9 - 1, "p":17 - 1, "OD":3 - 1, "ACD":13 - 1, "output_frequency":22.5792e6, "mod_init":555326, "sdm_rate":500000}
                }


    def __init__(self, profile):
        """
        Create a sigmal delta DCO targetting either 24.576 or 22.5792MHz
        """               
        self.profile = profile
        self.p_value = 8 # 8 frac settings + 1 non frac setting

        input_freq, F, R, f, p, OD, ACD, _, _, _ = list(self.profiles[profile].values())

        self.app_pll = app_pll_frac_calc(input_freq, F, R, f, p, OD, ACD)
        self.sdm_out = 0
        self.f = 0

        sdm.__init__(self)

    def _sdm_out_to_freq(self, sdm_out):
        """
        Translate the SDM steps to register settings
        """
        if sdm_out == 0:
            # Step 0
            self.f = 0
            return self.app_pll.update_frac(self.f, self.p_value - 1, False)
        else:
            # Steps 1 to 8 inclusive
            self.f = sdm_out - 1
            return self.app_pll.update_frac(self.f, self.p_value - 1, True)

    def do_modulate(self, input):
        """
        Input a control value and advance one software SDM update.

        Call at the selected profile's simulated sdm_rate: 1 MHz (one sample
        per 1 us) for *_1M, or 500 kHz (one sample per 2 us) for *_500k.
        This matches the high-rate firmware modulation task, not the slower
        PI controller. Reuse the control value between controller updates.
        Calls need not execute in real time; use the profile's sdm_rate as the
        sample rate when analyzing the resulting sequence.
        """
        # self.sdm_out, lock_status = sdm.do_sigma_delta(self, input)
        self.sdm_out = sdm.do_sigma_delta_int(self, input)

        frequency = self._sdm_out_to_freq(self.sdm_out)
  
        return frequency

    def print_stats(self):
        """
        Returns a summary of the SDM range and steps.
        """

        steps = self.p_value + 1 # +1 we have frac off state
        min_freq = self._sdm_out_to_freq(0)
        max_freq = self._sdm_out_to_freq(self.p_value)
        target_output_frequency = self.profiles[self.profile]["output_frequency"]


        ave_step_size = (max_freq - min_freq) / steps

        print(f"SDM min_freq: {min_freq:.0f}Hz")
        print(f"SDM max_freq: {max_freq:.0f}Hz")
        print(f"SDM steps: {steps}")
        print(f"PPM range: {1e6 * (1 - target_output_frequency / min_freq):.6}")
        print(f"PPM range: +{1e6 * (max_freq / target_output_frequency - 1):.6}")

        return min_freq, max_freq, steps


    def plot_freq_range(self):
        """
        Generates a plot of the frequency range of the LUT and
        visually shows the spacing of the discrete frequencies
        that it can produce.
        """

        frequencies = []
        for step in range(self.p_value + 1): # +1 since p value is +1 in datasheet
            frequencies.append(self._sdm_out_to_freq(step))

        plt.clf()
        plt.plot(frequencies, color='green', marker='.', label='frequency')
        plt.title('PLL fractional range', fontsize=14)
        plt.xlabel(f'SDM step', fontsize=14)
        plt.ylabel('Frequency', fontsize=10)
        plt.legend(loc="upper right")
        plt.grid(True)
        # plt.show()
        plt.savefig("sdm_dco_range.png", dpi=150)

    def write_register_file(self):
        with open(register_file, "w") as reg_vals:
            reg_vals.write(f"/* Autogenerated SDM App PLL setup by {Path(__file__).name} using {self.profile} profile */\n")
            reg_vals.write(self.app_pll.gen_register_file_text())
            reg_vals.write(f"#define SW_PLL_SDM_CTRL_MID {self.profiles[self.profile]['mod_init']}\n")
            reg_vals.write(f"#define SW_PLL_SDM_RATE {self.profiles[self.profile]['sdm_rate']}\n")
            reg_vals.write("\n\n")

            return register_file


if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    do_lut_dco = False
    do_sdm_dco = False
    do_mash_dco = True

    # Test the LUT DCO and Sigma-Delta DCO implementations from existing header file
    if do_lut_dco:
        dco = lut_dco()
        print(f"LUT size: {dco.get_lut_size()}")
        dco.plot_freq_range()
        dco.print_stats(12288000)


    if do_sdm_dco:
        sdm_dco = sigma_delta_dco("24.576_1M")
        sdm_dco.write_register_file()
        sdm_dco.print_stats()
        sdm_dco.plot_freq_range()
        for i in range(30):
            output_frequency = sdm_dco.do_modulate(500000)
            # print(i, output_frequency)

    if do_mash_dco:
        # MASH uses generated register values, not a software SDM profile.
        # Resolve the example header relative to this file, independent of cwd,
        # and leave it unchanged: this demo only reads settings and prints output.
        mash_header = Path(__file__).resolve().parents[2] / "examples/app_simple_mash/src/register_setup.h"
        mash_model = mash_dco.from_register_file(str(mash_header))
        mash_model.print_stats()
        for cycle in range(30):
            output_frequency = mash_model.do_modulate()
            print(f"Cycle {cycle}: MASH correction {mash_model.mash_out:+d}, ideal frequency {output_frequency:.6f}Hz")