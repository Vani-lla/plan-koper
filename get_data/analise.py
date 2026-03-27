import pandas as pd
import json

df = pd.read_csv("raw_data.csv")

# Find lessons with the same teacher, day, and time, but different classes

grouped = df.groupby(["Teacher", "Day", "Slot"])

overlaps = []
for (teacher, day, slot), group in grouped:
    classes = group["Student_group"].unique()
    if len(classes) > 1:
        overlaps.append({
            "Teacher": teacher,
            "Day": day,
            "Slot": slot,
            "Classes": list(classes),
            "Subjects": list(group["Subject"].unique())
        })

# Save overlaps to CSV: columns are teacher, subject, all student_groups, values are 0/1
if overlaps:
    # Get all unique student groups from overlaps
    all_student_groups = sorted({sg for overlap in overlaps for sg in overlap["Classes"]})
    rows = []
    for overlap in overlaps:
        teacher = overlap["Teacher"]
        subjects = overlap["Subjects"]
        for subject in subjects:
            row = [teacher, subject]
            for sg in all_student_groups:
                row.append(1 if sg in overlap["Classes"] else 0)
            rows.append(row)
    df_overlaps = pd.DataFrame(rows, columns=["Teacher", "Subject"] + all_student_groups)
    df_overlaps = df_overlaps.drop_duplicates().sort_values(by=["Subject", "Teacher"])
    df_overlaps.to_csv("data/multiclass_blocks.csv", index=False, encoding="utf-8")

subjects = sorted(df["Subject"].dropna().unique())
rooms = sorted(df["Room"].dropna().unique())

data = []
for room in rooms:
    row = [room]
    for subject in subjects:
        count = ((df["Room"] == room) & (df["Subject"] == subject)).sum()
        row.append(count)
    data.append(row)


rooms = pd.DataFrame(data, columns=["Room"] + subjects)
subject_cols = rooms.columns[1:]
rooms[subject_cols] = rooms[subject_cols].div(rooms[subject_cols].sum(axis=0), axis=1)
rooms.to_csv("data/rooms.csv", index=False)


concurrent_lessons = {}
grouped = df.groupby(["Slot", "Day", "Student_group"])
for (slot, day, student_group), group in grouped:
    if len(group["Subject"]) > 1 and pd.notna(group["Subject"]).all():
        subjects = list(group["Subject"].unique())
        if student_group not in concurrent_lessons:
            concurrent_lessons[student_group] = []
        if not sorted(subjects) in concurrent_lessons[student_group]:
            concurrent_lessons[student_group].append(sorted(subjects)) 

# Sort by student_group and save to JSON
sorted_concurrent_lessons = dict(sorted(concurrent_lessons.items()))
with open("data/overlapping_lessons.json", "w", encoding="utf-8") as f:
    json.dump(sorted_concurrent_lessons, f, ensure_ascii=False, indent=2)

# tuples = list(zip(df["Subject"], df["Teacher"], df["Student_group"]))
# count_dict = {}
# for t in tuples:
#     if pd.isna(t[0]) or pd.isna(t[1]) or pd.isna(t[2]):
#         continue
#     count_dict[t] = count_dict.get(t, 0) + 1

# # Extract unique subjects, teachers, student_groups
# subjects = sorted(set([t[0] for t in count_dict.keys()]))
# teachers = sorted(set([t[1] for t in count_dict.keys()]))
# student_groups = sorted(set([t[2] for t in count_dict.keys()]))

# # Build rows: each subject row, then teacher rows below, columns are student_groups

# output_rows = []


# clean_subjects = []
# for subject in subjects:
#     clean_subject = subject.lower().replace(".", "").replace("_", "")
#     clean_subjects.append(clean_subject)
#     subject_sums = []
#     for sg in student_groups:
#         total = sum(count_dict.get((subject, teacher, sg), 0) for teacher in teachers)
#         subject_sums.append(total if total > 0 else "")
#     output_rows.append([clean_subject] + subject_sums)
#     for teacher in teachers:
#         row = [teacher]
#         for sg in student_groups:
#             row.append(count_dict.get((subject, teacher, sg), ""))
#         if any(row[1:]):
#             output_rows.append(row)

# with open("data/subjects.txt", "w", encoding="utf-8") as f:
#     f.write("\n".join(clean_subjects))

# df_out = pd.DataFrame(output_rows, columns=["Subject/Teacher"] + student_groups)
# df_out.to_csv("data/requirements.csv", index=False, encoding="utf-8")

