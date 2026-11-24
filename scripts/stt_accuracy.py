r"""How well does speech recognition understand *your* voice, and which
Whisper model should Ash use? Records you saying ~50 of Ash's own
commands, then transcribes them with each Whisper model size and
reports, per model:

- word error rate (WER), the standard measure
- command accuracy: how often the transcript still runs the right
  command (what actually matters for an assistant; see ash/evaluation.py).
  It's strict -- same command, same words for its target -- so it's a
  lower bound: Ash's fuzzy app-name matching can still rescue some
  misheard names ("open Spatifi" -> Spotify).
- time per command on this PC (median and 90th percentile)

Each model is run twice: as is, and with Ash's command words given to
Whisper as hotwords, which is how Ash runs it (ash/audio/vocabulary.py).

Your recordings stay in the folder you choose (never in Ash's data
folder) with a manifest.json of what each clip says. Delete the folder
when you're done.

  1. Record (about 10 minutes; press Enter before each command):
       .venv\Scripts\python.exe scripts\stt_accuracy.py record --out D:\ash-voice-test
  2. Evaluate:
       .venv\Scripts\python.exe scripts\stt_accuracy.py evaluate --clips D:\ash-voice-test

Each model is downloaded from Hugging Face the first time it's used
(through Ash's network gate: blocked in offline mode, and logged).

To check the pipeline without recording, `synthesize --out DIR` makes
the same clips with the Windows voices instead. Those numbers say
nothing about your voice; don't report them as if they did.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clips import read_wav, record_command, synthesize, write_wav  # noqa: E402

from ash.evaluation import same_command, summarize  # noqa: E402
from ash.skills import registry as skills  # noqa: E402

MANIFEST = "manifest.json"
MODELS = ("tiny", "base", "small")


def prompts(count: int) -> list[str]:
    """Ash's own example commands: the first example of every command,
    then second examples, and so on, until `count`."""
    rounds = [skill.examples for skill in skills.visible_skills() if skill.examples]
    chosen: list[str] = []
    depth = 0
    while len(chosen) < count and any(len(examples) > depth for examples in rounds):
        chosen += [examples[depth] for examples in rounds if len(examples) > depth]
        depth += 1
    return chosen[:count]


def _load_manifest(folder: Path) -> dict[str, str]:
    path = folder / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_manifest(folder: Path, manifest: dict[str, str]) -> None:
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def record(folder: Path, count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(folder)
    todo = [(i, text) for i, text in enumerate(prompts(count), start=1) if f"clip_{i:03}.wav" not in manifest]
    print(f"{len(todo)} commands to record into {folder}. Speak normally, as you would to Ash.")
    print("Enter: record   s: skip   q: stop (run again later to continue)\n")
    for i, text in todo:
        choice = input(f"[{i}/{count}] Say: \"{text}\"  > ").strip().lower()
        if choice == "q":
            break
        if choice == "s":
            continue
        while True:
            audio = record_command()
            if audio is not None:
                break
            if input("  Didn't hear anything. Try again? [Y/n] ").strip().lower() == "n":
                break
        if audio is None:
            continue
        name = f"clip_{i:03}.wav"
        write_wav(folder / name, audio)
        manifest[name] = text
        _save_manifest(folder, manifest)
        print(f"  saved {name} ({len(audio) / 16000:.1f} s)")
    print(f"\n{len(manifest)} clips recorded. Next: evaluate --clips {folder}")


def make_synthetic(folder: Path, count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for i, text in enumerate(prompts(count), start=1):
        name = f"clip_{i:03}.wav"
        synthesize(text, folder / name, voice_index=i)
        manifest[name] = text
    _save_manifest(folder, manifest)
    print(f"Made {len(manifest)} synthetic clips in {folder} (Windows voices, not yours).")


def evaluate(folder: Path, models: list[str], report_path: Path | None, device: str = "auto") -> None:
    from ash.audio.stt import SpeechToText

    manifest = _load_manifest(folder)
    if not manifest:
        sys.exit(f"No {MANIFEST} in {folder}: record (or synthesize) clips first.")
    clips = [(read_wav(folder / name), text, name) for name, text in sorted(manifest.items())]
    rows, details = [], []
    for size in models:
        for hints in (False, True):
            label = f"{size} + command hints" if hints else size
            print(f"Whisper {label}: loading...", flush=True)
            stt = SpeechToText(model_size=size, device=device, command_hints=hints)
            stt.transcribe(clips[0][0])  # warm-up, not timed
            heard, seconds = [], []
            for audio, text, name in clips:
                start = time.perf_counter()
                transcript = stt.transcribe(audio)
                seconds.append(time.perf_counter() - start)
                heard.append(transcript)
                details.append({"model": label, "clip": name, "said": text, "heard": transcript,
                                "same_command": same_command(text, transcript)})
            summary = summarize([text for _, text, _ in clips], heard, seconds)
            rows.append((label, summary))
            print(f"  WER {summary.wer:.1%}, command accuracy {summary.command_accuracy:.1%}, "
                  f"median {summary.median_seconds:.2f} s")

    table = ["| Model | Clips | Word error rate | Command accuracy | Median time | 90th percentile |",
             "|---|---|---|---|---|---|"]
    table += [f"| {size} | {s.clips} | {s.wer:.1%} | {s.command_accuracy:.1%} | "
              f"{s.median_seconds:.2f} s | {s.p90_seconds:.2f} s |" for size, s in rows]
    text = "\n".join(table)
    print("\n" + text)

    with open(folder / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "clip", "said", "heard", "same_command"])
        writer.writeheader()
        writer.writerows(details)
    print(f"\nEvery transcript, for spotting patterns: {folder / 'results.csv'}")
    if report_path:
        report_path.write_text(text + "\n", encoding="utf-8")
        print(f"Table saved to {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record", help="record yourself saying Ash's commands")
    rec.add_argument("--out", type=Path, required=True, help="a folder of your choice (not Ash's data folder)")
    rec.add_argument("--count", type=int, default=50)
    syn = commands.add_parser("synthesize", help="make the clips with Windows voices (pipeline check only)")
    syn.add_argument("--out", type=Path, required=True)
    syn.add_argument("--count", type=int, default=50)
    ev = commands.add_parser("evaluate", help="transcribe the clips with each model and score them")
    ev.add_argument("--clips", type=Path, required=True)
    ev.add_argument("--models", nargs="+", default=list(MODELS), help="e.g. tiny base small medium")
    ev.add_argument("--report", type=Path, help="also save the results table (Markdown) here")
    ev.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto",
                    help="where Whisper runs (auto: the NVIDIA GPU if it works)")
    args = parser.parse_args()

    if args.command == "record":
        record(args.out, args.count)
    elif args.command == "synthesize":
        make_synthetic(args.out, args.count)
    else:
        evaluate(args.clips, args.models, args.report, args.device)


if __name__ == "__main__":
    main()
