import argparse
from pathlib import Path

from xray.clean import run
from xray.paths import CLEANED_DIR, RAW_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera la capa cleaned (data/raw -> data/cleaned).")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=CLEANED_DIR)
    args = parser.parse_args()
    print(f"Limpieza: {args.raw_dir} -> {args.out_dir}")
    log = run(args.raw_dir, args.out_dir)
    print()
    print(log.to_string(index=False))


if __name__ == "__main__":
    main()
