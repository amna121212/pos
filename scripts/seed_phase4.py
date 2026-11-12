"""Run the phase 4 master data, synthetic history and snapshot steps in order."""
from scripts.seed_phase4_analytics import run as analytics
from scripts.seed_phase4_history import run as history
from scripts.seed_phase4_master import run as master


def main():
    master()
    history()
    analytics()


if __name__ == "__main__":
    main()
