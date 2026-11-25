"""Training your personal wake word (see ash/audio/personal_wake_word.py
for how it runs, and scripts/train_wake_word.py to record and train).

Transfer learning: openWakeWord's pretrained audio-embedding model stays
frozen; only a small classifier on top of its output is trained, which
is why ~40 recordings and a minute or two of CPU are enough.

1. Examples are made the way the live detector sees audio: each piece
   of audio is streamed through openWakeWord 80 ms at a time, exactly
   as Ash listens (computing features from isolated clips instead gave
   noticeably different numbers -- a train/serve mismatch). At each
   step the last 16 embedding frames are one example:
   - positive in the half second after you finish saying the phrase
     (each recording is replayed 12 times, with random loudness, speed,
     timing and background noise);
   - negative while nothing is said, long after the phrase, during the
     first half of the phrase alone ("Okay..."), and throughout
     everything that isn't the phrase: your near-misses, room sound,
     your other recordings, and sentences said by the Windows voices.
     The synthetic voices are only ever negatives: as positives, the
     model learned "a Windows voice" instead of the phrase.
2. A small neural network (scikit-learn MLP) on those examples.
3. The detector wakes when the score stays above the threshold for
   3 frames in a row: the phrase stays above it for longer, while
   false triggers (e.g. "okay" alone) are brief spikes.
4. Measured on recordings it never saw, by streaming them through the
   real detector frame by frame, as Ash would hear them:
   - of your held-out recordings of the phrase, how many it recognised
   - in held-out other speech and room sound, how often it woke by mistake
"""
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from ash.audio.clips import SAMPLE_RATE, read_wav
from ash.audio.personal_wake_word import CONSECUTIVE_FRAMES, FRAME_LENGTH, WINDOW_FRAMES, PersonalWakeWord, keyword_of

# Fixed before measuring your recordings, so their measurement isn't tuned
# to the test data: chosen in development (stand-in recordings), where
# 0.9 removed the remaining false wake-ups without missing any.
THRESHOLD = 0.9
VARIANTS_PER_CLIP = 12
TEST_SHARE = 0.25
FRAME_SECONDS = FRAME_LENGTH / SAMPLE_RATE
POSITIVE_SECONDS = 0.5   # after the phrase ends: when the detector should fire
CLEAR_SECONDS = 2.0      # after the phrase ends: when it's out of the detector's view
WARM_UP_FRAMES = 16      # as the live detector: features need some audio first
# Good enough to use: recognises at least 4 in 5 of your held-out
# recordings, and wakes by mistake at most twice an hour of other sound.
MIN_RECALL = 0.8
MAX_FALSE_WAKES_PER_HOUR = 2.0

NEGATIVE_SENTENCES = [
    "Okay, let's get started with the meeting.", "I'll ask him about it tomorrow.",
    "That's it for today, thanks everyone.", "Can you pass me the salt?", "Hey, what's up?",
    "The cash register is broken again.", "Ashley is coming over later.", "I need to wash the dishes.",
    "Okay Google, what's the weather?", "Hey Jarvis, set a timer.", "Put the ashtray outside, please.",
    "We should ask the teacher.", "Okay then, see you soon.", "That splash was huge!",
    "Open the window, it's hot.", "Did you finish the report?", "My flight leaves at nine.",
    "Let's watch a movie tonight.", "The weather is lovely today.", "I can't find my keys.",
]


@dataclass
class Report:
    phrase: str
    keyword: str
    recordings: int
    positive_examples: int
    negative_examples: int
    recognised: int
    held_out: int
    false_wakes: int
    negative_minutes: float
    by_threshold: dict[float, tuple[float, float]]  # threshold -> (recall, false wakes per hour)
    threshold: float = THRESHOLD
    model: dict | None = None  # saved only if you choose to use it (it's derived from your voice)

    @property
    def recall(self) -> float:
        return self.recognised / self.held_out if self.held_out else 0.0

    @property
    def false_wakes_per_hour(self) -> float:
        return self.false_wakes / (self.negative_minutes / 60) if self.negative_minutes else 0.0

    @property
    def good_enough(self) -> bool:
        return self.recall >= MIN_RECALL and self.false_wakes_per_hour <= MAX_FALSE_WAKES_PER_HOUR

    def summary(self) -> str:
        lines = [
            f'"{self.phrase}": trained on {self.recordings} recordings of you '
            f"({self.positive_examples} positive and {self.negative_examples} negative examples).",
            f"Measured on recordings it never saw (threshold {self.threshold}"
            f"{', chosen beforehand' if self.threshold == THRESHOLD else ', chosen by you after seeing results'}):",
            f"  recognised {self.recognised} of {self.held_out} of your recordings ({self.recall:.0%})",
            f"  woke by mistake {self.false_wakes} times in {self.negative_minutes:.1f} minutes of other speech "
            f"and room sound ({self.false_wakes_per_hour:.1f} per hour)",
            "At other thresholds:",
        ]
        lines += [f"  {t:.2f}: recognised {r:.0%}, {f:.1f} false wake-ups per hour"
                  for t, (r, f) in sorted(self.by_threshold.items())]
        return "\n".join(lines)


# --- audio ---------------------------------------------------------------------------

def speech_bounds(audio: np.ndarray) -> tuple[int, int]:
    """Start and end sample of the speech in a recording (by loudness)."""
    frame = SAMPLE_RATE // 50  # 20 ms
    count = max(1, len(audio) // frame)
    rms = np.sqrt(np.mean(audio[: count * frame].reshape(count, frame) ** 2, axis=1) + 1e-12)
    loud = np.flatnonzero(rms >= max(0.1 * rms.max(), 3 * np.percentile(rms, 10)))
    if len(loud) == 0:
        return 0, len(audio)
    return int(loud[0] * frame), int(min(len(audio), (loud[-1] + 1) * frame))


def _speed(audio: np.ndarray, factor: float) -> np.ndarray:
    from scipy.signal import resample

    return resample(audio, max(1, int(len(audio) / factor))).astype(np.float32)


def _noise(length: int, noise: np.ndarray | None, rng: random.Random, level: float) -> np.ndarray:
    if noise is not None and len(noise) > length:
        start = rng.randrange(len(noise) - length)
        piece = noise[start:start + length]
        return (piece / (np.abs(piece).max() + 1e-6) * level).astype(np.float32)
    return np.random.default_rng(rng.randrange(1 << 30)).normal(0, level / 3, length).astype(np.float32)


def stream_features(audio: np.ndarray) -> np.ndarray:
    """(frames, 16, 96): what the live detector would see after each 80 ms
    of `audio` (the first WARM_UP_FRAMES are left out, as it ignores them)."""
    from openwakeword.utils import AudioFeatures

    features = AudioFeatures(inference_framework="onnx")
    samples = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    windows = []
    for n, i in enumerate(range(0, len(samples) - FRAME_LENGTH + 1, FRAME_LENGTH), start=1):
        features(samples[i:i + FRAME_LENGTH])
        if n >= WARM_UP_FRAMES:
            windows.append(features.get_features(WINDOW_FRAMES)[0])
    return np.array(windows, dtype=np.float32).reshape(-1, WINDOW_FRAMES, 96)


def _frame_times(frames: int) -> np.ndarray:
    """End time (s) of the audio each streamed example covers."""
    return (np.arange(frames) + WARM_UP_FRAMES) * FRAME_SECONDS


def phrase_examples(clip: np.ndarray, rng: random.Random, noise: np.ndarray | None,
                    first_half_only: bool = False) -> tuple[list, list]:
    """Stream one replay of a recording (varied); label each step."""
    start, end = speech_bounds(clip)
    speech = clip[start:end]
    if first_half_only:
        speech = speech[: len(speech) // 2]
    speech = _speed(speech, rng.uniform(0.9, 1.1)) * 10 ** (rng.uniform(-6, 3) / 20)
    lead, tail = rng.uniform(1.6, 2.4), CLEAR_SECONDS + 0.5
    level = rng.uniform(0.002, 0.03)
    audio = np.concatenate([_noise(int(lead * SAMPLE_RATE), noise, rng, level),
                            speech + _noise(len(speech), noise, rng, level),
                            _noise(int(tail * SAMPLE_RATE), noise, rng, level)])
    windows = stream_features(np.clip(audio, -1, 1))
    times = _frame_times(len(windows))
    spoken_from, spoken_until = lead, lead + len(speech) / SAMPLE_RATE
    positives, negatives = [], []
    for window, t in zip(windows, times, strict=True):
        if t <= spoken_from or t >= spoken_until + CLEAR_SECONDS:
            negatives.append(window)
        elif not first_half_only and spoken_until <= t <= spoken_until + POSITIVE_SECONDS:
            positives.append(window)
        elif first_half_only and t >= spoken_until:
            negatives.append(window)  # "Okay..." with no "Ash" must not wake it
    return positives, negatives


# --- synthetic voices -------------------------------------------------------------------

def synthetic_audio(texts: list[str], folder: Path) -> list[np.ndarray]:
    """Each text, said by each Windows voice at three speeds."""
    import pyttsx3

    engine = pyttsx3.init()
    paths = []
    for v, voice in enumerate(engine.getProperty("voices")):
        engine.setProperty("voice", voice.id)
        for rate in (150, 185, 220):
            engine.setProperty("rate", rate)
            for t, text in enumerate(texts):
                path = folder / f"synthetic_{v}_{rate}_{t}.wav"
                engine.save_to_file(text, str(path))
                paths.append(path)
    engine.runAndWait()
    engine.stop()
    return [read_wav(path) for path in paths if path.exists()]


# --- training and measuring ----------------------------------------------------------------

def train_classifier(positives: np.ndarray, negatives: np.ndarray, seed: int = 0) -> dict:
    """A small MLP on flattened embeddings, exported as plain numbers."""
    from sklearn.neural_network import MLPClassifier

    x = np.concatenate([positives, negatives]).reshape(len(positives) + len(negatives), -1)
    y = np.concatenate([np.ones(len(positives)), np.zeros(len(negatives))])
    # Balance the classes by repeating positives (MLPClassifier has no class weights).
    repeat = max(1, len(negatives) // max(1, len(positives)))
    x = np.concatenate([x[y == 1]] * repeat + [x[y == 0]])
    y = np.concatenate([np.ones(int((y == 1).sum()) * repeat), np.zeros(int((y == 0).sum()))])
    mean, scale = x.mean(axis=0), x.std(axis=0) + 1e-6
    mlp = MLPClassifier(hidden_layer_sizes=(32,), alpha=1e-2, max_iter=400, early_stopping=True,
                        random_state=seed)
    mlp.fit((x - mean) / scale, y)
    return {
        "mean": mean.tolist(), "scale": scale.tolist(),
        "layers": [{"weights": w.tolist(), "bias": b.tolist()}
                   for w, b in zip(mlp.coefs_, mlp.intercepts_, strict=True)],
    }


def stream(model: dict, audio: np.ndarray, threshold: float) -> int:
    """How many times the real detector wakes, hearing `audio` live."""
    detector = PersonalWakeWord({**model, "threshold": threshold, "consecutive": CONSECUTIVE_FRAMES})
    samples = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    return sum(detector.process(samples[i:i + FRAME_LENGTH])
               for i in range(0, len(samples) - FRAME_LENGTH + 1, FRAME_LENGTH))


def _split(items: list, rng: random.Random, share: float = TEST_SHARE) -> tuple[list, list]:
    items = items[:]
    rng.shuffle(items)
    cut = max(1, round(len(items) * share)) if len(items) > 1 else 0
    return items[cut:], items[:cut]


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def train_and_evaluate(folder: Path, *, accuracy_clips: Path | None = None, synthetic: bool = True,
                       threshold: float = THRESHOLD, log: Callable[[str], None] = lambda message: None,
                       seed: int = 0) -> Report:
    rng = random.Random(seed)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    phrase = manifest["phrase"]
    by_label: dict[str, list[np.ndarray]] = {"wake": [], "near_miss": [], "room": []}
    for name, label in sorted(manifest["clips"].items()):
        by_label[label].append(read_wav(folder / name))
    if len(by_label["wake"]) < 8:
        raise ValueError(f"Only {len(by_label['wake'])} recordings of the wake word; record at least 8 (40 is better).")

    other_speech = list(by_label["near_miss"])
    if accuracy_clips is not None and (accuracy_clips / "manifest.json").exists():
        names = json.loads((accuracy_clips / "manifest.json").read_text(encoding="utf-8"))
        other_speech += [read_wav(accuracy_clips / name) for name in sorted(names)]
    if synthetic:
        import tempfile

        log("Making 'not the wake word' speech with the Windows voices...")
        with tempfile.TemporaryDirectory() as tmp:
            other_speech += synthetic_audio(NEGATIVE_SENTENCES, Path(tmp))

    room = np.concatenate(by_label["room"]) if by_label["room"] else None
    room_train = room[: int(len(room) * 0.6)] if room is not None else None
    room_test = room[int(len(room) * 0.6):] if room is not None else None
    wake_train, wake_test = _split(by_label["wake"], rng)
    speech_train, speech_test = _split(other_speech, rng, share=0.4)

    log(f"Streaming {len(wake_train) * VARIANTS_PER_CLIP} replays of your recordings...")
    positives, negatives = [], []
    for clip in wake_train:
        for _ in range(VARIANTS_PER_CLIP):
            pos, neg = phrase_examples(clip, rng, room_train)
            positives += pos
            negatives += neg
        negatives += phrase_examples(clip, rng, room_train, first_half_only=True)[1]
    log("Streaming the other speech and room sound...")
    pause = _silence(0.6)
    other_train = [pause] + [part for clip in speech_train for part in (clip, pause)]
    if room_train is not None:
        other_train.append(room_train)
    negatives += list(stream_features(np.concatenate(other_train)))

    log(f"Training on {len(positives)} positive and {len(negatives)} negative examples...")
    model = train_classifier(np.array(positives), np.array(negatives), seed=seed)

    log("Measuring on recordings it never saw...")
    gap = _silence(1.5)
    held_out_wake = [np.concatenate([gap, clip, gap]) for clip in wake_test]
    other = [gap] + [part for clip in speech_test for part in (clip, pause)]
    if room_test is not None:
        other.append(room_test)
    other_audio = np.concatenate(other)
    minutes = len(other_audio) / SAMPLE_RATE / 60
    by_threshold, counts = {}, {}
    for candidate in sorted({0.5, 0.7, 0.8, 0.9, 0.95, threshold}):
        recognised = sum(stream(model, audio, candidate) > 0 for audio in held_out_wake)
        false_wakes = stream(model, other_audio, candidate)
        counts[candidate] = (recognised, false_wakes)
        by_threshold[candidate] = (recognised / len(held_out_wake), false_wakes / (minutes / 60))

    model.update({
        "phrase": phrase, "threshold": threshold, "trained_at": datetime.now().isoformat(timespec="seconds"),
        "window_frames": WINDOW_FRAMES, "embedding": "openwakeword", "consecutive": CONSECUTIVE_FRAMES,
    })
    recognised, false_wakes = counts[threshold]
    report = Report(
        phrase=phrase, keyword=keyword_of(phrase), recordings=len(by_label["wake"]),
        positive_examples=len(positives), negative_examples=len(negatives),
        recognised=recognised, held_out=len(held_out_wake), false_wakes=false_wakes,
        negative_minutes=round(minutes, 1), by_threshold=by_threshold, threshold=threshold,
    )
    model["measured"] = {"recall": report.recall, "false_wakes_per_hour": round(report.false_wakes_per_hour, 2),
                         "held_out_recordings": report.held_out, "negative_minutes": report.negative_minutes}
    report.model = model
    return report
