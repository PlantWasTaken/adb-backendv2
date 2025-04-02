def are_n_elements_present_set(lst, elements, n):
    # Use set intersection for efficiency
    common = set(elements) & set(lst)
    return len(common) >= n