from collections import defaultdict
import numpy as np
from ortools.sat.python import cp_model
from read_data import PlanData
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# def create_blocks(data: PlanData) -> np.ndarray:

#     return


def distribute_hours(data: PlanData) -> np.ndarray:
    main_requirements = data.get_main_requirements_array()
    print(len(main_requirements))
    model = cp_model.CpModel()

    decision_vars = np.empty((5, len(main_requirements)), dtype=object)
    for d in range(5):
        for i, main_requirement in enumerate(main_requirements):
            decision_vars[d, i] = model.new_int_var(
                0, 2, f"{d+1}: {data.main_requirement_to_txt(main_requirement)}"
            )

    for i, (_, _, _, h) in enumerate(main_requirements):
        model.add(sum(decision_vars[:, i]) == h)

    for t, teacher in enumerate(data.teachers):
        teacher_requirements_index = [
            i for i in range(len(main_requirements)) if t in main_requirements[i][1]
        ]

        for d in range(5):
            model.Add(sum(decision_vars[d, i] for i in teacher_requirements_index) <= 8)

    optim_vars = []
    for c, student_group in enumerate(data.student_groups):
        student_group_index = [
            i for i in range(len(main_requirements)) if c in main_requirements[i][2]
        ]
        tmp = []
        for d in range(5):
            tmp.append(
                model.new_int_var(0, 20, f"{data.student_groups[c]} lesson for day {d}")
            )
        var = model.new_int_var(0, 20, f"max {data.student_groups[c]} lessons")
        model.add_max_equality(var, tmp)
        optim_vars.append(var)

    model.minimize(sum(optim_vars))

    solver = cp_model.CpSolver()
    status = solver.solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        solution = np.empty_like(decision_vars, dtype=int)
        for idx, var in np.ndenumerate(decision_vars):
            solution[idx] = solver.Value(var)
        return solution
    else:
        print("No solution found.")
        return None


def construct_plan(
    data: PlanData, blocks: np.ndarray, horizon: int = 11
) -> pd.DataFrame | None:
    main_requirements = data.get_main_requirements_array()
    
    model = cp_model.CpModel()

    intervals: dict[tuple[tuple[int]], list[cp_model.IntervalVar]] = defaultdict(list)
    starts: dict[tuple[tuple[int]], list[cp_model.IntervalVar]] = defaultdict(list)
    days: dict[tuple[tuple[int]], list[cp_model.IntervalVar]] = defaultdict(list)
    for block, h in main_requirements:
        s_, t_, s_ = block
        for _ in range(min(5, h)):
            start
            intervals[block].append(model.newin)
            
            


    # intervals: dict[tuple, tuple] = {}
    # day_vars: dict[tuple, object] = {}
    # starts: dict[tuple, object] = {}

    # for d in range(5):
    #     for block, h in enumerate(blocks[d]):
    #         if not h:
    #             continue

    #         block_name = data.main_requirement_to_txt(main_requirements[block])
    #         key = (block, d)

    #         # x-axis: day
    #         day_var = model.new_int_var(0, 4, f"day_d{d}_{block_name}")
    #         model.add_hint(day_var, d)
    #         xi = model.new_fixed_size_interval_var(day_var, 1, f"xi_d{d}_{block_name}")

    #         # y-axis
    #         start = model.new_int_var(0, horizon - h, f"start_d{d}_{block_name}")
    #         yi = model.new_fixed_size_interval_var(start, h, f"yi_d{d}_{block_name}")

    #         intervals[key] = (xi, yi)
    #         day_vars[key] = day_var
    #         starts[key] = start

    # for c in range(len(data.student_groups)):
    #     xi_list, yi_list = [], []
    #     for d in range(5):
    #         for block, h in enumerate(blocks[d]):
    #             if h and c in main_requirements[block][2]:
    #                 xi, yi = intervals[(block, d)]
    #                 xi_list.append(xi)
    #                 yi_list.append(yi)

    #     if len(xi_list) >= 2:
    #         model.add_no_overlap_2d(xi_list, yi_list)

    # solver = cp_model.CpSolver()
    # solver.parameters.log_search_progress = True
    # status = solver.solve(model)

    # if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    #     print("No solution found.")
    #     return None

    # ia_idx = data.student_groups.index("1B")
    # day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    # df = pd.DataFrame(
    #     [[[] for _ in range(horizon)] for _ in range(5)],
    #     index=day_labels,
    #     columns=range(horizon),
    # )

    # for d in range(5):
    #     for block, h in enumerate(blocks[d]):
    #         if not h:
    #             continue
    #         _, _, student_groups, _ = main_requirements[block]
    #         if ia_idx not in student_groups:
    #             continue
    #         subject_name = data.subjects[main_requirements[block][0][0]]
    #         key = (block, d)
    #         solved_day = solver.value(day_vars[key])
    #         start_val = solver.value(starts[key])
    #         for t in range(start_val, start_val + h):
    #             if t < horizon:
    #                 df.at[day_labels[solved_day], t].append(subject_name)

    # return df


DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOT_LABELS = [f"{8+i}:00" for i in range(11)]  # 08:00 … 18:00


def visualise_plan(df: pd.DataFrame, out_path: str = "plan_1A.png") -> None:
    """Draw the 1A timetable as a coloured grid (days × time slots)."""
    horizon = len(df.columns)
    n_days = len(df.index)

    # build a subject→colour map
    all_subjects = sorted({subj for row in df.values for cell in row for subj in cell})
    cmap = plt.cm.get_cmap("tab20", max(len(all_subjects), 1))
    colour_of = {s: cmap(i) for i, s in enumerate(all_subjects)}

    fig, ax = plt.subplots(figsize=(horizon * 1.4 + 1, n_days * 1.2 + 1))
    ax.set_xlim(0, horizon)
    ax.set_ylim(0, n_days)
    ax.invert_yaxis()
    ax.set_aspect("equal")

    for row_idx, day in enumerate(DAY_LABELS):
        for col_idx in range(horizon):
            subjects = df.at[day, col_idx]
            if not subjects:
                continue
            subj = subjects[0]  # there should be exactly one per cell now
            colour = colour_of.get(subj, "lightgrey")
            rect = mpatches.FancyBboxPatch(
                (col_idx + 0.04, row_idx + 0.04),
                0.92,
                0.92,
                boxstyle="round,pad=0.02",
                linewidth=1,
                edgecolor="black",
                facecolor=colour,
                alpha=0.85,
            )
            ax.add_patch(rect)
            ax.text(
                col_idx + 0.5,
                row_idx + 0.5,
                subj[:12],
                ha="center",
                va="center",
                fontsize=7,
                fontweight="bold",
                wrap=True,
            )

    # grid lines
    for x in range(horizon + 1):
        ax.axvline(x, color="grey", linewidth=0.4)
    for y in range(n_days + 1):
        ax.axhline(y, color="grey", linewidth=0.4)

    ax.set_xticks([i + 0.5 for i in range(horizon)])
    ax.set_xticklabels(SLOT_LABELS[:horizon], fontsize=8)
    ax.set_yticks([i + 0.5 for i in range(n_days)])
    ax.set_yticklabels(DAY_LABELS, fontsize=9)
    ax.set_title("Class 1A – Weekly Timetable", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Timetable saved to  {out_path}")


if __name__ == "__main__":
    data = PlanData("data")
    blocks = distribute_hours(data)

    df = construct_plan(data, blocks)
    if df is not None:
        print(df)
        # visualise_plan(df)
