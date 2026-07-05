#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def class_sort_key(class_name: str) -> tuple[int, str]:
    if not class_name:
        return (999, "")

    i = 0
    while i < len(class_name) and class_name[i].isdigit():
        i += 1

    year = int(class_name[:i]) if i > 0 else 999
    suffix = class_name[i:]
    return (year, suffix)


def format_variant(variant: list[list[str]]) -> str:
    parts = []
    for item in variant:
        if len(item) >= 2:
            subject, teacher = item[0], item[1]
            parts.append(f"{subject} ({teacher})")
        elif len(item) == 1:
            parts.append(item[0])
    return " + ".join(parts)


def print_groups(data: dict) -> None:
    classes = sorted(data.keys(), key=class_sort_key)

    print("=" * 70)
    print("GRUPY ROWNOLEGLE PROWADZONYCH ZAJEC")
    print("=" * 70)

    for class_name in classes:
        groups = data.get(class_name, {})

        print(f"\nKlasa {class_name}")
        print("-" * 70)

        if not groups:
            print("  (brak danych)")
            continue

        for group_name in sorted(groups.keys()):
            variants = groups[group_name]
            print(f"  {group_name}:")

            if not variants:
                print("    - brak wariantow")
                continue

            for idx, variant in enumerate(variants, start=1):
                pretty = format_variant(variant)
                print(f"    {idx}. {pretty}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Czytelny podglad grup z pliku groups.json"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="data/groups.json",
        help="Sciezka do pliku JSON z grupami (domyslnie: data/groups.json)",
    )

    args = parser.parse_args()
    json_path = Path(args.path)

    if not json_path.exists():
        raise SystemExit(f"Nie znaleziono pliku: {json_path}")

    with json_path.open("r", encoding="utf-8") as f:
        groups_data = json.load(f)

    if not isinstance(groups_data, dict):
        raise SystemExit("Niepoprawny format JSON: oczekiwano obiektu na poziomie glownym")

    print_groups(groups_data)
