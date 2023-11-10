# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import matplotlib.pyplot as plt
import numpy as np
import soundfile

class audio_modulator:
    def __init__(self, duration_s, sample_rate=48000, test_tone_hz=1000):
        self.sample_rate = sample_rate
        self.test_tone_hz = test_tone_hz

        self.modulator = np.full(int(duration_s * sample_rate), test_tone_hz, dtype=np.float64)

    def apply_frequency_deviation(self, start_s, end_s, delta_freq):
        start_idx = int(start_s * self.sample_rate)
        end_idx = int(end_s * self.sample_rate)
        self.modulator[start_idx:end_idx] += delta_freq


    def modulate_waveform(self):
        # Now create the frequency modulated waveform
        # this is designed to accumulate the phase so doesn't see discontinuities
        # https://dsp.stackexchange.com/questions/80768/fsk-modulation-with-python
        delta_phi = self.modulator * np.pi / (self.sample_rate / 2.0)
        phi = np.cumsum(delta_phi)
        self.waveform = np.sin(phi)

    def save_modulated_wav(self, filename):
        integer_output = np.int16(self.waveform * 32767)
        soundfile.write(filename, integer_output, int(self.sample_rate))

    def plot_modulated_fft(self, filename):
        xf = np.linspace(0.0, 1.0/(2.0/self.sample_rate), self.modulator.size//2)
        N = xf.size
        window = np.kaiser(N*2, 14)
        waveform = self.waveform * window
        yf = np.fft.fft(waveform)
        fig, ax = plt.subplots()
        
        # Plot a zoom in on the test
        tone_idx = int(self.test_tone_hz / (self.sample_rate / 2) * N)
        num_side_bins = 50
        yf = 20 * np.log10(np.abs(yf) / N)
        # ax.plot(xf[tone_idx - num_side_bins:tone_idx + num_side_bins], yf[tone_idx - num_side_bins:tone_idx + num_side_bins], marker='.')
        
        # Plot the whole frequncy range from DC to nyquist
        ax.plot(xf[:N], yf[:N], marker='.')
        ax.set_xscale("log")
        plt.xlim((10**1, 10**5))
        plt.ylim((-200, 0))
        plt.savefig(filename, dpi=150)

    def load_wav(self, filename):
        """
        Used for testing only - load a wav into self.waveform
        """
        self.waveform, self.sample_rate = soundfile.read(filename)


if __name__ == '__main__':
    """
    This module is not intended to be run directly. This is here for internal testing only.
    """
    if False:
        test_len = 10
        audio = audio_modulator(test_len)
        for time_s in range(test_len):
            modulation_hz = 10 * (time_s - (test_len) / 2)
            audio.apply_frequency_deviation(time_s, time_s + 1, modulation_hz)

        audio.modulate_waveform()
        audio.save_modulated_wav("modulated.wav")
        audio.plot_modulated_fft("modulated_fft.png")
    
    else:
        audio = audio_modulator(1)
        audio.load_wav("modulated_tone_1000Hz_sd_ds.wav")
        audio.plot_modulated_fft("modulated_tone_1000Hz_sd_ds.png")

