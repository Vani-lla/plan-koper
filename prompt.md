Design and implement a school timetable generator in Python using Google OR-Tools CP-SAT.

Use the code in this repository as the starting point, especially `read_data.py` and the `PlanData.get_main_requirements_array()` helper, but feel free to refactor and create additional modules if that produces a cleaner solution.

The result should be clean, well-structured code plus a short explanation of the modeling decisions, assumptions, and solve strategy.

## Repository context

Work inside this repository and use the files in `data/` as the source of truth.

### Data files

`requirements.csv`
- Main weekly demand matrix.
- Columns are class/division names such as `1A`, `1B`, `2A`, etc.
- The first column is `Subject/Teacher`.
- Rows alternate between:
	- a subject row, such as `ang`, `mat`, `biol`,
	- followed by one or more teacher rows that specify how many hours that teacher teaches that subject in each class.
- The teacher rows under a given subject partition the subject demand for that subject.
- This file should be transformed into atomic weekly lesson requirements of the form:
	- subject,
	- teacher,
	- class or classes,
	- required weekly hours.

`multiclass_blocks.csv`
- Defines lessons attended jointly by multiple classes.
- A row contains one teacher, one subject, and binary flags for the participating classes.
- These blocks are mandatory and must be scheduled as synchronized common lessons for all listed classes.
- `PlanData.get_main_requirements_array()` already merges such rows into combined requirements and validates that all involved classes need the same number of hours.

`groups.json`
- Authoritative description of within-class parallel-group lesson variants.
- Structure:
	- class -> group family name -> list of variants.
- Each variant is a list of one or more `[subject, teacher]` pairs that may run simultaneously.
- Example: for class `1A`, family `ang+inf`, one variant is `[["ang", "MM"], ["inf", "TG"]]`.
- This means the class can split into subgroups and those lessons can run in parallel.
- Some families cover all subgroups simultaneously, some cover only part of the class.
- If a timeslot covers only part of the class, that timeslot must be placed at the beginning or the end of the day for that class.
- If a timeslot covers all subgroups, it may appear in the middle of the day.

`overlapping_lessons.json` and `overlapping_lessons.csv`
- Legacy/coarser overlap hints.
- You may inspect them if useful, but `groups.json` should be treated as the more precise source for parallel-group behavior.

`rooms.csv`
- Room suitability matrix.
- Columns are subjects, rows are rooms.
- Value `0` means the subject cannot be taught in that room.
- Higher positive values mean the room is a better fit for that subject.
- The solver should forbid invalid room assignments and prefer better rooms in the objective.

`subjects.txt`, `teachers.txt`
- Supporting lists of subjects and teachers.
- Note: the scheduling CSV files currently use teacher short codes such as `MM`, `TG`, `PC`, while `teachers.txt` contains full names. Keep the code consistent with the identifiers actually used in the scheduling data.

## Core goal

Build a weekly timetable for all classes that satisfies the hard constraints and then optimizes timetable quality.

Use OR-Tools CP-SAT, not a greedy-only approach.

## Required modeling approach

Use a two-level interpretation of lessons:

1. Weekly lesson requirements
- Derived from `requirements.csv` and `multiclass_blocks.csv`.
- Each requirement represents how many weekly hours of a subject-teacher-class combination must be scheduled.

2. Timetable placements
- Concrete assignments of lesson blocks to `(day, slot, room)`.
- A lesson may involve one class, one subgroup, multiple subgroups, or multiple classes in the case of `multiclass_blocks.csv`.

Make the number of days and the number of slots per day configurable. Default to a standard 5-day week.

## Hard constraints

### 1. Weekly demand must be satisfied exactly
- Every required lesson hour from the processed requirements must be scheduled exactly once.
- Multiclass blocks must be scheduled exactly as shared lessons for all participating classes.

### 2. No teacher conflicts
- A teacher cannot teach more than one lesson in the same timeslot.

### 3. No class conflicts
- A class cannot attend more than one full-class lesson in the same timeslot.
- Parallel lessons are allowed only when they correspond to a valid subgroup split described by `groups.json`.

### 4. No subgroup conflicts
- Inside a class, a subgroup cannot be assigned to two lessons in the same timeslot.
- Parallel lessons are valid only if they cover disjoint subgroup demand.

### 5. Partial-group lessons must be edge lessons
- If, in a given class and timeslot, only some subgroups are occupied while others are free, that slot must be at the beginning or the end of that class's day.
- If all subgroups are occupied, the slot may appear anywhere within the day.

### 6. No student gaps
- For each class, the occupied timeslots within a day must form one contiguous block.
- This applies to the class day as seen by students.
- Partial-group edge lessons are allowed only on the outer boundary of that contiguous block.

### 7. Maximum repeated subject load per day
- A class cannot have more than 2 hours of the same subject in one day.
- If a class has 2 hours of the same subject on a day, those 2 hours must be consecutive.

### 8. Room feasibility
- Every scheduled lesson must be assigned to exactly one valid room.
- Room suitability must be positive for that subject.
- A room cannot host more than one lesson in the same timeslot.

### 9. Multiclass synchronization
- If a lesson belongs to a multiclass block, all participating classes must share the same day and slot.
- Model it as one common lesson event, not duplicated independent lessons.

## Parallel-group interpretation

This is the most important special case.

Within one class, some subjects are taught in groups and may run in parallel. The valid combinations come from `groups.json`.

Example for `1A`:
- `ang MM + inf TG`
- `ang PC + inf TG`
- `ang MM + ang PC`

Invalid example:
- `inf TG + inf TG`
- invalid because the same teacher cannot teach two lessons at once.

Also possible:
- only `ang MM`
- but then it must be an edge lesson for that day.

You must handle uneven demand carefully.

Example:
- if both subgroup subjects require balanced even counts, the schedule may consist entirely of paired parallel blocks,
- but if one side requires more hours than the other, the excess hours must appear as single-group edge lessons.

The solver must not create logically inconsistent combinations such as satisfying one subgroup's English demand while accidentally leaving the other subgroup without the required IT or language hours.

In other words:
- treat subgroup scheduling as coverage of subgroup-specific demand,
- permit only combinations that are compatible with the variant families from `groups.json`,
- and use edge placements only for the unmatched remainder that cannot be paired into full parallel blocks.

Do not hardcode only the `1A` case. Generalize this to the structure present in `groups.json`.

## Optimization goals

After satisfying all hard constraints, optimize the timetable quality.

Use either a weighted objective or a lexicographic objective, but document the choice.

Priorities:

1. Minimize teacher gaps within a day.
- A teacher may have a free day; that is acceptable.
- But on days when a teacher works, avoid holes between their first and last lesson.

2. Keep student load balanced across the week.
- Distribute each class's lessons as uniformly as possible over the days.
- Avoid very short days combined with overloaded days when a better balance exists.

3. Prefer better rooms.
- Maximize total room suitability score, or equivalently minimize a penalty for poor room choices.

4. Encourage useful parallel-group packing.
- When a full subgroup family can be scheduled as one simultaneous block, prefer that over unnecessarily splitting it into single-group edge lessons.
- This is a soft preference, not a license to violate demand or subgroup coverage.

## Implementation requirements

Produce clean code with clear steps.

At minimum, the solution should include:

1. Data preprocessing
- Parse the raw files into a normalized internal representation.
- Reuse or improve `PlanData` if helpful.
- Make the treatment of multiclass blocks and parallel-group families explicit.

2. Solver model
- Build a CP-SAT model with well-named decision variables.
- Separate hard constraints from soft penalties in the code.

3. Output
- Return or print a readable timetable structure.
- Include lesson subject, teacher, class or subgroup information, timeslot, and room.

4. Explanation
- Briefly explain:
	- the data model,
	- the decision variables,
	- the hard constraints,
	- the objective terms,
	- and any assumptions needed because the data is incomplete or ambiguous.

## Assumptions and ambiguity handling

If some detail is not fully specified by the data, do not silently guess. Instead:

- make the smallest reasonable modeling assumption,
- document it clearly,
- keep the assumption isolated in code so it can be changed later.

Examples of acceptable documented assumptions:
- how many slots per day exist by default,
- whether a multiclass lesson uses one shared room,
- how subgroup identities are represented internally when `groups.json` provides valid variants but not explicit subgroup labels.

## Suggested deliverable structure

Prefer a structure close to:

- `read_data.py` for parsing and normalization,
- a dedicated solver module for CP-SAT model construction,
- a small runner in `main.py`,
- optional helper utilities for formatting or validation.

## Expected outcome

Provide a working OR-Tools timetable solution for this repository, not just high-level pseudocode.

The code should be readable, modular, and ready to extend.