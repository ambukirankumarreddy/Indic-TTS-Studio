"""Entry point for Indic Parler-TTS Desktop Software & CLI."""

import sys
import argparse
import os

# Must run before transformers / huggingface_hub are imported anywhere.
_APP = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("HF_HOME", os.path.join(_APP, "models", "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
if os.environ.get("OFFLINE") == "1" or os.path.isfile(os.path.join(_APP, "models", ".offline")):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

from config import LANGUAGES_DATA, MODEL_ID, DEFAULT_OUTPUT_DIR
from tts_engine import TTSEngine


def run_cli(args):
    print("=" * 60)
    print(" Indic Parler-TTS — CLI Mode")
    print(f" Model: {MODEL_ID}")
    print("=" * 60)

    engine = TTSEngine(output_dir=os.path.abspath(args.output_dir or DEFAULT_OUTPUT_DIR))

    print(f"[*] Target device: {engine.device}")
    print("[*] Loading model weights into memory...")

    # Load model synchronously for CLI
    load_done = False
    load_err = None

    def _on_load(success, msg):
        nonlocal load_done, load_err
        load_done = True
        if not success:
            load_err = msg

    engine.load_model(device=engine.device, use_fp16=False, on_complete=_on_load)

    # Wait for loading
    import time
    while not load_done:
        time.sleep(0.5)

    if load_err:
        print(f"[!] Error loading model: {load_err}")
        sys.exit(1)

    # Determine description
    if args.description:
        description = args.description
    else:
        description = engine.build_description(
            speaker=args.speaker,
            language=args.language,
            emotion=args.emotion or "Neutral"
        )

    print(f"[*] Text: {args.text}")
    print(f"[*] Synthesized Description: {description}")
    print("[*] Generating speech audio...")

    gen_done = False
    gen_result = None
    gen_err = None

    def _on_gen(success, data, msg):
        nonlocal gen_done, gen_result, gen_err
        gen_done = True
        if success:
            gen_result = data
        else:
            gen_err = msg

    engine.generate(
        text=args.text,
        description=description,
        filename_prefix=args.prefix or "cli_out",
        on_complete=_on_gen
    )

    while not gen_done:
        time.sleep(0.2)

    if gen_err:
        print(f"[!] Synthesis failed: {gen_err}")
        sys.exit(1)

    print(f"[+] Audio successfully generated: {gen_result['wav_path']}")
    print(f"[+] Duration: {gen_result['audio_duration']:.2f}s | Generation Time: {gen_result['generation_time']:.2f}s | RTF: {gen_result['rtf']:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Indic Parler-TTS Desktop Software")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode without GUI")
    parser.add_argument("--text", type=str, help="Text to synthesize (in CLI mode)")
    parser.add_argument("--speaker", type=str, default="Rohit", help="Speaker name (e.g. Rohit, Divya, Thoma, Aditi, Jaya, Prakash)")
    parser.add_argument("--language", type=str, default="Hindi", help="Target language name")
    parser.add_argument("--emotion", type=str, default="Neutral", help="Emotion (e.g. Happy, Sad, Neutral, Anger, Narration)")
    parser.add_argument("--description", type=str, help="Custom full description caption prompt")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="Directory to save generated audio")
    parser.add_argument("--prefix", type=str, default="indic_tts", help="Filename prefix")

    args = parser.parse_args()

    if args.cli:
        if not args.text:
            print("[!] Error: --text is required when running in --cli mode.")
            sys.exit(1)
        run_cli(args)
    else:
        # Launch Studio Desktop GUI
        from ui import StudioApp
        app = StudioApp()
        app.mainloop()


if __name__ == "__main__":
    main()
