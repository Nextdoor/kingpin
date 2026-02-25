# Task Completion Checklist

After completing a code task, ensure:

1. **Formatting**: Run `DRY=false make lint` (black auto-format)
2. **Linting**: Run `make lint` (black check + pyflakes)
3. **Tests**: Run `make test` (pytest + pyflakes + integration)
4. **Coverage**: Maintain 100% unit test coverage
5. **Dry mode**: Any new actor must support `self._dry` properly
6. **`__author__`**: Every actor module must have this attribute
7. **PR Title**: Use conventional commits format matching prlint.yml
8. **PRs**: Always open in draft mode
