# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from sw_pll.pfd_model import port_timer_pfd
from sw_pll.dco_model import lut_dco, sigma_delta_dco, lock_status_lookup
from sw_pll.controller_model import lut_pi_ctrl, sdm_pi_ctrl
from sw_pll.analysis_tools import audio_modulator
import matplotlib.pyplot as plt
import numpy as np


def plot_simulation(freq_log, target_freq_log, real_time_log, name="sw_pll_tracking.png"):
    plt.clf()
    plt.plot(real_time_log, freq_log, color='red', marker='.', label='actual frequency')
    plt.plot(real_time_log, target_freq_log, color='blue', marker='.', label='target frequency')
    plt.title('PLL tracking', fontsize=14)
    plt.xlabel(f'Time in seconds', fontsize=10)
    plt.ylabel('Frequency', fontsize=10)
    plt.legend(loc="upper right")
    plt.grid(True)
    # plt.show()
    plt.savefig(name, dpi=150)


##############################
# LOOK UP TABLE IMPLEMENTATION
##############################

class sim_sw_pll_lut:
    def __init__(   self,
                    target_output_frequency,
                    nominal_nominal_control_rate_frequency,
                    Kp,
                    Ki,
                    Kii=None):

        self.pfd = port_timer_pfd(target_output_frequency, nominal_nominal_control_rate_frequency)
        self.controller = lut_pi_ctrl(Kp, Ki)
        self.dco = lut_dco()

        self.target_output_frequency = target_output_frequency
        self.time = 0.0
        self.control_time_inc = 1 / nominal_nominal_control_rate_frequency

    def do_control_loop(self, output_clock_count, period_fraction=1.0, verbose=False):
        """
        This should be called once every control period nominally
        """

        error, first_loop = self.pfd.get_error(output_clock_count, period_fraction=period_fraction)
        dco_ctl = self.controller.get_dco_control_from_error(error, first_loop=first_loop)
        output_frequency, lock_status = self.dco.get_frequency_from_dco_control(dco_ctl)
        if first_loop: # We cannot claim to be locked if the PFD sees an error
            lock_status = -1

        if verbose:
            print(f"Raw error: {error}")
            print(f"dco_ctl: {dco_ctl}")
            print(f"Output_frequency: {output_frequency}")
            print(f"Lock status: {lock_status_lookup[lock_status]}")

        return output_frequency, lock_status



def run_lut_sw_pll_sim():
    nominal_output_hz = 12288000
    nominal_control_rate_hz = 93.75
    output_frequency = nominal_output_hz
    simulation_iterations = 100
    Kp = 0.0
    Ki = 0.1
    Kii = 0.0

    sw_pll = sim_sw_pll_lut(nominal_output_hz, nominal_control_rate_hz, Kp, Ki, Kii=Kii)
    output_clock_count = 0

    test_tone_hz = 1000
    audio = audio_modulator(simulation_iterations * 1 / nominal_control_rate_hz, sample_rate=48000, test_tone_hz=test_tone_hz)

    
    freq_log = []
    target_freq_log = []
    real_time_log = []
    real_time = 0.0
    period_fraction = 1.0

    ppm_shift = -200

    for loop in range(simulation_iterations):
        output_frequency, lock_status = sw_pll.do_control_loop(output_clock_count, period_fraction=period_fraction, verbose=True)

        # Now work out how many output clock counts this translates to
        measured_clock_count_inc = output_frequency / nominal_control_rate_hz * (1 - ppm_shift / 1e6)

        # Add some jitter to the output_count to test jitter compensation
        jitter_amplitude = 100 # measured in output clock counts
        clock_count_sampling_jitter = jitter_amplitude * (np.random.sample() - 0.5)         
        period_fraction = (measured_clock_count_inc + clock_count_sampling_jitter) * measured_clock_count_inc

        output_clock_count += measured_clock_count_inc * period_fraction

        real_time_log.append(real_time)
        target_output_frequency = nominal_output_hz * (1 + ppm_shift / 1e6)
        target_freq_log.append(target_output_frequency)
        freq_log.append(output_frequency)

        time_inc = 1 / nominal_control_rate_hz
        scaled_frequency_shift = test_tone_hz * (output_frequency - target_output_frequency) / target_output_frequency
        audio.apply_frequency_deviation(real_time, real_time + time_inc, scaled_frequency_shift)

        real_time += time_inc


    plot_simulation(freq_log, target_freq_log, real_time_log, "tracking_lut.png")
    
    audio.modulate_waveform()
    audio.save_modulated_wav("modulated_tone_1000Hz_lut.wav")
    audio.plot_modulated_fft("modulated_fft_lut.png", skip_s=real_time / 2) # skip so we ignore the inital lock period



######################################
# SIGMA DELTA MODULATOR IMPLEMENTATION
######################################

class sim_sw_pll_sd:
    def __init__(   self,
                    target_output_frequency,
                    nominal_nominal_control_rate_frequency,
                    Kp,
                    Ki,
                    Kii=None):

        self.pfd = port_timer_pfd(target_output_frequency, nominal_nominal_control_rate_frequency, ppm_range=20000)
        self.controller = sdm_pi_ctrl(Kp, Ki, Kii)
        self.dco = sigma_delta_dco("24.576")

        self.target_output_frequency = target_output_frequency
        self.time = 0.0
        self.control_time_inc = 1 / nominal_nominal_control_rate_frequency

        self.control_setting = (self.dco.ds_in_max + self.dco.ds_in_min) / 2 # Mid way


    def do_control_loop(self, output_clock_count, verbose=False):

        error, first_loop = self.pfd.get_error(output_clock_count)
        ctrl_output = self.controller.do_control_from_error(error)
        self.control_setting = ctrl_output

        if verbose:
            print(f"Raw error: {error}")
            print(f"ctrl_output: {ctrl_output}")
            print(f"Lock status: {lock_status_lookup[lock_status]}")

        return self.control_setting

    def do_sigma_delta(self):
        frequncy, lock_status = self.dco.do_modulate(self.control_setting)

        return frequncy, lock_status


def run_sd_sw_pll_sim():
    nominal_output_hz = 24576000
    nominal_control_rate_hz = 100
    nominal_sd_rate_hz = 1e6
    output_frequency = nominal_output_hz
    
    simulation_iterations = 2000000
    Kp = 0.0
    Ki = 32.0
    Kii = 0.25

    sw_pll = sim_sw_pll_sd(nominal_output_hz, nominal_control_rate_hz, Kp, Ki, Kii=Kii)
    output_clock_count = 0

    test_tone_hz = 1000
    audio = audio_modulator(simulation_iterations * 1 / nominal_sd_rate_hz, sample_rate=6144000, test_tone_hz=test_tone_hz)

    freq_log = []
    target_freq_log = []
    real_time_log = []
    real_time = 0.0

    ppm_shift = +0

    # For working out when to do control calls
    control_time_inc = 1 / nominal_control_rate_hz
    control_time_trigger = control_time_inc

    for loop in range(simulation_iterations):

        output_frequency, lock_status = sw_pll.do_sigma_delta()

        # Log results
        freq_log.append(output_frequency)
        target_output_frequency = nominal_output_hz * (1 + ppm_shift / 1e6)
        target_freq_log.append(target_output_frequency)
        real_time_log.append(real_time)

        # Modulate tone
        sdm_time_inc = 1 / nominal_sd_rate_hz
        scaled_frequency_shift = test_tone_hz * (output_frequency - target_output_frequency) / target_output_frequency
        audio.apply_frequency_deviation(real_time, real_time + sdm_time_inc, scaled_frequency_shift)

        # Accumulate the real number of output clocks
        output_clock_count += output_frequency / nominal_sd_rate_hz * (1 - ppm_shift / 1e6)

        # Check for control loop run ready
        if real_time > control_time_trigger:
            control_time_trigger += control_time_inc

            # Now work out how many output clock counts this translates to
            sw_pll.do_control_loop(output_clock_count)

        real_time += sdm_time_inc


    plot_simulation(freq_log, target_freq_log, real_time_log, "tracking_sdm.png")

    audio.modulate_waveform()
    audio.save_modulated_wav("modulated_tone_1000Hz_sdm.wav")
    audio.plot_modulated_fft("modulated_fft_sdm.png", skip_s=real_time/2) # skip so we ignore the inital lock period


if __name__ == '__main__':
    # run_lut_sw_pll_sim()
    run_sd_sw_pll_sim()
        