import unittest

from ratchet.extract import extract_code

T1 = "def transform(grid):\n    return grid\n"
T2 = "def transform(grid):\n    return [r[::-1] for r in grid]\n"


class TestExtract(unittest.TestCase):
    def test_last_block_defining_transform(self):
        text = f"Plan.\n```python\n{T1}```\nBetter:\n```python\n{T2}```\nAnd a note:\n```python\nx = 1\n```\n"
        self.assertEqual(extract_code(text), T2)

    def test_think_stripped(self):
        text = f"<think>\n```python\n{T2}```\n</think>\nAnswer:\n```python\n{T1}```"
        self.assertEqual(extract_code(text), T1)
        only_think = f"<think>```python\n{T2}```</think>no code here"
        self.assertIsNone(extract_code(only_think))

    def test_unclosed_think_dropped(self):
        self.assertIsNone(extract_code(f"<think>\n```python\n{T2}```\nstill thinking"))

    def test_whole_text_fallback(self):
        self.assertEqual(extract_code(T2), T2)

    def test_untagged_and_py_fences(self):
        self.assertEqual(extract_code(f"```\n{T1}```"), T1)
        self.assertEqual(extract_code(f"```py\n{T2}```"), T2)

    def test_non_python_fence_ignored(self):
        self.assertIsNone(extract_code(f"```json\n{T1}```"))

    def test_truncated_fence_is_a_block(self):
        text = f"```python\n{T2}# cut here by max_tokens"
        self.assertEqual(extract_code(text), T2 + "# cut here by max_tokens\n")

    def test_syntax_error_block_returned_for_SYNTAX_status(self):
        bad = "def transform(grid):\n    return [r for r in grid\n"
        self.assertEqual(extract_code(f"```python\n{bad}```"), bad)

    def test_nested_transform_not_top_level(self):
        code = "class A:\n    def transform(self, g):\n        return g\n"
        self.assertIsNone(extract_code(f"```python\n{code}```"))

    def test_none_and_empty(self):
        self.assertIsNone(extract_code(None))
        self.assertIsNone(extract_code(""))
        self.assertIsNone(extract_code("I cannot solve this."))


if __name__ == '__main__':
    unittest.main()
