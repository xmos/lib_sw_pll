# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

"""Host-side checks of the MASH DCO's averaged and clock-stepped interfaces.

Verify register decoding and the two fixed /2 stages, independent rational
frequency calculations, firmware clamp/lock semantics, header parsing, and
invalid configurations. Check the RTL-derived MASH recurrence, reset seed,
disable/hold behavior, carry cancellation, and finite-window mean separately
from the average-frequency API. These are Python regressions, not an HDL
co-simulation or a model of analog jitter. No target hardware is required.
"""

from fractions import Fraction
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from sw_pll.dco_model import lock_count_threshold, mash, mash_dco
import sw_pll.sw_pll_sim as sim_module


@pytest.fixture
def dco():
    return mash_dco(0x08003E00, 0x8000001E, 0x7CED9)


@pytest.mark.parametrize("control,divider,word,fields", [
    (0x08003E00, 0x8000001E, 0x7CED9, (62, 0, 0, 30)),
    (0x0B804000, 0x80000003, 0x89375, (64, 0, 7, 3)),
    (0x0880CB01, 0x80000018, 0xCCCCD, (203, 1, 1, 24)),
])
def test_mash_registers_and_average_frequency(control, divider, word, fields):
    model = mash_dco(control, divider, word)
    assert (model.F, model.R, model.OD, model.ACD) == fields
    feedback, reference, output, final = fields
    expected = Fraction(24000000, 4 * (reference + 1) * (output + 1) * (final + 1)) * (
        feedback + 1 + Fraction(word, 1 << 20))
    frequency, status = model.get_frequency_from_dco_control(None)
    assert frequency == pytest.approx(float(expected), rel=1e-14)
    assert status == -1
    next_frequency, _ = model.get_frequency_from_dco_control(word + 1)
    assert next_frequency - frequency == pytest.approx(model.step_hz, abs=1e-8)


def test_mash_limits_match_firmware(dco):
    assert dco.mash_in_min == 0x1999A
    assert dco.mash_in_max == 0xE6666
    for requested, limit, status in ((0, dco.mash_in_min, -1),
                                     (0xFFFFF, dco.mash_in_max, 1)):
        frequency, actual_status = dco.get_frequency_from_dco_control(requested)
        assert dco.current_mash_val == limit
        assert frequency == pytest.approx(dco.step_hz * (63 * (1 << 20) + limit))
        assert actual_status == status
        assert dco.lock_count == lock_count_threshold


def test_mash_lock_count_and_hold(dco):
    dco.get_frequency_from_dco_control(dco.mash_in_max + 1)
    for _ in range(lock_count_threshold):
        _, status = dco.get_frequency_from_dco_control(dco.nominal_mash_val)
        assert status == 1
    held = (dco.last_output_frequency, dco.lock_status, dco.lock_count)
    assert dco.get_frequency_from_dco_control(None) == held[:2]
    assert dco.lock_count == held[2]
    assert dco.get_frequency_from_dco_control(dco.nominal_mash_val)[1] == 0
    # Endpoints are legal; only requests beyond them restart the lock counter.
    assert dco.get_frequency_from_dco_control(dco.mash_in_min)[1] == 0
    assert dco.get_frequency_from_dco_control(dco.mash_in_max)[1] == 0
    assert dco.get_frequency_from_dco_control(dco.mash_in_min - 1)[1] == -1


def test_mash_statistics_preserve_state(dco, capsys):
    dco.get_frequency_from_dco_control(dco.nominal_mash_val + 100)
    before = (dco.current_mash_val, dco.last_output_frequency, dco.lock_status, dco.lock_count)
    minimum, nominal, maximum, settings = dco.print_stats()
    assert minimum < nominal < maximum
    assert maximum - minimum == pytest.approx((settings - 1) * dco.step_hz)
    assert before == (dco.current_mash_val, dco.last_output_frequency, dco.lock_status, dco.lock_count)
    assert "MASH step size:" in capsys.readouterr().out


def test_mash_header_without_legacy_metadata(tmp_path):
    header = tmp_path / "register_setup.h"
    header.write_text(
        "#define APP_PLL_CTL_REG 0x08003E00u\n"
        "#define APP_PLL_DIV_REG 0x8000001EUL // final divider\n"
        "#define APP_PLL_MASH_REG 511705\n"
    )
    model = mash_dco.from_register_file(header)
    assert model.nominal_mash_val == 0x7CED9
    assert model.ACD == 30


@pytest.mark.parametrize("contents", [
    "", "#define APP_PLL_CTL_REG (1 << 27)\n",
    "#define APP_PLL_CTL_REG 0x08003E00 + 1\n",
    "#define APP_PLL_CTL_REG 1\n#define APP_PLL_CTL_REG 2\n",
])
def test_mash_rejects_incomplete_or_ambiguous_headers(tmp_path, contents):
    header = tmp_path / "register_setup.h"
    header.write_text(contents)
    with pytest.raises(ValueError, match="APP_PLL_CTL_REG"):
        mash_dco.from_register_file(header)


@pytest.mark.parametrize("control,divider,word,input_frequency", [
    (-1, 0x8000001E, 0x80000, 24000000),
    (0x08003E00, 1 << 32, 0x80000, 24000000),
    (0x08003E00, 0x8000001E, 0x10000, 24000000),
    (0x08003E00, 0x8000001E, 0xF0000, 24000000),
    (0x08003E00, 0x8000001E, 0x80000, 0),
    (0x08003E00, 0x8000001E, 0x80000, float('nan')),
    (0x08000000, 0x8000001E, 0x80000, 24000000),
    (0x08003E00, 0x8000001E, 0x80000, 1000000),
])
def test_mash_rejects_invalid_configuration(control, divider, word, input_frequency):
    with pytest.raises(ValueError):
        mash_dco(control, divider, word, input_frequency)


@pytest.mark.parametrize("control", [float('nan'), float('inf')])
def test_mash_rejects_nonfinite_control(dco, control):
    with pytest.raises(ValueError, match="finite"):
        dco.get_frequency_from_dco_control(control)


def modulator_state(model):
    """Snapshot the registers which RTL freezes when i_mash_enable is low."""
    return (model.delay0_q, model.delay1_q, model.delay2_q,
            model.carry1_q, model.carry2_q, model.carry2_q_q)


def test_mash_half_scale_startup_and_reset():
    model = mash()
    assert modulator_state(model) == (1, 0, 0, 0, 0, 0)
    # Hand-derived pre-edge outputs with the RTL's reset seed. The negative
    # sample tests carry subtraction rather than an unsigned/wrapped result.
    expected = [0, 2, -1, 1, 0, 2, -1, 1]
    assert [model.do_mash_int(0x80000) for _ in expected] == expected
    model.reset_mash()
    assert [model.do_mash_int(0x80000) for _ in expected] == expected


@pytest.mark.parametrize("word", [0, 1, 0x1999A, 0x80000, 0x89375, 0xE6666, 0xFFFFF])
def test_mash_output_range_and_carry_balance(word):
    model = mash()
    count = 8192
    samples = [model.do_mash_int(word) for _ in range(count)]
    assert all(-3 <= sample <= 4 for sample in samples)
    assert all(0 <= remainder < model.mash_scale for remainder in
               (model.delay0_q, model.delay1_q, model.delay2_q))
    # Sum the cancellation equation over time: carry differences telescope,
    # leaving only the final carries and first-accumulator remainder. This
    # tests the delayed-carry alignment without duplicating the step algorithm.
    assert sum(samples) * model.mash_scale == (
        count * word + 1 - model.delay0_q
        + model.mash_scale * (model.carry1_q + model.carry2_q - model.carry2_q_q))
    assert abs(sum(samples) / count - word / model.mash_scale) < 4 / count


def test_mash_disabled_cycles_freeze_and_resume():
    model = mash()
    reference = mash()
    for word in (0x80000, 0x89375, 0xFFFFF, 0):
        assert model.do_mash_int(word) == reference.do_mash_int(word)
    before = modulator_state(model)
    for _ in range(10):
        assert model.do_mash_int(0x1999A, enable=False) == 0
        assert modulator_state(model) == before
    for _ in range(20):
        assert model.do_mash_int(0x1999A) == reference.do_mash_int(0x1999A)


@pytest.mark.parametrize("word", [-1, 1 << 20, 0.5, float('nan')])
def test_mash_raw_input_requires_20_bit_integer(word):
    with pytest.raises(ValueError, match="20-bit"):
        mash().do_mash_int(word)


def test_mash_dco_clock_steps_leave_software_lock_state_unchanged(dco):
    software_state = (dco.lock_status, dco.lock_count)
    corrections = []
    for _ in range(32):
        frequency = dco.do_modulate(0x80000)
        corrections.append(dco.mash_out)
        assert frequency == pytest.approx(dco.step_hz * (1 << 20) * (dco.F + 1 + dco.mash_out))
        assert (dco.lock_status, dco.lock_count) == software_state
    assert corrections[:8] == [0, 2, -1, 1, 0, 2, -1, 1]
    assert len(set(corrections)) > 1
    before = modulator_state(dco)
    assert dco.do_modulate(enable=False) == pytest.approx(dco.step_hz * (1 << 20) * (dco.F + 1))
    assert modulator_state(dco) == before
    dco.reset_mash()
    assert dco.do_modulate() == pytest.approx(dco.step_hz * (1 << 20) * (dco.F + 1))


def test_mash_average_control_does_not_clock_modulator(dco):
    before = modulator_state(dco)
    frequency, _ = dco.get_frequency_from_dco_control(0x89375)
    assert modulator_state(dco) == before
    assert frequency == pytest.approx(dco.step_hz * ((dco.F + 1) * (1 << 20) + 0x89375))
    dco.do_modulate(0)
    assert dco.current_mash_val == dco.mash_in_min
    dco.do_modulate(0xFFFFF)
    assert dco.current_mash_val == dco.mash_in_max


def test_mash_direct_run_demo(tmp_path, monkeypatch, capsys):
    # Exercise the same entry point as `python dco_model.py`. Running outside
    # the source directory also checks that header resolution is cwd-independent.
    script = Path(__file__).resolve().parents[1] / "python/sw_pll/dco_model.py"
    monkeypatch.chdir(tmp_path)
    namespace = runpy.run_path(str(script), run_name="__main__")
    output = capsys.readouterr().out
    assert isinstance(namespace['mash_dco'], type)
    assert "MASH nominal_freq:" in output
    assert output.count("MASH correction") == 30
    assert not list(tmp_path.iterdir())


def test_mash_sim_controller_direction(dco):
    simulation = sim_module.sim_sw_pll_mash(dco, 12288000, 100, Kp=10, Ki=0)
    simulation.do_control_loop(0)
    assert simulation.do_control_loop(122881) == dco.nominal_mash_val - 10
    assert simulation.do_control_loop(2 * 122880) == dco.nominal_mash_val + 10
    assert modulator_state(dco) == (1, 0, 0, 0, 0, 0)


def test_mash_sim_optional_low_pass(dco):
    simulation = sim_module.sim_sw_pll_mash(
        dco, 12288000, 100, Kp=0, Ki=0, pll_bandwidth_hz=1000)
    initial_frequency = simulation.output_frequency
    frequency = simulation.do_mash()
    demand = dco._word_to_frequency(dco.mash_out * dco.mash_scale)
    expected_alpha = -np.expm1(-2 * np.pi * 1000 / 24000000)
    assert simulation.modulation_rate_hz == 24000000
    assert frequency == pytest.approx(initial_frequency + expected_alpha * (demand - initial_frequency))
    assert demand < frequency < initial_frequency


@pytest.mark.parametrize("arguments", [
    {'nominal_control_rate_hz': 0}, {'modulation_rate_hz': 50},
    {'modulation_rate_hz': float('nan')}, {'pll_bandwidth_hz': 0},
    {'pll_bandwidth_hz': 12000000},
])
def test_mash_sim_invalid_rates(dco, arguments):
    settings = dict(target_output_frequency=12288000, nominal_control_rate_hz=100,
                    Kp=0, Ki=0)
    settings.update(arguments)
    with pytest.raises(ValueError):
        sim_module.sim_sw_pll_mash(dco, **settings)


def test_mash_sim_runner_records_without_rewriting_header(tmp_path, monkeypatch):
    header = tmp_path / "register_setup.h"
    contents = ("#define APP_PLL_CTL_REG 0x08003E00\n"
                "#define APP_PLL_DIV_REG 0x8000001E\n"
                "#define APP_PLL_MASH_REG 0x7CED9\n")
    header.write_text(contents)
    audio = SimpleNamespace(modulator=np.full(961, 1000.0),
                            modulate_waveform=Mock(), save_modulated_wav=Mock(),
                            plot_modulated_fft=Mock())
    monkeypatch.setattr(sim_module, 'audio_modulator', lambda *args, **kwargs: audio)
    plot = Mock()
    monkeypatch.setattr(sim_module, 'plot_simulation', plot)
    # Override the assumed hardware rate only to keep this scheduling test
    # short. A real spectral run must use the actual MASH clock rate.
    result = sim_module.run_mash_sw_pll_sim(
        duration_s=0.021, register_header=header, modulation_rate_hz=48000,
        pll_bandwidth_hz=1000)
    assert result['frequency_hz'].size == 960
    assert np.all(np.isfinite(result['frequency_hz']))
    assert np.all(result['target_frequency_hz'] == 12288000 * 1.00005)
    assert result['time_s'][-1] == pytest.approx(959 / 48000)
    assert header.read_text() == contents
    plot.assert_called_once()
    audio.modulate_waveform.assert_called_once()
    audio.save_modulated_wav.assert_called_once_with("modulated_tone_1000Hz_mash.wav")
    audio.plot_modulated_fft.assert_called_once_with("modulated_fft_mash.png", skip_s=0.01)