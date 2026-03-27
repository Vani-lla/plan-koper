with open("plan_data/classes.txt") as file:
    klasy = file.readlines()

l = []
for klasa in klasy:
    l.append(klasa.strip())

# l = [klasa.strip() for klasa in klasy]

print(l)
