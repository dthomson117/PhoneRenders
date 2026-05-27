def set_attr_safe(obj, attr, value):
    """Best-effort setattr that silently skips missing or read-only attrs."""
    if not hasattr(obj, attr):
        return False
    try:
        setattr(obj, attr, value)
        return True
    except (AttributeError, TypeError):
        return False
