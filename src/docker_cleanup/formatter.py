"""Utilities for formatting sizes and output."""


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 0:
        raise ValueError(f"size_bytes must be non-negative, got {size_bytes}")
    if size_bytes == 0:
        return "0B"

    units = [
        ("TB", 1000**4),
        ("GB", 1000**3),
        ("MB", 1000**2),
        ("kB", 1000),
        ("B", 1),
    ]

    for suffix, threshold in units:
        if size_bytes >= threshold:
            value = size_bytes / threshold
            if value == int(value):
                return f"{int(value)}{suffix}"
            return f"{value:.1f}{suffix}"

    return "0B"  # pragma: no cover


def format_table(headers: list[str], rows: list[list[str]], padding: int = 2) -> str:
    """Format data as a simple text table."""
    if not rows:
        return ""

    # Calculate column widths
    col_count = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i in range(min(len(row), col_count)):
            widths[i] = max(widths[i], len(row[i]))

    # Build output
    lines = []

    # Header
    header_parts = []
    for i, h in enumerate(headers):
        if i < col_count - 1:
            header_parts.append(h.ljust(widths[i]))
        else:
            header_parts.append(h)
    lines.append((" " * padding).join(header_parts))

    # Separator
    sep_parts = ["-" * w for w in widths]
    lines.append((" " * padding).join(sep_parts))

    # Rows
    for row in rows:
        row_parts = []
        for i in range(col_count):
            val = row[i] if i < len(row) else ""
            if i < col_count - 1:
                row_parts.append(val.ljust(widths[i]))
            else:
                row_parts.append(val)
        lines.append((" " * padding).join(row_parts))

    return "\n".join(lines)
