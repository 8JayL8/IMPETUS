# recommendation.py
import numpy as np
import file_utils
import section_checks


class EnergyRecommendation:
    """
    Finds the recommended (lower and upper bound) slider values for every track type,
    based on the speed coming out of the 'Starts' section.

    Each slider value is tested by building that track part and running the same physics
    checks the Create button uses (section_checks.analyze_section), so the recommended
    range always agrees with what Create will report.

    Approximation: every section is tested with the speed leaving the 'Starts' section.
    Track parts start and end at (almost) the same height, and friction is ignored,
    so the speed entering each later section is nearly the same.
    """
    _cache = {}

    @classmethod
    def get_recommendations(cls, start_type, start_value, builders, sections, value_range=(1, 50)):
        """
        start_type, start_value: what the user picked in the 'Starts' section
        builders: track type -> track part function (GUI.track_function_map)
        sections: section name -> list of track types to recommend for, e.g. {"Turns": ["Helix", ...]}
        Returns {"v_exit": float, section name: {track type: (min, max) or None}}
        """
        key = (start_type, float(start_value), tuple((s, tuple(t)) for s, t in sections.items()), value_range)
        if key in cls._cache:
            return cls._cache[key]

        # Test builds must not save files into the section's Segments folder
        with file_utils.no_segment_writes():
            _, raw_v = builders[start_type](float(start_value))
            v_exit = float(np.ravel(raw_v)[0])

            recs = {"v_exit": v_exit}
            tested = {}   # Thrills 1 and Thrills 2 use the same tracks, so only test each once
            for section_name, track_types in sections.items():
                recs[section_name] = {}
                for track_type in track_types:
                    test_key = (section_name == "Ends", track_type)
                    if test_key not in tested:
                        tested[test_key] = cls._safe_range(builders[track_type], section_name, track_type, v_exit, value_range)
                    recs[section_name][track_type] = tested[test_key]

        cls._cache[key] = recs
        return recs

    @staticmethod
    def _safe_range(build, section_name, track_type, v_entry, value_range):
        """Largest continuous range of slider values where every physics check passes, or None."""
        best = None
        run_start = None
        low, high = value_range

        for value in range(low, high + 2):   # one extra step closes a run that reaches 'high'
            passed = False
            if value <= high:
                try:
                    _, checks, _ = section_checks.analyze_section(section_name, track_type, build(float(value)), v_entry)
                    passed = all(check is not False for check in checks.values())
                except Exception:
                    passed = False

            if passed and run_start is None:
                run_start = value
            elif not passed and run_start is not None:
                run = (run_start, value - 1)
                if best is None or (run[1] - run[0]) > (best[1] - best[0]):
                    best = run
                run_start = None

        return best
