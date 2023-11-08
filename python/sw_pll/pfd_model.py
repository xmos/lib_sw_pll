# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import controller_model

class port_timer_pfd():
    def __init__(self, nominal_output_hz, nominal_nominal_control_rate_hz):
        self.output_count_last_int = 0 # Integer value of last output_clock_count

        self.expected_output_count_inc = nominal_output_hz / nominal_control_rate_hz

        print(f"expected_output_count_inc: {self.expected_output_count_inc}")

    def get_error(self, output_clock_count_float, period_fraction=1.0):

        """ 
        Calculate frequency error from the port output_count taken at the ref clock time.
        Note it uses a floating point input clock count to make simulation easier. This
        handles fractional counts and carries them properly.

        If the time of sampling the output_count is not precisely 1.0 x the ref clock time,
        you may pass a fraction to allow for a proportional value using period_fraction. This is optional.
        """

        output_count_int = int(output_clock_count_float) # round down to nearest int to match hardware

        expected_output_count = self.output_count_last_int + int(self.expected_output_count_inc * period_fraction) # Compensate for jitter if period fraction is specified
        self.output_count_last_int = output_count_int

        error = output_count_int - expected_output_count
       
        return error



if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    
    nominal_output_hz = 12288000
    nominal_control_rate_hz = 93.75
    expected_output_clock_inc = nominal_output_hz / nominal_control_rate_hz 

    pfd = port_timer_pfd(nominal_output_hz, nominal_control_rate_hz)

    output_clock_count_float = 0.0
    for output_hz in range(nominal_output_hz - 1000, nominal_output_hz + 1000, 10):
        output_clock_count_float += output_hz / nominal_output_hz * expected_output_clock_inc
        error = pfd.get_error(output_clock_count_float)
        print(f"actual output Hz: {output_hz} output_clock_count: {output_clock_count_float} error: {error}")


