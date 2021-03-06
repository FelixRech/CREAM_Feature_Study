"""Implements all spectral features.
"""


import numpy as np
from scipy import fft

from features.helpers import rms, geo_mean, normalize


POWER_FREQUENCY = 50  # Hz
SAMPLING_RATE = 6400  # Measurements / second
PERIOD_LENGTH = SAMPLING_RATE // POWER_FREQUENCY


def _get_default_window(current):
    """Calculates the default window for FFT.

    Window is calculated to be the smallest power of two smaller or equal than
    the window size of the complete current array. Example: input of 2s
    interval = 12800 measurements -> window is calculated to be 8192

    Args:
        current (numpy.ndarray): (n_samples, window_size)-dimensional array of current measurements.

    Returns:
        int: Window as an int.
    """
    return int(2**np.floor(np.log2(current.shape[1])))


def _get_window_from_spectrum(spectrum_amp):
    """
    Calculates the window length used from a given spectrum.
    """
    return (spectrum_amp.shape[1] - 1) * 2


def spectrum(current, window=None, sampling_rate=SAMPLING_RATE):
    """Calculates the spectrum (absolute amplitude for positive frequencies)
    for (two-dimensional) arrays of current measurements.

    Will use window-sized subsets of current measurements. Note that for
    performance reasons window should be a power of two. By default, window
    will be calculated to be the smallest power of two smaller or equal than
    the window size of the complete current array. Example: input of 2s
    interval = 12800 measurements -> window is calculated to be 8192. You can
    get the corresponding frequencies with the spectral_frequencies method.

    Args:
        current (numpy.ndarray): (n_samples, window_size)-dimensional array of current measurements.
        window (int): Optional, use window-sized subsets of current measurements for FFT.

    Returns:
        numpy.ndarray: Spectrum as a (n_samples, n_frequencies)-dimensional array.
    """
    # If window is not specified floor to next power of two
    if window is None:
        window = _get_default_window(current)

    normalized_current = normalize(current[:, :window])
    return np.abs(fft.rfft(normalized_current, axis=1))


def spectral_frequencies(window, n=20, limit_to_harmonics=True,
                         power_frequency=POWER_FREQUENCY,
                         sampling_rate=SAMPLING_RATE):
    """Calculates the spectral frequencies (in Hz) for an application of
    fft.rfft.

    Args:
        window (int): Length of input array.
        limit_to_harmonics (bool): Whether to return harmonic frequencies (True) or the full spectrum.
        n (int): Number of harmonics.

    Returns:
        list: Spectral frequencies as a list.
    """
    freqs = fft.rfftfreq(window) * sampling_rate
    if limit_to_harmonics:
        return freqs[_get_harmonics_indices(freqs, n=n,
                                            power_frequency=power_frequency)]
    return freqs


def _get_harmonics_indices(spectral_frequencies, n=20,
                           power_frequency=POWER_FREQUENCY):
    """Calculates the indices of bins containing the harmonics.
    """
    harmonics = np.arange(1, n+1) * power_frequency
    freqs = np.where(spectral_frequencies < 0, 0, spectral_frequencies)
    return np.argmin(np.abs(np.dstack([freqs]*n) - harmonics), axis=1).reshape(-1)


def harmonics(current, n=20, window=None,
              power_frequency=POWER_FREQUENCY, sampling_rate=SAMPLING_RATE):
    """Calculates the amplitudes of the first n harmonics frequencies.

    Will use window-sized subsets of current measurements. Note that for
    performance reasons window should be a power of two. By default, window
    will be calculated to be the smallest power of two smaller or equal than
    the window size of the complete current array. Example: input of 2s
    interval = 12800 measurements -> window is calculated to be 8192. You can
    get the corresponding frequencies with the spectral_frequencies method.

    Args:
        current (numpy.ndarray): (n_samples, window_size)-dimensional array of current measurements.
        n (int): Number of harmonics.
        window (int): Only use window-sized subset of current measurements.

    Returns:
        numpy.ndarray: Harmonic amplitudes as a (n_samples, n)-dimensional array.
    """
    # If window is not specified floor to next power of two
    if window is None:
        window = _get_default_window(current)

    freqs = spectral_frequencies(window, limit_to_harmonics=False,
                                 power_frequency=power_frequency,
                                 sampling_rate=sampling_rate)
    idxs = _get_harmonics_indices(freqs, n=n, power_frequency=power_frequency)
    return spectrum(current, window)[:, idxs]


def _peak_amplitude_frequency(spectrum_amp, freqs, all=False):
    """Calculates the peak amplitude frequency.

    For each sample, select frequency from the spectrum that has biggest
    amplitude. Returns the most common of those frequencies.

    Args:
        spectrum_amp (numpy.ndarray): (n_samples, l)-dimensional array of spectral amplitudes
        freqs (numpy.ndarray): (l,)-dimensional array of corresponding frequencies
        all (bool): whether to return the most common frequency (False) or all (True)

    Returns:
        numpy.ndarray: Peak amplitude frequency as an int (or a (n_samples, 1)-dimensional array).
    """
    indices = np.argmax(spectrum_amp, axis=1).reshape(-1, 1)

    if all:
        return freqs[indices]

    values, counts = np.unique(freqs[indices], return_counts=True)
    return values[np.argmax(counts)]


def _mains_frequency_amplitude(spectrum_amp, mains_frequency=POWER_FREQUENCY,
                               power_frequency=POWER_FREQUENCY,
                               sampling_rate=SAMPLING_RATE):
    """Calculates the amplitude of the mains frequency.

    The mains frequency can be specified in three way:
    1. Default value: mains frequency is assumed to be the power frequency
    2. Custom value: any frequency that is part of the FFT spectrum (check
       the output of spectral_frequencies for your window)
    3. None: calculate as the frequency with peak amplitude in spectrum

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.
        mains_frequency (int): Mains frequency, defaults to power frequency.

    Returns:
        numpy.ndarray: Harmonic amplitudes as a(n_samples, n)-dimensional array.
    """
    # If window is not specified floor to next power of two
    window = _get_window_from_spectrum(spectrum_amp)

    freqs = spectral_frequencies(window, limit_to_harmonics=False,
                                 power_frequency=power_frequency,
                                 sampling_rate=sampling_rate)

    if mains_frequency is None:
        mains_frequency = _peak_amplitude_frequency(spectrum_amp, freqs)

    try:
        idx = np.where(freqs == mains_frequency)[0][0]
    except IndexError:
        raise ValueError(f"Mains frequency of {mains_frequency}Hz is not in "
                         "spectral frequencies as generated by FFT...")

    return spectrum_amp[:, [idx]]


def odd_even_ratio(harmonics_amp):
    """Calculates Odd-even ratio (OER).

    Let \\(x_{f_1}, ..., x_{f_{20}}\\) be the amplitudes of the first 20
    harmonics of the current. Then:

    \\[OER = \\frac{\\text{mean}(x_{f_1}, x_{f_3}, ..., x_{f_{19}})}
                   {\\text{mean}(x_{f_2}, x_{f_4}, ..., x_{f_{20}})}\\]

    Args:
        harmonics_amp (numpy.ndarray): Harmonic amplitudes as a (n_samples, n)-dimensional array.

    Returns:
        numpy.ndarray: Odd-even ratio as a (n_samples, 1)-dimensional array.
    """
    odd, even = np.arange(0, 20, step=20), np.arange(1, 20, step=20)
    return (np.mean(harmonics_amp[:, odd], axis=1)
            / np.mean(harmonics_amp[:, even], axis=1)).reshape(-1, 1)


def spectral_flatness(spectrum_amp):
    """Calculates the Spectral flatness (SPF).

    Let \\(x_{f}\\) be the real-part amplitude of the bin with frequency
    \\(f\\) in the current's spectrum. Then:

    \\[SPF = \\frac{\\sqrt[N]{\\prod_{f \\in f_{bins}} x_f}}
                   {\\text{mean}\\left(\\{x_f | f \\in f_{bins}\\}\\right)}\\]

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.

    Returns:
        numpy.ndarray: Spectral flatness as a (n_samples, 1)-dimensional array.
    """
    spectrum_amp = np.where(spectrum_amp == 0, 0.00001, spectrum_amp)
    return (geo_mean(spectrum_amp) / np.mean(spectrum_amp, axis=1)).reshape(-1, 1)


def harmonics_energy_distribution(harmonics_amp, spectrum_amp):
    """Calculates the Harmonics energy distribution (HED).

    Let \\(x_{f_1}, ..., x_{f_{20}}\\) be the amplitudes of the first 20
    harmonics of the current and \\(x_{f_0}\\) the mains frequency amplitude.
    Then:

    \\[HED = \\frac{1}{x_{f_0}} \\times [x_{f_1}, x_{f_2}, x_{f_3}, ...,
    x_{f_{20}}]\\]

    Args:
        harmonics_amp (numpy.ndarray): Harmonic amplitudes as a (n_samples, n)-dimensional array.
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.

    Returns:
        numpy.ndarray: Harmonics energy distribution as a (n_samples, 20)-dimensional array.
    """
    return harmonics_amp / _mains_frequency_amplitude(spectrum_amp)


def tristiumulus(harmonics_amp):
    """Calculates the Tristimulus.

    Let \\(x_{f_1}, ..., x_{f_{20}}\\) be the amplitudes of the first 20
    harmonics of the current. Then the tristimulus is the triple containing:

    \\[T_1 = \\frac{x_{f_1}}{\\sum_{i=1}^{20} x_{f_i}} \\quad \\quad
       T_2 = \\frac{x_{f_2} + x_{f_3} + x_{f_4}}{\\sum_{i=1}^{20} x_{f_i}}\\]
    \\[T_3 = \\frac{x_{f_5} + x_{f_6} + ... + x_{f_{10}}}{\\sum_{i=1}^{20} x_{f_i}}\\]

    Args:
        harmonics_amp (numpy.ndarray): Harmonic amplitudes as a (n_samples, n)-dimensional array.

    Returns:
        numpy.ndarray: Tristimulus as a (n_samples, 3)-dimensional array.
    """
    harmonics_sum = np.sum(harmonics_amp, axis=1)
    t_1 = harmonics_amp[:, 0] / harmonics_sum
    t_2 = np.sum(harmonics_amp[:, (1, 2, 3)], axis=1) / harmonics_sum
    t_3 = np.sum(harmonics_amp[:, 4:9], axis=1) / harmonics_sum
    return np.hstack((t_1.reshape(-1, 1), t_2.reshape(-1, 1),
                      t_3.reshape(-1, 1)))


def total_harmonic_distortion(harmonics_amp, spectrum_amp):
    """Calculates the Total harmonic distortion (THD).

    Let \\(x_{f_1}, ..., x_{f_{20}}\\) be the amplitudes of the first 20
    harmonics of the current and \\(x_{f_0}\\) the mains frequency amplitude.
    Then:

    \\[THD = \\frac{\\text{rms}([x_{f_1}, x_{f_2}, x_{f_3}, ..., x_{f_{20}}])}
                   {x_{f_0}}\\]

    Args:
        harmonics_amp (numpy.ndarray): Harmonic amplitudes as a (n_samples, n)-dimensional array.
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.

    Returns:
        numpy.ndarray: Total harmonic distortion as a (n_samples, 1)-dimensional array.
    """
    return (rms(harmonics_amp) / _mains_frequency_amplitude(spectrum_amp))


def spectral_centroid(spectrum_amp, current, power_frequency=POWER_FREQUENCY,
                      sampling_rate=SAMPLING_RATE):
    """Calculates the Spectral centroid \\(C_f\\).

    Let \\(x_{f}\\) be the real-part amplitude of the bin with frequency
    \\(f\\) in the current's spectrum. Then:

    \\[C_f = \\frac{\\sum_{f \\in f_{bins}} x_f \\times f}
                   {\\sum_{f \\in f_{bins}} x_f}\\]

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.

    Returns:
        numpy.ndarray: Spectral centroid as a (n_samples, 1)-dimensional array.
    """
    window = _get_default_window(current)
    freqs = spectral_frequencies(window, limit_to_harmonics=False,
                                 power_frequency=power_frequency,
                                 sampling_rate=sampling_rate)[1:]

    return (np.sum(spectrum_amp[:, 1:] / freqs, axis=1)
            / np.sum(spectrum_amp[:, 1:], axis=1)).reshape(-1, 1)


def harmonic_spectral_centroid(current, power_frequency=POWER_FREQUENCY,
                               sampling_rate=SAMPLING_RATE):
    """Calculates the spectral centroid \\(C_h\\).

    \\[C_h = \\frac{\\sum_{i=1}^{50} x_{f_i} \\cdot i}
                   {\\sum_{i=1}^{50} x_{f_i}}\\]

    Args:
        current (numpy.ndarray): (n_samples, window_size)-dimensional array of current measurements.

    Returns:
        numpy.ndarray: Harmonic spectral centroid as a (n_samples, 1)-dimensional array.
    """
    harmonics_amp = harmonics(current, n=50, power_frequency=power_frequency,
                              sampling_rate=sampling_rate)
    return (np.sum(harmonics_amp * np.arange(1, 51), axis=1)
            / np.sum(harmonics_amp, axis=1)).reshape(-1, 1)


def signal_to_signal_mean_ratio(spectrum_amp):
    """Calculates the signal to signal mean ratio (SSMR).

    Let \\(x_{f}\\) be the real-part amplitude of the bin with frequency
    \\(f\\) in the current's spectrum. Then:

    \\[SSMR = \\frac{\\max_{f \\in f_{bins}} x_f}
                    {\\text{mean}\\left(\\{x_f | f \\in f_{bins}\\}\\right)}\\]

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.

    Returns:
        numpy.ndarray: Signal to signal mean ratio as a (n_samples, 1)-dimensional array.
    """
    return (np.max(spectrum_amp, axis=1)
            / np.mean(spectrum_amp, axis=1)).reshape(-1, 1)


def second_harmonic(harmonics_amp):
    """Calculates the amplitude of the second harmonic.

    You can get the corresponding frequency with the spectral_frequencies
    method (use the second element of its return value).

    Args:
        harmonics_amp (numpy.ndarray): Harmonic amplitudes as a (n_samples, n)-dimensional array.

    Returns:
        numpy.ndarray: Amplitude of the second harmonic as a (n_samples, 1)-dimensional array.
    """
    return harmonics_amp[:, [1]]


def high_pass_filter(spectrum_amp, filter_type='zero', filter_frequency=1000):
    """Applies a high pass filter of chosen type to the spectrum.

    The high pass filter passes all spectral amplitudes with a frequency
    higher than the specified cutoff frequency. Amplitudes with a lower
    frequency get attenuated to a degree that depends on the filter type
    chosen. Three filter types have been implemented:

    - Zero: Low-frequency amplitudes are set to zero.
    - Linear: Amplitude with frequency \\(f\\) are scaled by
    \\(\\frac{1}{f} / \\text{filter_frequency}\\)
    - Quadratic: Amplitude with frequency \\(f\\) are scaled by
    \\((\\frac{1}{f} / \\text{filter_frequency})^2\\).

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.
        filter_type (string): Type of filter to apply.
        filter_frequency (int): Cutoff frequency (in Hz) to use.

    Returns:
        numpy.ndarray: Filtered spectrum as a (n_samples, window)-dimensional array.
    """
    window = _get_window_from_spectrum(spectrum_amp)
    freqs = spectral_frequencies(window, limit_to_harmonics=False)

    if filter_type == 'zero':
        filter = np.where(freqs < filter_frequency, 0, 1)
    elif filter_type == 'linear':
        filter = np.where(freqs < filter_frequency,
                          freqs / filter_frequency, 1)
    elif filter_type == 'quadratic':
        filter = np.where(freqs < filter_frequency,
                          np.square(freqs / filter_frequency), 1)
    elif filter_type == 'none':
        filter = np.ones_like(freqs)
    else:
        raise ValueError(f"High pass filter of type '{filter_type}'"
                         "not implemented...")

    return spectrum_amp * filter


def high_frequency_spectral_centroid(spectrum_amp, current,
                                     filter_type='zero', filter_frequency=1000,
                                     power_frequency=POWER_FREQUENCY,
                                     sampling_rate=SAMPLING_RATE):
    """Calculates the High frequency spectral centroid (HFSPC).

    The high frequency spectral centroid is the normal spectral centroid but
    applied to a high pass filtered spectrum. For high pass filter type
    options see the high_pass_filter function.

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.
        filter_type (string): Type of filter to apply.
        filter_frequency (int): Cutoff frequency (in Hz) to use.

    Returns:
        numpy.ndarray: High frequency spectral centroid as a (n_samples, 1)-dimensional array.
    """
    return spectral_centroid(
        high_pass_filter(spectrum_amp, filter_type, filter_frequency),
        current, power_frequency=power_frequency, sampling_rate=sampling_rate
    )


def high_frequency_spectral_flatness(spectrum_amp, filter_type='zero',
                                     filter_frequency=1000):
    """Calculates the High frequency spectral flatness (HFSPF).

    The high frequency spectral flatness is the normal spectral flatness but
    applied to a high pass filtered spectrum. For high pass filter type
    options see the high_pass_filter function.

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.
        filter_type (string): Type of filter to apply.
        filter_frequency (int): Cutoff frequency (in Hz) to use.

    Returns:
        numpy.ndarray: High frequency spectral centroid as a (n_samples, 1)-dimensional array.
    """
    filtered = high_pass_filter(spectrum_amp, filter_type, filter_frequency)
    return spectral_flatness(filtered)


def high_frequency_spectral_mean(spectrum_amp, filter_type='zero',
                                 filter_frequency=1000):
    """Calculates the High frequency spectral mean (HFSPM).

    The high frequency spectral mean is the mean of spectral amplitudes after
    application of a high pass filter: Let \\(x_{f}'\\) be the real-part
    amplitude of the bin with frequency \\(f\\) in the current's spectrum after
    application of the high pass filter and \\(N\\) the number of bins.

    \\[HFSPM = \\frac{1}{N} \\sum_{f \\in f_{bins}} x_f'\\]

    For high pass filter type options see the high_pass_filter function.

    Args:
        spectrum_amp (numpy.ndarray): Spectral amplitudes as a (n_samples, window)-dimensional array.
        filter_type (string): Type of filter to apply.
        filter_frequency (int): Cutoff frequency (in Hz) to use.

    Returns:
        numpy.ndarray: High frequency spectral mean as a (n_samples, 1)-dimensional array.
    """
    filtered = high_pass_filter(spectrum_amp, filter_type, filter_frequency)
    return np.mean(filtered, axis=1).reshape(-1, 1)
