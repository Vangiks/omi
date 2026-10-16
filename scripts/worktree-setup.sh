#!/usr/bin/env bash
# Копирует в только что созданный worktree неотслеживаемые файлы основного
# репозитория, подходящие под шаблоны из .worktreeinclude (синтаксис .gitignore).
# git worktree add вызывает post-checkout с нулевым предыдущим HEAD.

[ "$1" = "0000000000000000000000000000000000000000" ] || exit 0

main="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
target="$(git rev-parse --show-toplevel)"
list="$main/.worktreeinclude"
[ "$main" = "$target" ] && exit 0
[ -f "$list" ] || exit 0

cd "$main" || exit 0
git ls-files -z --others --ignored --exclude-from="$list" |
while IFS= read -r -d '' f; do
  [ -e "$target/$f" ] && continue
  cp -p --parents "$f" "$target/" && echo "post-checkout: скопирован $f"
done
