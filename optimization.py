from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

import pandas as pd

from ortools.sat.python import cp_model

from read_data import PlanData, normalize_subject


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class SolverConfig:
    days: int = 5
    slots_per_day: int = 11
    time_limit_seconds: float = 60.0
    num_workers: int = 8
    random_seed: int = 0
    teacher_gap_weight: int = 10_000
    class_balance_weight: int = 800
    partial_group_weight: int = 200
    room_weight_divisor: int = 20
    subject_daily_rule_mode: str = "full-class-only"
    enforce_subject_daily_hard: bool = False
    additional_patterns_solution_csv: str = "raw_data.csv"


@dataclass(frozen=True)
class TimetableCell:
    label: str
    rooms: tuple[str, ...]
    is_partial_group: bool


@dataclass
class TimetableSolution:
    status_name: str
    objective_value: int | float
    class_timetables: dict[str, list[list[list[TimetableCell]]]]
    teacher_gap_count: int
    class_spread: dict[str, int]
    partial_group_slots: int
    room_score: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_csv_hints(
    data: PlanData,
    csv_path: str,
    slots_per_day: int,
) -> dict[str, list[tuple[int, int]]] | None:
    """Return ``{lesson_id: sorted[(day, slot)]}`` from a known-valid CSV."""
    path = Path(csv_path)
    if not path.exists():
        return None

    df = pd.read_csv(path).dropna(subset=["Subject"]).fillna("")
    df = df[
        (df["Subject"].astype(str).str.strip() != "")
        & (df["Teacher"].astype(str).str.strip() != "")
    ].copy()
    df["Day"] = pd.to_numeric(df["Day"], errors="coerce").fillna(-1).astype(int)
    df["Slot"] = pd.to_numeric(df["Slot"], errors="coerce").fillna(-1).astype(int)
    df = df[(df["Day"] >= 0) & (df["Slot"] >= 0)]

    by_key: dict[tuple[str, str, str], str] = {}
    for lesson in data.lessons:
        for cn in lesson.classes:
            by_key[(lesson.subject, lesson.teacher, cn)] = lesson.lesson_id

    lid_pos: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for row in df.itertuples(index=False):
        lid = by_key.get((
            normalize_subject(str(row.Subject).strip()),
            str(row.Teacher).strip(),
            str(row.Student_group).strip(),
        ))
        if lid is not None:
            lid_pos[lid].add((int(str(row.Day)), int(str(row.Slot))))

    S = slots_per_day
    return {
        lid: sorted(positions, key=lambda x: x[0] * S + x[1])
        for lid, positions in lid_pos.items()
    }


def _build_class_families(
    data: PlanData,
    csv_path: str,
) -> dict[str, list[set[str]]]:
    """For each class, build merged families of lesson-IDs that may overlap."""
    empirical = data.get_additional_parallel_patterns_from_solution(csv_path)
    result: dict[str, list[set[str]]] = {}

    for class_name in data.student_groups:
        families: list[set[str]] = []

        for family in data.group_families.get(class_name, []):
            families.append(set(family.lesson_ids))

        for pattern_set in empirical.get(class_name, set()):
            lid_set = set(pattern_set)
            if len(lid_set) < 2:
                continue
            merged = False
            for existing in families:
                if existing & lid_set:
                    existing.update(lid_set)
                    merged = True
                    break
            if not merged:
                families.append(lid_set)

        # Merge overlapping families until stable
        changed = True
        while changed:
            changed = False
            merged_list: list[set[str]] = []
            for f in families:
                did_merge = False
                for mf in merged_list:
                    if mf & f:
                        mf.update(f)
                        did_merge = True
                        changed = True
                        break
                if not did_merge:
                    merged_list.append(f)
            families = merged_list

        result[class_name] = families
    return result


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def solve_timetable(
    data: PlanData, config: SolverConfig | None = None,
) -> TimetableSolution | None:
    config = config or SolverConfig()
    model = cp_model.CpModel()

    D = config.days
    S = config.slots_per_day

    # ---- Family structure ----
    class_families = _build_class_families(data, config.additional_patterns_solution_csv)

    # ---- Decision variables: (day, slot) per lesson occurrence ----
    day_v: dict[tuple[str, int], cp_model.IntVar] = {}
    slot_v: dict[tuple[str, int], cp_model.IntVar] = {}
    x_iv: dict[tuple[str, int], cp_model.IntervalVar] = {}
    y_iv: dict[tuple[str, int], cp_model.IntervalVar] = {}

    for lesson in data.lessons:
        lid = lesson.lesson_id
        for i in range(lesson.weekly_hours):
            dv = model.new_int_var(0, D - 1, f"d::{lid}::{i}")
            sv = model.new_int_var(0, S - 1, f"s::{lid}::{i}")
            day_v[(lid, i)] = dv
            slot_v[(lid, i)] = sv
            x_iv[(lid, i)] = model.new_fixed_size_interval_var(
                dv, 1, f"xi::{lid}::{i}"
            )
            y_iv[(lid, i)] = model.new_fixed_size_interval_var(
                sv, 1, f"yi::{lid}::{i}"
            )

        # Symmetry breaking: order occurrences by encoded position
        for i in range(1, lesson.weekly_hours):
            model.add(
                day_v[(lid, i - 1)] * S + slot_v[(lid, i - 1)]
                < day_v[(lid, i)] * S + slot_v[(lid, i)]
            )

    # ---- Teacher no-overlap ----
    teacher_occs: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for lesson in data.lessons:
        for i in range(lesson.weekly_hours):
            teacher_occs[lesson.teacher].append((lesson.lesson_id, i))

    for occs in teacher_occs.values():
        if len(occs) > 1:
            model.add_no_overlap_2d(
                [x_iv[k] for k in occs],
                [y_iv[k] for k in occs],
            )

    # ---- Class no-overlap with family exclusions ----
    #
    # For each family member m, build:
    #   no_overlap_2d( all_class_occ  minus  siblings_of_m )
    #
    # m is IN the set  ->  can't share a slot with non-family or other families
    # siblings are OUT ->  m CAN share a slot with its own family
    #
    # Classes without families get a single no_overlap_2d over everything.

    for class_name in data.student_groups:
        class_occs = [
            (lesson.lesson_id, i)
            for lesson in data.lessons
            if class_name in lesson.classes
            for i in range(lesson.weekly_hours)
        ]

        families = class_families[class_name]

        if not families:
            if len(class_occs) > 1:
                model.add_no_overlap_2d(
                    [x_iv[k] for k in class_occs],
                    [y_iv[k] for k in class_occs],
                )
        else:
            for fam in families:
                for m_lid in fam:
                    siblings = fam - {m_lid}
                    included = [k for k in class_occs if k[0] not in siblings]
                    if len(included) > 1:
                        model.add_no_overlap_2d(
                            [x_iv[k] for k in included],
                            [y_iv[k] for k in included],
                        )

    # ---- CSV hints ----
    hints = _load_csv_hints(data, config.additional_patterns_solution_csv, S)
    if hints:
        for lid, positions in hints.items():
            for i, (d, s) in enumerate(positions):
                if (lid, i) in day_v:
                    model.add_hint(day_v[(lid, i)], d)
                    model.add_hint(slot_v[(lid, i)], s)

    # ---- Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.time_limit_seconds
    solver.parameters.num_search_workers = config.num_workers
    solver.parameters.random_seed = config.random_seed

    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # ---- Build class timetables ----
    class_names = list(data.student_groups)
    class_timetables: dict[str, list[list[list[TimetableCell]]]] = {
        cn: [[[] for _ in range(S)] for _ in range(D)] for cn in class_names
    }

    for lesson in data.lessons:
        lid = lesson.lesson_id
        for i in range(lesson.weekly_hours):
            d = solver.value(day_v[(lid, i)])
            s = solver.value(slot_v[(lid, i)])
            label = f"{lesson.subject} [{lesson.teacher}]"
            if lesson.is_multiclass:
                label += f" ({'+'.join(lesson.classes)})"
            cell = TimetableCell(label=label, rooms=("?",), is_partial_group=False)
            for cn in lesson.classes:
                class_timetables[cn][d][s].append(cell)

    # ---- Metrics ----
    tds: dict[tuple[str, int], list[int]] = defaultdict(list)
    for lesson in data.lessons:
        for i in range(lesson.weekly_hours):
            d = solver.value(day_v[(lesson.lesson_id, i)])
            s = solver.value(slot_v[(lesson.lesson_id, i)])
            tds[(lesson.teacher, d)].append(s)

    teacher_gaps = sum(
        max(ss) - min(ss) + 1 - len(ss)
        for ss in tds.values()
        if len(ss) > 1
    )

    cdb: dict[tuple[str, int], set[int]] = defaultdict(set)
    for lesson in data.lessons:
        for i in range(lesson.weekly_hours):
            d = solver.value(day_v[(lesson.lesson_id, i)])
            s = solver.value(slot_v[(lesson.lesson_id, i)])
            for cn in lesson.classes:
                cdb[(cn, d)].add(s)

    class_spread = {
        cn: (
            max(len(cdb.get((cn, d), set())) for d in range(D))
            - min(len(cdb.get((cn, d), set())) for d in range(D))
        )
        for cn in class_names
    }

    return TimetableSolution(
        status_name=solver.status_name(status),
        objective_value=0,
        class_timetables=class_timetables,
        teacher_gap_count=teacher_gaps,
        class_spread=class_spread,
        partial_group_slots=0,
        room_score=0,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_solution(solution: TimetableSolution, config: SolverConfig) -> str:
    lines = [
        f"Status: {solution.status_name}",
        f"Objective: {solution.objective_value}",
        f"Teacher gaps: {solution.teacher_gap_count}",
        f"Partial-group slots: {solution.partial_group_slots}",
        f"Room score: {solution.room_score}",
        "",
    ]

    for class_name, timetable in solution.class_timetables.items():
        lines.append(f"=== {class_name} ===")
        for day in range(config.days):
            day_name = DAY_NAMES[day] if day < len(DAY_NAMES) else f"Day {day + 1}"
            lines.append(day_name)
            for slot in range(config.slots_per_day):
                cells = timetable[day][slot]
                if not cells:
                    continue
                rendered = []
                for cell in cells:
                    room_text = f" @ {', '.join(cell.rooms)}" if cell.rooms else ""
                    edge_text = " [edge]" if cell.is_partial_group else ""
                    rendered.append(f"{cell.label}{room_text}{edge_text}")
                lines.append(f"  {slot + 1:02d}. " + " || ".join(rendered))
            lines.append("")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
