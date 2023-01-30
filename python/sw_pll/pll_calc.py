#!/usr/bin/env python3
# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

#======================================================================================================================
# Copyright XMOS Ltd. 2021
#
# Original Author: Joe Golightly
#
# File type: Python script
#                 
# Description:
#   Stand-alone script to provide correct paramaters and registers settings to achieve desired clock frequency from
#   xcore.ai PLLs
#   
#
# Status:
#    Released for internal engineering use 
#
#======================================================================================================================

# PLL Structure + Final Output Divider
#                                                                               PLL Macro
#                  +--------------------------------------------------------------------+
#                  |                                                                    |
# ref clk input ---+--- ref_div --- PFC --- Filter --- VCO ---+--- /2 --- output_div ---+--- Final Output Div ---> output
#                  |                 |                        |                         |
#                  |                 +----- feedback_div -----+                         |
#                  |                             |                                      |
#                  +-----------------------------+--------------------------------------+
#                                                |
#                            XMOS Fractional-N Control (Secondary PLL only)

# Terminology Note
# TruCircuits effectively incorporate the /2 into the feedback divider to allow the multiplication ratio to equal the feedback divider value.
# I find this terminology very confusing (particularly when talking about the fractional-n system as well) so I have shown the actual structure above.
# Specs of the above system, extracted from the TruCircuits specs.
#   - Reference divider values (R)          1-64
#   - Feedback divider values (F)           1-8192
#   - Output divider values (OD)            1-8
#   - VCO Frequency                         720MHz - 3.6GHz

# PFC frequency = Divided ref clock frequency = Fpfc = Fin / R.
# VCO frequency = Fvco = Fpfc * F.
# PLL Output frequency = Fout = Fvco / (2 * OD).
# Overall PLL Fout = (Fin * F) / (2 * R * OD)

# After the PLL, the output frequency can be further divided by the final output divider which can divide by 1 to 65536.

# For the App Clock output, there is an additional divide by 2 at the output to give a 50/50 duty cycle.

# All frequencies are in MHz.

import math
from operator import itemgetter

import argparse


def print_regs(args, op_div, fb_div, ref_div, fin_op_div):
  if args.app:
    app_pll_ctl_reg = (1 << 27) | (((op_div)-1) << 23) | ((int(fb_div[0])-1) << 8) | (ref_div-1)
    app_pll_div_reg = (1 << 31) | (fin_op_div-1)
    app_pll_frac_reg = 0
    if (fb_div[1] != 0): # Fractional Mode
      #print(fb_div)
      app_pll_frac_reg = (1 << 31) | ((fb_div[1]-1) << 8) | (fb_div[2]-1)
      
    print('APP PLL CTL REG 0x' + '{:08X}'.format(app_pll_ctl_reg))
    print('APP PLL DIV REG 0x' + '{:08X}'.format(app_pll_div_reg))
    print('APP PLL FRAC REG 0x' + '{:08X}'.format(app_pll_frac_reg))
  else:
    pll_ctl_reg = (((op_div)-1) << 23) | ((int(fb_div[0])-1) << 8) | (ref_div-1)
    pll_div_reg = fin_op_div-1
    print('PLL CTL REG 0x' + '{:08X}'.format(pll_ctl_reg))
    print('SWITCH/CORE DIV REG 0x' + '{:08X}'.format(pll_div_reg))

def print_solution(args, ppm_error, input_freq, out_freq, vco_freq, ref_div, fb_div, op_div, fin_op_div):
  if (fb_div[1] != 0): # Fractional-N mode
    fb_div_string = '{:8.3f}'.format(fb_div[0]) + " (m = " + '{:3d}'.format(fb_div[1]) + ", n = " + '{:3d}'.format(fb_div[2]) + ")"
  else: # Integer mode
    fb_div_string = '{:4d}'.format(int(fb_div[0]))
    fb_div_string = '{:27}'.format(fb_div_string)
  print("Found solution: IN " + '{:3.3f}'.format(input_freq) + "MHz, OUT " + '{:3.6f}'.format(out_freq) + "MHz, VCO " + '{:4.2f}'.format(vco_freq) + "MHz, RD " + '{:2d}'.format(ref_div) + ", FD " + fb_div_string + ", OD " + '{:2d}'.format(op_div) + ", FOD " + '{:4d}'.format(fin_op_div) + ", ERR " + str(round((ppm_error),3)) + "ppm")
  print_regs(args, op_div, fb_div, ref_div, fin_op_div)

def print_solution_set(args, solutions):
  if args.raw:
    sol_str = ' Raw'
  else:
    sol_str = ' Filtered'
  print('***  Found ' + str(len(solutions)) + sol_str + ' Solutions ***')
  print('');
  for solution in solutions:
    print_solution(args, solution['ppm_error'], solution['input_freq'], solution['out_freq'], solution['vco_freq'], solution['ref_div'], solution['fb_div'], solution['op_div'], solution['fin_op_div'])


def find_pll():
    parser = argparse.ArgumentParser(description='A script to calculate xcore.ai PLL settings to achieve desired output clock frequencies.')
    parser.add_argument("-i", "--input", type=float, help="PLL reference input frequency (MHz)", default=24.0)
    parser.add_argument("-t", "--target", type=float, help="Target output frequency (MHz)", default=600.0)
    parser.add_argument("-e", "--error", type=int, help="Allowable frequency error (ppm)", default=0)
    parser.add_argument("-m", "--denmax", type=int, help="Maximum denominator in frac-n config", default=0)
    parser.add_argument("-p", "--pfcmin", type=float, help="Minimum phase frequency comparator frequency (MHz)", default=1.0)
    parser.add_argument("-s", "--maxsol", type=int, help="Maximum number of raw solutions", default=200)
    parser.add_argument("-a", "--app", help="Use the App PLL", action="store_true")
    parser.add_argument("-r", "--raw", help="Show all solutions with no filtering", action="store_true")
    parser.add_argument("--header", help="Output a header file with fraction option reg values", action="store_true")
    parser.add_argument("--fracmax", type=float, help="Maximum fraction value to use", default=1.0)
    parser.add_argument("--fracmin", type=float, help="Minimum fraction value to use", default=0.0)

    args = parser.parse_args()

    input_freq = args.input
    output_target = args.target
    ppm_error_max = args.error

    # PLL Reference divider (R) 1-64
    ref_div_list = list(range(1,65))

    # PLL Output divider (OD) 1-8
    op_div_list = list(range(1,9))

    # Post PLL output divider 1-65536
    fin_op_div_list = list(range(1,65537))

    # To create the feedback divider list we need to create the list of fractions we can use for when using frac-n mode.
    # den_max is the highest number we want to use as the denominator. This is useful to set as higher den_max values will have higher jitter so ideally this should be as low as possible.
    if args.app:
      pll_type = "App PLL"
      den_max = args.denmax
    else:
      pll_type = "Core PLL"
      den_max = 0
      if (args.denmax != 0):
        print("Core PLL does not have frac-n capability. Setting fracmax to 0")

    # Fraction is m/n - m is numerator, n is denominator.
    frac_list_raw = []
    for m in range(1, den_max): # numerator from 1 to (den_max - 1)
      for n in range(m+1, den_max+1): # denominator from (numerator+1) to den_max
        frac = float(m)/float(n)
        if (args.fracmin < frac < args.fracmax):
          frac_list_raw.append([frac,m,n]) # We store the fraction as a float plus the integer numerator and denominator.

    # Sort the fraction list based on the first element (the fractional value) then by the numerator of the fraction.
    # This means we'll get the more desirable fraction to use first. So 1/2 comes before 2/4 even though they both produce the fraction 0.5

    frac_list_sorted = sorted(frac_list_raw, key=itemgetter(0,1))

    # Now we want to weed out useless fractional divide values.
    # For example 1/2 and 2/4 both result in a divide ratio of 0.5 but 1/2 is preferable as the denominator is lower and so it will cause Phase Freq Comparator jitter to be at higher freq and so will be filtered more by the analogue loop filter.

    frac_list = []
    last_item = 0.0
    for item in frac_list_sorted:
      if (item[0] > last_item): # Fractional value has to be greater than the last value or not useful
        #print("{0:.4f}".format(item[0]) + ", " + "{0:2d}".format(item[1]) + ", " + "{0:2d}".format(item[2]))
        frac_list.append(item)
        last_item = item[0]

    # Output a header file containing the list of fractions as register values
    if args.header:
      with open("fractions.h", "w") as f:
        print("// Header file listing fraction options searched", file=f)
        print("// These values to go in the bottom 16 bits of the secondary PLL fractional-n divider register.", file=f)
        print("short frac_values_" + str(den_max) + "[" + str(len(frac_list)) +"] = {", file=f)
        for index, item in enumerate(frac_list):
          #print(item[0],item[1],item[2])
          frac_str = str(item[1]) + "/" + str(item[2])
          frac_str_line = "Index: {:>3} ".format(index) + 'Fraction: {:>5}'.format(frac_str) + " = {0:.4f}".format(item[0])
          print("0x" + format(  (((item[1]-1) << 8) | (item[2]-1)),'>04X') + ", // " + frac_str_line, file=f)
        print("};", file=f)

    # Feedback divider 1-8192 - we store a total list of the integer and fractional portions.
    fb_div_list = []
    for i in range(1,8193):
      fb_div_list.append([i,0,0]) # This is when not using frac-n mode.
      for item in frac_list:
         fb_div_list.append([i+item[0], item[1], item[2]]) 

    # Actual Phase Comparator Limits
    pc_freq_min = 0.22 # 220kHz
    pc_freq_max = 1800.0 # 1.8GHz

    # ... but for lower jitter ideally we'd use a higher minimum PC freq of ~1MHz.
    if (0.22 <= args.pfcmin <= 1800.0):
      pc_freq_min = args.pfcmin

    # Actual VCO Limits (/1 output from PLL goes from 360 - 1800MHz so before the /2 this is 720 - 3600MHz)
    vco_freq_min = 720.0 #720MHz
    vco_freq_max = 3600.0 #3.6GHz

    # New constraint of /1 output of PLL being 800MHz max (Both Core and App PLLs)
    # So this doesn't constrain VCO freq becuase you have the output divider.
    pll_out_max = 800.0 # 800MHz

    # Print a summary of inputs

    print("Using " + pll_type)
    print("Input Frequency = " + str(input_freq) + "MHz")
    print("Target Output Frequency = " + str(output_target) + "MHz")
    print("Allowable frequency error = " + str(ppm_error_max) + "ppm")
    print("Minimum Phase Frequency Comparator Frequency = " +str(pc_freq_min) + "MHz")
    if (pll_type == "App PLL"):
      print("Maximum denominator in frac-n config = " + str(den_max))
    print("")

    # Main loop

    raw_solutions = []

    for ref_div in ref_div_list:
      pc_freq = input_freq/ref_div
      if (pc_freq_min <= pc_freq <= pc_freq_max): # Check pc clock is in valid freq range.
        for fb_div in fb_div_list:
          vco_freq = pc_freq * fb_div[0]
          if (vco_freq_min <= vco_freq <= vco_freq_max): # Check vco is in valid freq range.
            for op_div in op_div_list:
              pll_out_freq = vco_freq/(2*op_div)
              if (pll_out_freq <= pll_out_max): # Check PLL out freq is in valid freq range.
                for fin_op_div in fin_op_div_list:
                  if (len(raw_solutions) >= args.maxsol): # Stop when we've reached the max number of raw solutions
                    break
                  # See if our output freq is what we want?
                  out_freq = vco_freq/(2*op_div*fin_op_div)
                  if args.app:
                    out_freq = out_freq / 2 # fixed /2 for 50/50 duty cycle on app_clk output
                  # Calculate parts per million error
                  ppm_error = ((out_freq - output_target)/output_target) * 1000000.0
                  if (abs(ppm_error) <= (ppm_error_max+0.01)): # Hack a tiny additional error in to handle the floating point calc errors.
                    raw_solutions.append({'ppm_error':ppm_error, 'input_freq':input_freq, 'out_freq':out_freq, 'vco_freq':vco_freq, 'ref_div':ref_div, 'fb_div':fb_div, 'op_div':op_div, 'fin_op_div':fin_op_div})
                  if (out_freq < output_target):
                    break

    # First filter out less desirable solutions with the same vco frequency and RD value. Keep the results with the highest PLL OD value.

    # print_solution_set(raw_solutions)

    solutions_sorted1 = sorted(raw_solutions, key=itemgetter('op_div'), reverse=True) # OD, higher first
    solutions_sorted2 = sorted(solutions_sorted1, key=itemgetter('ref_div')) # Ref Div, lower first
    solutions_sorted3 = sorted(solutions_sorted2, key=itemgetter('vco_freq'), reverse=True) # vco, higher first

    # print_solution_set(solutions_sorted3)

    filtered_solutions = []
    for count, solution in enumerate(solutions_sorted3):
      if count == 0:
        filtered_solutions.append(solution)
      else:
        # Only keep solution If vco or ref_div values are different from last solution
        if (solution['vco_freq'] != last_solution['vco_freq']) | (solution['ref_div'] != last_solution['ref_div']):
          filtered_solutions.append(solution)
      last_solution = solution

    # print_solution_set(filtered_solutions)

    # Final overall sort with lowest ref divider first
    final_filtered_solutions = sorted(filtered_solutions, key=itemgetter('ref_div'))

    if args.raw:
      print_solution_set(args, raw_solutions)
    else:
      print_solution_set(args, final_filtered_solutions)



# When invoked as main program, invoke the profiler on a script
if __name__ == '__main__':
    find_pll()