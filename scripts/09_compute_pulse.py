"""Raw CSVs → canonical Cash Truth → immutable PulseFourPillars artifacts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.pulse.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
