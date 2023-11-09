# Copyright 2022-2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import dco_model
import numpy as np

class sw_pll_lut_pi_ctrl(dco_model.lut_dco):
    """
        This class instantiates a control loop instance. It takes a lookup table function which can be generated 
        from the error_from_h class which allows it use the actual pre-calculated transfer function.
        Once instantiated, the do_control method runs the control loop.

        This class forms the core of the simulator and allows the constants (K..) to be tuned to acheive the 
        desired response. The function run_sim allows for a plot of a step resopnse input which allows this
        to be done visually.
    """

    def __init__(self,  Kp, Ki, Kii=None, base_lut_index=None, verbose=False):

        self.dco = dco_model.lut_dco()
        self.lut_lookup_function = self.dco.get_lut()
        lut_size = self.dco.get_lut_size()

        # By default set the nominal LUT index to half way
        if base_lut_index is None:
            base_lut_index = lut_size // 2
        self.base_lut_index = base_lut_index

        self.Kp     = Kp
        self.Ki     = Ki
        self.Kii    = 0.0 if Kii is None else Kii

        self.diff = 0.0                 # Most recent diff between expected and actual
        self.error_accum = 0.0          # Integral of error
        self.error_accum_accum = 0.0    # Double integral of error
        self.total_error = 0.0          # Calculated total error

        # Set windup limit to the lut_size, which by default is double of the deflection from nominal
        self.i_windup_limit     = lut_size / self.Ki if self.Ki != 0.0 else 0.0
        self.ii_windup_limit    = lut_size / self.Kii if self.Kii != 0.0 else 0.0

        self.verbose = verbose

        if verbose:
            print(f"Init sw_pll_lut_pi_ctrl, Kp: {Kp} Ki: {Ki} Kii: {Kii}")

    def get_dco_ctrl(self):
        return self.error


    def do_control_from_error(self, error):
        """
        Calculate the LUT setting from the input error
        """
        self.diff = error # Used by tests

        # clamp integral terms to stop them irrecoverably drifting off.
        self.error_accum = np.clip(self.error_accum + error, -self.i_windup_limit, self.i_windup_limit) 
        self.error_accum_accum = np.clip(self.error_accum_accum + self.error_accum, -self.ii_windup_limit, self.ii_windup_limit) 

        error_p  = self.Kp * error;
        error_i  = self.Ki * self.error_accum
        error_ii = self.Kii * self.error_accum_accum

        self.total_error = error_p + error_i + error_ii

        if self.verbose:
            print(f"error: {error} error_p: {error_p} error_i: {error_i} error_ii: {error_ii} total error: {self.total_error}")

        dco_ctrl = self.base_lut_index - self.total_error

        return dco_ctrl



if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    Kp = 1.0
    Ki = 0.1
    
    sw_pll = sw_pll_lut_pi_ctrl(Kp, Ki, verbose=True)
    for error_input in range(-10, 20):
        dco_ctrl = sw_pll.do_control_from_error(error_input)

