from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import json
from pathlib import Path

import pandas as pd


SUBJECT_ALIASES = {
    "zajkszkr": "zajksztkr",
}


def normalize_subject(subject: str) -> str:
    return SUBJECT_ALIASES.get(subject.strip(), subject.strip())


def get_txt(path: str | Path) -> list[str]:
    with Path(path).open("r", encoding="utf-8") as file:
        return [line.strip() for line in file.readlines() if line.strip()]


@dataclass(frozen=True)
class AtomicLesson:
    lesson_id: str
    subject: str
    teacher: str
    classes: tuple[str, ...]
    weekly_hours: int
    grouped_class: str | None = None
    family_name: str | None = None

    @property
    def is_multiclass(self) -> bool:
        return len(self.classes) > 1

    @property
    def is_grouped(self) -> bool:
        return self.grouped_class is not None


@dataclass(frozen=True)
class GroupPattern:
    pattern_id: str
    lessons: tuple[str, ...]
    is_full_coverage: bool


@dataclass
class GroupFamily:
    class_name: str
    family_name: str
    lesson_ids: tuple[str, ...]
    full_patterns: tuple[GroupPattern, ...]
    partial_patterns: tuple[GroupPattern, ...]

    @property
    def all_patterns(self) -> tuple[GroupPattern, ...]:
        return self.full_patterns + self.partial_patterns


class PlanData:
    def __init__(self, data_path: str | Path):
        self._data_path = Path(data_path)

        self.subjects = [normalize_subject(subject) for subject in get_txt(self._data_path / "subjects.txt")]
        self._subject_set = set(self.subjects)
        self.main_requirements = self._get_main_requirements_df()
        self.student_groups = self.main_requirements.columns.tolist()

        teacher_requirements = self._parse_teacher_requirements()
        self._multiclass_blocks = pd.read_csv(self._data_path / "multiclass_blocks.csv").fillna(0)
        self.lessons = self._build_atomic_lessons(teacher_requirements)
        self.lesson_by_id = {lesson.lesson_id: lesson for lesson in self.lessons}
        self.group_families = self._build_group_families()
        self.teachers = sorted({lesson.teacher for lesson in self.lessons})
        self.room_scores = self._read_room_scores()

        missing_room_subjects = {
            lesson.subject for lesson in self.lessons if lesson.subject not in self.room_scores
        }
        if missing_room_subjects:
            raise ValueError(
                "Missing room suitability data for subjects: "
                + ", ".join(sorted(missing_room_subjects))
            )

    def _get_main_requirements_df(self) -> pd.DataFrame:
        df = pd.read_csv(self._data_path / "requirements.csv")
        df.index = df[df.columns[0]]
        df.drop(df.columns[0], axis=1, inplace=True)
        return df.fillna(0).astype(int)

    def _parse_teacher_requirements(self) -> dict[tuple[str, str, str], int]:
        requirements_df = pd.read_csv(self._data_path / "requirements.csv").fillna(0)
        class_names = list(requirements_df.columns[1:])
        current_subject: str | None = None
        parsed: dict[tuple[str, str, str], int] = {}

        for row in requirements_df.itertuples(index=False):
            label = str(row[0]).strip()
            values = [int(value) for value in row[1:]]
            normalized_label = normalize_subject(label)

            if normalized_label in self._subject_set:
                current_subject = normalized_label
                continue

            if current_subject is None:
                raise ValueError(f"Teacher row {label!r} appears before any subject row")

            for class_name, hours in zip(class_names, values, strict=True):
                if hours <= 0:
                    continue
                parsed[(current_subject, label, class_name)] = hours

        return parsed

    def _build_atomic_lessons(
        self, teacher_requirements: dict[tuple[str, str, str], int]
    ) -> list[AtomicLesson]:
        remaining = dict(teacher_requirements)
        lessons: list[AtomicLesson] = []

        for _, row in self._multiclass_blocks.iterrows():
            teacher = str(row["Teacher"]).strip()
            subject = normalize_subject(str(row["Subject"]).strip())
            participating_classes = tuple(
                class_name
                for class_name in self.student_groups
                if int(row[class_name]) == 1
            )
            if not participating_classes:
                continue

            keys = [(subject, teacher, class_name) for class_name in participating_classes]
            missing_keys = [key for key in keys if key not in remaining]
            if missing_keys:
                missing_txt = ", ".join(f"{subject}/{teacher}/{class_name}" for _, _, class_name in missing_keys)
                raise ValueError(f"Multiclass block refers to missing requirement rows: {missing_txt}")

            hours = {remaining[key] for key in keys}
            if len(hours) != 1:
                raise ValueError(
                    f"Multiclass block {subject}/{teacher}/{participating_classes} has unequal hours: {sorted(hours)}"
                )

            for key in keys:
                del remaining[key]

            lesson_id = f"multi::{subject}::{teacher}::{'+'.join(participating_classes)}"
            lessons.append(
                AtomicLesson(
                    lesson_id=lesson_id,
                    subject=subject,
                    teacher=teacher,
                    classes=participating_classes,
                    weekly_hours=hours.pop(),
                )
            )

        for (subject, teacher, class_name), hours in sorted(remaining.items()):
            lesson_id = f"single::{class_name}::{subject}::{teacher}"
            lessons.append(
                AtomicLesson(
                    lesson_id=lesson_id,
                    subject=subject,
                    teacher=teacher,
                    classes=(class_name,),
                    weekly_hours=hours,
                )
            )

        return lessons

    def _build_group_families(self) -> dict[str, list[GroupFamily]]:
        with (self._data_path / "groups.json").open("r", encoding="utf-8") as file:
            raw_groups = json.load(file)

        by_key = {
            (lesson.subject, lesson.teacher, class_name): lesson
            for lesson in self.lessons
            for class_name in lesson.classes
        }

        grouped_families: dict[str, list[GroupFamily]] = {class_name: [] for class_name in self.student_groups}
        grouped_lesson_ids: set[str] = set()

        for class_name, families in raw_groups.items():
            for family_name, variants in families.items():
                normalized_variants = [
                    tuple((normalize_subject(subject), teacher) for subject, teacher in variant)
                    for variant in variants
                ]

                lesson_ids = []
                for variant in normalized_variants:
                    for subject, teacher in variant:
                        key = (subject, teacher, class_name)
                        lesson = by_key.get(key)
                        if lesson is None:
                            raise ValueError(
                                f"groups.json refers to missing lesson {subject}/{teacher}/{class_name}"
                            )
                        lesson_ids.append(lesson.lesson_id)

                family_lesson_ids = tuple(sorted(set(lesson_ids)))
                full_pattern_lesson_sets = self._derive_full_pattern_lesson_sets(
                    class_name=class_name,
                    family_name=family_name,
                    normalized_variants=normalized_variants,
                    lesson_lookup=by_key,
                )

                full_patterns = tuple(
                    GroupPattern(
                        pattern_id=f"{class_name}::{family_name}::full::{pattern_index}",
                        lessons=lesson_set,
                        is_full_coverage=True,
                    )
                    for pattern_index, lesson_set in enumerate(sorted(full_pattern_lesson_sets))
                )

                partial_sets: set[tuple[str, ...]] = set()
                for lesson_set in full_pattern_lesson_sets:
                    for subset_size in range(1, len(lesson_set)):
                        for subset in combinations(lesson_set, subset_size):
                            partial_sets.add(tuple(sorted(subset)))

                partial_patterns = tuple(
                    GroupPattern(
                        pattern_id=f"{class_name}::{family_name}::partial::{pattern_index}",
                        lessons=lesson_set,
                        is_full_coverage=False,
                    )
                    for pattern_index, lesson_set in enumerate(sorted(partial_sets))
                )

                group_family = GroupFamily(
                    class_name=class_name,
                    family_name=family_name,
                    lesson_ids=family_lesson_ids,
                    full_patterns=full_patterns,
                    partial_patterns=partial_patterns,
                )
                grouped_families[class_name].append(group_family)
                grouped_lesson_ids.update(family_lesson_ids)

        self._grouped_lesson_ids = grouped_lesson_ids
        return grouped_families

    def _derive_full_pattern_lesson_sets(
        self,
        class_name: str,
        family_name: str,
        normalized_variants: list[tuple[tuple[str, str], ...]],
        lesson_lookup: dict[tuple[str, str, str], AtomicLesson],
    ) -> set[tuple[str, ...]]:
        full_patterns: set[tuple[str, ...]] = set()

        if all(len(variant) == 1 for variant in normalized_variants):
            lesson_ids = tuple(
                sorted(
                    lesson_lookup[(subject, teacher, class_name)].lesson_id
                    for ((subject, teacher),) in normalized_variants
                )
            )
            full_patterns.add(lesson_ids)
            return full_patterns

        variant_widths = {len(variant) for variant in normalized_variants}
        if len(variant_widths) != 1:
            raise ValueError(
                f"Mixed-width group family {class_name}/{family_name} is not supported: {sorted(variant_widths)}"
            )

        target_width = next(iter(variant_widths))

        for variant in normalized_variants:
            lesson_ids = tuple(
                sorted(lesson_lookup[(subject, teacher, class_name)].lesson_id for subject, teacher in variant)
            )
            full_patterns.add(lesson_ids)

        lessons_by_subject: dict[str, list[str]] = {}
        for variant in normalized_variants:
            for subject, teacher in variant:
                lesson_id = lesson_lookup[(subject, teacher, class_name)].lesson_id
                lessons_by_subject.setdefault(subject, []).append(lesson_id)

        # Assumption for mixed families such as ang+inf:
        # when one subject has enough teacher-specific variants to fill the slot width,
        # that same-subject bundle is also considered a full-coverage pattern.
        for lesson_ids in lessons_by_subject.values():
            distinct_lesson_ids = tuple(sorted(set(lesson_ids)))
            if len(distinct_lesson_ids) == target_width:
                full_patterns.add(distinct_lesson_ids)

        for pattern in full_patterns:
            teachers = [updated.teacher for updated in (self.lesson_by_id[lesson_id] for lesson_id in pattern)]
            if len(teachers) != len(set(teachers)):
                raise ValueError(
                    f"Family {class_name}/{family_name} produced a full pattern with repeated teacher"
                )

        return full_patterns

    def _read_room_scores(self) -> dict[str, dict[str, int]]:
        rooms_df = pd.read_csv(self._data_path / "rooms.csv").fillna(0)
        column_lookup = {
            normalize_subject(column): column
            for column in rooms_df.columns
            if column != "Room"
        }

        room_scores: dict[str, dict[str, int]] = {}
        for subject, original_column in column_lookup.items():
            scores: dict[str, int] = {}
            for row in rooms_df.itertuples(index=False):
                room_name = str(row.Room)
                score = float(getattr(row, original_column))
                if score > 0:
                    scores[room_name] = int(round(score * 1000))
            room_scores[subject] = scores
        return room_scores

    @property
    def grouped_lessons(self) -> list[AtomicLesson]:
        return [lesson for lesson in self.lessons if lesson.lesson_id in self._grouped_lesson_ids]

    @property
    def ungrouped_lessons(self) -> list[AtomicLesson]:
        return [lesson for lesson in self.lessons if lesson.lesson_id not in self._grouped_lesson_ids]

    def get_main_requirements_array(self) -> list[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], int]]:
        teacher_index = {teacher: idx for idx, teacher in enumerate(self.teachers)}
        subject_index = {subject: idx for idx, subject in enumerate(self.subjects)}
        class_index = {class_name: idx for idx, class_name in enumerate(self.student_groups)}

        requirements = []
        for lesson in self.lessons:
            requirements.append(
                (
                    (subject_index[lesson.subject],),
                    (teacher_index[lesson.teacher],),
                    tuple(class_index[class_name] for class_name in lesson.classes),
                    lesson.weekly_hours,
                )
            )
        return requirements

    def get_additional_parallel_patterns_from_solution(
        self, solution_csv_path: str | Path
    ) -> dict[str, set[tuple[str, ...]]]:
        """
        Derive additional allowed within-class parallel combinations from an existing solution file.

        This is used when groups.json is not fully exhaustive but a known-valid timetable
        demonstrates extra legal combinations.
        """
        path = Path(solution_csv_path)
        if not path.exists():
            return {class_name: set() for class_name in self.student_groups}

        df = pd.read_csv(path)
        df = df.dropna(subset=["Subject"])
        df = df.fillna("")
        df = df[
            (df["Subject"].astype(str).str.strip() != "")
            & (df["Teacher"].astype(str).str.strip() != "")
        ].copy()
        df["Day"] = pd.to_numeric(df["Day"], errors="coerce").fillna(-1).astype(int)
        df["Slot"] = pd.to_numeric(df["Slot"], errors="coerce").fillna(-1).astype(int)

        by_key = {}
        for lesson in self.lessons:
            for class_name in lesson.classes:
                by_key[(lesson.subject, lesson.teacher, class_name)] = lesson.lesson_id

        grouped_slots: dict[tuple[str, int, int], set[str]] = {}
        for row in df.itertuples(index=False):
            subject = normalize_subject(str(row.Subject).strip())
            teacher = str(row.Teacher).strip()
            class_name = str(row.Student_group).strip()
            day = int(str(row.Day))
            slot = int(str(row.Slot))
            if day < 0 or slot < 0:
                continue
            lesson_id = by_key.get((subject, teacher, class_name))
            if lesson_id is None:
                continue
            grouped_slots.setdefault((class_name, day, slot), set()).add(lesson_id)

        result: dict[str, set[tuple[str, ...]]] = {
            class_name: set() for class_name in self.student_groups
        }
        for (class_name, _, _), lesson_ids in grouped_slots.items():
            if len(lesson_ids) <= 1:
                continue
            result[class_name].add(tuple(sorted(lesson_ids)))

        return result

    def main_requirement_to_txt(
        self, main_requirement: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], int]
    ) -> str:
        subjects, teachers, class_ids, _ = main_requirement
        subject_text = ", ".join(self.subjects[index] for index in subjects)
        teacher_text = ", ".join(self.teachers[index] for index in teachers)
        class_text = ", ".join(self.student_groups[index] for index in class_ids)
        return f"{subject_text} | {teacher_text} | {class_text}"


if __name__ == "__main__":
    data = PlanData("data")
    print(f"Loaded {len(data.lessons)} atomic lesson requirements")
    print(f"Grouped families: {sum(len(families) for families in data.group_families.values())}")