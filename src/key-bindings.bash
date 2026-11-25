# aptfz key bindings for bash.
#
# Source this from your .bashrc:
#
#   source /usr/share/aptfz/key-bindings.bash
#
# Binds ctrl+p to launch the same interactive picker aptfz itself gives you
# (fuzzy search, live colorized preview pane) - the only difference is what
# happens when you pick a package: instead of printing a rendered preview and
# exiting, the selected package's name is inserted at your cursor, so
# "apt remove " + ctrl+p + Enter gives you "apt remove firefox" ready to run.
#
# Modeled on fzf's own key-bindings.bash (CTRL-T / CTRL-R): run a command,
# capture its stdout, splice it into READLINE_LINE via `bind -x`.

__aptfz_select_package__() {
  local selected
  selected="$(aptfz --print-selection </dev/tty)"
  if [[ -n "$selected" ]]; then
    READLINE_LINE="${READLINE_LINE:0:$READLINE_POINT}${selected}${READLINE_LINE:$READLINE_POINT}"
    READLINE_POINT=$((READLINE_POINT + ${#selected}))
  fi
}

# </dev/tty is needed because bind -x's command normally has its stdin/stdout
# wired to the pipeline bind -x itself runs from, not your terminal - and fzf
# needs a real terminal to draw its interface on.
bind -x '"\C-p": __aptfz_select_package__'
