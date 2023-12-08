# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from sw_pll.app_pll_model import get_pll_solution
from sw_pll.pfd_model import port_timer_pfd
from sw_pll.dco_model import lut_dco, sigma_delta_dco, lock_status_lookup
from sw_pll.controller_model import lut_pi_ctrl, sdm_pi_ctrl
from sw_pll.analysis_tools import audio_modulator
import matplotlib.pyplot as plt
import numpy as np
import sys


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
    """
    Complete SW PLL simulation class which contains all of the components including
    Phase Frequency Detector, Controller and Digitally Controlled Oscillator using
    a Look Up Table method.
    """ 
    def __init__(   self,
                    target_output_frequency,
                    nominal_nominal_control_rate_frequency,
                    Kp,
                    Ki,
                    Kii=None):
        """
        Init a Lookup Table based SW_PLL instance
        """

        self.pfd = port_timer_pfd(target_output_frequency, nominal_nominal_control_rate_frequency)
        self.controller = lut_pi_ctrl(Kp, Ki, Kii=Kii, verbose=False)
        self.dco = lut_dco(verbose=False)

        self.target_output_frequency = target_output_frequency
        self.time = 0.0
        self.control_time_inc = 1 / nominal_nominal_control_rate_frequency

    def do_control_loop(self, output_clock_count, period_fraction=1.0, verbose=False):
        """
        This should be called once every control period.

        output_clock_count is fed into the PDF and period_fraction is an optional jitter
        reduction term where the control period is not exact, but can be compensated for.
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
    """
    Test program / example showing how to run the simulator object    
    """

    # Example profiles to produce typical frequencies seen in audio systems. ALl assume 24MHz input clock to the hardware PLL. 
    profiles = [
        # 0 - 12.288MHz with 48kHz ref (note also works with 16kHz ref), +-250PPM, 29.3Hz steps, 426B LUT size
        {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":80, "min_F":200, "ppm_max":5, "fracmin":0.843, "fracmax":0.95},
        # 1 - 12.288MHz with 48kHz ref (note also works with 16kHz ref), +-500PPM, 30.4Hz steps, 826B LUT size
        {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":80, "min_F":200, "ppm_max":5, "fracmin":0.695, "fracmax":0.905},
        # 2 - 24.576MHz with 48kHz ref (note also works with 16kHz ref), +-1000PPM, 31.9Hz steps, 1580B LUT size
        {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":90, "min_F":140, "ppm_max":5, "fracmin":0.49, "fracmax":0.81},
        # 3 - 24.576MHz with 48kHz ref (note also works with 16kHz ref), +-100PPM, 9.5Hz steps, 1050B LUT size
        {"nominal_ref_frequency":48000.0, "target_output_frequency":24576000, "max_denom":120, "min_F":400, "ppm_max":5, "fracmin":0.764, "fracmax":0.884},
        # 4 - 6.144MHz with 16kHz ref, +-200PPM, 30.2Hz steps, 166B LUT size
        {"nominal_ref_frequency":16000.0, "target_output_frequency":6144000, "max_denom":40, "min_F":400, "ppm_max":5, "fracmin":0.635, "fracmax":0.806},
        ]

    profile_used = 1
    profile = profiles[profile_used]

    nominal_output_hz = profile["target_output_frequency"]

    # This generates the needed header files read later by sim_sw_pll_lut
    # 12.288MHz with 48kHz ref (note also works with 16kHz ref), +-500PPM, 30.4Hz steps, 826B LUT size
    get_pll_solution(24000000, nominal_output_hz, max_denom=80, min_F=200, ppm_max=5, fracmin=0.695, fracmax=0.905)
            
    output_frequency = nominal_output_hz
    nominal_control_rate_hz = profile["nominal_ref_frequency"] / 512
    simulation_iterations = 100
    Kp = 0.0
    Ki = 1.0
    Kii = 0.0

    sw_pll = sim_sw_pll_lut(nominal_output_hz, nominal_control_rate_hz, Kp, Ki, Kii=Kii)
    sw_pll.dco.print_stats(nominal_output_hz)
    
    output_clock_count = 0

    test_tone_hz = 1000
    audio = audio_modulator(simulation_iterations * 1 / nominal_control_rate_hz, sample_rate=48000, test_tone_hz=test_tone_hz)

    
    freq_log = []
    target_freq_log = []
    real_time_log = []
    real_time = 0.0
    period_fraction = 1.0

    ppm_shift = +50

    for loop in range(simulation_iterations):
        output_frequency, lock_status = sw_pll.do_control_loop(output_clock_count, period_fraction=period_fraction, verbose=False)

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
    """
    Complete SW PLL simulation class which contains all of the components including
    Phase Frequency Detector, Controller and Digitally Controlled Oscillator using
    a Sigma Delta Modulator method.
    """ 

    def __init__(   self,
                    target_output_frequency,
                    nominal_nominal_control_rate_frequency,
                    Kp,
                    Ki,
                    Kii=None):
        """
        Init a Sigma Delta Modulator based SW_PLL instance
        """

        self.pfd = port_timer_pfd(target_output_frequency, nominal_nominal_control_rate_frequency, ppm_range=3000)
        self.dco = sigma_delta_dco("24.576_1M")
        self.controller = sdm_pi_ctrl( (self.dco.sdm_in_max + self.dco.sdm_in_min) / 2,
                                        self.dco.sdm_in_max,
                                        self.dco.sdm_in_min,
                                        Kp,
                                        Ki,
                                        Kii)

        self.target_output_frequency = target_output_frequency
        self.time = 0.0
        self.control_time_inc = 1 / nominal_nominal_control_rate_frequency

        self.control_setting = (self.controller.sdm_in_max + self.controller.sdm_in_min) / 2 # Mid way


    def do_control_loop(self, output_clock_count, verbose=False):
        """
        Run the control loop (which runs at a tiny fraction of the SDM rate)
        This should be called once every control period.

        output_clock_count is fed into the PDF and period_fraction is an optional jitter
        reduction term where the control period is not exact, but can be compensated for.
        """

        error, first_loop = self.pfd.get_error(output_clock_count)
        ctrl_output, lock_status = self.controller.do_control_from_error(error)
        self.control_setting = ctrl_output

        if verbose:
            print(f"Raw error: {error}")
            print(f"ctrl_output: {ctrl_output}")
            print(f"Lock status: {lock_status_lookup[lock_status]}")

        return self.control_setting

    def do_sigma_delta(self):
        """
        Run the SDM which needs to be run constantly at the SDM rate.
        See DCO (dco_model) for details
        """
        frequncy = self.dco.do_modulate(self.control_setting)

        return frequncy


def run_sd_sw_pll_sim():
    """
    Test program / example showing how to run the simulator object
    """
    nominal_output_hz = 24576000
    nominal_control_rate_hz = 100
    nominal_sd_rate_hz = 1e6
    output_frequency = nominal_output_hz
    
    simulation_iterations = 1000000
    Kp = 0.0
    Ki = 32.0
    Kii = 0.25

    sw_pll = sim_sw_pll_sd(nominal_output_hz, nominal_control_rate_hz, Kp, Ki, Kii=Kii)
    sw_pll.dco.write_register_file()
    sw_pll.dco.print_stats()

    output_clock_count = 0

    test_tone_hz = 1000
    audio = audio_modulator(simulation_iterations * 1 / nominal_sd_rate_hz, sample_rate=6144000, test_tone_hz=test_tone_hz)

    freq_log = []
    target_freq_log = []
    real_time_log = []
    real_time = 0.0

    ppm_shift = +50

    # For working out when to do control calls
    control_time_inc = 1 / nominal_control_rate_hz
    control_time_trigger = control_time_inc

    for loop in range(simulation_iterations):

        output_frequency = sw_pll.do_sigma_delta()

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
    audio.plot_modulated_fft("modulated_fft_sdm.png", skip_s=real_time / 2) # skip so we ignore the inital lock period


if __name__ == '__main__':
    if len(sys.argv) != 2:
        assert 0, "Please select either LUT or SDM: sw_pll_sim.py <LUT/SDM>"
    if sys.argv[1] == "LUT":
        run_lut_sw_pll_sim() # Run LUT sim - generates "register_setup.h" and "fractions.h"
    elif sys.argv[1] == "SDM":
        run_sd_sw_pll_sim() # Run SDM sim - generates "register_setup.h"
    else:
        assert 0, "Please select either LUT or SDM: sw_pll_sim.py <LUT/SDM>"