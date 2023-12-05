# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from sw_pll.app_pll_model import register_file, app_pll_frac_calc
import matplotlib.pyplot as plt
import numpy as np
import os
import re
from pathlib import Path

"""
This file contains implementations of digitally controlled oscillators.
It uses the app_pll_model underneath to turn a control signal into a 
calculated output frequency.

It currently contains two implementations of DCO:

-   A lookup table version which is efficient in computation and offers
    a range of frequencies based on a pre-calculated look up table (LUT)
-   A Sigma Delta Modulator which typically uses a dedicated thread to
    run the modulator but results in lower noise in the audio spectrum
"""


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

        self.last_output_frequency = self.app_pll.update_frac_reg(self.lut[self.get_lut_size() // 2] | app_pll_frac_calc.frac_enable_mask)
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
        Input a control value and output a SDM signal
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
    dco = lut_dco()
    print(f"LUT size: {dco.get_lut_size()}")
    dco.plot_freq_range()
    dco.print_stats(12288000)

    sdm_dco = sigma_delta_dco("24.576_1M")
    sdm_dco.write_register_file()
    sdm_dco.print_stats()
    sdm_dco.plot_freq_range()
    for i in range(30):
        output_frequency = sdm_dco.do_modulate(500000)
        # print(i, output_frequency)
