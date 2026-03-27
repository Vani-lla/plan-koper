import pandas as pd
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass


@dataclass
class Lesson:
    subject: str
    teacher: str
    student_group: str
    room: str
    slot: int
    day: int


def get_lessons(cell: str, student_group: str, slot: int, day: int) -> list[Lesson]:
    l = []
    for c in cell.split("|"):
        l.append(c.split("/"))

    if len(l) == 2:
        l.append(["Unknown" for _ in range(len(l[0]))])
    elif len(l) == 1:
        return

    r = []
    for subject, teacher, room in zip(*l):
        r.append(Lesson(subject, teacher, student_group, room, slot, day))

    return r


classes = [
    "1,1,1,1,1,1,2,2,2,2,3,3,3,3,3,3,4,4,4,4,4,4",
    "A,B,C,D,F,G,A,B,D,G,A,B,C,D,F,G,A,B,C,D,F,G",
]
classes = [a + b for a, b in zip(classes[0].split(","), classes[1].split(","))]
with open("plan_data/classes.txt", "w") as file:
    file.writelines(c + "\n" for c in classes)

all_lessons = []
all_lessons_raw = []
slots_map = {
    "7.10 - 7.55": 0,
    "8.00 - 8.45": 1,
    "8.50 - 9.35": 2,
    "9.40 - 10.25": 3,
    "10.35 - 11.20": 4,
    "11.30 - 12.15": 5,
    "12.25 - 13.10": 6,
    "13.25 - 14.10": 7,
    "14.15 - 15.00": 8,
    "15.05 - 15.50": 9,
}

for c in classes:
    url = f"https://koper.edu.pl/index.php?podstrona=plan_sql&klasa={c}&klasa2={c}#main"
    print(url)
    response = requests.get(url)
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", class_="table table-dark table-hover")

    if not table:
        continue

    l = []
    cell_strings = []
    for row in table.find_all("tr"):
        row_cells = [
            cell.get_text(strip=True, separator="|")
            for cell in row.find_all(["td", "th"])
        ]
        l.append(row_cells)

    times = [row[0] for row in l[1:]]
    l = [row[1:] for row in l[1:]]
    for slot, row in zip(times, l):
        for day, cell in enumerate(row):
            lessons = get_lessons(cell, c, slots_map[slot], day)
            if lessons:
                all_lessons.extend(lessons)

                for lesson in lessons:
                    all_lessons_raw.append(
                        (
                            lesson.subject.lower()
                            .replace(".", "")
                            .replace("_", "")
                            .replace(" ", "")
                            .replace("zajkszkr", "zajksztkr"),
                            lesson.teacher,
                            lesson.student_group,
                            lesson.room,
                            lesson.slot,
                            lesson.day,
                        )
                    )

df = pd.DataFrame(
    all_lessons_raw,
    columns=["Subject", "Teacher", "Student_group", "Room", "Slot", "Day"],
)
df.to_csv("raw_data.csv", index=False)
