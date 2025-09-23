"""
Patch some of the function in fidex.fidelity_check.layout tree. For this project's specific needs.
"""
from fidex.fidelity_check import layout_tree

def dimension_eq_patch(e1, e2):
    if e1.tagname == 'img' and e2.tagname == 'img':
        return True
    d1, d2 = e1.dimension, e2.dimension
    d1w, d1h = d1.get('width', 1), d1.get('height', 1)
    d2w, d2h = d2.get('width', 1), d2.get('height', 1)
    wdiff = abs(d1w - d2w) / max(d1w, d2w, 1)
    hdiff = abs(d1h - d2h) / max(d1h, d2h, 1)
    return (wdiff <= 0.05 and hdiff <= 0.05) or (wdiff == 0) or (hdiff == 0)

layout_tree.dimension_eq = dimension_eq_patch