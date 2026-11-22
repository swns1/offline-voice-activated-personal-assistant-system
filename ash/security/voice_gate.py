"""Classical MFCC-similarity voice gate for confirming destructive
actions -- see ash/actions/confirmation.py's wrap_with_confirmation(),
which is the only caller of verify(). This is on top of, not instead
of, the existing spoken yes/no: opt-in via config.security.
voice_gate_enabled, and requires one-time enrollment first
(scripts/enroll_voice.py).

Deliberately NOT a trained deep speaker-embedding model (e.g.
speechbrain's ECAPA-TDNN) -- that needs torch/torchaudio and a
multi-GB install, the same tradeoff that already ruled out training a
real "Hey Ash" wake word locally (see README). This is mean-pooled
MFCCs -- the same classical features GMM-UBM speaker verification
systems used before deep learning became standard -- compared by cosine
similarity. Meaningfully less accurate than a trained embedding, and
especially noisy on a short utterance like a single word "yes" (an
enrollment sample should be several seconds of natural speech; a
confirmation answer is whatever it is). Treat this as a soft additional
check on a single-user machine: it raises the bar above "anyone who
says yes", it is not a strong biometric guarantee.

Every failure mode (nothing enrolled, corrupt voiceprint file, audio
too short to frame) fails OPEN -- i.e. verify() returns True, falling
back to the plain yes/no confirmation the user already had before
turning this on. A flaky add-on check should never be able to make a
core action like shutdown permanently unconfirmable.
"""
import logging

import numpy as np
from scipy.fftpack import dct

from ash.audio.stt import SAMPLE_RATE
from ash.config import Config
from ash.privacy import secure_store
from ash.utils.paths import VOICEPRINT_PATH

_FRAME_MS = 25
_HOP_MS = 10
_FRAME_LEN = SAMPLE_RATE * _FRAME_MS // 1000
_HOP_LEN = SAMPLE_RATE * _HOP_MS // 1000
_NUM_MEL_FILTERS = 26
_NUM_MFCC = 13
_PRE_EMPHASIS = 0.97


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _mel_filterbank(n_fft: int) -> np.ndarray:
    high_mel = _hz_to_mel(np.array([SAMPLE_RATE / 2.0]))[0]
    mel_points = np.linspace(0.0, high_mel, _NUM_MEL_FILTERS + 2)
    bins = np.floor((n_fft + 1) * _mel_to_hz(mel_points) / SAMPLE_RATE).astype(int)

    n_bins = n_fft // 2 + 1
    filters = np.zeros((_NUM_MEL_FILTERS, n_bins))
    for i in range(1, _NUM_MEL_FILTERS + 1):
        left, center, right = bins[i - 1], bins[i], bins[i + 1]
        if center > left:
            for j in range(max(left, 0), min(center, n_bins)):
                filters[i - 1, j] = (j - left) / (center - left)
        if right > center:
            for j in range(max(center, 0), min(right, n_bins)):
                filters[i - 1, j] = (right - j) / (right - center)
    return filters


def _extract_features(audio: np.ndarray) -> np.ndarray | None:
    """Mean-pooled MFCCs across the whole utterance -- a single
    fixed-size "voiceprint" vector. None if there's not even one full
    frame's worth of audio to work with."""
    if len(audio) < _FRAME_LEN:
        return None

    emphasized = np.append(audio[0], audio[1:] - _PRE_EMPHASIS * audio[:-1])
    num_frames = 1 + (len(emphasized) - _FRAME_LEN) // _HOP_LEN
    window = np.hamming(_FRAME_LEN)
    filterbank = _mel_filterbank(_FRAME_LEN)

    mfccs = np.zeros((num_frames, _NUM_MFCC))
    for i in range(num_frames):
        start = i * _HOP_LEN
        frame = emphasized[start:start + _FRAME_LEN] * window
        power_spectrum = (np.abs(np.fft.rfft(frame)) ** 2) / _FRAME_LEN
        energies = filterbank @ power_spectrum
        energies = np.where(energies <= 0, np.finfo(float).eps, energies)
        mfccs[i] = dct(np.log(energies), type=2, norm="ortho")[:_NUM_MFCC]

    return mfccs.mean(axis=0)


def enroll(audio: np.ndarray) -> bool:
    """Saves audio's voiceprint, overwriting any previous enrollment.
    Returns False (nothing saved) if the audio was too short to extract
    features from at all."""
    features = _extract_features(audio)
    if features is None:
        return False
    # Biometric data -- the most sensitive thing Ash stores, so it's
    # encrypted at rest like everything else (ash/privacy/secure_store.py).
    secure_store.write_json(VOICEPRINT_PATH, {"mfcc_mean": features.tolist()})
    return True


def is_enrolled() -> bool:
    return VOICEPRINT_PATH.exists()


def verify(audio: np.ndarray, config: Config, log: logging.Logger) -> bool:
    """True if audio matches the enrolled voiceprint closely enough per
    config.security.voice_match_threshold -- and also True (fails open,
    see module docstring) if nothing's enrolled, the stored file is
    unreadable, or the audio's too short to analyze."""
    if not VOICEPRINT_PATH.exists():
        log.warning("Voice gate enabled but no voice enrolled (run scripts/enroll_voice.py) -- allowing")
        return True
    try:
        stored = np.array(secure_store.read_json(VOICEPRINT_PATH)["mfcc_mean"])
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("Could not read stored voiceprint -- allowing")
        return True

    features = _extract_features(audio)
    if features is None:
        log.warning("Confirmation audio too short to voice-match -- allowing")
        return True

    denom = np.linalg.norm(stored) * np.linalg.norm(features)
    similarity = float(np.dot(stored, features) / denom) if denom > 0 else 0.0
    matched = similarity >= config.security.voice_match_threshold
    log.info("Voice gate similarity %.3f (threshold %.2f) -> %s",
              similarity, config.security.voice_match_threshold, "match" if matched else "no match")
    return matched
