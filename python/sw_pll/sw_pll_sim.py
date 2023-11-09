# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from pfd_model import port_timer_pfd
from dco_model import lut_dco 
from controller_model import sw_pll_lut_pi_ctrl
from analysis_tools import audio_modulator


class sim_sw_pll_lut:
    def __init__(   self,
                    target_output_frequency,
                    nominal_nominal_control_rate_frequency,
                    Kp,
                    Ki,
                    Kii=None):

        self.pfd = port_timer_pfd(target_output_frequency, nominal_nominal_control_rate_frequency)
        self.controller = sw_pll_lut_pi_ctrl(Kp, Ki)
        self.dco = lut_dco()

        self.target_output_frequency = target_output_frequency
        self.time = 0.0
        self.control_time_inc = 1 / nominal_nominal_control_rate_frequency

    def do_control_loop(self, output_clock_count, period_fraction=1.0, verbose=False):
        """
        This should be called once every control period nominally
        """

        error = self.pfd.get_error(output_clock_count, period_fraction=period_fraction)
        dco_ctl = self.controller.do_control_from_error(error)
        output_frequency, lock_status = self.dco.get_frequency_from_error(dco_ctl)

        if verbose:
            print(f"Raw error: {error}")
            print(f"dco_ctl: {dco_ctl}")
            print(f"Output_frequency: {output_frequency}")
            print(f"Lock status: {self.dco.lock_status_lookup[lock_status]}")

        return output_frequency, lock_status


# def run_sim_sw_pll_lut( target_output_frequency,
#                         nominal_ref_frequency,
#                         lut_lookup_function,
#                         lut_size,
#                         Kp,
#                         Ki,
#                         simulation_iterations,
#                         ppm_shifts,
#                         jitter_amplitude=100, # Used to simulate port timer sampling time jitter, which can be compensated for
#                         test_tone_hz=1000,
#                         verbose=False):
#     """
#         This function uses the sw_pll_ctrl and passed lut_lookup_function to run a simulation of the response
#         of the sw_pll to changes in input reference frequency.
#         A plot of the simulation is generated to allow visual inspection and tuning.
#     """

#     ref_frequency = nominal_ref_frequency
#     sw_pll = sw_pll_ctrl(target_output_frequency, lut_lookup_function, lut_size, multiplier, ref_to_loop_call_rate, Kp, Ki, verbose=False)
    
#     output_count_end_float = 0.0
#     real_time = 0.0
#     actual_output_frequency = target_output_frequency

#     last_count = 0

#     freq_log = []
#     target_log = []


  
#     audio = audio_modulator(simulation_iterations * ref_to_loop_call_rate / ref_frequency, sample_rate = ref_frequency, test_tone_hz = test_tone_hz)

#     for count in range(simulation_iterations):
#         output_count_start_float = output_count_end_float
#         output_count_float_inc = actual_output_frequency / ref_frequency * ref_to_loop_call_rate
     
#         # Add some jitter to the output_count to test jitter compensation
#         output_sample_jitter = jitter_amplitude * (np.random.sample() - 0.5)         
#         output_count_end_float += output_count_float_inc + output_sample_jitter
#         # Compensate for the jitter
#         period_fraction = (output_count_float_inc + output_sample_jitter) / output_count_float_inc

#         # print(f"output_count_float_inc: {output_count_float_inc}, period_fraction: {period_fraction}, ratio: {output_count_float_inc / period_fraction}")

#         actual_output_frequency, lock_status = sw_pll.do_control(output_count_end_float, period_fraction = period_fraction)
#         # lock_status = 0

#         # Sigma delta section
#         micro_time_inc = output_count_float_inc / sigma_delta_loop_ratio
#         for sd_count in range(sigma_delta_loop_ratio):
#             # Helpers for the tone modulation
#             actual_output_frequency, lock_status = sw_pll.do_deviation(0)

#             time_in_s = lambda count: count * ref_to_loop_call_rate / ref_frequency
#             freq_shift = lambda actual_output_frequency, target_output_frequency, test_tone_hz: (actual_output_frequency / target_output_frequency - 1) * test_tone_hz
#             start_time = time_in_s(count + sd_count / sigma_delta_loop_ratio) 
#             end_time = time_in_s(count + (sd_count + 1) / sigma_delta_loop_ratio) 
#             audio.apply_frequency_deviation(start_time, end_time, freq_shift(actual_output_frequency, target_output_frequency, test_tone_hz))
#             # print(freq_shift(actual_output_frequency, target_output_frequency, test_tone_hz))

#             freq_log.append(actual_output_frequency)
#             target_log.append(ref_frequency * multiplier)

#         if verbose:
#             print(f"Loop: count: {count}, time: {real_time}, actual_output_frequency: {actual_output_frequency}, lock_status: {sw_pll_ctrl.lock_status_lookup[lock_status]}")
     



#         real_time += ref_to_loop_call_rate / ref_frequency


#         # A number of events where the input reference is stepped
#         ppm_adjust = lambda f, ppm: f * (1 + (ppm / 1000000))
#         for ppm_shift in ppm_shifts:
#             (change_at_count, ppm) = ppm_shift
#             if count == change_at_count:
#                 ref_frequency = ppm_adjust(nominal_ref_frequency, ppm)


#     plt.clf()
#     plt.plot(freq_log, color='red', marker='.', label='actual frequency')
#     plt.plot(target_log, color='blue', marker='.', label='target frequency')
#     plt.title('PLL tracking', fontsize=14)
#     plt.xlabel(f'loop_cycle {ref_to_loop_call_rate}', fontsize=14)
#     plt.ylabel('Frequency', fontsize=10)
#     plt.legend(loc="upper right")
#     plt.grid(True)
#     # plt.show()
#     plt.savefig("pll_step_response.png", dpi=150)

#     # Generate fft of modulated test tone
#     audio.plot_modulated_fft(f"modulated_tone_fft_{test_tone_hz}Hz.png", audio.get_modulated_waveform())
#     audio.save_modulated_wav(f"modulated_tone_{test_tone_hz}Hz.wav", audio.get_modulated_waveform())


# """
# ref_to_loop_call_rate   - Determines how often to call the control loop in terms of ref clocks
# xtal_frequency          - The xcore clock frequency
# nominal_ref_frequency   - The nominal input reference frequency
# target_output_frequency - The nominal target output frequency
# max_denom               - (Optional) The maximum fractional denominator. See/doc/sw_pll.rst for guidance  
# min_F                   - (Optional) The minimum integer numerator. See/doc/sw_pll.rst for guidance
# ppm_max                 - (Optional) The allowable PPM deviation for the target nominal frequency. See/doc/sw_pll.rst for guidance
# fracmin                 - (Optional) The minimum  fractional multiplier. See/doc/sw_pll.rst for guidance
# fracmax                 - (Optional) The maximum fractional multiplier. See/doc/sw_pll.rst for guidance
# """

# ref_to_loop_call_rate = 512 # this results in the control loop being called at a rate of nominal_ref_frequency / ref_to_loop_call_rate. Typically ~100Hz
# xtal_frequency = 24000000
# profile_choice = 0

# # Example profiles to produce typical frequencies seen in audio systems
# profiles = [
#     # 0 - 12.288MHz with 48kHz ref (note also works with 16kHz ref), +-250PPM, 29.3Hz steps, 426B LUT size
#     {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":80, "min_F":200, "ppm_max":5, "fracmin":0.843, "fracmax":0.95},
#     # 1 - 12.288MHz with 48kHz ref (note also works with 16kHz ref), +-500PPM, 30.4Hz steps, 826B LUT size
#     {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":80, "min_F":200, "ppm_max":5, "fracmin":0.695, "fracmax":0.905},
#     # 2 - 12.288MHz with 48kHz ref (note also works with 16kHz ref), +-500PPM, 30.4Hz steps, 826B LUT size
#     {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":80, "min_F":200, "ppm_max":5, "fracmin":0.695, "fracmax":0.905},
#     # 3 - 24.576MHz with 48kHz ref (note also works with 16kHz ref), +-1000PPM, 31.9Hz steps, 1580B LUT size
#     {"nominal_ref_frequency":48000.0, "target_output_frequency":12288000, "max_denom":90, "min_F":140, "ppm_max":5, "fracmin":0.49, "fracmax":0.81},
#     # 4 - 24.576MHz with 48kHz ref (note also works with 16kHz ref), +-100PPM, 9.5Hz steps, 1050B LUT size
#     {"nominal_ref_frequency":48000.0, "target_output_frequency":24576000, "max_denom":120, "min_F":400, "ppm_max":5, "fracmin":0.764, "fracmax":0.884},
#     # 5 - 6.144MHz with 16kHz ref, +-200PPM, 30.2Hz steps, 166B LUT size
#     {"nominal_ref_frequency":16000.0, "target_output_frequency":6144000, "max_denom":40, "min_F":400, "ppm_max":5, "fracmin":0.635, "fracmax":0.806},
#     ]



# if __name__ == '__main__':
#     """
#         This script checks to see if PLL settings have already been generated, if not, generates them.
#         It then uses these settings to generate a LUT and control loop instance. 
#         A set of step functions in input reference frequencies are then generated and the
#         response of the sw_pll to these changes is logged and then plotted.
#     """

#     profile_used = profiles[profile_choice]

#     # Make a list of the correct args for get_pll_solution
#     get_pll_solution_args = {"input_frequency":xtal_frequency}
#     get_pll_solution_args.update(profile_used)
#     del get_pll_solution_args["nominal_ref_frequency"]
#     get_pll_solution_args = list(get_pll_solution_args.values())

#     # Extract the required vals from the profile
#     target_output_frequency = profile_used["target_output_frequency"]
#     nominal_ref_frequency = profile_used["nominal_ref_frequency"]
#     multiplier = target_output_frequency / nominal_ref_frequency
#     # input_frequency, target_output_frequency, max_denom=80, min_F=200, ppm_max=2, fracmin=0.65, fracmax=0.95


#     # Use pre-caclulated saved values if they exist, otherwise generate new ones
#     if not os.path.exists(header_file) or not os.path.exists(register_file):
#         output_frequency, vco_freq, F, R, f, p, OD, ACD, ppm = get_pll_solution(*get_pll_solution_args)
#         print(f"output_frequency: {output_frequency}, vco_freq: {vco_freq}, F: {F}, R: {R}, f: {f}, p: {p}, OD: {OD}, ACD: {ACD}, ppm: {ppm}")
#     else:
#         F, R, f, p, OD, ACD = parse_register_file(register_file)
#         print(f"Using pre-calculated settings read from {header_file} and {register_file}:")

#     print(f"PLL register settings F: {F}, R: {R}, OD: {OD}, ACD: {ACD}, f: {f}, p: {p}")

#     # Instantiate controller
#     error_from_h = error_to_pll_output_frequency(header_file, xtal_frequency, F, R, OD, ACD, f, p, verbose=False)
#     error_from_h.plot_freq_range()
    
#     min_freq, mid_freq, max_freq, steps = error_from_h.get_stats()
#     step_size = ((max_freq - min_freq) / steps)

#     print(f"min_freq: {min_freq:.0f}Hz")
#     print(f"mid_freq: {mid_freq:.0f}Hz")
#     print(f"max_freq: {max_freq:.0f}Hz")
#     print(f"average step size: {step_size:.6}Hz, PPM: {1e6 * step_size/mid_freq:.6}")
#     print(f"PPM range: {1e6 * (1 - target_output_frequency / min_freq):.6}")
#     print(f"PPM range: +{1e6 * (max_freq / target_output_frequency - 1):.6}")
#     print(f"LUT entries: {steps} ({steps*2} bytes)")


#     # PI loop control constants
#     Kp = 0.0
#     Ki = 1.0
#     simulation_iterations = 150
#     ppm_shifts = ((250, 300), (500, 150), (800, -200), (1300, 0))
#     ppm_shifts = () # Straight run with no PPM deviation

#     run_sim(target_output_frequency,
#             nominal_ref_frequency,
#             error_from_h.get_output_frequency_from_error,
#             error_from_h.get_lut_size(),
#             Kp,
#             Ki,
#             simulation_iterations,
#             ppm_shifts,
#             verbose=False)

if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    nominal_output_hz = 12288000
    nominal_control_rate_hz = 93.75
    output_frequency = nominal_output_hz
   
    sw_pll = sim_sw_pll_lut(nominal_output_hz, nominal_control_rate_hz, 0.0, 0.1, Kii=0.0)
    output_clock_count = 0.0
    for i in range(50):
        output_clock_count += output_frequency / nominal_control_rate_hz + 10
        output_frequency, lock_status = sw_pll.do_control_loop(output_clock_count, verbose=True)
        
