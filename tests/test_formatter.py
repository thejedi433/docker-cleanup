"""Tests for the formatter module."""

import pytest

from docker_cleanup.formatter import format_size, format_table


class TestFormatSize:
    def test_zero(self):
        assert format_size(0) == "0B"

    def test_bytes(self):
        assert format_size(500) == "500B"

    def test_kilobytes(self):
        assert format_size(1000) == "1kB"

    def test_kilobytes_decimal(self):
        assert format_size(1500) == "1.5kB"

    def test_megabytes(self):
        assert format_size(1_000_000) == "1MB"

    def test_megabytes_large(self):
        assert format_size(100_000_000) == "100MB"

    def test_gigabytes(self):
        assert format_size(1_500_000_000) == "1.5GB"

    def test_terabytes(self):
        assert format_size(2_000_000_000_000) == "2TB"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            format_size(-1)

    def test_exact_kilobytes(self):
        assert format_size(5000) == "5kB"

    def test_one_byte(self):
        assert format_size(1) == "1B"

    def test_999_bytes(self):
        assert format_size(999) == "999B"

    def test_large_gb(self):
        assert format_size(10_000_000_000) == "10GB"


class TestFormatTable:
    def test_empty_rows(self):
        result = format_table(["A", "B"], [])
        assert result == ""

    def test_single_row(self):
        result = format_table(["NAME", "SIZE"], [["test", "100MB"]])
        assert "NAME" in result
        assert "SIZE" in result
        assert "test" in result
        assert "100MB" in result
        assert "---" in result

    def test_multiple_rows(self):
        rows = [["a", "1"], ["bb", "22"], ["ccc", "333"]]
        result = format_table(["ID", "VAL"], rows)
        lines = result.split("\n")
        assert len(lines) == 5  # header + separator + 3 rows

    def test_column_alignment(self):
        rows = [["short", "x"], ["muchlonger", "y"]]
        result = format_table(["A", "B"], rows)
        lines = result.split("\n")
        # All lines should have the same separator width
        assert len(lines[1].replace(" ", "").replace("-", "")) == 0

    def test_padding(self):
        result = format_table(["A"], [["x"]], padding=4)
        assert "A" in result
        assert "x" in result

    def test_uneven_row_lengths(self):
        """Rows shorter than headers should still render."""
        rows = [["only_one_col"]]
        result = format_table(["A", "B"], rows)
        assert "only_one_col" in result

    def test_header_widths(self):
        """Column should be at least as wide as header."""
        rows = [["x", "y"]]
        result = format_table(["LONGHEADER", "B"], rows)
        # The separator for first column should be at least len("LONGHEADER")
        lines = result.split("\n")
        sep = lines[1]
        first_sep = sep.split("  ")[0]
        assert len(first_sep) >= len("LONGHEADER")
