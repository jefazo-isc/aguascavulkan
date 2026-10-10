#!/usr/bin/env python3

def is_convex(p0, p1, p2):
    return (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0]) >= 0

def point_in_triangle(pt, a, b, c):
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1 = sign(pt, a, b)
    d2 = sign(pt, b, c)
    d3 = sign(pt, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)

def triangulate_2d(pts):
    """Triangula polígonos 2D (huellas de edificios) usando ear clipping."""
    if len(pts) < 3:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]

    area = sum(pts[i][0] * pts[(i+1)%n][1] - pts[(i+1)%n][0] * pts[i][1] for i in range(n))
    indices = list(range(n))
    if area < 0:
        indices.reverse()

    triangles = []
    iters = 0
    while len(indices) > 3 and iters < n * 4:
        iters += 1
        m = len(indices)
        found = False
        for i in range(m):
            p0 = pts[indices[(i - 1) % m]]
            p1 = pts[indices[i]]
            p2 = pts[indices[(i + 1) % m]]
            if not is_convex(p0, p1, p2):
                continue
            inside = False
            for j in range(m):
                if j in ((i - 1) % m, i, (i + 1) % m):
                    continue
                if point_in_triangle(pts[indices[j]], p0, p1, p2):
                    inside = True
                    break
            if not inside:
                triangles.append((indices[(i - 1) % m], indices[i], indices[(i + 1) % m]))
                indices.pop(i)
                found = True
                break
        if not found:
            break

    for i in range(1, len(indices) - 1):
        triangles.append((indices[0], indices[i], indices[i + 1]))

    return triangles
