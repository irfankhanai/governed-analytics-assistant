def calculate_match_score(components, weights):
    if set(components) != set(weights) or sum(weights.values()) <= 0:
        raise ValueError('Components and weights must match.')
    if any(not 0 <= v <= 1 for v in components.values()) or any(v < 0 for v in weights.values()):
        raise ValueError('Components must be between zero and one; weights nonnegative.')
    return round(100 * sum(components[k] * weights[k] for k in weights) / sum(weights.values()), 2)
