# Copyright 2022-2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

from vcd import VCDWriter 

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
