from ortools.sat.python import cp_model
import matplotlib.pyplot as plt

# Problem data
bin_width, bin_height = 3, 3
item_widths = [1, 1, 1, 1, 1]
item_heights = [1, 1, 1, 2, 2]
num_items = len(item_widths)

model = cp_model.CpModel()

# Variables: x, y positions for each item
x = [model.NewIntVar(0, bin_width - item_widths[i], f'x_{i}') for i in range(num_items)]
y = [model.NewIntVar(0, bin_height - item_heights[i], f'y_{i}') for i in range(num_items)]

# 2D intervals for each item
intervals = [
    model.NewRectangle(x[i], item_widths[i], y[i], item_heights[i])
    for i in range(num_items)
]