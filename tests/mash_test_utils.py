# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

"""Shared MASH controller adapters for behavior and C/Python equivalence tests.

xsim exposes average PLL frequency, not individual hardware MASH corrections.
Derive average Hz from the reported control word; do not clock do_modulate here.
This tests firmware/PFD behavior, not RTL modulation, analog dynamics or jitter.
The integer reference is deliberately separate from the floating-point simulator.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import struct
from subprocess import Popen, PIPE, TimeoutExpired

from sw_pll.dco_model import mash_dco


MASH_XE = Path(__file__).parent / "test_mash/bin/test_mash.xe"


@dataclass
class MashDutArgs:
    """Command-line argument order for tests/test_mash/main.c."""

    kp: float = 0.0
    ki: float = 50.0
    kii: float = 0.0
    loop_rate_count: int = 1
    pll_ratio: int = 131072
    ref_clk_expected_inc: int = 0
    app_pll_ctl_reg_val: int = 0x08003E00
    app_pll_div_reg_val: int = 0x8000001E
    nominal_mash_val: int = 0x7CED9
    ppm_range: int = 10000
    target_output_frequency: int = 12288000

    def make_dco(self):
        return mash_dco(self.app_pll_ctl_reg_val, self.app_pll_div_reg_val,
                        self.nominal_mash_val)


@dataclass(frozen=True)
class MashSnapshot:
    lock_status: int
    word: int
    error: int
    integral: int
    double_integral: int
    first_loop: int
    ticks: int
    lock_counter: int
    loop_counter: int

    def controller_state(self):
        """Exact comparison excludes execution time, which Python cannot match."""
        return (self.lock_status, self.word, self.error, self.integral,
                self.double_integral, self.first_loop, self.lock_counter,
                self.loop_counter)


def signed16(value):
    return (int(value) + (1 << 15)) % (1 << 16) - (1 << 15)


class MashSimDut:
    """Integer reference for current MASH C controller and port-timer PFD.

    Mirrors float-to-Q16 gain conversion, arithmetic shifts, accumulator limits,
    clipping and lock countdown. The current firmware uses the SDM limit span
    (980000-60000) for both windup bounds; do not silently substitute MASH span.
    The reference exercises average frequency only, as supported by xsim.
    """

    lock_count = 10
    windup_limit = 980000 - 60000

    def __init__(self, args, mode="timers"):
        self.args = args
        self.dco = args.make_dco()
        self.gains = tuple(int(struct.unpack("f", struct.pack("f", gain))[0] * (1 << 16))
                           for gain in (args.kp, args.ki, args.kii))
        self.word = args.nominal_mash_val
        self.integral = 0
        self.double_integral = 0
        self.error = 0
        self.lock_status = -1
        self.lock_counter = self.lock_count
        self.loop_counter = 0
        self.first_loop = 1
        self.mclk_last = 0
        self.ref_last = 0
        self.expected_count = args.pll_ratio * args.loop_rate_count
        self.ref_increment = args.ref_clk_expected_inc * args.loop_rate_count
        self.ref_scale = (1 << 37) // self.ref_increment + 1 if self.ref_increment else 0
        self.max_error = (args.ppm_range * 2 * self.expected_count // 1000000) & 0xFFFF

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def snapshot(self):
        return MashSnapshot(self.lock_status, self.word, self.error, self.integral,
                            self.double_integral, self.first_loop, 0,
                            self.lock_counter, self.loop_counter)

    def frequency_hz(self, snapshot):
        # This is the mean frequency implied by the command, not a measurement
        # of hardware MASH cycles or an analog PLL transient response.
        return self.dco._word_to_frequency(snapshot.word)

    def do_control_from_error(self, error):
        if not -32768 <= error <= 32767:
            raise ValueError("Expected a signed 16-bit error")
        self.error = int(error)
        self.integral = min(self.windup_limit, max(-self.windup_limit, self.integral + self.error))
        self.double_integral = min(self.windup_limit, max(-self.windup_limit, self.double_integral + self.integral))
        correction = sum(gain * value for gain, value in zip(
            self.gains, (self.error, self.integral, self.double_integral))) >> 16
        correction = (correction + (1 << 31)) % (1 << 32) - (1 << 31)
        requested = self.args.nominal_mash_val - correction
        self.word = min(self.dco.mash_in_max, max(self.dco.mash_in_min, requested))
        if requested < self.dco.mash_in_min:
            self.lock_status = -1
            self.lock_counter = self.lock_count
        elif requested > self.dco.mash_in_max:
            self.lock_status = 1
            self.lock_counter = self.lock_count
        elif self.lock_counter:
            self.lock_counter -= 1
        else:
            self.lock_status = 0
        return self.snapshot()

    def do_control(self, mclk_pt, ref_pt=0):
        mclk_pt = int(mclk_pt) & 0xFFFF
        ref_pt = int(ref_pt) & 0xFFFF
        self.loop_counter += 1
        if self.loop_counter != self.args.loop_rate_count:
            return self.snapshot()
        self.loop_counter = 0
        if self.first_loop:
            # Firmware retains the last command while resetting PI/lock state.
            self.mclk_last = mclk_pt
            self.ref_last = ref_pt
            self.integral = 0
            self.double_integral = 0
            self.lock_counter = self.lock_count
            self.lock_status = -1
            self.first_loop = 0
        else:
            increment = self.expected_count
            if self.ref_increment:
                ref_diff = signed16(ref_pt - (self.ref_last + self.ref_increment))
                self.ref_last = ref_pt
                product = self.expected_count * (self.ref_increment + ref_diff) * self.ref_scale
                increment = ((product & ((1 << 64) - 1)) >> 37) & 0xFFFFFFFF
            self.error = signed16(mclk_pt - (self.mclk_last + increment))
            if abs(self.error) > self.max_error:
                self.first_loop = 1
            # The C implementation still updates control on the detecting
            # iteration; the requested reset occurs on the next scheduled one.
            self.do_control_from_error(self.error)
            self.mclk_last = mclk_pt
        return self.snapshot()


class MashDut:
    """Run the VX C harness in xsim and decode its integer state snapshots."""

    def __init__(self, args, mode="timers"):
        if not MASH_XE.is_file():
            raise FileNotFoundError(f"Build the VX MASH test executable first: {MASH_XE}")
        self.dco = args.make_dco()
        self.mode = mode
        command = ["xsim", "--args", str(MASH_XE),
                   *(str(value) for value in asdict(args).values()), mode]
        self.process = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                             text=True, bufsize=1)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.process.stdin is not None and not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=10)
        except TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()

    def _exchange(self, line):
        assert self.process.stdin is not None and self.process.stdout is not None
        try:
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()
        except BrokenPipeError as error:
            raise RuntimeError("MASH xsim harness terminated while writing input") from error
        response = self.process.stdout.readline()
        if not response:
            assert self.process.stderr is not None
            raise RuntimeError("MASH xsim harness terminated: " + self.process.stderr.read())
        return self._decode(response)

    @staticmethod
    def _decode(response):
        values = response.split()
        if len(values) != 9:
            raise RuntimeError(f"Unexpected MASH harness response: {response!r}")
        return MashSnapshot(*(int(value) for value in values))

    def run_control_trace(self, samples, timeout=300):
        """Replay a reference-generated timer trace without per-step IPC waits.

        The caller must compare every returned state with its reference: that
        proves the replay has the same trajectory as the feedback simulation,
        rather than assuming an unverified C output for the next timer input.
        communicate drains stdout and stderr together, avoiding a full-pipe
        deadlock, and bounds simulator execution time.
        """
        if self.mode != "timers-batch":
            raise ValueError("Trace replay requires timers-batch mode")
        inputs = "".join(f"{int(mclk) & 0xFFFF} {int(ref) & 0xFFFF}\n" for mclk, ref in samples)
        try:
            output, errors = self.process.communicate(inputs, timeout=timeout)
        except TimeoutExpired as error:
            self.process.kill()
            _, errors = self.process.communicate()
            raise TimeoutError(f"MASH xsim trace exceeded {timeout}s: {errors[-2000:]}") from error
        if self.process.returncode:
            raise RuntimeError(f"MASH xsim trace failed ({self.process.returncode}): {errors}")
        states = [self._decode(line) for line in output.splitlines()]
        if len(states) != len(samples):
            raise RuntimeError(f"Expected {len(samples)} MASH responses, received {len(states)}: {errors}")
        return states

    def do_control_from_error(self, error):
        return self._exchange(str(int(error)))

    def do_control(self, mclk_pt, ref_pt=0):
        return self._exchange(f"{int(mclk_pt) & 0xFFFF} {int(ref_pt) & 0xFFFF}")

    def frequency_hz(self, snapshot):
        return self.dco._word_to_frequency(snapshot.word)