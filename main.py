from __future__ import annotations

import argparse
from pathlib import Path

from optimization import SolverConfig, format_solution, solve_timetable
from read_data import PlanData


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a school timetable with OR-Tools CP-SAT")
    parser.add_argument("--data-dir", default="data", help="Directory containing timetable input files")
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="Number of teaching days in the week (default: 5)",
    )
    parser.add_argument(
        "--slots-per-day",
        type=int,
        default=11,
        help="Number of lesson slots per day (default: 11; chosen because the repository data needs 55 class-slots per week in the largest class before parallel packing)",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=60.0,
        help="CP-SAT time limit in seconds",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel CP-SAT workers",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional file path for the formatted timetable output",
    )
    parser.add_argument(
        "--subject-daily-rule-mode",
        choices=["full-class-only", "strict-all"],
        default="full-class-only",
        help="Interpretation of the 'max same subject per day' rule. 'full-class-only' ignores subgroup-parallel family slots; 'strict-all' enforces it on all occupied class slots.",
    )
    parser.add_argument(
        "--additional-patterns-solution-csv",
        default="raw_data.csv",
        help="Optional CSV file with a known-valid timetable used to augment allowed parallel subgroup combinations when groups.json is incomplete.",
    )
    parser.add_argument(
        "--strict-subject-daily-hard",
        action="store_true",
        help="Enforce the max-2-and-consecutive per-subject-per-day rule as a hard constraint.",
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    data = PlanData(args.data_dir)
    config = SolverConfig(
        days=args.days,
        slots_per_day=args.slots_per_day,
        time_limit_seconds=args.time_limit,
        num_workers=args.workers,
        subject_daily_rule_mode=args.subject_daily_rule_mode,
        enforce_subject_daily_hard=args.strict_subject_daily_hard,
        additional_patterns_solution_csv=args.additional_patterns_solution_csv,
    )

    solution = solve_timetable(data, config)
    if solution is None:
        print("No feasible timetable found.")
        return 1

    rendered = format_solution(solution, config)
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")

    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())