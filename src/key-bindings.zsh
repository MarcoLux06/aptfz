# aptfz key bindings for zsh.
#
# Source this from your .zshrc:
#
#   source /usr/share/aptfz/key-bindings.zsh
#
# Binds ctrl+p to launch the same interactive picker aptfz itself gives you,
# but instead of printing a rendered preview, the selected package's name is
# inserted at your cursor, so "apt remove " + ctrl+p + Enter gives you
# "apt remove firefox" ready to run.
#
# Modeled on fzf's own key-bindings.zsh: a ZLE widget bound to a key sequence.

__aptfz_select_package() {
  local selected
  selected="$(aptfz --print-selection </dev/tty)"
  if [[ -n "$selected" ]]; then
    LBUFFER="${LBUFFER}${selected}"
  fi
  zle reset-prompt
}

zle -N __aptfz_select_package
bindkey '^P' __aptfz_select_package
