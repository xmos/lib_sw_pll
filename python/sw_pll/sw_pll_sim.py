# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from sw_pll.app_pll_model import get_pll_solution
from sw_pll.pfd_model import port_timer_pfd
from sw_pll.dco_model import (
    lut_dco, sigma_delta_dco, mash_dco, lock_status_lookup, lock_count_threshold)
from sw_pll.controller_model import lut_pi_ctrl, sdm_pi_ctrl, pi_ctrl
from sw_pll.analysis_tools import audio_modulator
from sw_pll.pll_calc import find_mash_pll
import math
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
        if target_output_frequency == 24576000:
            self.dco = sigma_delta_dco("24.576_1M")
        elif target_output_frequency == 22579200:
            self.dco = sigma_delta_dco("22.5792_1M")
        else:
            assert f"Inavlid target_output_frequency: {target_output_frequency}"

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


def run_sd_sw_pll_sim(nominal_output_hz):
    """
    Test program / example showing how to run the simulator object
    """

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
    audio.save_modulated_wav("modulated_tone_1000Hz_sdm.wav", output_sample_rate=48000)
    audio.plot_modulated_fft("modulated_fft_sdm.png", skip_s=real_time / 2) # skip so we ignore the inital lock period


######################################
# HARDWARE MASH IMPLEMENTATION
######################################

class sim_sw_pll_mash:
    """Floating-point software loop around the clock-stepped MASH DCO.

    The digital MASH recurrence is modeled explicitly. Optional first-order
    filtering approximates the analog PLL's frequency response; it is not a
    calibrated PLL model and must not be used to claim physical jitter figures.
    """

    def __init__(self, dco, target_output_frequency, nominal_control_rate_hz,
                 Kp, Ki, Kii=None, ppm_range=1000, pll_bandwidth_hz=None,
                 modulation_rate_hz=None):
        if not math.isfinite(target_output_frequency) or target_output_frequency <= 0:
            raise ValueError("Target output frequency must be positive and finite")
        if not math.isfinite(nominal_control_rate_hz) or nominal_control_rate_hz <= 0:
            raise ValueError("Control rate must be positive and finite")
        self.dco = dco
        # This assumes normal-mode fben occurs once per feedback divide while
        # locked. Allow an override until macro timing is independently verified.
        self.modulation_rate_hz = (dco.input_frequency / (dco.R + 1)
                                   if modulation_rate_hz is None else modulation_rate_hz)
        if not math.isfinite(self.modulation_rate_hz) or self.modulation_rate_hz < nominal_control_rate_hz:
            raise ValueError("MASH rate must be finite and at least the control rate")
        if pll_bandwidth_hz is not None and (
                not math.isfinite(pll_bandwidth_hz) or not 0 < pll_bandwidth_hz < self.modulation_rate_hz / 2):
            raise ValueError("PLL approximation bandwidth must be positive and below MASH Nyquist")
        self.control_time_inc = 1 / nominal_control_rate_hz
        self.modulation_time_inc = 1 / self.modulation_rate_hz
        self.target_output_frequency = target_output_frequency
        self.pfd = port_timer_pfd(target_output_frequency, nominal_control_rate_hz, ppm_range=ppm_range)
        # Match the firmware's windup bounds for both accumulators.
        windup_limit = sigma_delta_dco.sdm_in_max - sigma_delta_dco.sdm_in_min
        self.controller = pi_ctrl(
            Kp, Ki, Kii=Kii,
            i_windup_limit=windup_limit,
            ii_windup_limit=windup_limit)
        self.control_setting = dco.nominal_mash_val
        self.lock_status = dco.lock_status
        self.output_frequency = dco.last_output_frequency
        # Exact discretization of a single-pole response to a held frequency
        # demand. None bypasses this approximation for raw digital analysis.
        self.pll_alpha = (1.0 if pll_bandwidth_hz is None else
                          -math.expm1(-2 * math.pi * pll_bandwidth_hz * self.modulation_time_inc))

    def do_control_loop(self, output_clock_count, period_fraction=1.0, verbose=False):
        """Update PI once per control interval, using cumulative output clocks."""
        error, first_loop = self.pfd.get_error(output_clock_count, period_fraction=period_fraction)
        if first_loop:
            self.controller._reset_controller()
            self.lock_status = -1
            self.dco.lock_status = -1
            self.dco.lock_count = lock_count_threshold
        else:
            correction = self.controller.do_control_from_error(error)
            requested_word = self.dco.nominal_mash_val - int(correction)
            _, self.lock_status = self.dco.get_frequency_from_dco_control(requested_word)
            self.control_setting = self.dco.current_mash_val
        if verbose:
            print(f"MASH error: {error}, word: {self.control_setting}, status: {lock_status_lookup[self.lock_status]}")
        return self.control_setting

    def do_mash(self):
        """Advance one hardware MASH sample, optionally filtering its demand."""
        demand_frequency = self.dco.do_modulate(self.control_setting)
        self.output_frequency += self.pll_alpha * (demand_frequency - self.output_frequency)
        return self.output_frequency


def run_mash_sw_pll_sim(nominal_output_hz=12288000, duration_s=1.0,
                        register_header=None, input_frequency=24000000,
                        nominal_control_rate_hz=93.75, ppm_shift=50,
                        Kp=150.0, Ki=50.0, Kii=1.0, pll_bandwidth_hz=None,
                        modulation_rate_hz=None, audio_sample_rate=48000,
                        pfd_ppm_range=None):
    """Run the MASH counterpart of run_sd_sw_pll_sim and write diagnostics.

    Frequencies are in Hz. Each hardware MASH cycle is simulated, but only
    audio-interval averages are logged to bound memory usage. At a 24 MHz MASH
    rate a one-second run still requires 24 million Python updates. Use a short
    duration for smoke checks and longer runs to study controller settling.

    pll_bandwidth_hz=None leaves the ideal divider demand unfiltered. Supplying
    a bandwidth enables an illustrative single-pole PLL approximation, not a
    measured device model. The plots/WAV are diagnostic modulation results,
    not predictions of physical jitter or calibrated audio performance.
    pfd_ppm_range defaults to at least 1000 ppm beyond the reference shift.
    """
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Simulation duration must be positive and finite")
    if not math.isfinite(nominal_output_hz) or nominal_output_hz <= 0:
        raise ValueError("Nominal output frequency must be positive and finite")
    if not math.isfinite(ppm_shift) or ppm_shift <= -1e6:
        raise ValueError("Reference deviation must give a positive finite reference rate")
    if pfd_ppm_range is None:
        pfd_ppm_range = max(1000, abs(ppm_shift) + 1000)
    elif (not math.isfinite(pfd_ppm_range) or pfd_ppm_range <= abs(ppm_shift)):
        raise ValueError("PFD ppm range must be finite and exceed the absolute reference deviation")
    if not math.isfinite(audio_sample_rate) or audio_sample_rate <= 2000:
        raise ValueError("Audio sample rate must exceed the 1 kHz tone's Nyquist requirement")
    if int(duration_s * audio_sample_rate) < 8:
        raise ValueError("Simulation must contain at least eight audio samples")

    if register_header is None:
        # Reuse the register solver rather than maintaining hardcoded MASH
        # frequency profiles. No register header is written or overwritten.
        solutions = find_mash_pll(input_freq=input_frequency / 1e6,
                                  output_target=nominal_output_hz / 1e6,
                                  ppm_error_max=0.01, tuning_ppm=1000, maxsol=1)
        if not solutions:
            raise ValueError("No MASH configuration meets the nominal frequency and tuning requirements")
        solution = solutions[0]
        control_reg = ((1 << 27) | ((solution['op_div'] - 1) << 23)
                       | ((int(solution['fb_div'][0]) - 1) << 8) | (solution['ref_div'] - 1))
        divider_reg = (1 << 31) | (solution['fin_op_div'] - 1)
        dco = mash_dco(control_reg, divider_reg, solution['mash_word'], input_frequency)
    else:
        dco = mash_dco.from_register_file(str(register_header), input_frequency=input_frequency)

    sw_pll = sim_sw_pll_mash(dco, nominal_output_hz, nominal_control_rate_hz,
                            Kp, Ki, Kii=Kii, ppm_range=pfd_ppm_range,
                            pll_bandwidth_hz=pll_bandwidth_hz,
                            modulation_rate_hz=modulation_rate_hz)
    reference_scale = 1 + ppm_shift / 1e6
    actual_control_rate = nominal_control_rate_hz * reference_scale
    if actual_control_rate > sw_pll.modulation_rate_hz or audio_sample_rate > sw_pll.modulation_rate_hz:
        raise ValueError("Control and audio recording rates must not exceed the MASH rate")
    target_frequency = nominal_output_hz * reference_scale
    min_frequency = dco._word_to_frequency(dco.mash_in_min)
    max_frequency = dco._word_to_frequency(dco.mash_in_max)
    if not min_frequency <= target_frequency <= max_frequency:
        raise ValueError("Shifted target frequency is outside the configured MASH tuning range")
    dco.print_stats()
    print(f"MASH sample rate: {sw_pll.modulation_rate_hz:g} Hz; control rate: {nominal_control_rate_hz:g} Hz")
    print("PLL response: ideal/unfiltered" if pll_bandwidth_hz is None else
          f"PLL response: illustrative single pole at {pll_bandwidth_hz:g} Hz (not calibrated)")

    test_tone_hz = 1000
    audio = audio_modulator(duration_s, sample_rate=audio_sample_rate, test_tone_hz=test_tone_hz)
    # The existing FFT helper forms an even-length window. Discard at most
    # one recording sample rather than passing it an incompatible odd length.
    if audio.modulator.size % 2:
        audio.modulator = audio.modulator[:-1]
    sample_count = audio.modulator.size
    simulated_duration = sample_count / audio_sample_rate
    total_cycles = math.ceil(simulated_duration * sw_pll.modulation_rate_hz)
    time_inc = sw_pll.modulation_time_inc
    # Prime the PFD at time zero, then schedule from integer cycle counts to
    # avoid accumulated floating-point time drift and missing control updates.
    output_clock_count = 0.0
    sw_pll.do_control_loop(output_clock_count)
    control_index = 1
    previous_control_cycle = 0
    next_control_cycle = math.ceil(sw_pll.modulation_rate_hz / actual_control_rate)
    audio_index = 1
    previous_audio_cycle = 0
    next_audio_cycle = math.ceil(sw_pll.modulation_rate_hz / audio_sample_rate)
    interval_clock_count = 0.0
    freq_log = []
    real_time_log = []

    for cycle in range(1, total_cycles + 1):
        output_frequency = sw_pll.do_mash()
        clock_increment = output_frequency * time_inc
        output_clock_count += clock_increment
        interval_clock_count += clock_increment
        if cycle >= next_control_cycle:
            # Compensate only the sub-cycle scheduling quantization. The real
            # reference ppm shift is retained, so the loop must track it.
            period_fraction = (cycle - previous_control_cycle) * time_inc * actual_control_rate
            sw_pll.do_control_loop(output_clock_count, period_fraction=period_fraction)
            previous_control_cycle = cycle
            control_index += 1
            next_control_cycle = math.ceil(control_index * sw_pll.modulation_rate_hz / actual_control_rate)
        if cycle >= next_audio_cycle:
            average_frequency = interval_clock_count / ((cycle - previous_audio_cycle) * time_inc)
            freq_log.append(average_frequency)
            real_time_log.append((audio_index - 1) / audio_sample_rate)
            # Recording averages rather than dropping high-rate samples avoids
            # point-sampling the raw sequence. This boxcar is not a calibrated
            # analog or audio anti-alias filter; interpret the FFT accordingly.
            audio.modulator[audio_index - 1] += test_tone_hz * (average_frequency - target_frequency) / target_frequency
            interval_clock_count = 0.0
            previous_audio_cycle = cycle
            audio_index += 1
            next_audio_cycle = math.ceil(audio_index * sw_pll.modulation_rate_hz / audio_sample_rate)

    target_freq_log = np.full(len(freq_log), target_frequency)
    plot_simulation(freq_log, target_freq_log, real_time_log, "tracking_mash.png")
    audio.modulate_waveform()
    audio.save_modulated_wav("modulated_tone_1000Hz_mash.wav")
    audio.plot_modulated_fft("modulated_fft_mash.png", skip_s=simulated_duration / 2)
    return {'sw_pll': sw_pll, 'time_s': np.asarray(real_time_log),
            'frequency_hz': np.asarray(freq_log), 'target_frequency_hz': target_freq_log}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        assert 0, "Please select LUT, SDM or MASH: sw_pll_sim.py <LUT/SDM/MASH>"
    if sys.argv[1] == "LUT":
        run_lut_sw_pll_sim() # Run LUT sim - generates "register_setup.h" and "fractions.h"
    elif sys.argv[1] == "SDM":
        run_sd_sw_pll_sim(24576000) # Run SDM sim - generates "register_setup.h"
    elif sys.argv[1] == "MASH":
        run_mash_sw_pll_sim()
    else:
        assert 0, "Please select LUT, SDM or MASH: sw_pll_sim.py <LUT/SDM/MASH>"