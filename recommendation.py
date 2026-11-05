# recommendation.py
import math
import numpy as np
import file_utils
import section_checks


class EnergyRecommendation:
    """
    Finds the recommended (lower and upper bound) slider values for every track type.

    Each slider value is tested by building that track part and running the same physics
    checks the Create button uses (section_checks.analyze_section), so the recommended
    range always agrees with what Create will report.

    Entry speed of each section:
      - Frictionless (losses=None): every section is tested with the speed leaving 'Starts'.
        Track parts start and end at (almost) the same height and no energy is lost,
        so the speed entering each later section is nearly the same.
      - With friction / air resistance: energy is lost along the way, so each section is
        tested with the speed it will actually enter with. That speed comes from running
        the tracks the user has already picked for the sections before it (same chain as
        tracks.TrackPart.combine_tracks). A section left empty doesn't change the speed.
    """
    _cache = {}          # (section kind, track type, entry speed, range, losses) -> (min, max) or None
    _CACHE_LIMIT = 5000

    @classmethod
    def get_recommendations(cls, start_type, start_value, builders, sections, value_range=(1, 50),
                            losses=None, chosen=None):
        """
        start_type, start_value: what the user picked in the 'Starts' section
        builders: track type -> track part function (GUI.track_function_map)
        sections: section name -> list of track types to recommend for, in ride order,
                  e.g. {"Thrills 1": [...], "Turns": ["Helix", ...], ...}
        losses: None (frictionless) or physics.make_losses(...) for friction / air resistance
        chosen: {section name: (track type, value)} of the tracks the user has picked so far.
                Only used with losses, to find the speed entering each later section.
        Returns {"v_exit": float, "v_entry": {section: float},
                 section name: {track type: (min, max) or None}}
        """
        chosen = chosen or {}
        loss_key = tuple(sorted(losses.items())) if losses else None
        value_range = tuple(value_range)

        # Test builds must not save files into the section's Segments folder
        with file_utils.no_segment_writes():
            start_arrays, raw_v = builders[start_type](float(start_value))
            v_exit = section_checks.start_exit_speed(start_type, start_arrays, float(np.ravel(raw_v)[0]), losses)

            recs = {"v_exit": v_exit, "v_entry": {}}
            v = v_exit   # speed entering the next section
            for section_name, track_types in sections.items():
                v_entry = v if losses else v_exit
                recs["v_entry"][section_name] = v_entry
                recs[section_name] = {}
                for track_type in track_types:
                    if not (math.isfinite(v_entry) and v_entry > 0):
                        recs[section_name][track_type] = None   # the train never gets here
                        continue
                    # Thrills 1 and Thrills 2 use the same tracks, so a range is only tested once per speed
                    test_key = (section_name == "Ends", track_type, round(float(v_entry), 6), value_range, loss_key)
                    if test_key not in cls._cache:
                        if len(cls._cache) >= cls._CACHE_LIMIT:
                            cls._cache.clear()
                        cls._cache[test_key] = cls._safe_range(
                            builders[track_type], section_name, track_type, v_entry, value_range, losses)
                    recs[section_name][track_type] = cls._cache[test_key]

                # Carry the speed through the track the user picked here (if any)
                if losses and section_name in chosen and v > 0:
                    v = cls._exit_speed(builders, section_name, chosen[section_name], v, losses)

        return recs

    @staticmethod
    def _exit_speed(builders, section_name, pick, v_entry, losses):
        """Speed leaving the user's chosen track for this section (0 if the train stalls in it)."""
        track_type, value = pick
        if not track_type or track_type not in builders:
            return v_entry   # section skipped: speed unchanged
        try:
            _, _, v_out = section_checks.analyze_section(
                section_name, track_type, builders[track_type](float(value)), v_entry, losses)
            v_out = float(v_out)
        except Exception:
            return 0.0
        return v_out if math.isfinite(v_out) else 0.0

    @staticmethod
    def _safe_range(build, section_name, track_type, v_entry, value_range, losses=None):
        """Largest continuous range of slider values where every physics check passes, or None."""
        best = None
        run_start = None
        low, high = value_range

        for value in range(low, high + 2):   # one extra step closes a run that reaches 'high'
            passed = False
            if value <= high:
                try:
                    _, checks, _ = section_checks.analyze_section(section_name, track_type, build(float(value)), v_entry, losses)
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
