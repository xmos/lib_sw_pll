# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

# Description:
#   Stand-alone script to provide correct paramaters and registers settings to achieve desired clock frequency from
#   xcore.ai and XCORE-400 PLLs

# PLL Structure + Final Output Divider
#                        PLL macro (through output_div)
#
# ref clk --> ref_div --> PFC --> Filter --> VCO --+--> /2 --> output_div --> final_div --> [app /2] --> output
#                         ^                      |
#                         +-- feedback_div <-----+
#                                  N[k]
#
# Feedback-divider control (Secondary / Application PLL only)
#
# programmed F + 1 -------------------------------------------+
#                                                             |
# PWM numerator/period --> PWM (0 or 1) --> [PWM enable] -----+--> SUM --> N[k]
#                                                             |
# 20-bit MASH word ------> MASH (-3..+4) --> [MASH enable] ---+
#
# A disabled modulator contributes zero. MASH-only operation disables PWM;
# enabling both adds both corrections. Neither path changes R or OD.
# F above is the encoded register field: the base physical ratio is F + 1.
# With constant settings, mean N = F + 1 + PWM fraction + MASH word / 2^20.
# The /2 after final_div applies only to the application-clock output.

# Terminology Note
# Macro documentation effectively incorporates the /2 into the feedback divider to allow the multiplication ratio to equal the feedback divider value.
# The diagram above shows the /2 explicitly to distinguish the physical feedback divider from the overall multiplication ratio, particularly for fractional-N operation.
# Specs of the above system, extracted from the Macro docs.
#   - Reference divider values (R)          1-64
#   - Feedback divider values (F)           1-8192
#   - Output divider values (OD)            1-8
#   - VCO Frequency                         720MHz - 3.6GHz

# PFC frequency = Divided ref clock frequency = Fpfc = Fin / R.
# VCO frequency = Fvco = Fpfc * F.
# PLL Output frequency = Fout = Fvco / (2 * OD).
# Overall PLL Fout = (Fin * F) / (2 * R * OD)

# After the PLL, the output frequency can be further divided by the final output divider (APP_CLK_DIVIDER or PLL_CLK_DIVIDER) which can divide by 1 to 65536.

# For the App Clock output, there is an additional divide by 2 at the output to give a 50/50 duty cycle.

# All frequencies are in MHz.

import math
from fractions import Fraction
from operator import itemgetter

import argparse


def print_regs(op_div, fb_div, ref_div, fin_op_div, app = 0, include_frac = True):
  """Preserve legacy PWM output unless the MASH caller opts out of it."""
  if app:
    app_pll_ctl_reg = (1 << 27) | (((op_div)-1) << 23) | ((int(fb_div[0])-1) << 8) | (ref_div-1)
    app_pll_div_reg = (1 << 31) | (fin_op_div-1)
    app_pll_frac_reg = 0
    if (fb_div[1] != 0): # Fractional Mode
      #print(fb_div)
      app_pll_frac_reg = (1 << 31) | ((fb_div[1]-1) << 8) | (fb_div[2]-1)

    print('APP_PLL_CTL_REG 0x' + '{:08X}'.format(app_pll_ctl_reg))
    print('APP_PLL_DIV_REG 0x' + '{:08X}'.format(app_pll_div_reg))
    if include_frac:
      print('APP_PLL_FRAC_REG 0x' + '{:08X}'.format(app_pll_frac_reg))
  else:
    pll_ctl_reg = (((op_div)-1) << 23) | ((int(fb_div[0])-1) << 8) | (ref_div-1)
    pll_div_reg = fin_op_div-1
    print('PLL_CTL_REG 0x' + '{:08X}'.format(pll_ctl_reg))
    print('SWITCH/CORE_DIV_REG 0x' + '{:08X}'.format(pll_div_reg))

def print_solution(ppm_error, input_freq, out_freq, vco_freq, ref_div, fb_div, op_div, fin_op_div, app = 0):
  fb_div_string = '{:4d}'.format(int(fb_div[0])) + ", FRAC " + '{:1.3f}'.format(fb_div[0]-int(fb_div[0])) + " (m = " + '{:3d}'.format(fb_div[1]) + ", n = " + '{:3d}'.format(fb_div[2]) + ")"
  print("Found solution: IN " + '{:3.3f}'.format(input_freq) + "MHz, OUT " + '{:3.6f}'.format(out_freq) + "MHz, VCO " + '{:>7.2f}'.format(vco_freq) + "MHz, RD " + '{:2d}'.format(ref_div) + ", FD " + fb_div_string + ", OD " + '{:2d}'.format(op_div) + ", FOD " + '{:4d}'.format(fin_op_div) + ", ERR " + str(round((ppm_error),3)) + "ppm")
  print_regs(op_div, fb_div, ref_div, fin_op_div, app)

def print_solution_set(solutions, raw = 0, app = 0):
  if raw:
    sol_str = ' Raw'
  else:
    sol_str = ' Filtered'
  print('***  Found ' + str(len(solutions)) + sol_str + ' Solutions ***')
  print('');
  for solution in solutions:
    print_solution(solution['ppm_error'], solution['input_freq'], solution['out_freq'], solution['vco_freq'], solution['ref_div'], solution['fb_div'], solution['op_div'], solution['fin_op_div'], app)


def find_pll(input_freq = 24, output_target = 600, ppm_error_max = 0, den_max = 0, pfcmin = 1.0, maxsol = 200, app = 0, raw = 0, header = 0, fracmax = 1.0, fracmin = 0.0):
    # PLL Reference divider (R) 1-64
    ref_div_list = list(range(1,65))

    # PLL Output divider (OD) 1-8
    op_div_list = list(range(1,9))

    # Post PLL output divider (FOD) 1-65536
    fin_op_div_list = list(range(1,65537))

    # To create the feedback divider list we need to create the list of fractions we can use for when using frac-n mode.
    # den_max is the highest number we want to use as the denominator. This is useful to set as higher den_max values will have higher jitter so ideally this should be as low as possible.
    if app:
      pll_type = "App PLL"
    else:
      pll_type = "Core PLL"
      den_max = 0
      if (den_max != 0):
        print("Core PLL does not have frac-n capability. Setting fraction to 0")

    # Fraction is m/n - m is numerator, n is denominator.
    frac_list_raw = []
    for m in range(1, den_max): # numerator from 1 to (den_max - 1)
      for n in range(m+1, den_max+1): # denominator from (numerator+1) to den_max
        frac = float(m)/float(n)
        if (fracmin < frac < fracmax):
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
    if header:
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
    if (0.22 <= pfcmin <= 1800.0):
      pc_freq_min = pfcmin

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
                  if (len(raw_solutions) >= maxsol): # Stop when we've reached the max number of raw solutions
                    break
                  # See if our output freq is what we want?
                  out_freq = vco_freq/(2*op_div*fin_op_div)
                  if app:
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

    if raw:
      print_solution_set(raw_solutions, raw, app)
      return raw_solutions
    else:
      print_solution_set(final_filtered_solutions, raw, app)
      return final_filtered_solutions

def find_mash_pll(input_freq: float = 24, output_target=12.288, ppm_error_max: float = 0,
          pfcmin=1.0, maxsol=200, raw=False, mash_min=0.1,
          mash_max=0.9, tuning_ppm=0):
  """Find MASH-only application-clock configurations; frequencies are in MHz.

  Unlike PWM, the MASH fraction is a fixed-point number with uniform steps.
  Solve for its nearest representable value rather than enumerating a million
  words. Keep this path separate so existing PWM callers and output retain
  their original behavior. The default fractional window is a conservative
  tuning policy, not a restriction imposed by the RTL or a jitter guarantee.
  """
  values = (input_freq, output_target, ppm_error_max, pfcmin,
        mash_min, mash_max, tuning_ppm)
  if not all(math.isfinite(value) for value in values):
    raise ValueError("MASH search arguments must be finite")
  if input_freq <= 0 or output_target <= 0:
    raise ValueError("Input and target frequencies must be positive")
  if ppm_error_max < 0 or tuning_ppm < 0:
    raise ValueError("Frequency error and tuning range must be nonnegative")
  if not 0.22 <= pfcmin <= 1800:
    raise ValueError("Minimum phase-comparator frequency must be 0.22 to 1800 MHz")
  if not 0 <= mash_min < mash_max <= 1:
    raise ValueError("MASH limits must satisfy 0 <= min < max <= 1")
  if not isinstance(maxsol, int) or maxsol <= 0:
    raise ValueError("Maximum solution count must be a positive integer")

  scale = 1 << 20
  # Round the policy limits inward: 1.0 itself cannot fit in the 20-bit word.
  policy_min = math.ceil(mash_min * scale)
  policy_max = min(scale - 1, math.floor(mash_max * scale))
  if policy_min > policy_max:
    raise ValueError("MASH window contains no representable 20-bit values")

  # Interpret the supplied decimal values exactly, rather than preserving
  # their binary floating-point approximations. Quantization is a real error,
  # not numeric noise: unlike the legacy PWM path, MASH has no hidden allowance.
  input_exact = Fraction(str(input_freq))
  target_exact = Fraction(str(output_target))
  error_limit = Fraction(str(ppm_error_max))
  error_fraction = error_limit / 1000000
  target_low = target_exact * max(0, 1 - error_fraction)
  target_high = target_exact * (1 + error_fraction)
  solutions = []

  for ref_div in range(1, 65):
    pc_freq = input_exact / ref_div
    if not pfcmin <= pc_freq <= 1800:
      continue
    for op_div in range(1, 9):
      # VCO is before the macro's fixed /2. The application-clock path
      # has a second fixed /2 after its programmable final divider.
      vco_max = min(3600, 800 * 2 * op_div)
      final_min = max(1, math.ceil(720 / (4 * op_div * target_high)))
      final_max = 65536
      if target_low > 0:
        final_max = min(final_max, math.floor(vco_max / (4 * op_div * target_low)))
      for fin_op_div in range(final_min, final_max + 1):
        target_ratio = target_exact * 4 * op_div * fin_op_div / pc_freq
        # Normalize a rounded carry through fractional 1.0, then check
        # neighboring integer values for legal fractional-window candidates.
        nearest_base = round(target_ratio * scale) // scale
        # The nearest legal fractional word may lie on the other side of an
        # integer boundary, so check the nearest and both adjacent dividers.
        for base_div in (nearest_base, nearest_base - 1, nearest_base + 1):
          # F is base_div-1. Reserve space for every instantaneous MASH
          # correction (-3..+4), not just the average fraction. This uses
          # the documented 13-bit F range 1..8191; hardware with a narrower
          # F interface requires correspondingly tighter limits.
          if not 5 <= base_div <= 8188:
            continue

          # Intersect the fractional policy with the legal average VCO
          # and PLL-output ranges. Every tuning word between these
          # endpoints is legal because frequency is linear in the word.
          word_min = max(policy_min, math.ceil((720 / pc_freq - base_div) * scale))
          word_max = min(policy_max, math.floor((vco_max / pc_freq - base_div) * scale))
          if word_min > word_max:
            continue

          # Keep the requested tuning range inside the legal window before
          # selecting the nominal word. Using the largest effective divider
          # makes this bound conservative for every word in the interval.
          max_effective_div = base_div + Fraction(word_max, scale)
          required_words = math.ceil(
            Fraction(str(tuning_ppm)) * max_effective_div * scale / 1000000)
          candidate_min = word_min + required_words
          candidate_max = word_max - required_words
          if candidate_min > candidate_max:
            continue
          ideal_word = (target_ratio - base_div) * scale
          mash_word = min(candidate_max, max(candidate_min, round(ideal_word)))

          effective_div = base_div + Fraction(mash_word, scale)
          vco_freq = pc_freq * effective_div
          out_freq = vco_freq / (4 * op_div * fin_op_div)
          ppm_error = (out_freq - target_exact) / target_exact * 1000000
          if abs(ppm_error) > error_limit:
            continue

          symmetric_words = min(mash_word - word_min, word_max - mash_word)
          available_ppm = symmetric_words / (effective_div * scale) * 1000000
          solutions.append({
            # Keep the numeric reporting API float-based, but decide exactness
            # before conversion so display rounding can never imply an exact lock.
            'ppm_error': float(ppm_error), 'exact': ppm_error == 0, 'input_freq': input_freq,
            'out_freq': float(out_freq), 'vco_freq': float(vco_freq),
            'ref_div': ref_div, 'fb_div': [float(effective_div), 0, 0],
            'op_div': op_div, 'fin_op_div': fin_op_div,
            'mash_word': mash_word, 'mash_min_word': word_min,
            'mash_max_word': word_max, 'tuning_ppm': float(available_ppm),
            'step_hz': float(pc_freq * 1000000 / (4 * op_div * fin_op_div * scale)),
          })

  # Do not apply the PWM deduplication: equal VCO frequencies can have very
  # different MASH headroom. Rank all candidates before limiting the output,
  # rather than letting enumeration order hide the best DCO configurations.
  if not raw:
    solutions.sort(key=lambda solution: (
      -solution['tuning_ppm'], abs(solution['ppm_error']),
      solution['ref_div'], -solution['op_div']))
  solutions = solutions[:maxsol]
  print("Using App PLL, MASH only (PWM disabled)")
  print("MASH window: {:.6f} to {:.6f}; required symmetric tuning: +/-{:g} ppm".format(
    mash_min, mash_max, tuning_ppm))
  print("*** Found {} {} Solutions ***".format(len(solutions), "Raw" if raw else "Ranked"))
  for solution in solutions:
    print_mash_solution(solution)
  return solutions


def print_mash_solution(solution):
  """Print divider register encodings and the raw MASH payload separately.

  APP_PLL_MASH_REG follows the existing MASH example: it is the nominal word
  passed to the driver, not an enabled hardware control-register image. The
  driver is responsible for the device-specific MASH enable field.
  """
  # Significant digits preserve tiny nonzero errors in scientific notation.
  # Exactness refers to the specified input, not the physical crystal accuracy.
  print("\nOUT {:.9f} MHz, ERR {:+.12g} ppm ({}), VCO {:.6f} MHz, PFC {:.6f} MHz".format(
    solution['out_freq'], solution['ppm_error'], "exact" if solution['exact'] else "rounded", solution['vco_freq'],
    solution['input_freq'] / solution['ref_div']))
  print("RD {}, FD {:.9f}, OD {}, FOD {} (physical ratios, before register encoding)".format(
    solution['ref_div'], solution['fb_div'][0], solution['op_div'], solution['fin_op_div']))
  print("MASH fraction {:.9f}, step {:.9f} Hz/LSB, symmetric range +/-{:.3f} ppm".format(
    solution['mash_word'] / (1 << 20), solution['step_hz'], solution['tuning_ppm']))
  print("MASH tuning limits: 0x{:05X} to 0x{:05X}".format(
    solution['mash_min_word'], solution['mash_max_word']))
    # sw_pll_mash_init disables PWM internally, so no PWM definition is needed.
  # Only the integer feedback ratio is minus-one encoded; MASH is not.
  print_regs(solution['op_div'], solution['fb_div'], solution['ref_div'],
      solution['fin_op_div'], app=1, include_frac=False)
  print("APP_PLL_MASH_REG 0x{:05X} (raw nominal payload; enable through MASH driver)".format(
    solution['mash_word']))


# Preserve the legacy CLI unless MASH is explicitly selected.
if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='A script to calculate xcore.ai PLL settings to achieve desired output clock frequencies.')
  parser.add_argument("-i", "--input", type=float, help="PLL reference input frequency (MHz)", default=24.0)
  parser.add_argument("-t", "--target", type=float, help="Target output frequency (MHz)", default=600.0)
  parser.add_argument("-e", "--error", type=float, help="Allowable frequency error in ppm (fractional values supported in MASH mode; 0 requires exact MASH frequency)", default=0.0)
  parser.add_argument("-m", "--denmax", type=int, help="Maximum denominator in frac-n config", default=0)
  parser.add_argument("-p", "--pfcmin", type=float, help="Minimum phase frequency comparator frequency (MHz)", default=1.0)
  parser.add_argument("-s", "--maxsol", type=int, help="Maximum number of raw solutions", default=200)
  parser.add_argument("-a", "--app", help="Use the App PLL", action="store_true")
  parser.add_argument("-r", "--raw", help="Show all solutions with no filtering", action="store_true")
  parser.add_argument("--header", help="Output a header file with fraction option reg values", action="store_true")
  parser.add_argument("--fracmax", type=float, help="Maximum fraction value to use", default=1.0)
  parser.add_argument("--fracmin", type=float, help="Minimum fraction value to use", default=0.0)
  parser.add_argument("--mash", help="Search MASH-only App PLL settings (requires --app)", action="store_true")
  parser.add_argument("--mash-min", type=float, help="Minimum MASH fraction (default: 0.1)", default=0.1)
  parser.add_argument("--mash-max", type=float, help="Maximum MASH fraction (default: 0.9)", default=0.9)
  parser.add_argument("--tuning-ppm", type=float, help="Required symmetric MASH tuning range about achieved nominal (default: 0)", default=0)

  args = parser.parse_args()

  if args.mash:
    if not args.app:
      parser.error("--mash requires --app")
    if args.denmax != 0 or args.header or args.fracmin != 0.0 or args.fracmax != 1.0:
      parser.error("--mash cannot be combined with PWM --denmax, --header, or --fracmin/--fracmax settings")
    try:
      find_mash_pll(input_freq=args.input, output_target=args.target,
                    ppm_error_max=args.error, pfcmin=args.pfcmin,
                    maxsol=args.maxsol, raw=args.raw, mash_min=args.mash_min,
                    mash_max=args.mash_max, tuning_ppm=args.tuning_ppm)
    except ValueError as error:
      parser.error(str(error))
  else:
    if args.mash_min != 0.1 or args.mash_max != 0.9 or args.tuning_ppm != 0:
      parser.error("--mash-min, --mash-max, and --tuning-ppm require --mash")
    # Preserve integer-only legacy limits and their printed representation.
    if not math.isfinite(args.error) or not args.error.is_integer():
      parser.error("Legacy --error must be an integer; fractional limits require --mash")
    args.error = int(args.error)
    find_pll(input_freq = args.input, output_target = args.target, ppm_error_max = args.error, den_max = args.denmax, pfcmin = args.pfcmin, maxsol = args.maxsol, app = args.app, raw = args.raw, header = args.header, fracmax = args.fracmax, fracmin = args.fracmin)
