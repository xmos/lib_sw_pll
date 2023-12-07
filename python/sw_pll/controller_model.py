# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from sw_pll.dco_model import lut_dco, sigma_delta_dco, lock_count_threshold
import numpy as np


class pi_ctrl():
    """
    Parent PI(I) controller class
    """
    def __init__(self,  Kp, Ki, Kii=None, i_windup_limit=None, ii_windup_limit=None, verbose=False):
        self.Kp     = Kp
        self.Ki     = Ki
        self.Kii    = 0.0 if Kii is None else Kii
        self.i_windup_limit = i_windup_limit
        self.ii_windup_limit = ii_windup_limit

        self.error_accum = 0.0          # Integral of error
        self.error_accum_accum = 0.0    # Double integral of error (optional)
        self.total_error = 0.0          # Calculated total error

        self.verbose = verbose

        if verbose:
            print(f"Init sw_pll_pi_ctrl, Kp: {Kp} Ki: {Ki} Kii: {Kii}")

    def _reset_controller(self):
        """
        Reset any accumulated state
        """
        self.error_accum = 0.0
        self.error_accum_accum = 0.0
        self.total_error = 0.0

    def do_control_from_error(self, error):
        """
        Calculate the LUT setting from the input error
        """

        # clamp integral terms to stop them irrecoverably drifting off.
        if self.i_windup_limit is None:
            self.error_accum = self.error_accum + error
        else:
            self.error_accum = np.clip(self.error_accum + error, -self.i_windup_limit, self.i_windup_limit) 
        
        if self.ii_windup_limit is None:
            self.error_accum_accum = self.error_accum_accum + self.error_accum
        else:
            self.error_accum_accum = np.clip(self.error_accum_accum + self.error_accum, -self.ii_windup_limit, self.ii_windup_limit) 
    
        error_p  = self.Kp * error;
        error_i  = self.Ki * self.error_accum
        error_ii = self.Kii * self.error_accum_accum

        self.total_error = error_p + error_i + error_ii

        if self.verbose:
            print(f"error: {error} error_p: {error_p} error_i: {error_i} error_ii: {error_ii} total error: {self.total_error}")

        return self.total_error



##############################
# LOOK UP TABLE IMPLEMENTATION
##############################

class lut_pi_ctrl(pi_ctrl):
    """
        This class instantiates a control loop instance. It takes a lookup table function which can be generated 
        from the error_from_h class which allows it use the actual pre-calculated transfer function.
        Once instantiated, the do_control method runs the control loop.

        This class forms the core of the simulator and allows the constants (K..) to be tuned to acheive the 
        desired response. The function run_sim allows for a plot of a step resopnse input which allows this
        to be done visually.
    """
    def __init__(self, Kp, Ki, Kii=None, base_lut_index=None, verbose=False):
        """
        Create instance absed on specific control constants
        """        
        self.dco = lut_dco()
        self.lut_lookup_function = self.dco.get_lut()
        lut_size = self.dco.get_lut_size()
        self.diff = 0.0                 # Most recent diff between expected and actual. Used by tests


        # By default set the nominal LUT index to half way
        if base_lut_index is None:
            base_lut_index = lut_size // 2
        self.base_lut_index = base_lut_index

        # Set windup limit to the lut_size, which by default is double of the deflection from nominal
        i_windup_limit     = lut_size / Ki if Ki != 0.0 else 0.0
        ii_windup_limit    = 0.0 if Kii is None else lut_size / Kii if Kii != 0.0 else 0.0

        pi_ctrl.__init__(self, Kp, Ki, Kii=Kii, i_windup_limit=i_windup_limit, ii_windup_limit=ii_windup_limit, verbose=verbose)

        self.verbose = verbose

        if verbose:
            print(f"Init lut_pi_ctrl, Kp: {Kp} Ki: {Ki} Kii: {Kii}")

    def get_dco_control_from_error(self, error, first_loop=False):
        """
        Calculate the LUT setting from the input error
        """
        self.diff = error # Used by tests

        if first_loop:
            pi_ctrl._reset_controller(self)
            error = 0.0

        dco_ctrl = self.base_lut_index - pi_ctrl.do_control_from_error(self, error)

        return None if first_loop else dco_ctrl 


######################################
# SIGMA DELTA MODULATOR IMPLEMENTATION
######################################

class sdm_pi_ctrl(pi_ctrl):
    def __init__(self, mod_init, sdm_in_max, sdm_in_min, Kp, Ki, Kii=None, verbose=False):
        """
        Create instance absed on specific control constants
        """        
        pi_ctrl.__init__(self, Kp, Ki, Kii=Kii, verbose=verbose)

        # Low pass filter state
        self.alpha = 0.125
        self.iir_y = 0

        # Nominal setting for SDM
        self.initial_setting = mod_init

        # Limits for SDM output
        self.sdm_in_max = sdm_in_max
        self.sdm_in_min = sdm_in_min

        # Lock status state
        self.lock_status = -1
        self.lock_count = lock_count_threshold

    def do_control_from_error(self, error):
        """
        Run the control loop. Also contains an additional
        low passs filtering stage.
        """
        x = pi_ctrl.do_control_from_error(self, -error)
        x = int(x)

        # Filter noise into DCO to reduce jitter
        # First order IIR, make A=0.125
        # y = y + A(x-y)

        # self.iir_y = int(self.iir_y + (x - self.iir_y) * self.alpha)
        self.iir_y += (x - self.iir_y) >> 3 # This matches the firmware

        sdm_in = self.initial_setting + self.iir_y


        if sdm_in > self.sdm_in_max:
            print(f"SDM Pos clip: {sdm_in}, {self.sdm_in_max}")
            sdm_in = self. sdm_in_max
            self.lock_status = 1
            self.lock_count = lock_count_threshold

        elif sdm_in < self.sdm_in_min:
            print(f"SDM Neg clip: {sdm_in}, {self.sdm_in_min}")
            sdm_in = self.sdm_in_min
            self.lock_status = -1
            self.lock_count = lock_count_threshold

        else:
            if self.lock_count > 0:
                self.lock_count -= 1
            else:
                self.lock_status = 0

        return sdm_in, self.lock_status 


if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    Kp = 1.0
    Ki = 0.1
    Kii = 0.0
    
    sw_pll = lut_pi_ctrl(Kp, Ki, Kii=Kii, verbose=True)
    for error_input in range(-10, 20):
        dco_ctrl = sw_pll.do_control_from_error(error_input)

    mod_init = (sigma_delta_dco.sdm_in_max + sigma_delta_dco.sdm_in_min) / 2
    Kp = 0.0
    Ki = 0.1
    Kii = 0.1

    sw_pll = sdm_pi_ctrl(mod_init, sigma_delta_dco.sdm_in_max, sigma_delta_dco.sdm_in_min, Kp, Ki, Kii=Kii, verbose=True)
    for error_input in range(-10, 20):
        dco_ctrl, lock_status = sw_pll.do_control_from_error(error_input)
