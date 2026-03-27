import pandas as pd
from json import load


def get_txt(path: str) -> list[str]:
    with open(path, "r") as file:
        lines = list(map(lambda l: l.strip(), file.readlines()))

    return lines


class PlanData:
    def __init__(self, data_path: str):
        self._data_path = data_path

        self.subjects = get_txt(data_path + "/subjects.txt")
        self.main_requirements = self._get_main_requirements_df()
        self.teachers = list(
            set(
                [
                    teacher
                    for teacher in self.main_requirements.index.tolist()
                    if teacher not in self.subjects
                ]
            )
        )
        self.student_groups = self.main_requirements.columns.tolist()

        self._multiclass_blocks = pd.read_csv(data_path + "/multiclass_blocks.csv")
        self._multiclass_reqs_set = set(
            (
                self.subjects.index(row["Subject"]),
                self.teachers.index(row["Teacher"]),
                self.student_groups.index(sg),
            )
            for _, row in self._multiclass_blocks.iterrows()
            for sg in self.student_groups
            if row.get(sg, 0) == 1
        )
        
        self._subgroups = load(open(+data_path + "/groups.json"))

    def _def_get_student_group_no_overlaps(student_group_id: int) -> list[list[int]]:
        return
    
    def _get_main_requirements_df(self) -> pd.DataFrame:
        df = pd.read_csv(self._data_path + "/requirements.csv")

        df.index = df[df.columns[0]]
        df.drop(df.columns[0], axis=1, inplace=True)
        df = df.fillna(0).astype(int)

        return df

    def _get_main_requirements_dict(self) -> dict[int, dict[int, dict[int, int]]]:
        """
        {
            subject_id: {
                teacher_id: {
                    student_group_id: hours
                }
            }
        }
        """
        d = {}
        for index, row in self.main_requirements.iterrows():
            if index in self.subjects:
                s = self.subjects.index(index)
                d[s] = {}
                continue
            t = self.teachers.index(index)
            d[s][t] = {}

            for c, student_group in enumerate(self.student_groups):
                if row[student_group] > 0:
                    d[s][t][c] = int(row[student_group])

        return d

    def get_main_requirements_array(self) -> list:
        """
        Dimentions:
        - Subject
        - Teacher
        - Student Group
        - Hours
        """
        main_requiremet_dictionary = self._get_main_requirements_dict()
        main_requirements_array = []
        for s, sd in main_requiremet_dictionary.items():
            for t, td in sd.items():
                for c, h in td.items():
                    if (s, t, c) not in self._multiclass_reqs_set:
                        main_requirements_array.append(((s,), (t,), (c,), h))

        for teacher, subject, *student_groups in self._multiclass_blocks.itertuples(
            index=False, name=None
        ):
            t = self.teachers.index(teacher)
            s = self.subjects.index(subject)
            cs = tuple(
                [
                    self.student_groups.index(self.student_groups[i])
                    for i, v in enumerate(student_groups)
                    if v
                ]
            )

            values = [main_requiremet_dictionary[s][t][c] for c in cs]
            if all(v == values[0] for v in values):
                main_requirements_array.append(((s,), (t,), cs, values[0]))
            else:
                raise Exception("Hours of the group are not equal")

        return main_requirements_array

    def main_requirement_to_txt(
        self, main_requirement: tuple[int, int, int, int]
    ) -> str:
        return f"{", ".join([self.subjects[s] for s in main_requirement[0]])} | {", ".join([self.teachers[t] for t in main_requirement[1]])} | {", ".join([self.student_groups[c] for c in main_requirement[2]])}"


if __name__ == "__main__":
    data = PlanData("data")
    print(data.get_main_requirements_array())
